# Telegram OpenAI Agent Bot

Minimal Python Telegram bot that forwards chat messages to an OpenAI Agent using the OpenAI Agents SDK.

## Quick start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m telegram_openai_bot --check-config
python -m telegram_openai_bot
```

## Stack

- Python 3.12
- `openai-agents` for the agent runtime
- `python-telegram-bot` for Telegram polling
- `python-dotenv` for `.env` loading

## Configuration

Set these values in `.env`:

- `OPENAI_API_KEY`: your OpenAI API key
- `OPENAI_MODEL`: the model name to use. Default example is `gpt-5.4-nano`
- `TELEGRAM_BOT_TOKEN`: your Telegram bot token from BotFather

## Run

```bash
. .venv/bin/activate
python -m telegram_openai_bot
```

The bot uses long polling, so no webhook or Docker setup is required.

## Development commands

Install dependencies:

```bash
pip install -r requirements.txt
```

Validate configuration without starting polling:

```bash
python -m telegram_openai_bot --check-config
```

Basic syntax/import validation:

```bash
python -m compileall telegram_openai_bot
```

## Validation

The local validation flow for this project is:

1. install dependencies in a virtual environment
2. run `python -m telegram_openai_bot --check-config`
3. run `python -m compileall telegram_openai_bot`

End-to-end Telegram and OpenAI message validation requires real credentials in `.env`.

## Assumptions

- Telegram "bot credentials" means the bot token issued by BotFather.
- Text messages are the primary input. Non-text messages receive a short fallback reply.
- Each Telegram chat keeps its own conversation thread through a stable OpenAI `conversation_id`.
