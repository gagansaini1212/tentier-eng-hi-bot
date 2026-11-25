import logging
import os
from pathlib import Path

from deep_translator import GoogleTranslator, MyMemoryTranslator
from telegram import ChatMember, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _read_env_value(key_name: str) -> str:
    """Read a config value from environment variables or local .env file."""
    val = os.environ.get(key_name, "").strip()
    if val:
        return val

    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == key_name:
                return value.strip().strip('"').strip("'")
    return ""


def load_token() -> str:
    token = _read_env_value("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Add it to .env or export it in your shell."
        )
    return token


def load_admin_ids() -> set[int]:
    """Parse comma-separated Telegram numeric user IDs from ADMIN_USER_IDS."""
    raw = _read_env_value("ADMIN_USER_IDS")
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


ADMIN_IDS: set[int] = load_admin_ids()


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Allow configured ADMIN_USER_IDS everywhere, plus group/supergroup chat admins."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False

    if user.id in ADMIN_IDS:
        return True

    if chat.type in ("group", "supergroup"):
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            return member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER)
        except Exception as exc:
            logger.warning("Failed to check chat member status: %s", exc)

    return False


def _translate_chunk(text: str) -> str:
    """Translate a single chunk with GoogleTranslator and fall back to MyMemory if rate-limited."""
    try:
        return GoogleTranslator(source="en", target="hi").translate(text)
    except Exception as exc:
        logger.warning("GoogleTranslator failed (%s), falling back to MyMemory", exc)
        mm = MyMemoryTranslator(source="en-US", target="hi-IN")
        if len(text) <= 450:
            return mm.translate(text)
        parts = [text[i : i + 450] for i in range(0, len(text), 450)]
        return " ".join(mm.translate(part) for part in parts)


def translate_en_to_hi(text: str) -> str:
    """Translate English text to Hindi, chunking long messages safely."""
    max_chunk = 4500
    if len(text) <= max_chunk:
        return _translate_chunk(text)

    parts = [text[i : i + max_chunk] for i in range(0, len(text), max_chunk)]
    return "\n".join(_translate_chunk(part) for part in parts)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if await is_admin(update, context):
        await update.message.reply_text(
            "Namaste Admin! Send me any English text and I will translate it to Hindi."
        )
    else:
        uid = user.id if user else "unknown"
        await update.message.reply_text(
            f"Access denied. This bot is restricted to admins only.\nYour Telegram User ID: {uid}"
        )


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user:
        await update.message.reply_text(f"Your Telegram User ID: {user.id}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context):
        uid = update.effective_user.id if update.effective_user else "unknown"
        await update.message.reply_text(
            f"Access denied. Admins only.\nYour Telegram User ID: {uid}"
        )
        return
    await update.message.reply_text(
        "Send any English message, sentence, or paragraph — I'll reply with the Hindi translation.\n"
        "Commands: /start, /help, /myid"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    if not await is_admin(update, context):
        uid = update.effective_user.id if update.effective_user else "unknown"
        await update.message.reply_text(
            f"Access denied. Only admins can use this bot.\nYour Telegram User ID: {uid}"
        )
        return

    text = update.message.text.strip()
    if not text:
        return

    try:
        hindi = translate_en_to_hi(text)
        await update.message.reply_text(hindi)
    except Exception as exc:
        logger.exception("Translation failed")
        await update.message.reply_text(f"Sorry, translation failed: {exc}")


def main() -> None:
    token = load_token()
    logger.info("Loaded %d configured admin user ID(s)", len(ADMIN_IDS))
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("English-to-Hindi bot is running (admin-only polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
