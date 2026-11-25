# Telegram English-to-Hindi Translator Bot (Admin-Only)

Free English -> Hindi Telegram bot using `python-telegram-bot` and `deep-translator` (with MyMemory fallback).

## Setup & Run

1. Get a bot token from `@BotFather` on Telegram.
2. Create `.env` from `.env.example` and paste your token:
   ```bash
   cp .env.example .env
   ```
3. Add your numeric Telegram User ID(s) to `ADMIN_USER_IDS` in `.env` (comma-separated).
   - You can message `/myid` to the bot to see your numeric User ID.
   - In groups/supergroups, Telegram group admins (`OWNER` / `ADMINISTRATOR`) are also allowed automatically.
4. Start the bot:
   ```bash
   .venv/bin/python bot.py
   ```
