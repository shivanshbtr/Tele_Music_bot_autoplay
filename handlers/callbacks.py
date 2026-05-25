"""
Callback Query Handlers — all inline button interactions.
"""

import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import TimedOut, NetworkError, BadRequest

from services.session_manager import session_manager
from services.music_api import music_api
from services.recommender import recommender
from services.autoplay_engine import autoplay_manager
from utils.keyboards import (
    now_playing_keyboard,
    recommendations_keyboard,
    queue_keyboard,
)
from utils.formatters import (
    fmt_now_playing,
    fmt_queue,
    fmt_recommendations,
)

logger = logging.getLogger(__name__)

# How many times to retry a timed-out Telegram upload before giving up.
_UPLOAD_RETRIES = 3
# Seconds to wait between upload attempts (grows with each retry).
_RETRY_BASE_DELAY = 2


async def _send_audio_to_message(message, file_path: str, track,
                                 retries: int = _UPLOAD_RETRIES) -> bool:
    """
    Upload an audio file as a reply to `message` (works for both
    callback query messages and direct command messages).
    Returns True on success, False if all attempts fail.
    """
    for attempt in range(1, retries + 1):
        try:
            with open(file_path, "rb") as audio_file:
                await message.reply_audio(
                    audio=audio_file,
                    title=track.title,
                    performer=track.artist,
                    thumbnail=None,
                    caption=(
                        f"🎵 *{track.title}*\n"
                        f"👤 {track.artist}"
                    ),
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=now_playing_keyboard(track),
                )
            return True
        except (TimedOut, NetworkError) as e:
            if attempt < retries:
                delay = _RETRY_BASE_DELAY * attempt
                logger.warning(
                    "Audio upload attempt %d/%d timed out (%s). Retrying in %ds...",
                    attempt, retries, e, delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error("Audio upload failed after %d attempts: %s", retries, e)
        except BadRequest as e:
            logger.error("Audio upload bad request — not retrying: %s", e)
            break
        except Exception as e:
            logger.error("Unexpected error sending audio: %s", e)
            break
    return False


async def _download_and_send(message, context, track, session):
    """
    Core playback helper — works from callbacks, commands, and skip.
    Downloads `track`, sends it as an audio message to `message`,
    then hooks into the autoplay engine.

    `message`  — the telegram Message object to reply to
    `context`  — the handler context (for context.bot)
    `track`    — a Track instance (already resolved)
    `session`  — the caller's UserSession
    """
    from services.audio_streamer import audio_streamer

    status_msg = await message.reply_text(
        f"⬇️ Downloading *{track.title}* by *{track.artist}*...",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Update session state — only if this track isn't already current
    # (skip handlers call session.next_track() first which already sets it)
    if session.current_track != track:
        if session.current_track:
            session.history.insert(0, session.current_track)
        session.current_track = track
        session.play_count += 1

    file_path = await audio_streamer.download_audio(track.external_id)

    if not file_path:
        await status_msg.edit_text("⚠️ Could not download audio. Try another track.")
        return

    try:
        success = await _send_audio_to_message(message, file_path, track)
        if success:
            await status_msg.delete()
        else:
            await status_msg.edit_text(
                "⚠️ Upload timed out after several attempts. "
                "Server uplink may be slow — try again in a moment."
            )
    finally:
        await audio_streamer.cleanup(file_path)

    # ── Autoplay pipeline ──────────────────────────────────────────────────
    engine = autoplay_manager.start(
        user_id=session.user_id,
        chat_id=message.chat_id,
        bot=context.bot,
    )
    await engine._maybe_fill_queue(session)
    if session.queue:
        next_item = session.queue[0].track
        asyncio.create_task(
            engine._prefetch(next_item),
            name=f"prefetch_{next_item.external_id}",
        )


async def _play_track(update: Update, context, track_ext_id: str):
    """Entry point when the user taps ▶️ Play on a search result."""
    query = update.callback_query
    user = update.effective_user
    session = session_manager.get(user.id)

    status_msg = await query.message.reply_text("⬇️ Loading track...")

    track = await music_api.get_track_by_id(track_ext_id)
    if not track:
        results = await music_api.search_tracks(track_ext_id, limit=1)
        track = results[0] if results else None
    if not track:
        await status_msg.edit_text("⚠️ Could not find track.")
        return

    await status_msg.delete()
    await _download_and_send(query.message, context, track, session)


class CallbackHandlers:

    # ── Play ──────────────────────────────────────────────────────────────────

    async def handle_play(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer("⏳ Loading track...")
        parts = query.data.split(":")           # play:ext_id[:source]
        ext_id = parts[1] if len(parts) > 1 else ""
        await _play_track(update, context, ext_id)

    # ── Queue Add ─────────────────────────────────────────────────────────────

    async def handle_queue_add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = update.effective_user
        session = session_manager.get(user.id)

        parts = query.data.split(":")           # queue:ext_id[:source]
        ext_id = parts[1] if len(parts) > 1 else ""

        track = await music_api.get_track_by_id(ext_id)
        if not track:
            await query.answer("⚠️ Could not add track to queue.")
            return

        if session.add_to_queue(track):
            await query.answer(f"➕ Added to queue: {track.title}")
        else:
            await query.answer("⚠️ Queue is full (max 50 tracks).")

    # ── Similar / Recommend ───────────────────────────────────────────────────

    async def handle_recommend(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = update.effective_user
        session = session_manager.get(user.id)

        await query.answer("🔀 Finding similar tracks...")

        if query.data == "rec:refresh":
            tracks = await recommender.get_recommendations(session, limit=8)
        else:
            parts = query.data.split(":")       # rec:<ext_id>
            ext_id = parts[1] if len(parts) > 1 else ""
            if ext_id:
                track = await music_api.get_track_by_id(ext_id)
                if track:
                    tracks = await music_api.get_similar_tracks(
                        track.artist, track.title, limit=6
                    )
                else:
                    tracks = await recommender.get_similar_to_current(session, limit=6)
            else:
                tracks = await recommender.get_similar_to_current(session, limit=6)

        text = fmt_recommendations(tracks, title="🎵 Similar Tracks")
        keyboard = recommendations_keyboard(tracks)
        await query.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    # ── Skip ──────────────────────────────────────────────────────────────────

    async def handle_skip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = update.effective_user
        session = session_manager.get(user.id)

        if not session.queue:
            await query.answer("📋 Queue is empty.")
            await query.message.reply_text(
                "Queue is empty! Use /recommend or /search to add tracks."
            )
            return

        await query.answer("⏭ Skipping...")

        # Pop the next track — _download_and_send will set it as current
        next_track = session.queue[0].track   # peek first so we can pass it
        session.next_track()                  # actually pop from queue

        await _download_and_send(query.message, context, next_track, session)

    # ── Clear ─────────────────────────────────────────────────────────────────

    async def handle_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = update.effective_user
        session = session_manager.get(user.id)
        count = len(session.queue)
        session.queue.clear()
        session.current_track = None
        # Also stop autoplay so it doesn't restart the cycle on an empty queue
        await autoplay_manager.stop(user.id)
        await query.answer(f"🗑 Cleared {count} track(s).")
        await query.message.edit_text("🗑 Queue cleared. Autoplay stopped.")

    # ── Like / Dislike ────────────────────────────────────────────────────────

    async def handle_like(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = update.effective_user
        session = session_manager.get(user.id)

        if session.like_current():
            await query.answer("❤️ Added to liked tracks!")
        else:
            await query.answer("❤️ Nothing playing to like.")

    async def handle_dislike(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer("👎 Got it — won't recommend similar tracks.")

    # ── Playlist Pagination ───────────────────────────────────────────────────

    async def handle_playlist_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = update.effective_user
        session = session_manager.get(user.id)
        page = int(query.data.split(":")[1])
        await query.answer()
        text = fmt_queue(session)
        keyboard = queue_keyboard(session, page=page)
        await query.message.edit_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    # ── Genre Select ──────────────────────────────────────────────────────────

    async def handle_genre_select(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = update.effective_user
        session = session_manager.get(user.id)
        genre = query.data.split(":")[1]

        await query.answer(f"🎸 Loading {genre} tracks...")
        tracks = await recommender.get_genre_playlist(session, genre, limit=8)

        text = fmt_recommendations(tracks, title=f"🎸 {genre} Picks")
        keyboard = recommendations_keyboard(tracks)
        await query.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    # ── Mood Select ───────────────────────────────────────────────────────────

    async def handle_mood_select(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = update.effective_user
        session = session_manager.get(user.id)
        mood_key = query.data.split(":")[1]
        from config import Config
        mood_emoji = Config().MOODS.get(mood_key, {}).get("emoji", "🎵")

        await query.answer(f"{mood_emoji} Building your {mood_key} playlist...")
        tracks = await recommender.get_mood_playlist(session, mood_key, limit=10)

        text = fmt_recommendations(tracks, title=f"{mood_emoji} {mood_key.capitalize()} Playlist")
        keyboard = recommendations_keyboard(tracks)
        await query.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    # ── Show Queue ────────────────────────────────────────────────────────────

    async def handle_show_queue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user = update.effective_user
        session = session_manager.get(user.id)
        await query.answer()
        text = fmt_queue(session)
        keyboard = queue_keyboard(session) if (session.queue or session.current_track) else None
        await query.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard,
        )

    # ── Autoplay: Play Next (early advance) ──────────────────────────────────

    async def handle_autoplay_next(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """User tapped ▶️ Play Next — cancel the timer, advance immediately."""
        query = update.callback_query
        user = update.effective_user
        session = session_manager.get(user.id)

        engine = autoplay_manager.get(user.id)
        if engine and engine.running:
            # Let the autoplay engine handle the transition (it has prefetch cache)
            await query.answer("⏭ Playing next track...")
            engine.request_early_advance()
        else:
            # Autoplay not running — do a manual download-and-send skip
            if not session.queue:
                await query.answer("📋 Queue is empty.")
                await query.message.reply_text(
                    "Queue is empty! Use /search or /recommend to add tracks."
                )
                return
            await query.answer("⏭ Loading next track...")
            next_track = session.queue[0].track
            session.next_track()
            await _download_and_send(query.message, context, next_track, session)

    # ── Autoplay: Stop ────────────────────────────────────────────────────────

    async def handle_autoplay_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """User tapped ⏹ Stop Autoplay."""
        query = update.callback_query
        user = update.effective_user

        if autoplay_manager.is_active(user.id):
            await autoplay_manager.stop(user.id)
            await query.answer("⏹ Autoplay stopped.")
            await query.message.reply_text(
                "⏹ *Autoplay stopped.*\n\n"
                "Your queue is still intact. "
                "Use /autoplay to resume seamless streaming.",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await query.answer("ℹ️ Autoplay is not running.")
