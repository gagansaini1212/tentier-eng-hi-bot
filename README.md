# Telegram English-to-Hindi Translator Bot

Free English -> Hindi Telegram bot using `python-telegram-bot` and `deep-translator` (with MyMemory fallback).

## Group Behavior
- **Bot Admin Required:** When added to a group, the bot stays inactive until promoted to **Group Admin**.
- **Per-Group Mode (`/mode`):** Once promoted, group admins can toggle whether the bot translates for **Admins Only** (default) or **Every User** using `/mode` (inline buttons or `/mode all` / `/mode admins`).

## Setup & Run

1. Get a bot token from `@BotFather` on Telegram.
2. Create `.env` from `.env.example` and paste your token:
   ```bash
   cp .env.example .env
   ```
3. *(Optional)* Add your numeric Telegram User ID(s) to `ADMIN_USER_IDS` in `.env` for private DM usage.
4. Start the bot:
   ```bash
   .venv/bin/python bot.py
   ```
