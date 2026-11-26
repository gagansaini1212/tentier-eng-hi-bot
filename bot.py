import json
import logging
import os
from pathlib import Path

from deep_translator import GoogleTranslator, MyMemoryTranslator
from telegram import ChatMember, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatMemberHandler,
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

BASE_DIR = Path(__file__).parent
SETTINGS_PATH = Path(os.environ.get("SETTINGS_PATH", str(BASE_DIR / "group_settings.json")))


def _read_env_value(key_name: str) -> str:
    """Read a config value from environment variables or local .env file."""
    val = os.environ.get(key_name, "").strip()
    if val:
        return val

    env_path = BASE_DIR / ".env"
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


def _load_settings() -> dict[str, str]:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_settings(settings: dict[str, str]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def get_group_mode(chat_id: int) -> str:
    """Return 'admins' (default) or 'all' for a group chat."""
    mode = _load_settings().get(str(chat_id), "admins")
    return mode if mode in ("admins", "all") else "admins"


def set_group_mode(chat_id: int, mode: str) -> None:
    settings = _load_settings()
    settings[str(chat_id)] = mode
    _save_settings(settings)


def mode_keyboard(current_mode: str) -> InlineKeyboardMarkup:
    admins_label = "✓ Admins Only" if current_mode == "admins" else "Admins Only"
    all_label = "✓ Every User" if current_mode == "all" else "Every User"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(admins_label, callback_data="mode:admins"),
                InlineKeyboardButton(all_label, callback_data="mode:all"),
            ]
        ]
    )


async def bot_is_group_admin(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check whether the bot itself currently holds admin rights in the group."""
    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        return bot_member.status in (ChatMember.ADMINISTRATOR, ChatMember.OWNER)
    except Exception as exc:
        logger.warning("Failed to check bot admin status in %s: %s", chat_id, exc)
        return False


async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Allow group/supergroup admins (including anonymous admins) and configured ADMIN_USER_IDS."""
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    if not chat:
        return False

    if chat.type in ("group", "supergroup") and msg and msg.sender_chat:
        if msg.sender_chat.id == chat.id:
            return True

    if user and user.id in ADMIN_IDS:
        return True

    if chat.type in ("group", "supergroup") and user:
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


async def handle_my_chat_member(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Require group admin access when the bot is added to or updated in a group."""
    chat_member = update.my_chat_member
    if not chat_member:
        return

    chat = chat_member.chat
    if chat.type not in ("group", "supergroup"):
        return

    old_status = chat_member.old_chat_member.status
    new_status = chat_member.new_chat_member.status

    # Bot was just added as a regular member (without admin rights)
    if old_status in (ChatMember.LEFT, ChatMember.BANNED) and new_status == ChatMember.MEMBER:
        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                "Admin access required: Please promote me to Group Admin so I can "
                "translate English messages to Hindi in this group."
            ),
        )
    # Bot was promoted to Administrator
    elif old_status != ChatMember.ADMINISTRATOR and new_status == ChatMember.ADMINISTRATOR:
        mode = get_group_mode(chat.id)
        mode_text = "Every User" if mode == "all" else "Admins Only"
        await context.bot.send_message(
            chat_id=chat.id,
            text=(
                f"Admin access granted! English-to-Hindi translation is now active.\n"
                f"Current mode: {mode_text}\n"
                "Group admins can change who gets translated using /mode."
            ),
            reply_markup=mode_keyboard(mode),
        )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat or not update.message:
        return

    if chat.type in ("group", "supergroup"):
        if not await bot_is_group_admin(chat.id, context):
            await update.message.reply_text(
                "Admin access required: Please promote me to Group Admin to enable translations."
            )
            return
        if await is_user_admin(update, context):
            mode = get_group_mode(chat.id)
            mode_text = "Every User" if mode == "all" else "Admins Only"
            await update.message.reply_text(
                f"Namaste! Translation is active in this group (Mode: {mode_text}).\n"
                "Use /mode to switch between Admins Only and Every User."
            )
        return

    bot_username = context.bot.username or "TentierEngToHi_bot"
    add_group_url = f"https://t.me/{bot_username}?startgroup=true&admin=manage_chat"
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Add to Group as Admin", url=add_group_url)]]
    )
    await update.message.reply_text(
        "Namaste! I translate English messages to Hindi.\n\n"
        "How to use in a group:\n"
        "1. Tap 'Add to Group as Admin' below and grant Admin access.\n"
        "2. Group admins can run /mode to choose:\n"
        "   • Admins Only (default)\n"
        "   • Every User",
        reply_markup=keyboard,
    )


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user:
        await update.message.reply_text(f"Your Telegram User ID: {user.id}")


def mode_status_text(mode: str) -> str:
    if mode == "all":
        return (
            "Bot is set for Every User.\n"
            "All group members' English messages will be translated to Hindi."
        )
    return (
        "Bot is set for Admins Only.\n"
        "Only group admins' English messages will be translated to Hindi."
    )


async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allow group admins to choose between 'admins' only or 'all' users."""
    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await update.message.reply_text("The /mode setting is only for group chats.")
        return

    if not await is_user_admin(update, context):
        return

    if not await bot_is_group_admin(chat.id, context):
        await update.message.reply_text(
            "Please promote me to Group Admin first before configuring /mode."
        )
        return

    args = context.args or []
    if args:
        arg = args[0].strip().lower()
        if arg in ("all", "everyone", "every"):
            set_group_mode(chat.id, "all")
            await update.message.reply_text(
                mode_status_text("all"),
                reply_markup=mode_keyboard("all"),
            )
            return
        if arg in ("admin", "admins"):
            set_group_mode(chat.id, "admins")
            await update.message.reply_text(
                mode_status_text("admins"),
                reply_markup=mode_keyboard("admins"),
            )
            return

    current = get_group_mode(chat.id)
    await update.message.reply_text(
        f"{mode_status_text(current)}\n\nChoose who can use the translator:",
        reply_markup=mode_keyboard(current),
    )


async def mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return

    chat = update.effective_chat
    if not chat or chat.type not in ("group", "supergroup"):
        await query.answer()
        return

    if not await is_user_admin(update, context):
        await query.answer("Only group admins can change this setting.", show_alert=True)
        return

    if not await bot_is_group_admin(chat.id, context):
        await query.answer("Please promote the bot to Group Admin first.", show_alert=True)
        return

    new_mode = "all" if query.data == "mode:all" else "admins"
    set_group_mode(chat.id, new_mode)
    label = "Every User" if new_mode == "all" else "Admins Only"
    await query.answer(f"Bot is set for {label}")
    try:
        await query.edit_message_text(
            mode_status_text(new_mode),
            reply_markup=mode_keyboard(new_mode),
        )
    except BadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_user_admin(update, context):
        return
    await update.message.reply_text(
        "Send any English text to translate it to Hindi.\n"
        "In groups:\n"
        "- The bot must be promoted to Group Admin.\n"
        "- Use /mode to toggle between Admins Only and Every User.\n"
        "Commands: /start, /mode, /help, /myid"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat = update.effective_chat
    if not chat:
        return

    if chat.type in ("group", "supergroup"):
        # Bot must have admin access in the group to operate
        if not await bot_is_group_admin(chat.id, context):
            return

        mode = get_group_mode(chat.id)
        if mode == "admins" and not await is_user_admin(update, context):
            return
    else:
        if not await is_user_admin(update, context):
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
    app.add_handler(
        ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER)
    )
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("mode", mode_command))
    app.add_handler(CallbackQueryHandler(mode_callback, pattern="^mode:(admins|all)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("English-to-Hindi bot is running (polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
