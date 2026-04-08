from __future__ import annotations

import unittest
from datetime import datetime, timezone, date
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Article, DigestRun
from app.pipeline import build_digest_step, retry_digest_run, send_digest_step


class DigestRunTests(unittest.TestCase):
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

    def test_build_digest_step_creates_digest_run(self) -> None:
        with self.SessionLocal() as db, patch(
            "app.pipeline.build_telegram_digest_blocks",
            return_value=("digest text", [101, 202]),
        ):
            result = build_digest_step(db, digest_date=date(2026, 4, 7))
            run = db.execute(select(DigestRun)).scalar_one()

        self.assertEqual(result.run_id, run.id)
        self.assertEqual(run.digest_date, date(2026, 4, 7))
        self.assertEqual(run.status, "built")
        self.assertEqual(run.article_count, 2)
        self.assertEqual(run.sent_count, 0)

    def test_send_digest_step_marks_run_failed_when_telegram_send_raises(self) -> None:
        with self.SessionLocal() as db:
            result = build_digest_step(db, digest_date=date(2026, 4, 7))
            result.sent_ids = [1]
            result.text = "digest"

            with patch("app.pipeline.send_telegram_message_html", side_effect=RuntimeError("telegram down")):
                with self.assertRaises(RuntimeError):
                    send_digest_step(db, result)

            run = db.execute(select(DigestRun)).scalar_one()

        self.assertEqual(run.status, "failed")
        self.assertIn("telegram down", run.error_message or "")

    def test_send_digest_step_marks_run_sent_and_updates_articles(self) -> None:
        with self.SessionLocal() as db:
            article = Article(
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
            db.add(article)
            db.commit()

            with patch("app.pipeline.build_telegram_digest_blocks", return_value=("digest", [article.id])):
                result = build_digest_step(db, digest_date=date(2026, 4, 7))
            result.sent_ids = [article.id]
            result.text = "digest"

            with patch("app.pipeline.send_telegram_message_html"):
                sent_count = send_digest_step(db, result)

            run = db.execute(select(DigestRun)).scalar_one()
            refreshed = db.get(Article, article.id)

        self.assertEqual(sent_count, 1)
        self.assertEqual(run.status, "sent")
        self.assertEqual(run.sent_count, 1)
        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertEqual(refreshed.processing_status, "sent")
        self.assertIsNotNone(refreshed.sent_at)

    def test_retry_digest_run_creates_new_attempt_and_sends(self) -> None:
        with self.SessionLocal() as db:
            article = Article(
                source_id="rapsi_judicial",
                source_name="РАПСИ",
                title="Retry article",
                url="https://example.com/retry",
                canonical_url="https://example.com/retry",
                content_hash="hash-retry",
                keep=True,
                event_type="COURTS",
                tags=["competition"],
                fetched_at=datetime(2026, 4, 8, 11, 0, tzinfo=timezone.utc),
                published_at=datetime(2026, 4, 8, 11, 0, tzinfo=timezone.utc),
            )
            db.add(article)
            db.commit()

            failed_run = DigestRun(
                digest_date=date(2026, 4, 7),
                status="failed",
                article_count=1,
                sent_count=0,
                error_message="telegram timeout",
                window_start=datetime(2026, 4, 7, 0, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 4, 8, 0, 0, tzinfo=timezone.utc),
                started_at=datetime(2026, 4, 8, 8, 55, tzinfo=timezone.utc),
                finished_at=datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc),
            )
            db.add(failed_run)
            db.commit()
            failed_run_id = failed_run.id

            with patch("app.pipeline.build_telegram_digest_blocks", return_value=("retry digest", [article.id])):
                with patch("app.pipeline.send_telegram_message_html"):
                    retry_run_id, sent_count = retry_digest_run(db, failed_run_id)

            runs = db.execute(select(DigestRun).order_by(DigestRun.id)).scalars().all()
            refreshed = db.get(Article, article.id)

        self.assertEqual(sent_count, 1)
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0].status, "failed")
        self.assertEqual(runs[1].id, retry_run_id)
        self.assertEqual(runs[1].status, "sent")
        self.assertEqual(runs[1].sent_count, 1)
        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertEqual(refreshed.processing_status, "sent")
