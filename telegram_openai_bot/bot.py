from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from telegram import BotCommand, Update
from telegram.constants import ChatAction
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from .codex_bridge import CodexBridge
from .config import Settings
from .state import ChatStateStore

LOGGER = logging.getLogger(__name__)

MAX_TELEGRAM_MESSAGE_LENGTH = 4000


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    state = get_state_store(context.application).get_chat_state(update.effective_chat.id)
    await message.reply_text(
        "\n".join(
            [
                "Este bot reenvia tus mensajes directamente a Codex CLI.",
                f"Path actual: `{state.workdir}`",
                f"Sesion actual: `{state.thread_id or 'nueva'}`",
                "Comandos: /path, /status, /new, /reset, /sessions, /resume",
            ]
        ),
        parse_mode="Markdown",
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    chat_id = update.effective_chat.id
    state = get_state_store(context.application).clear_chat_history(chat_id)
    await message.reply_text(
        f"Sesion actual e historial borrados para este chat. Path actual: `{state.workdir}`",
        parse_mode="Markdown",
    )


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    chat_id = update.effective_chat.id
    state = get_state_store(context.application).reset_chat(chat_id)
    await message.reply_text(
        f"Sesion de Codex desvinculada. El historial sigue disponible con /sessions. Path actual: `{state.workdir}`",
        parse_mode="Markdown",
    )


async def path_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    store = get_state_store(context.application)
    chat_id = update.effective_chat.id
    current_state = store.get_chat_state(chat_id)
    requested_path = " ".join(context.args).strip()

    if not requested_path:
        state = store.get_chat_state(chat_id)
        await message.reply_text(f"Path actual: `{state.workdir}`", parse_mode="Markdown")
        return

    try:
        workdir = validate_workdir(
            raw_path=requested_path,
            current_workdir=current_state.workdir,
            settings=context.application.bot_data["settings"],
        )
    except ValueError as error:
        await message.reply_text(str(error))
        return

    state = store.set_workdir(chat_id, workdir)
    await message.reply_text(
        "\n".join(
            [
                f"Path actualizado a `{state.workdir}`",
                f"Sesion actual: `{state.thread_id or 'nueva'}`",
            ]
        ),
        parse_mode="Markdown",
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    settings: Settings = context.application.bot_data["settings"]
    state = get_state_store(context.application).get_chat_state(update.effective_chat.id)
    roots = ", ".join(f"`{root}`" for root in settings.codex_allowed_roots) or "`sin restriccion`"
    lines = [
        f"Path actual: `{state.workdir}`",
        f"Thread actual: `{state.thread_id or 'nueva'}`",
        f"Modelo: `{settings.codex_model or 'default de Codex'}`",
        f"Sandbox: `{settings.codex_sandbox}`",
        f"Roots permitidos: {roots}",
    ]
    await message.reply_text("\n".join(lines), parse_mode="Markdown")


async def sessions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return
    chat_id = update.effective_chat.id
    store = get_state_store(context.application)
    current_state = store.get_chat_state(chat_id)
    sessions = store.list_chat_sessions(chat_id, limit=10)
    if not sessions:
        await message.reply_text("No hay sesiones guardadas para este chat.")
        return

    lines = ["Sesiones recientes:"]
    for index, session in enumerate(sessions, start=1):
        current_marker = " actual" if session.thread_id == current_state.thread_id else ""
        lines.append(
            f"{index}. {session.thread_id}{current_marker}\n"
            f"   path: {session.workdir}\n"
            f"   uso: {session.last_used_at}"
        )
    await message.reply_text("\n".join(lines))


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    chat_id = update.effective_chat.id
    store = get_state_store(context.application)
    selector = " ".join(context.args).strip()
    if not selector:
        await message.reply_text("Usa `/resume <numero|thread_id>`", parse_mode="Markdown")
        return

    sessions = store.list_chat_sessions(chat_id, limit=20)
    if not sessions:
        await message.reply_text("No hay sesiones guardadas para retomar.")
        return

    thread_id = selector
    if selector.isdigit():
        index = int(selector)
        if index < 1 or index > len(sessions):
            await message.reply_text(f"No existe la sesion {index}. Usa /sessions para ver la lista.")
            return
        thread_id = sessions[index - 1].thread_id

    try:
        state = store.resume_session(chat_id, thread_id)
    except KeyError:
        await message.reply_text("Ese thread_id no existe en el historial de este chat.")
        return

    await message.reply_text(
        "\n".join(
            [
                f"Sesion reanudada: `{state.thread_id}`",
                f"Path restaurado: `{state.workdir}`",
            ]
        ),
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    text = (message.text or "").strip()
    if not text:
        await message.reply_text("I can only process text messages right now.")
        return

    chat_id = update.effective_chat.id
    lock = get_chat_lock(context.application, chat_id)
    async with lock:
        store = get_state_store(context.application)
        state = store.get_chat_state(chat_id)
        bridge: CodexBridge = context.application.bot_data["codex_bridge"]
        typing_task = asyncio.create_task(_send_typing(context, message.chat_id))
        try:
            result = await bridge.run(prompt=text, workdir=state.workdir, thread_id=state.thread_id)
            store.set_thread_id(chat_id, result.thread_id)
            await reply_long_message(message, result.reply_text)
        except Exception as error:
            LOGGER.exception("Codex run failed")
            await message.reply_text(f"Error ejecutando Codex: {error}")
        finally:
            typing_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await typing_task


def get_state_store(application: Application) -> ChatStateStore:
    return application.bot_data["state_store"]


def get_chat_lock(application: Application, chat_id: int) -> asyncio.Lock:
    locks: dict[int, asyncio.Lock] = application.bot_data["chat_locks"]
    lock = locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        locks[chat_id] = lock
    return lock


async def _send_typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    while True:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await asyncio.sleep(4)


async def reply_long_message(message, text: str) -> None:
    chunks = split_message(text)
    for chunk in chunks:
        await message.reply_text(chunk)


def split_message(text: str) -> list[str]:
    stripped = text.strip()
    if len(stripped) <= MAX_TELEGRAM_MESSAGE_LENGTH:
        return [stripped]
    chunks: list[str] = []
    remaining = stripped
    while remaining:
        if len(remaining) <= MAX_TELEGRAM_MESSAGE_LENGTH:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, MAX_TELEGRAM_MESSAGE_LENGTH)
        if split_at <= 0:
            split_at = MAX_TELEGRAM_MESSAGE_LENGTH
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return chunks


def validate_workdir(raw_path: str, current_workdir: Path, settings: Settings) -> Path:
    path = Path(raw_path).expanduser()
    candidate = (current_workdir / path).resolve() if not path.is_absolute() else path.resolve()
    if not candidate.is_dir():
        raise ValueError(f"El path no existe o no es un directorio: {candidate}")
    if not settings.codex_allowed_roots:
        return candidate
    for root in settings.codex_allowed_roots:
        if candidate == root or root in candidate.parents:
            return candidate
    allowed = ", ".join(str(root) for root in settings.codex_allowed_roots)
    raise ValueError(f"Path fuera de los roots permitidos: {allowed}")


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Show usage and current path"),
            BotCommand("path", "Show or change the working directory"),
            BotCommand("status", "Show current Codex session state"),
            BotCommand("new", "Start a new conversation and keep history"),
            BotCommand("sessions", "List recent Codex conversations"),
            BotCommand("resume", "Resume a previous Codex conversation"),
            BotCommand("reset", "Clear current conversation and session history"),
        ]
    )


def build_application(settings: Settings) -> Application:
    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["codex_bridge"] = CodexBridge(settings)
    application.bot_data["state_store"] = ChatStateStore(
        db_path=settings.state_db_path,
        default_workdir=settings.codex_default_workdir,
    )
    application.bot_data["chat_locks"] = {}
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("new", new_command))
    application.add_handler(CommandHandler("path", path_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("sessions", sessions_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application
