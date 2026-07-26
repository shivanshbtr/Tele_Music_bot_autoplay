"""
Autoplay Engine — Seamless Spotify-like background playback.

Two complementary mechanisms make transitions seamless:

  1. TIMER  — when a track is sent, a countdown of track.duration seconds
              is started. When it fires, the next track is sent automatically.
              No user interaction needed.

  2. MANUAL — the now-playing keyboard shows a "▶️ Play Next" button. Tapping
              it cancels the running timer and sends the next track immediately.
              Combined with prefetching, the audio is already downloaded so the
              response is near-instant.

  3. STOP   — an "⏹ Stop" button (and /stop command) halts everything cleanly.

Queue fill logic (per transition):
  • If queue has room  → add AUTOPLAY_REFILL_COUNT similar tracks
  • If queue is full   → just send, don't add
  • If queue is empty  → restart: fetch recommendations, fill, continue

Prefetch:
  As soon as track N is being sent, the engine starts downloading track N+1
  in the background so it is ready when the timer fires.
"""

import asyncio
import logging
from typing import Optional, Dict
from telegram.constants import ParseMode
from telegram.error import TimedOut, NetworkError

from models import Track, UserSession
from services.session_manager import session_manager
from services.audio_streamer import audio_streamer
from services.recommender import recommender
from config import Config

logger = logging.getLogger(__name__)
cfg = Config()

AUTOPLAY_REFILL_COUNT = 3
_UPLOAD_RETRIES = 3
_RETRY_BASE_DELAY = 2

# Maximum number of songs autoplay will send before stopping automatically.
AUTOPLAY_MAX_SONGS = 250

# Seconds before track ends to send the next song.
# Timer = track.duration - _TIMER_LEAD  (minimum 10 s fallback).
_TIMER_LEAD = 15


class AutoplaySession:
    """All state for one user's autoplay pipeline."""

    def __init__(self, user_id: int, chat_id: int, bot):
        self.user_id = user_id
        self.chat_id = chat_id
        self.bot = bot
        self.running = False

        # Counts how many songs autoplay has sent; stops at AUTOPLAY_MAX_SONGS.
        self._autoplay_count: int = 0

        # The main loop task
        self._task: Optional[asyncio.Task] = None
        # Timer task for the current track's duration countdown
        self._timer_task: Optional[asyncio.Task] = None
        # Event set when an early-advance is requested (Play Next button)
        self._advance_event = asyncio.Event()

        # Prefetch cache: external_id -> local file path
        self._prefetched: Dict[str, str] = {}
        self._prefetch_lock = asyncio.Lock()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self):
        if self.running:
            return
        self.running = True
        self._advance_event.clear()
        self._task = asyncio.create_task(
            self._loop(), name=f"autoplay_{self.user_id}"
        )
        logger.info("Autoplay started for user %d", self.user_id)

    async def stop(self):
        self.running = False
        self._advance_event.set()          # unblock anything waiting
        await self._cancel_timer()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._cleanup_prefetch_cache()
        logger.info("Autoplay stopped for user %d", self.user_id)

    def request_early_advance(self):
        """Called when the user taps ▶️ Play Next — skip the timer."""
        self._advance_event.set()

    # ── Main Loop ──────────────────────────────────────────────────────────

    async def _loop(self):
        """
        Core pipeline:
          wait for something to be playing
          → fill queue if needed
          → prefetch next
          → start duration timer
          → when timer fires OR user taps Play Next → advance
          → send next track (from prefetch cache)
          → repeat
        """
        # Brief pause so the very first track is set in session
        await asyncio.sleep(2)

        while self.running:
            try:
                session = session_manager.get(self.user_id)

                if not session.current_track:
                    await asyncio.sleep(1)
                    continue

                current = session.current_track

                while self.running:
                    # ── Fill queue if there's room ─────────────────────────
                    await self._maybe_fill_queue(session)

                    # ── Prefetch the next queued track ─────────────────────
                    if session.queue:
                        asyncio.create_task(
                            self._prefetch(session.queue[0].track),
                            name=f"prefetch_{session.queue[0].track.external_id}",
                        )

                    # ── Wait duration of CURRENT song minus 15 s ──────────
                    await self._wait_for_advance(current)

                    if not self.running:
                        break

                    # ── 250-song autoplay limit ────────────────────────────
                    if self._autoplay_count >= AUTOPLAY_MAX_SONGS:
                        await self._notify(
                            f"⏹ Autoplay reached the {AUTOPLAY_MAX_SONGS}-song limit. "
                            "Use /autoplay to start a new session."
                        )
                        self.running = False
                        break

                    # ── Pop next track ─────────────────────────────────────
                    session = session_manager.get(self.user_id)
                    next_track = session.next_track()   # pops queue → current_track
                    if not next_track:
                        # Queue drained — refill and pop immediately (no re-wait)
                        await self._notify("📭 Queue empty — fetching more tracks...")
                        if not self.running:
                            break
                        added = await recommender.auto_queue_refill(session, threshold=99)
                        if not self.running:
                            break
                        if added:
                            await self._notify(
                                f"🔀 _Added {len(added)} tracks — continuing..._"
                            )
                            if not self.running:
                                break
                            next_track = session.next_track()
                        if not next_track:
                            await self._notify(
                                "⏹ No more recommendations available. Autoplay stopped."
                            )
                            self.running = False
                            break

                    # ── Final guard: a /stop during any of the awaits above
                    # (notify / refill) must not let a track slip through.
                    if not self.running:
                        break

                    # ── Send it — timer next round uses THIS track's duration
                    await self._send_track(next_track)
                    self._autoplay_count += 1
                    current = next_track   # ← timer on next iteration = this song's duration

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Autoplay loop error for user %d: %s", self.user_id, e)
                await asyncio.sleep(3)

    # ── Timer + Advance ────────────────────────────────────────────────────

    async def _wait_for_advance(self, current_track: Track):
        """
        Race two conditions:
          A) duration timer expires  (automatic)
          B) _advance_event is set   (user tapped Play Next)
        Whichever wins first triggers the transition.
        """
        self._advance_event.clear()
        await self._cancel_timer()

        duration = current_track.duration or 0
        wait = max(duration - _TIMER_LEAD, 10)   # at least 10 s

        logger.info(
            "Autoplay timer set for %ds (track: %s) for user %d",
            wait, current_track.title, self.user_id,
        )

        self._timer_task = asyncio.create_task(
            self._timer(wait), name=f"timer_{self.user_id}"
        )

        # Wait for whichever comes first
        done, pending = await asyncio.wait(
            {
                asyncio.create_task(self._advance_event.wait()),
                self._timer_task,
            },
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
        self._timer_task = None

    async def _timer(self, seconds: float):
        await asyncio.sleep(seconds)

    async def _cancel_timer(self):
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
            try:
                await self._timer_task
            except asyncio.CancelledError:
                pass
        self._timer_task = None

    # ── Queue Fill ─────────────────────────────────────────────────────────

    async def _maybe_fill_queue(self, session: UserSession):
        queue_size = len(session.queue)
        if queue_size >= cfg.MAX_QUEUE_SIZE:
            return

        slots = min(AUTOPLAY_REFILL_COUNT, cfg.MAX_QUEUE_SIZE - queue_size)
        if slots <= 0:
            return

        tracks = await recommender.get_similar_to_current(session, limit=slots + 2)

        existing = {q.track.external_id for q in session.queue}
        existing.update(t.external_id for t in session.history[:30])
        if session.current_track:
            existing.add(session.current_track.external_id)

        added = []
        for t in tracks:
            if t.external_id not in existing and session.add_to_queue(t):
                added.append(t)
                existing.add(t.external_id)
                if len(added) >= slots:
                    break

        if added:
            names = ", ".join(f"*{t.title}*" for t in added[:2])
            suffix = f" +{len(added)-2} more" if len(added) > 2 else ""
            await self._notify(f"🔀 _Queued: {names}{suffix}_")
            logger.info(
                "Autoplay queued %d tracks for user %d", len(added), self.user_id
            )

    # ── Prefetch ───────────────────────────────────────────────────────────

    async def _prefetch(self, track: Track):
        ext_id = track.external_id
        if not ext_id:
            return
        async with self._prefetch_lock:
            if ext_id in self._prefetched:
                return
        logger.info("Prefetching '%s' for user %d", track.title, self.user_id)
        file_path = await audio_streamer.download_audio(ext_id)
        if file_path:
            async with self._prefetch_lock:
                self._prefetched[ext_id] = file_path
            logger.info("Prefetch ready: %s", ext_id)
        else:
            logger.warning("Prefetch failed for %s", ext_id)

    # ── Send Track ─────────────────────────────────────────────────────────

    async def _send_track(self, track: Track):
        """Send audio — use prefetch cache when available, else download."""
        from utils.keyboards import autoplay_keyboard   # avoid circular import

        ext_id = track.external_id
        file_path = None

        async with self._prefetch_lock:
            file_path = self._prefetched.pop(ext_id, None)

        if not file_path:
            logger.info("No prefetch cache for %s — downloading now", ext_id)
            await self._notify(f"⬇️ _Loading_ *{track.title}*...")
            file_path = await audio_streamer.download_audio(ext_id)

        if not file_path:
            await self._notify(f"⚠️ Could not load *{track.title}*. Skipping.")
            return

        session = session_manager.get(self.user_id)
        keyboard = autoplay_keyboard(track)

        success = False
        for attempt in range(1, _UPLOAD_RETRIES + 1):
            try:
                with open(file_path, "rb") as f:
                    await self.bot.send_audio(
                        chat_id=self.chat_id,
                        audio=f,
                        title=track.title,
                        performer=track.artist,
                        caption=(
                            f"🎵 *{track.title}*\n"
                            f"👤 {track.artist}\n"
                            f"⏱ {track.duration_str}  •  🔄 _Autoplay_"
                        ),
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=keyboard,
                    )
                success = True
                break
            except (TimedOut, NetworkError) as e:
                if attempt < _UPLOAD_RETRIES:
                    delay = _RETRY_BASE_DELAY * attempt
                    logger.warning(
                        "Upload attempt %d/%d failed (%s), retrying in %ds",
                        attempt, _UPLOAD_RETRIES, e, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("Upload failed after %d attempts: %s", _UPLOAD_RETRIES, e)
            except Exception as e:
                logger.error("Unexpected upload error: %s", e)
                break

        await audio_streamer.cleanup(file_path)
        if success:
            logger.info("Autoplay sent '%s' to user %d", track.title, self.user_id)

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _notify(self, text: str):
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass

    async def _cleanup_prefetch_cache(self):
        async with self._prefetch_lock:
            for path in self._prefetched.values():
                await audio_streamer.cleanup(path)
            self._prefetched.clear()


# ── Global registry ────────────────────────────────────────────────────────

class AutoplayManager:

    def __init__(self):
        self._sessions: Dict[int, AutoplaySession] = {}

    def is_active(self, user_id: int) -> bool:
        s = self._sessions.get(user_id)
        return bool(s and s.running)

    def get(self, user_id: int) -> Optional[AutoplaySession]:
        return self._sessions.get(user_id)

    def start(self, user_id: int, chat_id: int, bot) -> AutoplaySession:
        existing = self._sessions.get(user_id)
        if existing and existing.running:
            return existing
        session = AutoplaySession(user_id, chat_id, bot)
        self._sessions[user_id] = session
        session.start()
        return session

    async def stop(self, user_id: int):
        session = self._sessions.pop(user_id, None)
        if session:
            await session.stop()

    async def stop_all(self):
        for uid in list(self._sessions):
            await self.stop(uid)


autoplay_manager = AutoplayManager()
