from __future__ import annotations

import argparse
import logging

from .bot import build_application
from .config import load_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Telegram Codex bridge bot.")
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

    settings = load_settings()

    if args.check_config:
        print("Configuration looks valid.")
        print(f"CODEX_COMMAND={settings.codex_command}")
        print(f"CODEX_BASE_ARGS={' '.join(settings.codex_base_args)}")
        print(f"CODEX_DEFAULT_WORKDIR={settings.codex_default_workdir}")
        print(f"CODEX_MODEL={settings.codex_model or ''}")
        print(f"CODEX_SANDBOX={settings.codex_sandbox}")
        print(f"CODEX_SKIP_GIT_REPO_CHECK={settings.codex_skip_git_repo_check}")
        print(f"CODEX_ENABLE_WEB_SEARCH={settings.codex_enable_web_search}")
        print(f"STATE_DB_PATH={settings.state_db_path}")
        print(f"TELEGRAM_SUMMARY_WORD_LIMIT={settings.telegram_summary_word_limit}")
        return

    application = build_application(settings)
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
