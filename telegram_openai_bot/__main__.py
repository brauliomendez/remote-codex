from __future__ import annotations

import argparse
import logging

from .bot import build_application
from .config import load_settings


class SuppressCodexMcpNotificationWarnings(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "Failed to validate notification" not in message:
            return True
        return "input_value='codex/event'" not in message


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Telegram OpenAI agent bot.")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate the .env configuration and exit.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    warning_filter = SuppressCodexMcpNotificationWarnings()
    for handler in logging.getLogger().handlers:
        handler.addFilter(warning_filter)

    settings = load_settings()

    if args.check_config:
        print("Configuration looks valid.")
        print(f"OPENAI_MODEL={settings.openai_model}")
        print(f"ENABLE_CODEX_MCP={settings.enable_codex_mcp}")
        if settings.enable_codex_mcp:
            print(f"CODEX_MCP_COMMAND={settings.codex_mcp_command}")
            print(f"CODEX_MCP_ARGS={' '.join(settings.codex_mcp_args)}")
            print(f"CODEX_MCP_DEFAULT_WORKDIR={settings.codex_mcp_default_workdir or ''}")
        return

    application = build_application(settings)
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
