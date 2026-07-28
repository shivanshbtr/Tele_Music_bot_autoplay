"""
Audio Streamer — downloads audio via yt-dlp and sends it to Telegram.
"""

import asyncio
import logging
import os
import tempfile
import time
from typing import Optional

import yt_dlp
from telegram import Bot
from telegram.error import TelegramError

from config import Config

logger = logging.getLogger(__name__)

_AUDIO_BITRATE = "128"

# yt-dlp socket-level timeout (seconds). Keeps a stalled download from
# hanging the executor thread indefinitely.
_YTDLP_SOCKET_TIMEOUT = 30

# Player clients to try in order. "android"/"ios" clients very rarely trigger
# YouTube's "Sign in to confirm you're not a bot" wall because they use a
# different (non-web) auth flow internally. "web" is tried last as a
# cookie-authenticated fallback.
_PLAYER_CLIENTS = ["android", "ios", "web"]

# Don't DM the owner on every single failed track — once every 30 minutes
# is plenty to know cookies need refreshing.
_OWNER_NOTIFY_COOLDOWN = 1800


class AudioStreamer:

    def __init__(self) -> None:
        cfg = Config()
        self._cookies_path = cfg.YTDLP_COOKIES_FILE
        self._bot_token = cfg.TELEGRAM_BOT_TOKEN
        self._owner_id = cfg.OWNER_ID
        self._last_owner_notify = 0.0
        if not (self._cookies_path and os.path.isfile(self._cookies_path)):
            logger.warning(
                "No yt-dlp cookies file found at '%s'. If you keep hitting "
                "'Sign in to confirm you're not a bot', export cookies.txt "
                "from a logged-in YouTube session (see README), or send it "
                "via /updatecookies.",
                self._cookies_path,
            )

    @property
    def _cookies_file(self) -> Optional[str]:
        # Re-checked on every call (cheap stat) rather than cached once at
        # startup, so a cookies.txt dropped in later via /updatecookies is
        # picked up immediately without restarting the bot.
        if self._cookies_path and os.path.isfile(self._cookies_path):
            return self._cookies_path
        return None

    async def download_audio(self, video_id: str) -> Optional[str]:
        """
        Download audio for a YouTube video ID.
        Returns the path to the downloaded MP3, or None on failure.
        """
        if not video_id:
            logger.error("download_audio called with empty video_id")
            return None

        url = f"https://music.youtube.com/watch?v={video_id}"
        loop = asyncio.get_running_loop()   # get_running_loop() replaces deprecated get_event_loop()

        last_error: Optional[Exception] = None
        any_bot_check = False
        for client in _PLAYER_CLIENTS:
            tmp_dir = tempfile.mkdtemp()
            output_template = os.path.join(tmp_dir, "%(title)s.%(ext)s")

            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": output_template,
                "quiet": True,
                "no_warnings": True,
                "socket_timeout": _YTDLP_SOCKET_TIMEOUT,
                "retries": 3,               # retry failed fragment fetches
                "extractor_args": {"youtube": {"player_client": [client]}},
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": _AUDIO_BITRATE,
                }],
            }
            if self._cookies_file:
                ydl_opts["cookiefile"] = self._cookies_file

            try:
                await loop.run_in_executor(None, self._download, url, ydl_opts)

                for fname in os.listdir(tmp_dir):
                    if fname.endswith(".mp3"):
                        return os.path.join(tmp_dir, fname)

                logger.warning("yt-dlp (%s client) finished but no .mp3 found, trying next client", client)
                self._safe_rmdir(tmp_dir)

            except Exception as e:
                last_error = e
                is_bot_check = "sign in" in str(e).lower() or "confirm you" in str(e).lower()
                any_bot_check = any_bot_check or is_bot_check
                logger.warning(
                    "yt-dlp (%s client) failed for video_id=%s%s: %s",
                    client, video_id, " [bot-check]" if is_bot_check else "", e,
                )
                self._safe_rmdir(tmp_dir)
                continue

        logger.error("Audio download error for video_id=%s: all player clients failed (%s)", video_id, last_error)

        # All clients failed and at least one looked like YouTube's bot-check
        # wall (rather than e.g. a network blip) — that almost always means
        # cookies.txt has expired. Let the owner know directly so they don't
        # have to notice missing music before realizing why.
        if any_bot_check:
            asyncio.create_task(self._notify_owner_cookies_expired())

        return None

    async def _notify_owner_cookies_expired(self) -> None:
        """DM the owner that cookies.txt likely needs refreshing, rate-limited
        so a burst of failed tracks doesn't spam multiple messages."""
        if not self._owner_id or not self._bot_token:
            return

        now = time.monotonic()
        if now - self._last_owner_notify < _OWNER_NOTIFY_COOLDOWN:
            return
        self._last_owner_notify = now

        try:
            bot = Bot(token=self._bot_token)
            await bot.send_message(
                chat_id=self._owner_id,
                text=(
                    "🍪 *Cookies expired* — YouTube is blocking downloads with "
                    "\"Sign in to confirm you're not a bot\".\n\n"
                    "Run /updatecookies and send a fresh cookies.txt to fix it."
                ),
                parse_mode="Markdown",
            )
        except TelegramError as e:
            logger.error("Failed to notify owner about expired cookies: %s", e)

    def _download(self, url: str, opts: dict) -> None:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    async def cleanup(self, file_path: Optional[str]) -> None:
        """Delete the temp file and its directory after sending."""
        if not file_path:
            return
        try:
            os.remove(file_path)
            self._safe_rmdir(os.path.dirname(file_path))
        except Exception:
            pass

    @staticmethod
    def _safe_rmdir(path: str) -> None:
        try:
            os.rmdir(path)
        except Exception:
            pass


audio_streamer = AudioStreamer()
