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
- `ENABLE_CODEX_MCP`: set to `true` to expose Codex CLI as an MCP server to the agent
- `CODEX_MCP_COMMAND`: launcher command for the Codex MCP server, default `npx`
- `CODEX_MCP_ARGS`: arguments for the server command, default `-y codex mcp-server`
- `CODEX_MCP_CLIENT_TIMEOUT_SECONDS`: MCP client timeout in seconds
- `CODEX_MCP_DEFAULT_WORKDIR`: optional default directory the assistant should use when asking Codex to implement code

## Run

```bash
. .venv/bin/activate
python -m telegram_openai_bot
```

The bot uses long polling, so no webhook or Docker setup is required.
Conversation history is stored locally in SQLite under `data/agent_sessions.sqlite3`, with one session per Telegram chat.
The stored history is trimmed to the last 10 user turns, where one turn means one user message plus everything until the next user message.
If Codex MCP is enabled, the bot connects to a local Codex CLI MCP server during startup and disconnects on shutdown.

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

Codex MCP smoke test:

```bash
npx -y codex --version
```

## Validation

The local validation flow for this project is:

1. install dependencies in a virtual environment
2. run `python -m telegram_openai_bot --check-config`
3. run `python -m compileall telegram_openai_bot`
4. if Codex MCP is enabled, verify `npx -y codex --version`

End-to-end Telegram and OpenAI message validation requires real credentials in `.env`.

## Assumptions

- Telegram "bot credentials" means the bot token issued by BotFather.
- Text messages are the primary input. Non-text messages receive a short fallback reply.
- Each Telegram chat keeps its own conversation history in a local SQLite-backed session, trimmed to the last 10 user turns.
- Codex MCP is optional and requires Node.js plus a working `codex` CLI launch path.
