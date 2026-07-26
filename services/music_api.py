"""
Music API Service — YouTube Music backend via ytmusicapi.
"""

import asyncio
import logging
from functools import partial
from typing import List, Optional
from ytmusicapi import YTMusic
from models import Track

logger = logging.getLogger(__name__)
ytmusic = YTMusic()


class MusicAPIService:

    async def _run(self, func, *args, **kwargs):
        """
        Run a blocking ytmusicapi call in a thread-pool executor so it
        doesn't stall the event loop (and every other user's requests)
        while waiting on network I/O.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, *args, **kwargs))

    async def search_tracks(self, query: str, limit: int = 5) -> List[Track]:
        try:
            results = await self._run(ytmusic.search, query, filter="songs", limit=limit)
            return [self._parse(r) for r in results[:limit] if r]
        except Exception as e:
            logger.error(f"YTMusic search error: {e}")
            return []

    async def get_trending_tracks(self, limit: int = 10) -> List[Track]:
        try:
            charts = await self._run(ytmusic.get_charts, country="US")
            items = charts.get("songs", {}).get("items", [])[:limit]
            return [self._parse(r) for r in items if r]
        except Exception as e:
            logger.error(f"YTMusic trending error: {e}")
            return await self.search_tracks("top hits 2025", limit=limit)

    async def get_artist_top_tracks(self, artist_name: str, limit: int = 5) -> List[Track]:
        try:
            results = await self._run(ytmusic.search, artist_name, filter="artists", limit=1)
            if not results:
                return []
            artist_id = results[0].get("browseId")
            if not artist_id:
                return []
            artist_data = await self._run(ytmusic.get_artist, artist_id)
            songs = artist_data.get("songs", {}).get("results", [])[:limit]
            return [self._parse(s) for s in songs if s]
        except Exception as e:
            logger.error(f"YTMusic artist error: {e}")
            return []

    async def get_track_by_id(self, track_id: str) -> Optional[Track]:
        try:
            results = await self._run(ytmusic.search, track_id, filter="songs", limit=1)
            if results:
                return self._parse(results[0])
        except Exception as e:
            logger.error(f"YTMusic get track error: {e}")
        return None

    async def get_similar_tracks(self, artist: str, title: str, limit: int = 5) -> List[Track]:
        try:
            results = await self._run(ytmusic.search, f"{artist} {title}", filter="songs", limit=1)
            if not results:
                return []
            video_id = results[0].get("videoId")
            if not video_id:
                return []
            radio = await self._run(ytmusic.get_watch_playlist, videoId=video_id, limit=limit + 1)
            tracks_data = radio.get("tracks", [])[1:limit + 1]  # skip first (same song)
            return [self._parse(t) for t in tracks_data if t]
        except Exception as e:
            logger.error(f"YTMusic similar error: {e}")
            return []

    async def get_similar_artists(self, artist: str, limit: int = 5) -> List[str]:
        try:
            results = await self._run(ytmusic.search, artist, filter="artists", limit=1)
            if not results:
                return []
            artist_id = results[0].get("browseId")
            if not artist_id:
                return []
            data = await self._run(ytmusic.get_artist, artist_id)
            related = data.get("related", {}).get("results", [])[:limit]
            return [r.get("title", "") for r in related if r.get("title")]
        except Exception as e:
            logger.error(f"YTMusic similar artists error: {e}")
            return []

    async def get_tag_top_tracks(self, tag: str, limit: int = 5) -> List[Track]:
        return await self.search_tracks(tag, limit=limit)

    async def search_by_genre(self, genre: str, limit: int = 5) -> List[Track]:
        return await self.search_tracks(genre, limit=limit)

    async def get_recommendations_for_profile(
        self, top_artists: list, top_tags: list, limit: int = 8
    ) -> List[Track]:
        tracks = []
        seen = set()
        seeds = (top_artists[:2] + top_tags[:2])[:4]
        for seed in seeds:
            results = await self.search_tracks(seed, limit=3)
            for t in results:
                if t.external_id not in seen:
                    seen.add(t.external_id)
                    tracks.append(t)
        return tracks[:limit]

    async def get_mood_tracks(self, mood_key: str, limit: int = 8) -> List[Track]:
        from config import Config
        tags = Config().MOODS.get(mood_key, {}).get("tags", [mood_key])
        return await self.search_tracks(tags[0], limit=limit)

    def _parse(self, item: dict) -> Track:
        """Parse a YTMusic result dict into a Track."""
        return Track.from_ytmusic(item)


# Singleton
music_api = MusicAPIService()
