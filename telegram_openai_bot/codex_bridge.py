from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .config import Settings

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CodexResult:
    thread_id: str
    reply_text: str


class CodexBridge:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def run(self, prompt: str, workdir: Path, thread_id: str | None) -> CodexResult:
        command = self._build_command(workdir=workdir, thread_id=thread_id)
        LOGGER.info("Running Codex in %s", workdir)
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(workdir),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
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
                if event_type != "item.completed":
                    continue
                item = event.get("item") or {}
                if item.get("type") != "agent_message":
                    continue
                text = (item.get("text") or "").strip()
                if text:
                    agent_messages.append(text)

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

        reply_text = "\n\n".join(agent_messages).strip()
        if not reply_text:
            if stderr_text:
                reply_text = stderr_text
            else:
                raise RuntimeError("Codex finished without a final assistant message.")

        return CodexResult(thread_id=captured_thread_id, reply_text=reply_text)

    def _build_command(self, workdir: Path, thread_id: str | None) -> list[str]:
        command = [self.settings.codex_command, *self.settings.codex_base_args, "exec"]
        if thread_id:
            command.extend(["resume", "--json"])
            if self.settings.codex_skip_git_repo_check:
                command.append("--skip-git-repo-check")
            if self.settings.codex_model:
                command.extend(["--model", self.settings.codex_model])
            command.extend([thread_id, "-"])
            return command

        command.extend(["--json", "--cd", str(workdir), "--sandbox", self.settings.codex_sandbox])
        if self.settings.codex_skip_git_repo_check:
            command.append("--skip-git-repo-check")
        if self.settings.codex_enable_web_search:
            command.append("--search")
        if self.settings.codex_model:
            command.extend(["--model", self.settings.codex_model])
        command.append("-")
        return command
