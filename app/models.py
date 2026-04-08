# app/models.py
from sqlalchemy import String, Text, Date, DateTime, UniqueConstraint, func, Boolean, JSON
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
    title: Mapped[str] = mapped_column(Text)

    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text)

    published_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_processed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Краткое описание содержания от LLM (1-2 предложения), выводится в дайджест
    llm_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Причина решения LLM (одно предложение)
    llm_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetch_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    classify_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="new", server_default="new")
    decision_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    manual_digest_parent_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    digest_force_standalone: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    topic: Mapped[str | None] = mapped_column(String(64), nullable=True)

    content_hash: Mapped[str] = mapped_column(String(64), index=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ArticleReview(Base):
    __tablename__ = "article_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    review_scope: Mapped[str] = mapped_column(String(16), index=True)

    previous_keep: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    new_keep: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    previous_event_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_event_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    previous_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class DigestRun(Base):
    __tablename__ = "digest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    digest_date: Mapped[Date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)

    article_count: Mapped[int] = mapped_column(default=0, server_default="0")
    sent_count: Mapped[int] = mapped_column(default=0, server_default="0")

    window_start: Mapped[DateTime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[DateTime] = mapped_column(DateTime(timezone=True))

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
