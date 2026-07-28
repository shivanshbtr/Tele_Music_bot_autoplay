"""
Message Handlers — handles plain text and audio file uploads.
"""

import logging
import os
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import Config
from services.session_manager import session_manager
from services.music_api import music_api
from utils.keyboards import search_results_keyboard
from utils.formatters import fmt_search_results

logger = logging.getLogger(__name__)
cfg = Config()


class MessageHandlers:

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle plain text messages.
        If the user has a pending search state, treat as query.
        Otherwise, auto-search for the typed text.
        """
        user = update.effective_user
        session = session_manager.get(user.id)
        text = update.message.text.strip()

        # Resolve pending search state
        if session.search_state == "awaiting_query":
            session.search_state = None
            await update.message.reply_text(
                f"🔍 Searching for *{text}*...", parse_mode=ParseMode.MARKDOWN
            )
            await self._do_search(update, text)
            return

        # Direct search for any plain text ≥ 3 chars
        if len(text) >= 3:
            await update.message.reply_text(
                f"🔍 Searching for *{text}*...", parse_mode=ParseMode.MARKDOWN
            )
            await self._do_search(update, text)
        else:
            await update.message.reply_text(
                "🎵 Send me a song name or artist to search! "
                "Or try /help to see all commands."
            )

    async def handle_audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle audio file uploads — identify the track and find similar songs."""
        audio = update.message.audio
        if not audio:
            return

        # Build query from available metadata
        parts = []
        if audio.performer:
            parts.append(audio.performer)
        if audio.title:
            parts.append(audio.title)
        query = " ".join(parts) or audio.file_name or ""

        if not query:
            await update.message.reply_text(
                "🎵 I received your audio file, but couldn't read its metadata. "
                "Try sending the song name as text instead."
            )
            return

        await update.message.reply_text(
            f"🎵 Got it! Searching for *{query}* and similar tracks...",
            parse_mode=ParseMode.MARKDOWN,
        )
        await self._do_search(update, query)

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle document uploads. Currently only used for the /updatecookies
        flow — the owner sends a fresh cookies.txt here after running
        /updatecookies, and it gets saved to the path yt-dlp reads from.
        Any other document, or any sender who isn't the owner / hasn't run
        /updatecookies first, is ignored.
        """
        user = update.effective_user

        if not context.user_data.get("awaiting_cookies"):
            return
        if not cfg.OWNER_ID or user.id != cfg.OWNER_ID:
            return

        context.user_data["awaiting_cookies"] = False
        doc = update.message.document

        if not doc:
            await update.message.reply_text("⚠️ That wasn't a file. Run /updatecookies again to retry.")
            return

        try:
            tg_file = await doc.get_file()
            dest_path = cfg.YTDLP_COOKIES_FILE or "cookies.txt"
            tmp_path = dest_path + ".tmp"

            await tg_file.download_to_drive(tmp_path)

            # Basic sanity check so a wrong/empty file doesn't silently
            # replace a working cookies.txt.
            with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(4096)
            if "youtube.com" not in head and "# Netscape" not in head:
                os.remove(tmp_path)
                await update.message.reply_text(
                    "⚠️ That file doesn't look like a Netscape-format "
                    "cookies.txt for YouTube. Nothing was changed. "
                    "Run /updatecookies to try again."
                )
                return

            os.replace(tmp_path, dest_path)
            logger.info("cookies.txt updated by owner (user_id=%s)", user.id)
            await update.message.reply_text(
                "✅ *cookies.txt updated!*\n"
                "New downloads will use it immediately — no restart needed.",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error("Failed to update cookies.txt: %s", e)
            await update.message.reply_text(
                "❌ Failed to save the file. Check the logs. "
                "You can run /updatecookies to try again."
            )

    async def _do_search(self, update: Update, query: str):
        tracks = await music_api.search_tracks(query, limit=6)
        text = fmt_search_results(tracks, query)
        keyboard = search_results_keyboard(tracks) if tracks else None
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
