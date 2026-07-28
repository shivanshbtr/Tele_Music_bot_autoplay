"""
Telegram Music Recommendation Bot
Main entry point - handles bot initialization and startup
"""
import logging
from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeDefault, Update
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    TypeHandler,
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

# Commands shown in Telegram's native "/" menu (the tappable autocomplete
# list next to the text box). This is separate from — and in addition to —
# the plain-text /command mentions in WELCOME_MESSAGE/HELP_MESSAGE, which
# Telegram auto-links as long as they aren't wrapped in `code` formatting.
_PUBLIC_COMMANDS = [
    BotCommand("start", "Welcome message & feature overview"),
    BotCommand("help", "Full command reference"),
    BotCommand("search", "Search for a song or artist"),
    BotCommand("recommend", "Get personalized recommendations"),
    BotCommand("trending", "Today's top tracks"),
    BotCommand("mood", "Pick a mood for an instant playlist"),
    BotCommand("genre", "Browse by genre"),
    BotCommand("artist", "Artist top tracks + similar artists"),
    BotCommand("queue", "View current playback queue"),
    BotCommand("skip", "Skip to next queued track"),
    BotCommand("clear", "Clear queue and stop"),
    BotCommand("now", "Show now-playing card"),
    BotCommand("autoplay", "Start seamless continuous playback"),
    BotCommand("stop", "Stop autoplay"),
    BotCommand("history", "Recently played tracks"),
    BotCommand("playlist", "Saved playlists & liked tracks"),
]


async def _setup_command_menu(app: Application) -> None:
    """
    Populate Telegram's native command menu. Runs once at startup
    (Application post_init hook).

    /updatecookies is deliberately NOT in the default (public) list — it's
    only added to a chat-scoped menu for TELEGRAM_OWNER_ID, so it doesn't
    advertise itself to anyone else even though the auth gate would block
    them from using it anyway.
    """
    await app.bot.set_my_commands(_PUBLIC_COMMANDS, scope=BotCommandScopeDefault())

    cfg = Config()
    if cfg.OWNER_ID:
        owner_commands = _PUBLIC_COMMANDS + [
            BotCommand("updatecookies", "Push a fresh cookies.txt (owner only)")
        ]
        try:
            await app.bot.set_my_commands(
                owner_commands, scope=BotCommandScopeChat(chat_id=cfg.OWNER_ID)
            )
        except Exception as e:
            # Fails if the owner hasn't started a chat with the bot yet —
            # harmless, the default menu still applies to them meanwhile.
            logger.warning(
                "Could not set owner-specific command menu (will retry on "
                "next restart once the owner has messaged the bot): %s", e
            )


async def _check_authorized(update: Update, context) -> None:
    """
    Runs before every other handler (group=-1). If TELEGRAM_OWNER_ID and/or
    TELEGRAM_ALLOWED_USER_IDS are set, silently drops updates from anyone
    not on that list — keeps this a personal bot instead of a public one.
    If neither is set, the bot stays open to everyone (unchanged behavior).
    """
    user = update.effective_user
    if not user:
        return

    cfg = Config()
    if cfg.is_allowed(user.id):
        return

    logger.info("Ignored update from unauthorized user_id=%s", user.id)
    if update.callback_query:
        await update.callback_query.answer()  # clear the loading spinner, no message
    # No reply for messages/commands either — stay silent so the bot's
    # existence/behavior isn't revealed to strangers who stumble onto it.
    raise ApplicationHandlerStop


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
        .post_init(_setup_command_menu)
        .build()
    )

    # Initialize handler classes
    cmd = CommandHandlers()
    cb = CallbackHandlers()
    msg = MessageHandlers()

    # ── Authorization Gate (runs first, before any other handler) ──────────────
    app.add_handler(TypeHandler(Update, _check_authorized), group=-1)

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
    app.add_handler(CommandHandler("updatecookies", cmd.update_cookies))

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
    app.add_handler(MessageHandler(filters.Document.ALL, msg.handle_document))

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
