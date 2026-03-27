# app/db.py
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")


def build_db_url() -> str:
    # 1) приоритет — DATABASE_URL (сервер/Neon)
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    # 2) локальная база из DB_*
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "legal_digest")
    user = os.getenv("DB_USER", "legal_digest")
    password = os.getenv("DB_PASSWORD", "legal_digest_password")

    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


DATABASE_URL = build_db_url()

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass