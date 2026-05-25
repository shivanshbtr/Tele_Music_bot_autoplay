"""
Message Handlers — handles plain text and audio file uploads.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from services.session_manager import session_manager
from services.music_api import music_api
from utils.keyboards import search_results_keyboard
from utils.formatters import fmt_search_results

logger = logging.getLogger(__name__)


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

    async def _do_search(self, update: Update, query: str):
        tracks = await music_api.search_tracks(query, limit=6)
        text = fmt_search_results(tracks, query)
        keyboard = search_results_keyboard(tracks) if tracks else None
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )
