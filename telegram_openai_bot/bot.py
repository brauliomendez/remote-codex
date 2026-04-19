from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path
import re
import tempfile

from telegram import BotCommand, Update
from telegram.constants import ChatAction
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from .codex_bridge import CodexBridge, CodexEvent
from .config import Settings
from .state import ChatStateStore
from .telegram_format import split_plain_text_chunks

LOGGER = logging.getLogger(__name__)
WORD_RE = re.compile(r"\S+")


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
    lines = [
        f"Path actual: `{state.workdir}`",
        f"Thread actual: `{state.thread_id or 'nueva'}`",
        f"Modelo: `{settings.codex_model or 'default de Codex'}`",
        f"Sandbox: `{settings.codex_sandbox}`",
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

    prompt = extract_prompt(message)
    has_image = bool(message.photo) or is_image_document(message)
    if not prompt and not has_image:
        await message.reply_text("Puedo procesar texto e imagenes, pero este mensaje no contiene contenido util.")
        return

    chat_id = update.effective_chat.id
    lock = get_chat_lock(context.application, chat_id)
    async with lock:
        store = get_state_store(context.application)
        state = store.get_chat_state(chat_id)
        bridge: CodexBridge = context.application.bot_data["codex_bridge"]
        typing_task = asyncio.create_task(_send_typing(context, message.chat_id))
        progress_message = await message.reply_text("Codex trabajando...")
        progress = ProgressMessage(progress_message)
        try:
            async with download_message_images(message, context) as image_paths:
                result = await bridge.run(
                    prompt=prompt or "Analiza esta imagen y responde en espanol.",
                    workdir=state.workdir,
                    thread_id=state.thread_id,
                    image_paths=image_paths,
                    event_callback=progress.handle_event,
                )
            result = await maybe_summarize_result(
                bridge=bridge,
                result=result,
                settings=context.application.bot_data["settings"],
                workdir=state.workdir,
                progress=progress,
            )
            store.set_thread_id(chat_id, result.thread_id)
            await reply_streamed_result(progress, result.reply_text)
        except Exception as error:
            LOGGER.exception("Codex run failed")
            await message.reply_text(f"Error ejecutando Codex: {error}")
        finally:
            typing_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await typing_task


def get_state_store(application: Application) -> ChatStateStore:
    return application.bot_data["state_store"]


def extract_prompt(message) -> str:
    return (message.text or message.caption or "").strip()


def is_image_document(message) -> bool:
    document = message.document
    return bool(document and document.mime_type and document.mime_type.startswith("image/"))


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


@contextlib.asynccontextmanager
async def download_message_images(message, context: ContextTypes.DEFAULT_TYPE):
    image_refs = []
    if message.photo:
        largest = message.photo[-1]
        image_refs.append((largest.file_id, ".jpg"))
    elif is_image_document(message):
        suffix = Path(message.document.file_name or "image").suffix or guess_image_suffix(
            message.document.mime_type
        )
        image_refs.append((message.document.file_id, suffix))

    if not image_refs:
        yield []
        return

    with tempfile.TemporaryDirectory(prefix="telegram-codex-images-") as temp_dir:
        downloaded_paths: list[Path] = []
        for index, (file_id, suffix) in enumerate(image_refs, start=1):
            telegram_file = await context.bot.get_file(file_id)
            destination = Path(temp_dir) / f"image-{index}{suffix}"
            await telegram_file.download_to_drive(custom_path=destination)
            downloaded_paths.append(destination)
        yield downloaded_paths


class ProgressMessage:
    def __init__(self, message):
        self.message = message
        self.lines = ["Codex trabajando..."]
        self.last_render = ""

    async def handle_event(self, event: CodexEvent) -> None:
        if event.type == "turn_started":
            await self._push(event.text or "Codex pensando...")
            return
        if event.type == "command_started":
            await self._push(f"Ejecutando: {summarize_command(event.command)}")
            return
        if event.type == "command_completed":
            line = f"Comando completado ({event.exit_code}): {summarize_command(event.command)}"
            if event.exit_code not in (None, 0) and event.output:
                line = f"{line}\n{event.output.strip()[:300]}"
            await self._push(line)
            return
        if event.type == "agent_message" and event.text:
            await self._push(event.text)

    async def note(self, text: str) -> None:
        await self._push(text)

    async def set_final(self, text: str) -> None:
        await self._edit(text)

    async def _push(self, text: str) -> None:
        clean = text.strip()
        if not clean:
            return
        if self.lines and self.lines[-1] == clean:
            return
        self.lines.append(clean)
        self.lines = self.lines[-12:]
        await self._edit("\n\n".join(self.lines)[-3200:])

    async def _edit(self, text: str) -> None:
        if text == self.last_render:
            return
        try:
            await self.message.edit_text(text)
            self.last_render = text
        except Exception:
            LOGGER.exception("Telegram message edit failed")


async def reply_streamed_result(progress: ProgressMessage, text: str) -> None:
    chunks = split_plain_text_chunks(text)
    if not chunks:
        await progress.set_final("")
        return
    await progress.set_final(chunks[0])
    for chunk in chunks[1:]:
        await progress.message.reply_text(chunk)


async def maybe_summarize_result(
    bridge: CodexBridge,
    result,
    settings: Settings,
    workdir: Path,
    progress: ProgressMessage | None = None,
):
    if count_words(result.reply_text) <= settings.telegram_summary_word_limit:
        return result

    LOGGER.info(
        "Reply exceeded %s words, requesting condensed summary",
        settings.telegram_summary_word_limit,
    )
    if progress is not None:
        await progress.note("Respuesta larga detectada. Pidiendo resumen...")
    summary_prompt = (
        "Tu ultima respuesta fue demasiado larga para reenviarla completa a Telegram. "
        "Resume solo lo ultimo que has hecho en formato operativo y breve.\n\n"
        "Incluye unicamente estas secciones:\n"
        "- Objetivo\n"
        "- Acciones realizadas\n"
        "- Archivos o rutas relevantes\n"
        "- Estado final o siguiente paso\n\n"
        f"Limite duro: 400 palabras. Responde en espanol."
    )
    summary_result = await bridge.run(
        prompt=summary_prompt,
        workdir=workdir,
        thread_id=result.thread_id,
        event_callback=progress.handle_event if progress is not None else None,
    )
    prefix = (
        f"Respuesta original omitida por superar {settings.telegram_summary_word_limit} palabras.\n\n"
    )
    return type(summary_result)(
        thread_id=summary_result.thread_id,
        reply_text=prefix + summary_result.reply_text.strip(),
    )


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def summarize_command(command: str | None) -> str:
    if not command:
        return "comando"
    single_line = " ".join(command.split())
    if len(single_line) <= 120:
        return single_line
    return f"{single_line[:117]}..."


def guess_image_suffix(mime_type: str | None) -> str:
    if mime_type == "image/png":
        return ".png"
    if mime_type == "image/webp":
        return ".webp"
    if mime_type == "image/gif":
        return ".gif"
    return ".jpg"


def validate_workdir(raw_path: str, current_workdir: Path) -> Path:
    path = Path(raw_path).expanduser()
    candidate = (current_workdir / path).resolve() if not path.is_absolute() else path.resolve()
    if not candidate.is_dir():
        raise ValueError(f"El path no existe o no es un directorio: {candidate}")
    return candidate


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
    application.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.Document.IMAGE) & ~filters.COMMAND,
            handle_message,
        )
    )
    return application
