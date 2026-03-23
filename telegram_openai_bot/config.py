from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    telegram_bot_token: str


def load_settings() -> Settings:
    load_dotenv()

    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    openai_model = os.getenv("OPENAI_MODEL", "").strip()
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

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
    )
