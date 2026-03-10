# app/models.py
from sqlalchemy import String, Text, DateTime, UniqueConstraint, func, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        UniqueConstraint("canonical_url", name="uq_articles_canonical_url"),
        UniqueConstraint("content_hash", name="uq_articles_content_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    source_id: Mapped[str] = mapped_column(String(64), index=True)
    source_name: Mapped[str] = mapped_column(String(256))

    keep: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)

    event_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    score: Mapped[int | None] = mapped_column(nullable=True)

    # было 512 — мало
    title: Mapped[str] = mapped_column(String(1024))

    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text)

    published_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Краткое описание содержания от LLM (1-2 предложения), выводится в дайджест
    llm_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    topic: Mapped[str | None] = mapped_column(String(64), nullable=True)

    content_hash: Mapped[str] = mapped_column(String(64), index=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())