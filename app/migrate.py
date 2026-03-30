# app/migrate.py
from __future__ import annotations

import os

from sqlalchemy import text
from app.db import engine, Base
from app import models  # noqa: F401  (нужно для регистрации моделей)


def _env_on(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    """
    По умолчанию: create_all() (не меняет существующую схему).
    Если RESET_DB=1: drop_all() + create_all() (полный reset схемы).
    """
    if _env_on("RESET_DB"):
        print("DB: RESET_DB=1 -> dropping all tables...")
        Base.metadata.drop_all(bind=engine)

    Base.metadata.create_all(bind=engine)
    print("DB: tables created/checked")

    # Добавляем новые колонки если их нет (идемпотентно)
    with engine.connect() as conn:
        for col, coldef in [
            ("llm_reason", "TEXT"),
        ]:
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='articles' AND column_name=:col"
            ), {"col": col}).fetchone()
            if not exists:
                conn.execute(text(f"ALTER TABLE articles ADD COLUMN {col} {coldef}"))
                conn.commit()
                print(f"DB: добавлена колонка {col}")


if __name__ == "__main__":
    main()