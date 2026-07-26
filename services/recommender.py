"""
Recommendation Engine
Combines taste profiling, queue state, and music APIs to generate
contextually relevant suggestions.
"""

import logging
import random
from typing import List

from models import Track, UserSession
from services.music_api import music_api
from config import Config

logger = logging.getLogger(__name__)
cfg = Config()


class RecommendationEngine:
    """Smart recommendation engine with multiple strategies."""

    async def get_recommendations(
        self, session: UserSession, limit: int = 8
    ) -> List[Track]:
        """
        Main recommendation entry point.
        Chooses strategy based on session state.
        """
        profile = session.get_taste_profile()

        if not profile["top_artists"] and not profile["top_tags"]:
            # Cold start — return trending
            logger.info(f"Cold start for user {session.user_id}, returning trending")
            return await music_api.get_trending_tracks(limit=limit)

        # Use profile-based recommendations
        tracks = await music_api.get_recommendations_for_profile(
            top_artists=profile["top_artists"],
            top_tags=profile["top_tags"],
            limit=limit,
        )

        # Filter out tracks already in queue or recently played
        existing_ids = {t.external_id for t in session.history[:20]}
        existing_ids.update(q.track.external_id for q in session.queue)
        tracks = [t for t in tracks if t.external_id not in existing_ids]

        # Pad with trending if not enough results
        if len(tracks) < limit:
            trending = await music_api.get_trending_tracks(limit=limit - len(tracks))
            existing_ids.update(t.external_id for t in tracks)
            tracks += [t for t in trending if t.external_id not in existing_ids]

        random.shuffle(tracks)
        return tracks[:limit]

    async def get_similar_to_current(
        self, session: UserSession, limit: int = 5
    ) -> List[Track]:
        """Get tracks similar to the currently playing track."""
        if not session.current_track:
            return await self.get_recommendations(session, limit)

        track = session.current_track
        similar = await music_api.get_similar_tracks(
            artist=track.artist, title=track.title, limit=limit
        )

        if not similar:
            # Fallback to artist top tracks
            similar = await music_api.get_artist_top_tracks(
                artist_name=track.artist, limit=limit
            )

        return similar

    async def auto_queue_refill(
        self, session: UserSession, threshold: int = None
    ) -> List[Track]:
        """
        Called when queue drops below threshold.
        Automatically adds recommendations to keep playback going.
        Uses cfg.AUTO_REFILL_THRESHOLD when threshold is not provided.
        """
        if threshold is None:
            threshold = cfg.AUTO_REFILL_THRESHOLD

        if len(session.queue) >= threshold:
            return []

        logger.info(
            f"Auto-refilling queue for user {session.user_id} "
            f"(queue={len(session.queue)})"
        )

        needed = cfg.AUTO_REFILL_COUNT
        tracks = await self.get_similar_to_current(session, limit=needed)

        added = []
        for track in tracks:
            if session.add_to_queue(track):
                added.append(track)

        return added

    async def get_mood_playlist(
        self, session: UserSession, mood_key: str, limit: int = 10
    ) -> List[Track]:
        """Build a mood-based playlist."""
        tracks = await music_api.get_mood_tracks(mood_key=mood_key, limit=limit)
        session.preferred_moods = list({mood_key} | set(session.preferred_moods))[:5]
        # Tag each track with the mood's descriptive tags — this is what
        # UserSession.get_taste_profile() scores on to build top_tags.
        mood_tags = cfg.MOODS.get(mood_key, {}).get("tags", [mood_key])
        for t in tracks:
            t.tags = list(dict.fromkeys(t.tags + mood_tags))
        return tracks

    async def get_genre_playlist(
        self, session: UserSession, genre: str, limit: int = 10
    ) -> List[Track]:
        """Build a genre-based playlist."""
        tracks = await music_api.search_by_genre(genre=genre, limit=limit)
        if genre not in session.preferred_genres:
            session.preferred_genres.insert(0, genre)
            session.preferred_genres = session.preferred_genres[:10]
        # Tag each track with its genre — this is what get_taste_profile()
        # scores on to build top_genres. music_api never sets this on its
        # own since plain YTMusic search results don't carry a genre field.
        for t in tracks:
            t.genre = genre
        return tracks

    async def get_artist_recommendations(
        self, session: UserSession, artist_name: str, limit: int = 8
    ) -> List[Track]:
        """Recommend tracks from an artist + similar artists."""
        artist_tracks = await music_api.get_artist_top_tracks(
            artist_name=artist_name, limit=limit // 2
        )

        similar_artists = await music_api.get_similar_artists(
            artist=artist_name, limit=3
        )

        sim_tracks = []
        for sim_artist in similar_artists:
            tracks = await music_api.get_artist_top_tracks(
                artist_name=sim_artist, limit=2
            )
            sim_tracks.extend(tracks)

        all_tracks = artist_tracks + sim_tracks
        random.shuffle(all_tracks)
        return all_tracks[:limit]


# Singleton
recommender = RecommendationEngine()
