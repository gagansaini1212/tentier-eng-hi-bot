import logging
import os
from pathlib import Path

from deep_translator import GoogleTranslator, MyMemoryTranslator
from telegram import Update
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


def load_token() -> str:
    """Load TELEGRAM_BOT_TOKEN from environment or local .env file."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        return token

    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "TELEGRAM_BOT_TOKEN":
                return value.strip().strip('"').strip("'")

    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN is not set. Add it to .env or export it in your shell."
    )


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
    await update.message.reply_text(
        "Namaste! Send me any English text and I will translate it to Hindi."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Just send any English message, sentence, or paragraph — I'll reply with the Hindi translation."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
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
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("English-to-Hindi bot is running (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
