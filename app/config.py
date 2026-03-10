# app/config.py
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Загружаем .env ДО чтения переменных — здесь, а не в каждом модуле отдельно
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")


class Settings:
    """
    Конфигурация читается из env при каждом обращении к атрибуту —
    это значит load_dotenv() гарантированно отработает раньше.
    """

    @property
    def db_host(self) -> str:
        return os.getenv("DB_HOST", "127.0.0.1")

    @property
    def db_port(self) -> int:
        return int(os.getenv("DB_PORT", "5432"))

    @property
    def db_name(self) -> str:
        return os.getenv("DB_NAME", "legal_digest")

    @property
    def db_user(self) -> str:
        return os.getenv("DB_USER", "legal_digest")

    @property
    def db_password(self) -> str:
        return os.getenv("DB_PASSWORD", "legal_digest_password")

    @property
    def tz(self) -> str:
        return os.getenv("TZ", "Europe/Moscow")

    @property
    def db_url(self) -> str:
        # Приоритет: DATABASE_URL (Neon/Railway/Heroku) > отдельные DB_* переменные
        url = os.getenv("DATABASE_URL")
        if url:
            return url
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def telegram_bot_token(self) -> str:
        v = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not v:
            raise EnvironmentError("TELEGRAM_BOT_TOKEN не задан в окружении")
        return v

    @property
    def telegram_chat_id(self) -> int:
        v = os.getenv("TELEGRAM_CHAT_ID", "")
        if not v:
            raise EnvironmentError("TELEGRAM_CHAT_ID не задан в окружении")
        try:
            return int(v)
        except ValueError:
            raise EnvironmentError(f"TELEGRAM_CHAT_ID должен быть числом, получено: {v!r}")

    def validate(self) -> None:
        """Вызови при старте приложения — упадёт сразу с понятной ошибкой."""
        _ = self.telegram_bot_token
        _ = self.telegram_chat_id
        _ = self.db_url


settings = Settings()