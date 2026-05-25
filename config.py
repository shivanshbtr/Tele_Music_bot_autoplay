"""
Configuration management for the Music Bot.
Loads settings from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # ── Telegram ──────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "user_token_here(get from @botfather)")
    )

    # ── Playback Settings ─────────────────────────────────────────────────────
    MAX_QUEUE_SIZE: int = 50
    AUTO_REFILL_COUNT: int = 3      # how many tracks to add on auto-refill
    AUTO_REFILL_THRESHOLD: int = 2  # refill when queue drops below this

    # ── Cache Settings ────────────────────────────────────────────────────────
    CACHE_TTL: int = 3600           # 1 hour
    MAX_HISTORY_SIZE: int = 100

    # ── Mood Mappings ─────────────────────────────────────────────────────────
    MOODS: dict = field(default_factory=lambda: {
        "happy": {"tags": ["happy", "feel-good", "upbeat", "cheerful"], "emoji": "😄"},
        "sad": {"tags": ["sad", "melancholy", "emotional", "heartbreak"], "emoji": "😢"},
        "energetic": {"tags": ["energetic", "workout", "pump-up", "high-energy"], "emoji": "⚡"},
        "chill": {"tags": ["chill", "relaxing", "lofi", "ambient"], "emoji": "😌"},
        "romantic": {"tags": ["romantic", "love", "soulful", "sensual"], "emoji": "❤️"},
        "angry": {"tags": ["angry", "aggressive", "metal", "intense"], "emoji": "😤"},
        "focused": {"tags": ["focus", "study", "instrumental", "concentration"], "emoji": "🎯"},
        "party": {"tags": ["party", "dance", "club", "edm"], "emoji": "🎉"},
    })

    # ── Genre List ────────────────────────────────────────────────────────────
    GENRES: List[str] = field(default_factory=lambda: [
        "Pop", "Rock", "Hip-Hop", "Electronic", "Jazz", "Classical",
        "R&B", "Country", "Reggae", "Metal", "Folk", "Blues",
        "Latin", "Indie", "Soul", "Funk", "Punk", "Alternative",
    ])

    # ── Bot Messages ──────────────────────────────────────────────────────────
    WELCOME_MESSAGE: str = """
🎵 *Welcome to MusicBot!*

I'm your personal music recommendation assistant. Here's what I can do:

🔍 *Search & Play*
`/search <song name>` — Find and play any track
`/trending` — Show today's trending tracks

🎯 *Recommendations*
`/recommend` — Get songs based on your history
`/mood` — Music for your current mood
`/genre` — Browse by genre
`/artist <name>` — Similar artists

📋 *Queue Management*
`/queue` — View your current queue
`/skip` — Skip current track
`/clear` — Clear the queue
`/now` — Now playing info

🔄 *Seamless Autoplay*
`/autoplay` — Enable Spotify-like continuous playback
  • Prefetches next track while current one plays
  • Auto-queues 3 similar tracks each time a song starts
  • Seamlessly streams until you say /stop
`/stop` — Stop autoplay

📚 *History & Playlists*
`/history` — Your recently played tracks
`/playlist` — Manage saved playlists

Just send me a *song name* or *artist* and I'll find it for you! 🎶
"""

    HELP_MESSAGE: str = """
🎵 *MusicBot Commands*

*Playback*
• `/search <query>` — Search for tracks
• `/now` — Now playing
• `/skip` — Skip current track

*Seamless Autoplay 🔄*
• `/autoplay` — Start Spotify-like continuous playback
  Prefetches next song, auto-queues similar tracks
• `/stop` — Stop autoplay

*Discovery*
• `/recommend` — Personalized picks
• `/trending` — Hot right now
• `/mood` — Mood-based music
• `/genre` — Genre explorer
• `/artist <name>` — Artist recommendations

*Queue*
• `/queue` — View queue
• `/clear` — Clear queue (also stops autoplay)

*Library*
• `/history` — Play history
• `/playlist` — Your playlists

💡 *Tip:* Hit /autoplay after your first song for a seamless infinite stream!
"""
