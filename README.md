# Telegram Codex Bridge

Python Telegram bot that forwards text and image messages directly to Codex CLI.

It does not use `openai-agents`, does not expose Codex through MCP, and does not keep a parallel conversation memory inside the bot. Conversation continuity is handled by Codex itself: each Telegram chat is linked to a Codex `thread_id`, and the next message uses `codex exec resume`.

## What It Does

- Forwards Telegram messages to `codex exec`
- Accepts one image with an optional caption and sends it to Codex as multimodal input
- Sends generated image outputs back to Telegram when Codex creates or edits raster assets
- Resumes the same Codex conversation for each Telegram chat
- Stores the per-chat `thread_id` and `workdir` in SQLite
- Lets you change the working directory with `/path`
- Lets you cut the current conversation with `/new` or `/reset`
- Lists recent sessions with `/sessions`
- Lets you resume a previous session with `/resume`

## Commands

- `/start`: shows quick help and the current state
- `/path`: shows the current working directory
- `/path <path>`: changes the working directory for that chat and starts a new session
- `/status`: shows `workdir`, `thread_id`, model, and sandbox
- `/sessions`: lists recent sessions stored for that chat
- `/resume <number|thread_id>`: resumes a previous session and restores its `workdir`
- `/new`: clears the current `thread_id` link but keeps session history for `/resume`
- `/reset`: clears the current `thread_id` link and deletes the session history stored by the bot for that chat

## Quick Start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m telegram_openai_bot --check-config
python -m telegram_openai_bot
```

## Requirements

- Python 3.12
- `python-telegram-bot`
- `python-dotenv`
- `codex` installed and authenticated on the machine

Minimum check:

```bash
codex --version
codex exec --help
```

## Configuration

Variables in `.env`:

- `TELEGRAM_BOT_TOKEN`: Telegram bot token
- `CODEX_COMMAND`: binary to run, default `codex`
- `CODEX_BASE_ARGS`: optional base arguments before `exec`
- `CODEX_DEFAULT_WORKDIR`: default initial directory for new chats
- `CODEX_MODEL`: optional model passed to Codex
- `CODEX_SANDBOX`: Codex sandbox mode, default `workspace-write`
- `CODEX_SKIP_GIT_REPO_CHECK`: defaults to `true`
- `CODEX_ENABLE_WEB_SEARCH`: enables `--search` in Codex
- `STATE_DB_PATH`: path to the bot's SQLite database
- `TELEGRAM_SUMMARY_WORD_LIMIT`: if a response exceeds this number of words, the bot asks Codex for a short summary before forwarding it

## How Continuity Works

1. The first message in a chat runs `codex exec`
2. Codex returns a `thread_id`
3. The bot stores that `thread_id`
4. The next message uses `codex exec resume <thread_id>`

If you change the path with `/path`, the bot cuts the current session so Codex context is not mixed across different repositories or directories.
Previous sessions remain stored in the chat history and can be recovered with `/sessions` and `/resume`.

## State Files

- Bot SQLite database: `data/telegram_codex_state.sqlite3`
- Internal Codex sessions: managed by the CLI itself in `~/.codex/`

## Local Validation

```bash
python -m telegram_openai_bot --check-config
python -m compileall telegram_openai_bot
```

End-to-end validation requires real Telegram credentials and a working Codex CLI installation.

## systemd Service

```bash
sudo cp deploy/systemd/telegram-openai-bot.service /etc/systemd/system/telegram-openai-bot.service
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-openai-bot
sudo systemctl status telegram-openai-bot
```

Logs:

```bash
journalctl -u telegram-openai-bot -f
```
