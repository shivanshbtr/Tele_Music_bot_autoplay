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

    # ── yt-dlp / YouTube auth ────────────────────────────────────────────────
    # Path to a Netscape-format cookies.txt exported from a logged-in YouTube
    # session. Without this, YouTube frequently throws up the "Sign in to
    # confirm you're not a bot" wall on repeated/automated requests.
    YTDLP_COOKIES_FILE: str = field(
        default_factory=lambda: os.getenv("YTDLP_COOKIES_FILE", "cookies.txt")
    )

    # Telegram user ID allowed to use /updatecookies (your numeric user ID —
    # get it from @userinfobot). Only this user can push a new cookies.txt.
    # Left blank = command is disabled entirely (safer default).
    OWNER_ID: int = field(
        default_factory=lambda: int(os.getenv("TELEGRAM_OWNER_ID", "0") or 0)
    )

    # Comma-separated list of numeric Telegram user IDs allowed to use the
    # bot at all, e.g. "111111111,222222222". The owner (TELEGRAM_OWNER_ID)
    # is always implicitly allowed even if not listed here.
    # Leave both this and TELEGRAM_OWNER_ID unset to keep the bot open to
    # everyone (old behavior). Set either one to lock the bot down to
    # just those accounts — everyone else is silently ignored.
    ALLOWED_USER_IDS: List[int] = field(
        default_factory=lambda: [
            int(uid.strip())
            for uid in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",")
            if uid.strip()
        ]
    )

    def is_allowed(self, user_id: int) -> bool:
        """Whether `user_id` may use the bot at all."""
        if not self.ALLOWED_USER_IDS and not self.OWNER_ID:
            return True  # no restriction configured — open bot
        return user_id == self.OWNER_ID or user_id in self.ALLOWED_USER_IDS

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
