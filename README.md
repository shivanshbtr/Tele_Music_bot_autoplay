# 🎵 Telegram Music Recommendation Bot

A fully async Telegram bot that searches for music, streams audio, manages a playback queue, and automatically suggests related songs based on your listening history.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔍 **Track Search** | Search YouTube Music's catalogue instantly |
| 🎧 **Audio Playback** | Download and stream tracks directly in Telegram via yt-dlp |
| 🎯 **Smart Recommendations** | Personalized picks based on play history & likes |
| 📋 **Queue Management** | Add, skip, and clear tracks with inline buttons |
| 🔀 **Auto-Queue Refill** | Automatically adds similar songs when queue runs low |
| 🎭 **Mood Playlists** | 8 moods: Happy, Sad, Chill, Energetic, Focused, etc. |
| 🎸 **Genre Explorer** | Browse 18 genres with one tap |
| 🔀 **Similar Tracks** | "Find similar" on any track via YouTube Music radio |
| 📚 **Play History** | Full history with like/dislike tracking |
| 🎤 **Artist Mode** | Top tracks + similar artists discovery |

---

## 🚀 Quick Start

### 1. Clone & install dependencies

```bash
git clone <repo>
cd Tele_Music_bot_autoplay
pip install -r requirements.txt
```

> **Note:** `yt-dlp` requires `ffmpeg` to be installed on your system for audio conversion.
> Install it via your package manager: `apt install ffmpeg` / `brew install ffmpeg`.

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your token:
nano .env
```

**Required:**
- `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)

### 3. Run the bot

```bash
python bot.py
```

---

## 📁 Project Structure

```
Tele_Music_bot_autoplay/
├── bot.py                    # Entry point, handler registration
├── config.py                 # Configuration & constants
├── requirements.txt
├── .env.example
│
├── models/
│   └── __init__.py           # Track, QueueItem, UserSession dataclasses
│
├── services/
│   ├── music_api.py          # YouTube Music API client (via ytmusicapi)
│   ├── audio_streamer.py     # Audio download via yt-dlp
│   ├── recommender.py        # Recommendation engine & strategies
│   └── session_manager.py    # Per-user session store
│
├── handlers/
│   ├── commands.py           # /start, /search, /recommend, /queue, etc.
│   ├── callbacks.py          # Inline button callbacks
│   └── messages.py           # Free-text & audio upload handling
│
└── utils/
    ├── keyboards.py          # InlineKeyboardMarkup builders
    └── formatters.py         # Message text formatters
```

---

## 🤖 Commands Reference

| Command | Description |
|---|---|
| `/start` | Welcome message & feature overview |
| `/help` | Full command reference |
| `/search <query>` | Search for a song or artist |
| `/recommend` | Get personalized recommendations |
| `/trending` | Today's top tracks |
| `/mood` | Pick a mood for an instant playlist |
| `/genre` | Browse by genre |
| `/artist <name>` | Artist top tracks + similar artists |
| `/queue` | View current playback queue |
| `/skip` | Skip to next queued track |
| `/clear` | Clear queue and stop |
| `/now` | Show now-playing card |
| `/history` | Recently played tracks |
| `/playlist` | Saved playlists & liked tracks |

> 💡 **Tip:** Just type any song or artist name without a command — the bot will search automatically!

---

## 🏗 Architecture

### Async Request Handling
All API calls (`music_api.py`) use `ytmusicapi` (synchronous SDK) run inside `asyncio.get_event_loop().run_in_executor()` to avoid blocking. The bot uses `python-telegram-bot`'s native `asyncio` support with `concurrent_updates=True` to handle multiple users simultaneously.

### Recommendation Strategies
`recommender.py` implements several strategies chosen based on session state:

1. **Cold Start** — trending tracks (new users with no history)
2. **Profile-Based** — seeds from top artists + top tags from play history
3. **Similarity-Based** — YouTube Music radio seeded from current track's videoId
4. **Mood/Genre** — keyword search using mood tags or genre name
5. **Auto-Refill** — triggers when queue drops below `AUTO_REFILL_THRESHOLD` tracks

### Queue Management
`UserSession.queue` is a `List[QueueItem]` maintained per-user in memory. In production, replace `_sessions` dict in `session_manager.py` with Redis for persistence and horizontal scaling.

### Data Flow
```
User types "Blinding Lights"
    → MessageHandler.handle_text()
    → music_api.search_tracks("Blinding Lights")  [YouTube Music]
    → fmt_search_results() + search_results_keyboard()
    → User taps ▶️ Play
    → CallbackHandler.handle_play()
    → music_api.get_track_by_id()
    → audio_streamer.download_audio(videoId)  [yt-dlp + ffmpeg]
    → session.current_track = track
    → recommender.auto_queue_refill()  [if queue low]
    → fmt_now_playing() + now_playing_keyboard()
```

---

## 🔧 Production Deployment

### Using a process manager (recommended)

```bash
# Install PM2 or use systemd
pip install supervisor

# Or simply run with nohup
nohup python bot.py > logs/bot.log 2>&1 &
```

### Scaling with Redis sessions

Replace `_sessions` dict in `services/session_manager.py` with a Redis-backed store:

```python
import redis.asyncio as redis

r = redis.from_url("redis://localhost:6379")

async def get(user_id: int) -> UserSession:
    data = await r.get(f"session:{user_id}")
    if data:
        return UserSession(**json.loads(data))
    return UserSession(user_id=user_id)
```

### Webhook mode (for high traffic)

Replace `run_polling()` in `bot.py` with:

```python
app.run_webhook(
    listen="0.0.0.0",
    port=8443,
    url_path=cfg.TELEGRAM_BOT_TOKEN,
    webhook_url=f"https://yourdomain.com/{cfg.TELEGRAM_BOT_TOKEN}",
)
```

---

## 📡 APIs & Libraries Used

| Library / API | Purpose |
|---|---|
| [python-telegram-bot](https://python-telegram-bot.org/) | Async bot framework |
| [ytmusicapi](https://ytmusicapi.readthedocs.io/) | YouTube Music search, charts, artist data |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Audio download from YouTube |
| ffmpeg | Audio conversion to MP3 (system dependency) |

---

## 🛠 Tech Stack

- **Python 3.11+**
- **python-telegram-bot 21** — async bot framework
- **ytmusicapi** — YouTube Music search & metadata (no API key required)
- **yt-dlp** — audio download
- **asyncio** — native concurrency for queue & API calls

---

## 📄 License

MIT — free to use, modify, and deploy.
