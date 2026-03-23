from __future__ import annotations

import argparse
import logging

from .bot import build_application
from .config import load_settings


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

    settings = load_settings()

    if args.check_config:
        print("Configuration looks valid.")
        print(f"OPENAI_MODEL={settings.openai_model}")
        return

    application = build_application(settings)
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
