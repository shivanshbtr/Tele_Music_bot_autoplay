"""
Audio Streamer — downloads audio via yt-dlp and sends it to Telegram.
"""

import asyncio
import logging
import os
import tempfile
from typing import Optional

import yt_dlp

logger = logging.getLogger(__name__)

_AUDIO_BITRATE = "128"

# yt-dlp socket-level timeout (seconds). Keeps a stalled download from
# hanging the executor thread indefinitely.
_YTDLP_SOCKET_TIMEOUT = 30


class AudioStreamer:

    async def download_audio(self, video_id: str) -> Optional[str]:
        """
        Download audio for a YouTube video ID.
        Returns the path to the downloaded MP3, or None on failure.
        """
        if not video_id:
            logger.error("download_audio called with empty video_id")
            return None

        url = f"https://music.youtube.com/watch?v={video_id}"
        tmp_dir = tempfile.mkdtemp()
        output_template = os.path.join(tmp_dir, "%(title)s.%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": _YTDLP_SOCKET_TIMEOUT,
            "retries": 3,               # retry failed fragment fetches
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": _AUDIO_BITRATE,
            }],
        }

        try:
            loop = asyncio.get_running_loop()   # get_running_loop() replaces deprecated get_event_loop()
            await loop.run_in_executor(None, self._download, url, ydl_opts)

            for fname in os.listdir(tmp_dir):
                if fname.endswith(".mp3"):
                    return os.path.join(tmp_dir, fname)

            logger.error("yt-dlp finished but no .mp3 found in %s", tmp_dir)
            return None

        except Exception as e:
            logger.error("Audio download error for video_id=%s: %s", video_id, e)
            self._safe_rmdir(tmp_dir)
            return None

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
