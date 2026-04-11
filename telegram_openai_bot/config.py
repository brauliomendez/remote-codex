from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    codex_command: str
    codex_base_args: list[str]
    codex_default_workdir: Path
    codex_allowed_roots: tuple[Path, ...]
    codex_model: str | None
    codex_sandbox: str
    codex_skip_git_repo_check: bool
    codex_enable_web_search: bool
    state_db_path: Path
    telegram_summary_word_limit: int


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_paths(value: str) -> tuple[Path, ...]:
    if not value.strip():
        return ()
    return tuple(Path(part).expanduser().resolve() for part in value.split(os.pathsep) if part.strip())


def load_settings() -> Settings:
    load_dotenv()

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    codex_command = os.getenv("CODEX_COMMAND", "codex").strip()
    codex_base_args = shlex.split(os.getenv("CODEX_BASE_ARGS", ""))
    default_workdir_raw = os.getenv("CODEX_DEFAULT_WORKDIR", "").strip() or os.getcwd()
    codex_default_workdir = Path(default_workdir_raw).expanduser().resolve()
    codex_allowed_roots = _split_paths(os.getenv("CODEX_ALLOWED_ROOTS", "").strip())
    codex_model = os.getenv("CODEX_MODEL", "").strip() or None
    codex_sandbox = os.getenv("CODEX_SANDBOX", "workspace-write").strip() or "workspace-write"
    codex_skip_git_repo_check = _get_bool("CODEX_SKIP_GIT_REPO_CHECK", default=True)
    codex_enable_web_search = _get_bool("CODEX_ENABLE_WEB_SEARCH", default=False)
    state_db_path = Path(
        os.getenv("STATE_DB_PATH", "data/telegram_codex_state.sqlite3").strip()
    ).expanduser()
    telegram_summary_word_limit = int(
        os.getenv("TELEGRAM_SUMMARY_WORD_LIMIT", "2000").strip()
    )

    missing = [
        name
        for name, value in (
            ("TELEGRAM_BOT_TOKEN", telegram_bot_token),
        )
        if not value
    ]
    if missing:
        missing_list = ", ".join(missing)
        raise RuntimeError(f"Missing required environment variables: {missing_list}")

    if not codex_default_workdir.is_dir():
        raise RuntimeError(f"CODEX_DEFAULT_WORKDIR is not a directory: {codex_default_workdir}")

    for root in codex_allowed_roots:
        if not root.is_dir():
            raise RuntimeError(f"CODEX_ALLOWED_ROOTS contains a non-directory path: {root}")

    return Settings(
        telegram_bot_token=telegram_bot_token,
        codex_command=codex_command,
        codex_base_args=codex_base_args,
        codex_default_workdir=codex_default_workdir,
        codex_allowed_roots=codex_allowed_roots,
        codex_model=codex_model,
        codex_sandbox=codex_sandbox,
        codex_skip_git_repo_check=codex_skip_git_repo_check,
        codex_enable_web_search=codex_enable_web_search,
        state_db_path=state_db_path,
        telegram_summary_word_limit=telegram_summary_word_limit,
    )
