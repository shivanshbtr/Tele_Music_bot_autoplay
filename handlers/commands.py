"""
Command Handlers — /start, /search, /recommend, /queue, etc.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config import Config
from services.session_manager import session_manager
from services.music_api import music_api
from services.recommender import recommender
from services.autoplay_engine import autoplay_manager
from utils.keyboards import (
    search_results_keyboard,
    recommendations_keyboard,
    queue_keyboard,
    mood_keyboard,
    genre_keyboard,
    now_playing_keyboard,
)
from utils.formatters import (
    fmt_queue,
    fmt_history,
    fmt_recommendations,
    fmt_search_results,
    fmt_now_playing,
)

logger = logging.getLogger(__name__)
cfg = Config()


class CommandHandlers:

    # ── /start ────────────────────────────────────────────────────────────────

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        session_manager.get(user.id, user.username or user.first_name)
        await update.message.reply_text(
            cfg.WELCOME_MESSAGE,
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── /help ─────────────────────────────────────────────────────────────────

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(cfg.HELP_MESSAGE, parse_mode=ParseMode.MARKDOWN)

    # ── /search ───────────────────────────────────────────────────────────────

    async def search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        query = " ".join(context.args) if context.args else ""

        if not query:
            session = session_manager.get(user.id)
            session.search_state = "awaiting_query"
            await update.message.reply_text(
                "🔍 What song or artist are you looking for?"
            )
            return

        await update.message.reply_text(f"🔍 Searching for *{query}*...", parse_mode=ParseMode.MARKDOWN)
        tracks = await music_api.search_tracks(query, limit=6)

        text = fmt_search_results(tracks, query)
        keyboard = search_results_keyboard(tracks) if tracks else None
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    # ── /recommend ────────────────────────────────────────────────────────────

    async def recommend(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        session = session_manager.get(user.id)

        await update.message.reply_text("🎯 Finding recommendations for you...")
        tracks = await recommender.get_recommendations(session, limit=8)

        text = fmt_recommendations(tracks)
        keyboard = recommendations_keyboard(tracks) if tracks else None
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    # ── /queue ────────────────────────────────────────────────────────────────

    async def show_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        session = session_manager.get(user.id)
        text = fmt_queue(session)
        keyboard = queue_keyboard(session) if (session.queue or session.current_track) else None
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    # ── /skip ─────────────────────────────────────────────────────────────────

    async def skip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        session = session_manager.get(user.id)

        if not session.queue:
            await update.message.reply_text(
                "📋 Queue is empty! Use /recommend or /search to add more tracks."
            )
            return

        from handlers.callbacks import _download_and_send
        next_track = session.queue[0].track
        session.next_track()   # pop from queue
        await _download_and_send(update.message, context, next_track, session)

    # ── /clear ────────────────────────────────────────────────────────────────

    async def clear_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        session = session_manager.get(user.id)
        count = len(session.queue)
        session.queue.clear()
        session.current_track = None
        # Also stop autoplay so it doesn't keep running against an empty session
        await autoplay_manager.stop(user.id)
        await update.message.reply_text(
            f"🗑 Cleared {count} track(s) from queue. Autoplay stopped."
        )

    # ── /history ──────────────────────────────────────────────────────────────

    async def history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        session = session_manager.get(user.id)
        await update.message.reply_text(
            fmt_history(session),
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── /trending ─────────────────────────────────────────────────────────────

    async def trending(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🔥 Fetching trending tracks...")
        tracks = await music_api.get_trending_tracks(limit=8)
        text = fmt_recommendations(tracks, title="🔥 Trending Now")
        keyboard = recommendations_keyboard(tracks) if tracks else None
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    # ── /mood ─────────────────────────────────────────────────────────────────

    async def mood(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🎭 *What's your mood?*\nPick one and I'll build the perfect playlist:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=mood_keyboard(),
        )

    # ── /genre ────────────────────────────────────────────────────────────────

    async def genre(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🎸 *Choose a genre:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=genre_keyboard(),
        )

    # ── /artist ───────────────────────────────────────────────────────────────

    async def artist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        artist_name = " ".join(context.args) if context.args else ""

        if not artist_name:
            await update.message.reply_text(
                "🎤 Please provide an artist name: `/artist Taylor Swift`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        session = session_manager.get(user.id)
        await update.message.reply_text(f"🎤 Finding music for *{artist_name}*...", parse_mode=ParseMode.MARKDOWN)
        tracks = await recommender.get_artist_recommendations(session, artist_name, limit=8)

        text = fmt_recommendations(tracks, title=f"🎤 {artist_name} & Similar Artists")
        keyboard = recommendations_keyboard(tracks) if tracks else None
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    # ── /now ─────────────────────────────────────────────────────────────────

    async def now_playing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        session = session_manager.get(user.id)

        if not session.current_track:
            await update.message.reply_text(
                "🔇 Nothing playing. Use /search or /trending to get started!"
            )
            return

        track = session.current_track
        text = fmt_now_playing(track, len(session.queue))
        keyboard = now_playing_keyboard(track)

        if track.cover_url:
            await update.message.reply_photo(
                photo=track.cover_url,
                caption=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )
        else:
            await update.message.reply_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard,
            )

    # ── /playlist ─────────────────────────────────────────────────────────────

    async def playlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        session = session_manager.get(user.id)

        if not session.playlists and not session.liked_tracks:
            await update.message.reply_text(
                "📂 You have no saved playlists yet.\n"
                "Like tracks with ❤️ to build your collection, "
                "or use /mood and /genre to create playlists!"
            )
            return

        lines = ["📂 *Your Playlists*\n"]
        if session.liked_tracks:
            lines.append(f"❤️ Liked Tracks ({len(session.liked_tracks)} songs)")

        for name, tracks in session.playlists.items():
            lines.append(f"📋 {name} ({len(tracks)} songs)")

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    # ── /autoplay ─────────────────────────────────────────────────────────────

    async def autoplay(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /autoplay — toggle seamless autoplay on/off.

        When ON the bot will:
          • Prefetch the next queued track the moment the current one starts
          • Auto-queue 3 similar tracks each time a new song begins
            (as long as the queue is not full)
          • Send the prefetched audio automatically so back-to-back playback
            is instant — just like Spotify Radio
          • When the queue fills up it keeps sending without adding more until
            the queue drains, then repeats the whole cycle
        """
        user = update.effective_user
        session = session_manager.get(user.id)

        if autoplay_manager.is_active(user.id):
            await update.message.reply_text(
                "✅ *Autoplay is already running!*\n\n"
                "Tracks are being prefetched and queued automatically.\n"
                "Use /stop to turn it off.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        if not session.current_track and not session.queue:
            await update.message.reply_text(
                "🎵 *Start a song first!*\n\n"
                "Use /search or /trending to find a track, then hit ▶️ Play.\n"
                "Once music is playing, /autoplay will keep the stream going.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        engine = autoplay_manager.start(
            user_id=user.id,
            chat_id=update.effective_chat.id,
            bot=context.bot,
        )

        # Kick off immediate queue fill + prefetch
        if session.current_track:
            await engine._maybe_fill_queue(session)
            if session.queue:
                next_item = session.queue[0].track
                import asyncio as _asyncio
                _asyncio.create_task(engine._prefetch(next_item))

        await update.message.reply_text(
            "🔄 *Autoplay enabled!*\n\n"
            "Here's what happens now:\n"
            "• When your current track ends and you hit ▶️ *Next*, the next song "
            "is already downloaded — instant playback\n"
            "• 3 similar songs are auto-queued after each track\n"
            "• Queue full? I'll keep sending without adding more until it drains\n"
            "• Queue empty? The whole cycle restarts\n\n"
            "Use /stop to turn off autoplay.",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── /stop ─────────────────────────────────────────────────────────────────

    async def stop_autoplay(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /stop — halt the autoplay engine for this user.
        Cleans up any prefetched temp files.
        """
        user = update.effective_user

        if not autoplay_manager.is_active(user.id):
            await update.message.reply_text(
                "ℹ️ Autoplay is not running.\n"
                "Use /autoplay to start seamless music streaming."
            )
            return

        await autoplay_manager.stop(user.id)
        await update.message.reply_text(
            "⏹ *Autoplay stopped.*\n\n"
            "Your queue is still intact — use /autoplay again to resume "
            "seamless streaming, or /clear to wipe the queue.",
            parse_mode=ParseMode.MARKDOWN,
        )
