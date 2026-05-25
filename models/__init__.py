"""
Data models for the Music Bot.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime
import uuid


@dataclass
class Track:
    """Represents a music track."""
    id: str
    title: str
    artist: str
    album: str = ""
    duration: int = 0               # seconds
    preview_url: Optional[str] = None
    cover_url: Optional[str] = None
    genre: str = ""
    tags: List[str] = field(default_factory=list)
    source: str = "ytmusic"
    external_id: str = ""           # ID from the source API
    play_count: int = 0
    liked: bool = False

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    @property
    def display_name(self) -> str:
        return f"{self.artist} — {self.title}"

    @property
    def duration_str(self) -> str:
        if self.duration <= 0:
            return "?:??"
        m, s = divmod(self.duration, 60)
        return f"{m}:{s:02d}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration": self.duration,
            "preview_url": self.preview_url,
            "cover_url": self.cover_url,
            "genre": self.genre,
            "tags": self.tags,
            "source": self.source,
            "external_id": self.external_id,
        }

    @classmethod
    def from_ytmusic(cls, data: dict) -> "Track":
        """Create a Track from a YTMusic API response dict."""
        title = data.get("title", "Unknown")

        artists = data.get("artists") or data.get("author") or []
        if isinstance(artists, list):
            artist = ", ".join(a.get("name", "") for a in artists if a.get("name"))
        else:
            artist = str(artists)
        artist = artist or "Unknown Artist"

        album_data = data.get("album") or {}
        album = album_data.get("name", "") if isinstance(album_data, dict) else ""

        # YTMusic uses different duration keys depending on the endpoint:
        #   search()             → "duration"  (string "M:SS")
        #   get_watch_playlist() → "length"    (string "M:SS")  ← this was the bug
        #   get_playlist()       → "duration" + "duration_seconds" (int)
        # We check all three so every endpoint gives a proper duration.
        duration = 0
        raw_duration = (
            data.get("duration_seconds")        # int — highest precision
            or data.get("duration")             # string "M:SS" from search
            or data.get("length")               # string "M:SS" from watch playlist
        )
        if isinstance(raw_duration, int):
            duration = raw_duration
        elif isinstance(raw_duration, str):
            try:
                parts = raw_duration.split(":")
                if len(parts) == 2:
                    duration = int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3:
                    duration = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            except Exception:
                duration = 0

        thumbnails = data.get("thumbnails") or []
        cover = thumbnails[-1].get("url") if thumbnails else None

        external_id = data.get("videoId") or data.get("id") or ""
        preview_url = f"https://music.youtube.com/watch?v={external_id}" if external_id else None

        return cls(
            id=external_id or str(uuid.uuid4()),
            title=title,
            artist=artist,
            album=album,
            duration=duration,
            preview_url=preview_url,
            cover_url=cover,
            source="ytmusic",
            external_id=external_id,
        )


@dataclass
class QueueItem:
    """An item in the playback queue."""
    track: Track
    added_at: datetime = field(default_factory=datetime.now)
    added_by: int = 0               # Telegram user ID
    position: int = 0


@dataclass
class UserSession:
    """Per-user bot session state."""
    user_id: int
    username: str = ""
    current_track: Optional[Track] = None
    queue: List[QueueItem] = field(default_factory=list)
    history: List[Track] = field(default_factory=list)
    playlists: dict = field(default_factory=dict)   # name -> List[Track]
    liked_tracks: List[Track] = field(default_factory=list)
    play_count: int = 0
    last_active: datetime = field(default_factory=datetime.now)
    preferred_genres: List[str] = field(default_factory=list)
    preferred_moods: List[str] = field(default_factory=list)
    search_state: Optional[str] = None             # pending search query

    def add_to_queue(self, track: Track) -> bool:
        from config import Config
        cfg = Config()
        if len(self.queue) >= cfg.MAX_QUEUE_SIZE:
            return False
        item = QueueItem(track=track, added_by=self.user_id, position=len(self.queue))
        self.queue.append(item)
        return True

    def next_track(self) -> Optional[Track]:
        if not self.queue:
            return None
        item = self.queue.pop(0)
        if self.current_track:
            self.history.insert(0, self.current_track)
            if len(self.history) > 100:
                self.history = self.history[:100]
        self.current_track = item.track
        self.play_count += 1
        self.last_active = datetime.now()
        return item.track

    def like_current(self) -> bool:
        if not self.current_track:
            return False
        self.current_track.liked = True
        if self.current_track not in self.liked_tracks:
            self.liked_tracks.append(self.current_track)
        return True

    def get_taste_profile(self) -> dict:
        """Derive taste from history for smarter recommendations."""
        all_tracks = self.history + self.liked_tracks
        artists: dict = {}
        tags: dict = {}
        genres: dict = {}
        for t in all_tracks:
            weight = 2 if t.liked else 1
            artists[t.artist] = artists.get(t.artist, 0) + weight
            if t.genre:                             # skip blank-genre tracks
                genres[t.genre] = genres.get(t.genre, 0) + weight
            for tag in t.tags:
                tags[tag] = tags.get(tag, 0) + weight
        return {
            "top_artists": sorted(artists, key=artists.get, reverse=True)[:5],
            "top_tags": sorted(tags, key=tags.get, reverse=True)[:10],
            "top_genres": sorted(genres, key=genres.get, reverse=True)[:5],
        }
