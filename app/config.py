from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")


def env_on(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int = 0) -> int:
    value = (os.getenv(name, "") or "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


class Settings:
    @property
    def db_host(self) -> str:
        return os.getenv("DB_HOST", "127.0.0.1")

    @property
    def db_port(self) -> int:
        return env_int("DB_PORT", 5432)

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
    def digest_tz(self) -> str:
        return os.getenv("DIGEST_TZ", self.tz)

    @property
    def web_host(self) -> str:
        return os.getenv("WEB_HOST", "0.0.0.0")

    @property
    def web_port(self) -> int:
        return env_int("WEB_PORT", 8002)

    @property
    def gigachat_auth_key(self) -> str:
        value = os.getenv("GIGACHAT_AUTH_KEY", "").strip()
        if not value:
            raise EnvironmentError("GIGACHAT_AUTH_KEY не задан — добавь в .env")
        return value

    @property
    def db_url(self) -> str:
        url = os.getenv("DATABASE_URL")
        if url:
            return url
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def telegram_bot_token(self) -> str:
        value = os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not value:
            raise EnvironmentError("TELEGRAM_BOT_TOKEN не задан в окружении")
        return value

    @property
    def telegram_chat_id(self) -> int:
        value = os.getenv("TELEGRAM_CHAT_ID", "")
        if not value:
            raise EnvironmentError("TELEGRAM_CHAT_ID не задан в окружении")
        try:
            return int(value)
        except ValueError as exc:
            raise EnvironmentError(
                f"TELEGRAM_CHAT_ID должен быть числом, получено: {value!r}"
            ) from exc

    def validate_runtime(self) -> None:
        _ = self.db_url
        _ = self.gigachat_auth_key
        _ = self.telegram_bot_token
        _ = self.telegram_chat_id


settings = Settings()
configure_logging()
