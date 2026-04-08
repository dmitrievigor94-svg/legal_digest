from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Article, ArticleReview, DigestRun
from app.web import app


class WebActionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)

        with self.SessionLocal() as db:
            article = Article(
                source_id="fas_news",
                source_name="ФАС",
                title="Test article",
                url="https://example.com/item",
                canonical_url="https://example.com/item",
                content_hash="hash-1",
                keep=None,
                tags=[],
                processing_status="new",
            )
            db.add(article)
            db.commit()
            self.article_id = article.id

        self.session_patch = patch("app.web.SessionLocal", self.SessionLocal)
        self.session_patch.start()
        self.digest_patch = patch("app.web.get_articles_for_digest")
        self.resolve_window_patch = patch("app.web._resolve_digest_window")
        self.mock_get_articles_for_digest = self.digest_patch.start()
        self.mock_resolve_digest_window = self.resolve_window_patch.start()
        self.mock_resolve_digest_window.return_value = (
            datetime(2026, 4, 7, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 8, 0, 0, tzinfo=timezone.utc),
        )
        self.client = app.test_client()

    def tearDown(self) -> None:
        self.digest_patch.stop()
        self.resolve_window_patch.stop()
        self.session_patch.stop()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _get_article(self) -> Article:
        with self.SessionLocal() as db:
            article = db.get(Article, self.article_id)
            assert article is not None
            db.expunge(article)
            return article

    def test_update_article_sets_manual_review_fields(self) -> None:
        response = self.client.post(
            f"/article/{self.article_id}/update",
            data={
                "keep": "1",
                "event_type": "ENFORCEMENT",
                "tag": "competition",
                "next": "status=new",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/?status=new"))

        article = self._get_article()
        self.assertTrue(article.keep)
        self.assertEqual(article.event_type, "ENFORCEMENT")
        self.assertEqual(article.tags, ["competition"])
        self.assertEqual(article.topic, "ENFORCEMENT")
        self.assertEqual(article.decision_source, "manual")
        self.assertEqual(article.processing_status, "manual_review")
        self.assertIsNotNone(article.last_processed_at)

        with self.SessionLocal() as db:
            review = db.execute(select(ArticleReview).where(ArticleReview.article_id == self.article_id)).scalar_one()
        self.assertEqual(review.action, "update")
        self.assertEqual(review.review_scope, "future")
        self.assertIsNone(review.previous_keep)
        self.assertTrue(review.new_keep)
        self.assertEqual(review.new_tag, "competition")

    def test_reprocess_article_clears_classification_and_marks_new(self) -> None:
        with self.SessionLocal() as db:
            article = db.get(Article, self.article_id)
            assert article is not None
            article.keep = False
            article.event_type = "COURTS"
            article.tags = ["competition"]
            article.score = -10
            article.topic = "COURTS"
            article.llm_summary = "summary"
            article.llm_reason = "reason"
            article.fetch_error = "fetch error"
            article.classify_error = "classify error"
            article.decision_source = "llm"
            article.fetched_at = datetime.now(timezone.utc)
            db.commit()

        response = self.client.post(f"/article/{self.article_id}/reprocess", data={"next": ""})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

        article = self._get_article()
        self.assertIsNone(article.keep)
        self.assertIsNone(article.event_type)
        self.assertIsNone(article.tags)
        self.assertIsNone(article.score)
        self.assertIsNone(article.topic)
        self.assertIsNone(article.llm_summary)
        self.assertIsNone(article.llm_reason)
        self.assertIsNone(article.fetch_error)
        self.assertIsNone(article.classify_error)
        self.assertIsNone(article.decision_source)
        self.assertIsNone(article.fetched_at)
        self.assertEqual(article.processing_status, "new")

    def test_reset_article_clears_manual_decision_but_preserves_fetch_state(self) -> None:
        with self.SessionLocal() as db:
            article = db.get(Article, self.article_id)
            assert article is not None
            article.keep = True
            article.event_type = "GUIDANCE"
            article.tags = ["banking"]
            article.score = 10
            article.topic = "GUIDANCE"
            article.llm_summary = "summary"
            article.llm_reason = "reason"
            article.classify_error = "classify error"
            article.fetch_error = "fetch error"
            article.fetched_at = datetime.now(timezone.utc)
            article.decision_source = "manual"
            db.commit()

        response = self.client.post(f"/article/{self.article_id}/reset", data={"next": "keep=1"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/?keep=1"))

        article = self._get_article()
        self.assertIsNone(article.keep)
        self.assertIsNone(article.event_type)
        self.assertIsNone(article.tags)
        self.assertIsNone(article.score)
        self.assertIsNone(article.topic)
        self.assertIsNone(article.llm_summary)
        self.assertIsNone(article.llm_reason)
        self.assertIsNone(article.decision_source)
        self.assertIsNone(article.classify_error)
        self.assertEqual(article.fetch_error, "fetch error")
        self.assertIsNotNone(article.fetched_at)
        self.assertEqual(article.processing_status, "reset")

    def test_index_renders_dashboard_sections(self) -> None:
        with self.SessionLocal() as db:
            digest_article = db.get(Article, self.article_id)
            assert digest_article is not None
            digest_article.keep = True
            digest_article.event_type = "ENFORCEMENT"
            digest_article.processing_status = "classified"
            digest_article.sent_at = datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc)
            db.add(
                DigestRun(
                    digest_date=datetime(2026, 4, 7, 0, 0, tzinfo=timezone.utc).date(),
                    status="sent",
                    article_count=1,
                    sent_count=1,
                    window_start=datetime(2026, 4, 7, 0, 0, tzinfo=timezone.utc),
                    window_end=datetime(2026, 4, 8, 0, 0, tzinfo=timezone.utc),
                    started_at=datetime(2026, 4, 8, 8, 55, tzinfo=timezone.utc),
                    finished_at=datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc),
                )
            )
            db.commit()
            preview_article = {
                "title": digest_article.title,
                "canonical_url": digest_article.canonical_url,
                "source_name": digest_article.source_name,
                "event_type": digest_article.event_type,
                "processing_status": digest_article.processing_status,
            }

        class StubArticle:
            def __init__(self, payload: dict):
                self.title = payload["title"]
                self.canonical_url = payload["canonical_url"]
                self.source_name = payload["source_name"]
                self.event_type = payload["event_type"]
                self.processing_status = payload["processing_status"]

        self.mock_get_articles_for_digest.return_value = [StubArticle(preview_article)]

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Предстоящий выпуск как сообщение в Telegram", html)
        self.assertIn("Эта новость требует внимания", html)
        self.assertNotIn("Массовые действия по выбранным статьям", html)
        self.assertNotIn("Правка этой новости", html)
        self.assertIn("Test article", html)

    def test_delivery_panel_renders_status_history(self) -> None:
        with self.SessionLocal() as db:
            db.add(
                DigestRun(
                    digest_date=datetime(2026, 4, 7, 0, 0, tzinfo=timezone.utc).date(),
                    status="failed",
                    article_count=3,
                    sent_count=0,
                    error_message="telegram timeout",
                    window_start=datetime(2026, 4, 7, 0, 0, tzinfo=timezone.utc),
                    window_end=datetime(2026, 4, 8, 0, 0, tzinfo=timezone.utc),
                    started_at=datetime(2026, 4, 8, 8, 55, tzinfo=timezone.utc),
                    finished_at=datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc),
                )
            )
            db.commit()

        response = self.client.get("/delivery")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Журнал отправки дайджестов", html)
        self.assertIn("Повторить отправку", html)
        self.assertIn("telegram timeout", html)

    def test_retry_delivery_run_calls_pipeline_retry(self) -> None:
        with self.SessionLocal() as db:
            run = DigestRun(
                digest_date=datetime(2026, 4, 7, 0, 0, tzinfo=timezone.utc).date(),
                status="failed",
                article_count=3,
                sent_count=0,
                error_message="telegram timeout",
                window_start=datetime(2026, 4, 7, 0, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 4, 8, 0, 0, tzinfo=timezone.utc),
                started_at=datetime(2026, 4, 8, 8, 55, tzinfo=timezone.utc),
                finished_at=datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc),
            )
            db.add(run)
            db.commit()
            run_id = run.id

        with patch("app.web.retry_digest_run", return_value=(999, 3)) as retry_mock:
            response = self.client.post(f"/delivery/{run_id}/retry")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/delivery")
        retry_mock.assert_called_once()

    def test_archive_reviews_panel_renders_review_log(self) -> None:
        with self.SessionLocal() as db:
            article = db.get(Article, self.article_id)
            assert article is not None
            article.keep = True
            db.add(
                ArticleReview(
                    article_id=self.article_id,
                    action="update",
                    review_scope="archive",
                    previous_keep=False,
                    new_keep=True,
                    previous_event_type="COURTS",
                    new_event_type="ENFORCEMENT",
                    previous_tag="banking",
                    new_tag="competition",
                )
            )
            db.commit()

        response = self.client.get("/archive/reviews")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Архив исправлений", html)
        self.assertIn("Test article", html)
        self.assertIn("competition", html)

    def test_index_supports_sent_digest_filter(self) -> None:
        with self.SessionLocal() as db:
            article = db.get(Article, self.article_id)
            assert article is not None
            article.keep = True
            article.event_type = "ENFORCEMENT"
            article.processing_status = "classified"
            article.sent_at = datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc)
            db.commit()

        class StubArticle:
            def __init__(self, article_id: int, title: str, canonical_url: str, source_name: str, event_type: str, processing_status: str):
                self.id = article_id
                self.title = title
                self.canonical_url = canonical_url
                self.source_name = source_name
                self.event_type = event_type
                self.processing_status = processing_status

        self.mock_get_articles_for_digest.return_value = [
            StubArticle(
                self.article_id,
                "Test article",
                "https://example.com/item",
                "ФАС",
                "ENFORCEMENT",
                "classified",
            )
        ]

        response = self.client.get("/archive?sent_digest=2026-04-08")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Зона архива и исправлений", html)
        self.assertIn("Архив выпусков", html)
        self.assertIn("Test article", html)

    def test_index_supports_future_workspace_focus_for_next_digest(self) -> None:
        with self.SessionLocal() as db:
            article = db.get(Article, self.article_id)
            assert article is not None
            article.keep = True
            article.event_type = "ENFORCEMENT"
            article.processing_status = "classified"
            db.commit()

        class StubArticle:
            def __init__(self, article_id: int, title: str, canonical_url: str, source_name: str, event_type: str, processing_status: str):
                self.id = article_id
                self.title = title
                self.canonical_url = canonical_url
                self.source_name = source_name
                self.event_type = event_type
                self.processing_status = processing_status

        self.mock_get_articles_for_digest.return_value = [
            StubArticle(
                self.article_id,
                "Test article",
                "https://example.com/item",
                "ФАС",
                "ENFORCEMENT",
                "classified",
            )
        ]

        response = self.client.get("/?focus=next_digest")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Зона работы с предстоящим дайджестом", html)
        self.assertIn("Предстоящий выпуск как сообщение в Telegram", html)
        self.assertNotIn("Правка этой новости", html)
        self.assertIn("Test article", html)

    def test_release_panel_shows_rejected_candidates(self) -> None:
        with self.SessionLocal() as db:
            article = db.get(Article, self.article_id)
            assert article is not None
            article.keep = False
            article.fetched_at = datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc)
            article.published_at = datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc)
            article.llm_reason = "нерелевантно"
            db.commit()

        self.mock_get_articles_for_digest.return_value = []
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Отложенные рядом с выпуском", html)
        self.assertIn("Закинуть в дайджест", html)

    def test_rejected_candidate_can_be_returned_to_digest(self) -> None:
        with self.SessionLocal() as db:
            article = db.get(Article, self.article_id)
            assert article is not None
            article.keep = False
            article.event_type = "ENFORCEMENT"
            article.tags = ["competition"]
            article.fetched_at = datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc)
            article.published_at = datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc)
            db.commit()

        response = self.client.post(
            f"/article/{self.article_id}/update",
            data={
                "keep": "1",
                "event_type": "ENFORCEMENT",
                "tag": "competition",
                "next": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        article = self._get_article()
        self.assertTrue(article.keep)
        self.assertEqual(article.event_type, "ENFORCEMENT")
        self.assertEqual(article.tags, ["competition"])
        self.assertEqual(article.processing_status, "manual_review")

    def test_bulk_update_marks_articles_as_manual_keep(self) -> None:
        with self.SessionLocal() as db:
            second = Article(
                source_id="cbr_press",
                source_name="ЦБ",
                title="Second article",
                url="https://example.com/second",
                canonical_url="https://example.com/second",
                content_hash="hash-2",
                keep=None,
                tags=[],
                processing_status="new",
            )
            db.add(second)
            db.commit()
            second_id = second.id

        response = self.client.post(
            "/articles/bulk-update",
            data={
                "article_ids": [str(self.article_id), str(second_id)],
                "bulk_action": "keep_true",
                "bulk_event_type": "ENFORCEMENT",
                "bulk_tag": "competition",
                "next": "sent=0",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/?sent=0"))

        with self.SessionLocal() as db:
            rows = db.execute(select(Article).where(Article.id.in_([self.article_id, second_id]))).scalars().all()

        self.assertEqual(len(rows), 2)
        for article in rows:
            self.assertTrue(article.keep)
            self.assertEqual(article.event_type, "ENFORCEMENT")
            self.assertEqual(article.tags, ["competition"])
            self.assertEqual(article.processing_status, "manual_review")
            self.assertEqual(article.decision_source, "manual")


if __name__ == "__main__":
    unittest.main()
