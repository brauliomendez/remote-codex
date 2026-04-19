from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from .config import Settings

LOGGER = logging.getLogger(__name__)
CODEX_STREAM_LIMIT_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class CodexResult:
    thread_id: str
    reply_text: str


@dataclass(frozen=True)
class CodexEvent:
    type: str
    text: str | None = None
    command: str | None = None
    exit_code: int | None = None
    output: str | None = None


EventCallback = Callable[[CodexEvent], Awaitable[None]]


class CodexBridge:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def run(
        self,
        prompt: str,
        workdir: Path,
        thread_id: str | None,
        image_paths: list[Path] | None = None,
        event_callback: EventCallback | None = None,
    ) -> CodexResult:
        command = self._build_command(workdir=workdir, thread_id=thread_id, image_paths=image_paths or [])
        LOGGER.info("Running Codex in %s", workdir)
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(workdir),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=CODEX_STREAM_LIMIT_BYTES,
        )

        assert process.stdin is not None
        process.stdin.write(prompt.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()

        assert process.stdout is not None
        assert process.stderr is not None

        captured_thread_id = thread_id
        agent_messages: list[str] = []

        async def read_stdout() -> None:
            nonlocal captured_thread_id
            while True:
                raw_line = await process.stdout.readline()
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    LOGGER.warning("Ignoring non-JSON Codex output: %s", line)
                    continue
                event_type = event.get("type")
                if event_type == "thread.started":
                    captured_thread_id = event.get("thread_id") or captured_thread_id
                    continue
                if event_type == "turn.started":
                    await self._emit(
                        event_callback,
                        CodexEvent(type="turn_started", text="Codex pensando..."),
                    )
                    continue
                if event_type == "item.started":
                    item = event.get("item") or {}
                    if item.get("type") == "command_execution":
                        await self._emit(
                            event_callback,
                            CodexEvent(
                                type="command_started",
                                command=item.get("command"),
                            ),
                        )
                    continue
                if event_type != "item.completed":
                    continue
                item = event.get("item") or {}
                if item.get("type") == "command_execution":
                    await self._emit(
                        event_callback,
                        CodexEvent(
                            type="command_completed",
                            command=item.get("command"),
                            exit_code=item.get("exit_code"),
                            output=item.get("aggregated_output"),
                        ),
                    )
                    continue
                if item.get("type") != "agent_message":
                    continue
                text = (item.get("text") or "").strip()
                if text:
                    agent_messages.append(text)
                    await self._emit(
                        event_callback,
                        CodexEvent(type="agent_message", text=text),
                    )

        stderr_chunks: list[str] = []

        async def read_stderr() -> None:
            while True:
                raw_line = await process.stderr.readline()
                if not raw_line:
                    break
                stderr_chunks.append(raw_line.decode("utf-8", errors="replace"))

        await asyncio.gather(read_stdout(), read_stderr())
        return_code = await process.wait()

        stderr_text = "".join(stderr_chunks).strip()
        if return_code != 0:
            raise RuntimeError(stderr_text or f"Codex exited with status {return_code}")

        if not captured_thread_id:
            raise RuntimeError("Codex did not return a thread id.")

        reply_text = agent_messages[-1].strip() if agent_messages else ""
        if not reply_text:
            if stderr_text:
                reply_text = stderr_text
            else:
                raise RuntimeError("Codex finished without a final assistant message.")

        return CodexResult(thread_id=captured_thread_id, reply_text=reply_text)

    async def _emit(self, callback: EventCallback | None, event: CodexEvent) -> None:
        if callback is None:
            return
        try:
            await callback(event)
        except Exception:
            LOGGER.exception("Codex event callback failed")

    def _build_command(
        self,
        workdir: Path,
        thread_id: str | None,
        image_paths: list[Path],
    ) -> list[str]:
        command = [self.settings.codex_command, *self.settings.codex_base_args, "exec"]
        if thread_id:
            command.extend(["resume", "--json"])
            if self.settings.codex_skip_git_repo_check:
                command.append("--skip-git-repo-check")
            if self.settings.codex_model:
                command.extend(["--model", self.settings.codex_model])
            for image_path in image_paths:
                command.extend(["-i", str(image_path)])
            command.extend([thread_id, "-"])
            return command

        command.extend(["--json", "--cd", str(workdir), "--sandbox", self.settings.codex_sandbox])
        if self.settings.codex_skip_git_repo_check:
            command.append("--skip-git-repo-check")
        if self.settings.codex_enable_web_search:
            command.append("--search")
        if self.settings.codex_model:
            command.extend(["--model", self.settings.codex_model])
        for image_path in image_paths:
            command.extend(["--image", str(image_path)])
        command.append("-")
        return command
