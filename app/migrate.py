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
            ("fetch_error", "TEXT"),
            ("classify_error", "TEXT"),
            ("processing_status", "VARCHAR(32) DEFAULT 'new'"),
            ("decision_source", "VARCHAR(32)"),
            ("last_processed_at", "TIMESTAMP WITH TIME ZONE"),
        ]:
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='articles' AND column_name=:col"
            ), {"col": col}).fetchone()
            if not exists:
                conn.execute(text(f"ALTER TABLE articles ADD COLUMN {col} {coldef}"))
                conn.commit()
                print(f"DB: добавлена колонка {col}")

        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS article_reviews (
                id BIGSERIAL PRIMARY KEY,
                article_id BIGINT NOT NULL,
                action VARCHAR(32) NOT NULL,
                review_scope VARCHAR(16) NOT NULL,
                previous_keep BOOLEAN NULL,
                new_keep BOOLEAN NULL,
                previous_event_type VARCHAR(32) NULL,
                new_event_type VARCHAR(32) NULL,
                previous_tag VARCHAR(32) NULL,
                new_tag VARCHAR(32) NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
            )
            """
        ))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_article_reviews_article_id ON article_reviews (article_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_article_reviews_action ON article_reviews (action)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_article_reviews_review_scope ON article_reviews (review_scope)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_article_reviews_created_at ON article_reviews (created_at)"))

        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS digest_runs (
                id BIGSERIAL PRIMARY KEY,
                digest_date DATE NOT NULL,
                status VARCHAR(16) NOT NULL,
                article_count INTEGER NOT NULL DEFAULT 0,
                sent_count INTEGER NOT NULL DEFAULT 0,
                window_start TIMESTAMP WITH TIME ZONE NOT NULL,
                window_end TIMESTAMP WITH TIME ZONE NOT NULL,
                error_message TEXT NULL,
                started_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                finished_at TIMESTAMP WITH TIME ZONE NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
            )
            """
        ))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_digest_runs_digest_date ON digest_runs (digest_date)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_digest_runs_status ON digest_runs (status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_digest_runs_started_at ON digest_runs (started_at)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_digest_runs_created_at ON digest_runs (created_at)"))

        conn.execute(text(
            "UPDATE articles SET processing_status = 'new' "
            "WHERE processing_status IS NULL OR processing_status = ''"
        ))
        conn.execute(text(
            """
            UPDATE articles
            SET processing_status = 'sent'
            WHERE sent_at IS NOT NULL
              AND processing_status NOT IN ('sent', 'manual_review')
            """
        ))
        conn.execute(text(
            """
            UPDATE articles
            SET processing_status = 'classified'
            WHERE sent_at IS NULL
              AND keep IS NOT NULL
              AND processing_status = 'new'
            """
        ))
        conn.execute(text(
            """
            UPDATE articles
            SET processing_status = 'classify_failed'
            WHERE classify_error IS NOT NULL
              AND processing_status = 'new'
            """
        ))
        conn.execute(text(
            """
            UPDATE articles
            SET processing_status = 'extract_failed'
            WHERE fetch_error IS NOT NULL
              AND processing_status = 'new'
            """
        ))
        conn.execute(text(
            """
            UPDATE articles
            SET tags = jsonb_build_array(tags->>0)
            WHERE tags IS NOT NULL
              AND jsonb_typeof(tags) = 'array'
              AND jsonb_array_length(tags) > 1
            """
        ))
        conn.commit()


if __name__ == "__main__":
    main()
