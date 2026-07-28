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
| 🔒 **Access Control** | Restrict the bot to your own Telegram account(s) only |
| 🍪 **Remote Cookie Refresh** | Push a fresh `cookies.txt` via Telegram — no server access needed |

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

**Optional (recommended for personal use):**
- `TELEGRAM_OWNER_ID` — your numeric Telegram user ID (get it from [@userinfobot](https://t.me/userinfobot)). Enables the `/updatecookies` command for you.
- `TELEGRAM_ALLOWED_USER_IDS` — comma-separated numeric user IDs allowed to use the bot at all, e.g. `111111111,222222222`. The owner above is always implicitly allowed even if not listed. Leave both this and `TELEGRAM_OWNER_ID` unset to keep the bot open to anyone who finds it.
- `YTDLP_COOKIES_FILE` — path to a Netscape-format `cookies.txt` (defaults to `cookies.txt` in the project root). See [Troubleshooting](#-troubleshooting-sign-in-to-confirm-youre-not-a-bot) below.

### 3. Run the bot

```bash
python bot.py
```

---

## 📁 Project Structure

```
Tele_Music_bot_autoplay/
├── bot.py                    # Entry point, handler registration, auth gate
├── config.py                 # Configuration, constants & access control
├── requirements.txt
├── .env.example
│
├── models/
│   └── __init__.py           # Track, QueueItem, UserSession dataclasses
│
├── services/
│   ├── music_api.py          # YouTube Music API client (via ytmusicapi)
│   ├── audio_streamer.py     # Audio download via yt-dlp + cookie-expiry DM
│   ├── recommender.py        # Recommendation engine & strategies
│   └── session_manager.py    # Per-user session store
│
├── handlers/
│   ├── commands.py           # /start, /search, /recommend, /updatecookies, etc.
│   ├── callbacks.py          # Inline button callbacks
│   └── messages.py           # Free-text, audio, and cookies.txt upload handling
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
| `/autoplay` | Start seamless continuous playback |
| `/stop` | Stop autoplay |
| `/history` | Recently played tracks |
| `/playlist` | Saved playlists & liked tracks |
| `/updatecookies` | *(owner only)* Push a new `cookies.txt` by sending it as a file |

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

## 🔒 Access Control

By default this bot is **open to anyone** who finds it on Telegram. For personal use, lock it down with two env vars in `.env`:

```bash
TELEGRAM_OWNER_ID=your_numeric_id          # from @userinfobot
TELEGRAM_ALLOWED_USER_IDS=id1,id2,id3      # comma-separated, owner is always included
```

- If **both are unset**, the bot works for everyone (original behavior).
- If **either is set**, every update is checked in `bot.py`'s `_check_authorized` handler (runs in group `-1`, before all other handlers) via `Config.is_allowed()`. Anyone not on the list is **silently ignored** — no reply, no error — so the bot's existence isn't revealed to strangers who stumble onto it.
- The owner ID is always implicitly allowed, even if you forget to add it to `TELEGRAM_ALLOWED_USER_IDS`.

### Getting Your Telegram Numeric ID

`TELEGRAM_OWNER_ID` and `TELEGRAM_ALLOWED_USER_IDS` need your **numeric** Telegram user ID (e.g. `123456789`) — not your `@username`. A username can change or be removed; the numeric ID never changes.

1. Open Telegram and search for **[@userinfobot](https://t.me/userinfobot)**.
2. Send it any message, e.g. `/start`.
3. It replies with your numeric `Id:` — copy that into `.env`.

Have each additional person you want to allow do the same and send you their ID.

> ⚠️ If you accidentally paste an `@username` instead of the numeric ID, the bot will fail to start with a `ValueError` on the `int(...)` conversion in `config.py` — that's expected, not a bug. Just swap in the numeric ID instead.

---

## 🛡 Troubleshooting: "Sign in to confirm you're not a bot"

If track downloads start failing with this YouTube error (via yt-dlp),
it's YouTube's bot-detection wall — common when a bot makes frequent
automated requests from the same IP, and more likely on outdated yt-dlp
versions. Several things are already built in to handle it:

1. **Multi-client fallback** — `services/audio_streamer.py` tries yt-dlp's
   `android` client first, then `ios`, then `web`. The mobile clients use
   a different backend flow that YouTube's bot-check rarely triggers on.
   This alone resolves the wall most of the time, with no setup needed.

2. **Owner alert, automatically** — if all three clients fail with what
   looks like the bot-check wall, the bot DMs the `TELEGRAM_OWNER_ID`
   account directly (rate-limited to once per 30 minutes):
   > 🍪 Cookies expired — YouTube is blocking downloads with "Sign in to
   > confirm you're not a bot". Run /updatecookies and send a fresh
   > cookies.txt to fix it.

   Regular users still just see the normal "⚠️ Could not download audio"
   message — only the owner gets the diagnostic DM.

3. **Refresh cookies without touching the server** — run `/updatecookies`
   in the bot's chat as the owner:
   1. On any computer, log into youtube.com with a Google account.
   2. Install a "Get cookies.txt" browser extension (e.g. *Get
      cookies.txt LOCALLY* for Chrome/Firefox) and export cookies for
      `youtube.com`.
   3. Send `/updatecookies` to the bot, then attach the exported
      `cookies.txt` as a file in the same chat.
   4. The bot validates it looks like a real cookies file, saves it to
      `YTDLP_COOKIES_FILE` (defaults to `cookies.txt` in the project
      root), and confirms — **no restart needed**, `audio_streamer.py`
      re-checks the file on every download.

   You can still drop `cookies.txt` into the project folder manually and
   restart the bot if you prefer — both paths work.

4. **Keep yt-dlp updated.** YouTube changes its internals periodically,
   and yt-dlp usually ships a patch within days. An outdated yt-dlp
   (this repo was previously pinned to a version from August 2024) is
   itself one of the most common causes of the bot-check wall. Update
   with:
   ```bash
   pip install -U yt-dlp
   ```
   (On Termux: `pip install -U yt-dlp --break-system-packages` if you hit
   an externally-managed-environment error.)

If the wall persists after all steps, it usually means YouTube has
temporarily flagged the IP itself (common on shared/cloud IPs) — cookies
from a real account are the most reliable fix in that case.

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
