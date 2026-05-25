"""
Keyboard builders — all inline keyboards for the bot UI.

Telegram hard-caps callback_data at 64 bytes per button.
Rules enforced here:
  - play:<id>        — 11-char video ID + prefix = ~16 bytes  ✓
  - queue:<id>       — same                                   ✓
  - rec:<id>         — same; handler resolves artist/title    ✓
  - like:<id>        — same                                   ✓
  - dislike:<id>     — same                                   ✓
Source is always ytmusic so it is never stored in callback_data.
"""

from typing import List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from models import Track, UserSession
from config import Config

cfg = Config()

# Telegram's hard limit for callback_data, in bytes.
_CB_LIMIT = 64


def _safe_cb(data: str) -> str:
    """Assert callback data is within Telegram's 64-byte limit."""
    encoded = data.encode("utf-8")
    if len(encoded) > _CB_LIMIT:
        raise ValueError(
            f"callback_data too long ({len(encoded)} bytes > {_CB_LIMIT}): {data!r}"
        )
    return data


def track_keyboard(track: Track) -> InlineKeyboardMarkup:
    """Keyboard shown below a single track result."""
    eid = track.external_id
    buttons = [
        [
            InlineKeyboardButton("▶️ Play",    callback_data=_safe_cb(f"play:{eid}")),
            InlineKeyboardButton("➕ Queue",   callback_data=_safe_cb(f"queue:{eid}")),
        ],
        [
            InlineKeyboardButton("🔀 Similar", callback_data=_safe_cb(f"rec:{eid}")),
            InlineKeyboardButton("❤️ Like",    callback_data=_safe_cb(f"like:{eid}")),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def now_playing_keyboard(track: Track) -> InlineKeyboardMarkup:
    """Keyboard for now-playing message."""
    eid = track.external_id
    buttons = [
        [
            InlineKeyboardButton("⏭ Skip",     callback_data="skip"),
            InlineKeyboardButton("❤️ Like",    callback_data=_safe_cb(f"like:{eid}")),
            InlineKeyboardButton("👎 Dislike", callback_data=_safe_cb(f"dislike:{eid}")),
        ],
        [
            InlineKeyboardButton("🔀 Similar", callback_data=_safe_cb(f"rec:{eid}")),
            InlineKeyboardButton("📋 Queue",   callback_data="show_queue"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def search_results_keyboard(tracks: List[Track]) -> InlineKeyboardMarkup:
    """Keyboard for a list of search results."""
    buttons = []
    for i, track in enumerate(tracks, 1):
        eid = track.external_id
        label = f"{i}. {track.artist[:15]} — {track.title[:20]}"
        buttons.append([
            InlineKeyboardButton(f"▶️ {label}", callback_data=_safe_cb(f"play:{eid}")),
            InlineKeyboardButton("➕",           callback_data=_safe_cb(f"queue:{eid}")),
        ])
    return InlineKeyboardMarkup(buttons)


def mood_keyboard() -> InlineKeyboardMarkup:
    """Mood selector keyboard."""
    buttons = []
    items = list(cfg.MOODS.items())
    for i in range(0, len(items), 2):
        row = [
            InlineKeyboardButton(
                f"{val['emoji']} {key.capitalize()}",
                callback_data=_safe_cb(f"mood:{key}"),
            )
            for key, val in items[i:i + 2]
        ]
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def genre_keyboard() -> InlineKeyboardMarkup:
    """Genre selector keyboard."""
    buttons = []
    for i in range(0, len(cfg.GENRES), 3):
        row = [
            InlineKeyboardButton(g, callback_data=_safe_cb(f"genre:{g}"))
            for g in cfg.GENRES[i:i + 3]
        ]
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def queue_keyboard(session: UserSession, page: int = 0) -> InlineKeyboardMarkup:
    """Paginated queue keyboard."""
    PAGE_SIZE = 5
    start = page * PAGE_SIZE
    items = session.queue[start:start + PAGE_SIZE]

    buttons = []
    for item in items:
        t = item.track
        buttons.append([
            InlineKeyboardButton(
                f"🎵 {t.artist[:12]} — {t.title[:15]}",
                callback_data=_safe_cb(f"play:{t.external_id}"),
            )
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page:{page - 1}"))
    if start + PAGE_SIZE < len(session.queue):
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"page:{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([
        InlineKeyboardButton("⏭ Skip",  callback_data="skip"),
        InlineKeyboardButton("🗑 Clear", callback_data="clear"),
    ])
    return InlineKeyboardMarkup(buttons)


def autoplay_keyboard(track: Track) -> InlineKeyboardMarkup:
    """
    Keyboard attached to every autoplay-sent audio message.

    Row 1: ▶️ Play Next (early advance)  |  ⏹ Stop Autoplay
    Row 2: ❤️ Like  |  👎 Dislike  |  🔀 Similar
    Row 3: 📋 Queue
    """
    eid = track.external_id
    buttons = [
        [
            InlineKeyboardButton("▶️ Play Next",      callback_data="ap:next"),
            InlineKeyboardButton("⏹ Stop Autoplay",  callback_data="ap:stop"),
        ],
        [
            InlineKeyboardButton("❤️ Like",           callback_data=_safe_cb(f"like:{eid}")),
            InlineKeyboardButton("👎 Dislike",        callback_data=_safe_cb(f"dislike:{eid}")),
            InlineKeyboardButton("🔀 Similar",        callback_data=_safe_cb(f"rec:{eid}")),
        ],
        [
            InlineKeyboardButton("📋 Queue",          callback_data="show_queue"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def recommendations_keyboard(tracks: List[Track]) -> InlineKeyboardMarkup:
    """Keyboard for recommendation list."""
    buttons = []
    for track in tracks:
        eid = track.external_id
        label = f"🎵 {track.artist[:14]} — {track.title[:16]}"
        buttons.append([
            InlineKeyboardButton(f"▶️ {label}", callback_data=_safe_cb(f"play:{eid}")),
            InlineKeyboardButton("➕",           callback_data=_safe_cb(f"queue:{eid}")),
        ])
    buttons.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="rec:refresh")
    ])
    return InlineKeyboardMarkup(buttons)
