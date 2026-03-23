from __future__ import annotations

import logging
import os

from agents import Agent, Runner
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from .config import Settings

LOGGER = logging.getLogger(__name__)


def build_agent(settings: Settings) -> Agent:
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
    return Agent(
        name="Telegram Assistant",
        instructions=(
            "You are a concise and helpful Telegram assistant. "
            "Answer directly, keep formatting simple, and ask for clarification only when needed."
        ),
        model=settings.openai_model,
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
    conversation_id = f"telegram-chat-{update.effective_chat.id}"

    await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")

    try:
        result = await Runner.run(
            agent,
            text,
            conversation_id=conversation_id,
        )
        reply_text = str(result.final_output).strip()
        if not reply_text:
            reply_text = "I could not generate a reply for that message."
    except Exception:
        LOGGER.exception("OpenAI agent run failed")
        reply_text = "I hit an internal error while processing your message."

    await message.reply_text(reply_text)


def build_application(settings: Settings) -> Application:
    application = ApplicationBuilder().token(settings.telegram_bot_token).build()
    application.bot_data["agent"] = build_agent(settings)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application
