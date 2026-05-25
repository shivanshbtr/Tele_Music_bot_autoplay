"""
Telegram Music Recommendation Bot
Main entry point - handles bot initialization and startup
"""
import logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.request import HTTPXRequest
from config import Config
from handlers.commands import CommandHandlers
from handlers.callbacks import CallbackHandlers
from handlers.messages import MessageHandlers

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log"),
    ],
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Initialize and run the bot."""
    config = Config()

    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Copy .env.example to .env and fill in your token."
        )

    # HTTPXRequest with extended timeouts — audio uploads can be 5–10 MB and
    # take many seconds on a slow uplink. The PTB defaults (5 s read/write)
    # cause "Timed out" errors on virtually every track send.
    request = HTTPXRequest(
        connect_timeout=10,
        read_timeout=120,       # wait up to 2 min for Telegram to acknowledge
        write_timeout=120,      # wait up to 2 min while uploading the file
        pool_timeout=10,
    )

    # Build application
    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .request(request)
        .concurrent_updates(True)
        .build()
    )

    # Initialize handler classes
    cmd = CommandHandlers()
    cb = CallbackHandlers()
    msg = MessageHandlers()

    # ── Command Handlers ──────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", cmd.start))
    app.add_handler(CommandHandler("help", cmd.help))
    app.add_handler(CommandHandler("search", cmd.search))
    app.add_handler(CommandHandler("recommend", cmd.recommend))
    app.add_handler(CommandHandler("queue", cmd.show_queue))
    app.add_handler(CommandHandler("skip", cmd.skip))
    app.add_handler(CommandHandler("clear", cmd.clear_queue))
    app.add_handler(CommandHandler("history", cmd.history))
    app.add_handler(CommandHandler("trending", cmd.trending))
    app.add_handler(CommandHandler("playlist", cmd.playlist))
    app.add_handler(CommandHandler("mood", cmd.mood))
    app.add_handler(CommandHandler("genre", cmd.genre))
    app.add_handler(CommandHandler("artist", cmd.artist))
    app.add_handler(CommandHandler("now", cmd.now_playing))
    app.add_handler(CommandHandler("autoplay", cmd.autoplay))
    app.add_handler(CommandHandler("stop", cmd.stop_autoplay))

    # ── Callback Query Handlers ───────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(cb.handle_play, pattern=r"^play:"))
    app.add_handler(CallbackQueryHandler(cb.handle_queue_add, pattern=r"^queue:"))
    app.add_handler(CallbackQueryHandler(cb.handle_recommend, pattern=r"^rec:"))
    app.add_handler(CallbackQueryHandler(cb.handle_skip, pattern=r"^skip$"))
    app.add_handler(CallbackQueryHandler(cb.handle_clear, pattern=r"^clear$"))
    app.add_handler(CallbackQueryHandler(cb.handle_like, pattern=r"^like:"))
    app.add_handler(CallbackQueryHandler(cb.handle_dislike, pattern=r"^dislike:"))
    app.add_handler(CallbackQueryHandler(cb.handle_playlist_page, pattern=r"^page:"))
    app.add_handler(CallbackQueryHandler(cb.handle_genre_select, pattern=r"^genre:"))
    app.add_handler(CallbackQueryHandler(cb.handle_mood_select, pattern=r"^mood:"))
    app.add_handler(CallbackQueryHandler(cb.handle_show_queue, pattern=r"^show_queue$"))
    app.add_handler(CallbackQueryHandler(cb.handle_autoplay_next, pattern=r"^ap:next$"))
    app.add_handler(CallbackQueryHandler(cb.handle_autoplay_stop, pattern=r"^ap:stop$"))

    # ── Message Handlers ──────────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg.handle_text))
    app.add_handler(MessageHandler(filters.AUDIO, msg.handle_audio))

    # ── Error Handler ─────────────────────────────────────────────────────────
    app.add_error_handler(handle_error)

    logger.info("🎵 Music Recommendation Bot starting...")
    app.run_polling(allowed_updates=["message", "callback_query"])


async def handle_error(update, context):
    """Global error handler."""
    logger.error(f"Update {update} caused error: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ An error occurred. Please try again or use /help for assistance."
        )


if __name__ == "__main__":
    main()
