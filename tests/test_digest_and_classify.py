from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.classify_llm import _ensure_keep_tag
from app.db import Base
from app.digest import build_telegram_digest_blocks, get_articles_for_digest
from app.models import Article


class ClassifyRulesTests(unittest.TestCase):
    def test_keep_articles_receive_fallback_tag_when_missing(self) -> None:
        self.assertEqual(_ensure_keep_tag(True, []), ["_other"])
        self.assertEqual(_ensure_keep_tag(True, ["competition"]), ["competition"])
        self.assertEqual(_ensure_keep_tag(False, []), [])


class DigestSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)

    def tearDown(self) -> None:
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_sent_articles_are_excluded_from_next_digest(self) -> None:
        with self.SessionLocal() as db:
            sent_article = Article(
                source_id="rapsi_judicial",
                source_name="РАПСИ",
                title="Sent article",
                url="https://example.com/sent",
                canonical_url="https://example.com/sent",
                content_hash="hash-sent",
                keep=True,
                event_type="COURTS",
                tags=["_other"],
                fetched_at=datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc),
                published_at=datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc),
                sent_at=datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc),
            )
            fresh_article = Article(
                source_id="rapsi_judicial",
                source_name="РАПСИ",
                title="Fresh article",
                url="https://example.com/fresh",
                canonical_url="https://example.com/fresh",
                content_hash="hash-fresh",
                keep=True,
                event_type="COURTS",
                tags=["competition"],
                fetched_at=datetime(2026, 4, 8, 11, 0, tzinfo=timezone.utc),
                published_at=datetime(2026, 4, 8, 11, 0, tzinfo=timezone.utc),
            )
            db.add_all([sent_article, fresh_article])
            db.commit()

            rows = get_articles_for_digest(db, limit=20)

        titles = {row.title for row in rows}
        self.assertIn("Fresh article", titles)
        self.assertNotIn("Sent article", titles)

    def test_build_digest_renders_related_publications_for_manual_group(self) -> None:
        with self.SessionLocal() as db:
            primary = Article(
                source_id="rapsi_judicial",
                source_name="РАПСИ",
                title="Primary article",
                url="https://example.com/primary",
                canonical_url="https://example.com/primary",
                content_hash="hash-primary",
                keep=True,
                event_type="COURTS",
                tags=["competition"],
                fetched_at=datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc),
                published_at=datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc),
            )
            db.add(primary)
            db.commit()

            secondary = Article(
                source_id="pravo_ru",
                source_name="Право.ru",
                title="Secondary article",
                url="https://example.com/secondary",
                canonical_url="https://example.com/secondary",
                content_hash="hash-secondary",
                keep=True,
                event_type="COURTS",
                tags=["competition"],
                fetched_at=datetime(2026, 4, 8, 8, 0, tzinfo=timezone.utc),
                published_at=datetime(2026, 4, 8, 8, 0, tzinfo=timezone.utc),
                manual_digest_parent_id=primary.id,
            )
            db.add(secondary)
            db.commit()

            text, sent_ids = build_telegram_digest_blocks(db, limit=20)

        self.assertEqual(len(sent_ids), 2)
        self.assertIn("Другие публикации по теме", text)
        self.assertIn("Право.ru", text)


if __name__ == "__main__":
    unittest.main()
