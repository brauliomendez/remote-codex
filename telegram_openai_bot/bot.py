from __future__ import annotations

import logging
import os
from pathlib import Path

from agents import Agent, Runner
from agents.mcp import MCPServerStdio
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from .config import Settings
from .session import TurnLimitedSession

LOGGER = logging.getLogger(__name__)
SESSION_DB_PATH = Path("data/agent_sessions.sqlite3")
MAX_SESSION_TURNS = 10


def build_agent(settings: Settings) -> Agent:
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    instructions = [
        "You are a concise and helpful Telegram assistant.",
        "Answer directly, keep formatting simple, and ask for clarification only when needed.",
    ]
    mcp_servers = []
    codex_server = build_codex_mcp_server(settings)
    if codex_server is not None:
        mcp_servers.append(codex_server)
        instructions.append(
            "When the user asks you to write code, edit files, inspect a codebase, run shell "
            "commands, or implement features, use the Codex MCP tools instead of only "
            "describing what to do."
        )
        if settings.codex_mcp_default_workdir:
            instructions.append(
                "When using Codex for implementation and the user does not specify a directory, "
                f"use `{settings.codex_mcp_default_workdir}` as the default working directory."
            )
    return Agent(
        name="Telegram Assistant",
        instructions=" ".join(instructions),
        model=settings.openai_model,
        mcp_servers=mcp_servers,
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if update.message is None:
        return
    await update.message.reply_text(
        "Send me a text message and I will reply using the configured OpenAI agent."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    text = (message.text or "").strip()
    if not text:
        await message.reply_text("I can only process text messages right now.")
        return

    agent: Agent = context.application.bot_data["agent"]
    session = get_session(context.application, update.effective_chat.id)

    await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")

    try:
        result = await Runner.run(
            agent,
            text,
            session=session,
        )
        reply_text = str(result.final_output).strip()
        if not reply_text:
            reply_text = "I could not generate a reply for that message."
    except Exception:
        LOGGER.exception("OpenAI agent run failed")
        reply_text = "I hit an internal error while processing your message."

    await message.reply_text(reply_text)


def get_session(application: Application, chat_id: int) -> TurnLimitedSession:
    sessions: dict[int, TurnLimitedSession] = application.bot_data["sessions"]
    session = sessions.get(chat_id)
    if session is None:
        SESSION_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        session = TurnLimitedSession(
            session_id=f"telegram-chat-{chat_id}",
            db_path=SESSION_DB_PATH,
            max_turns=MAX_SESSION_TURNS,
        )
        sessions[chat_id] = session
    return session


def build_codex_mcp_server(settings: Settings) -> MCPServerStdio | None:
    if not settings.enable_codex_mcp:
        return None

    return MCPServerStdio(
        name="Codex CLI",
        params={
            "command": settings.codex_mcp_command,
            "args": settings.codex_mcp_args,
        },
        client_session_timeout_seconds=settings.codex_mcp_client_timeout_seconds,
    )


async def post_init(application: Application) -> None:
    codex_server: MCPServerStdio | None = application.bot_data.get("codex_server")
    if codex_server is None:
        return
    LOGGER.info("Connecting Codex MCP server")
    await codex_server.connect()


async def post_shutdown(application: Application) -> None:
    codex_server: MCPServerStdio | None = application.bot_data.get("codex_server")
    if codex_server is None:
        return
    LOGGER.info("Cleaning up Codex MCP server")
    await codex_server.cleanup()


def build_application(settings: Settings) -> Application:
    agent = build_agent(settings)
    codex_server = agent.mcp_servers[0] if agent.mcp_servers else None

    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data["agent"] = agent
    application.bot_data["codex_server"] = codex_server
    application.bot_data["sessions"] = {}
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application
