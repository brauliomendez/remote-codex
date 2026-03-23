from __future__ import annotations

import os
import shlex
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    telegram_bot_token: str
    enable_codex_mcp: bool
    codex_mcp_command: str
    codex_mcp_args: list[str]
    codex_mcp_client_timeout_seconds: float
    codex_mcp_server_cwd: str | None
    codex_mcp_default_workdir: str | None


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    load_dotenv()

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    openai_model = os.getenv("OPENAI_MODEL", "").strip()
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    enable_codex_mcp = _get_bool("ENABLE_CODEX_MCP", default=False)
    codex_mcp_command = os.getenv("CODEX_MCP_COMMAND", "npx").strip()
    codex_mcp_args = shlex.split(os.getenv("CODEX_MCP_ARGS", "-y codex mcp-server"))
    codex_mcp_client_timeout_seconds = float(
        os.getenv("CODEX_MCP_CLIENT_TIMEOUT_SECONDS", "360000").strip()
    )
    codex_mcp_server_cwd = os.getenv("CODEX_MCP_SERVER_CWD", "").strip() or None
    codex_mcp_default_workdir = os.getenv("CODEX_MCP_DEFAULT_WORKDIR", "").strip() or None

    missing = [
        name
        for name, value in (
            ("OPENAI_API_KEY", openai_api_key),
            ("OPENAI_MODEL", openai_model),
            ("TELEGRAM_BOT_TOKEN", telegram_bot_token),
        )
        if not value
    ]
    if missing:
        missing_list = ", ".join(missing)
        raise RuntimeError(f"Missing required environment variables: {missing_list}")

    return Settings(
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        telegram_bot_token=telegram_bot_token,
        enable_codex_mcp=enable_codex_mcp,
        codex_mcp_command=codex_mcp_command,
        codex_mcp_args=codex_mcp_args,
        codex_mcp_client_timeout_seconds=codex_mcp_client_timeout_seconds,
        codex_mcp_server_cwd=codex_mcp_server_cwd,
        codex_mcp_default_workdir=codex_mcp_default_workdir,
    )
