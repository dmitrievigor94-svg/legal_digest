from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as date_type, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classify_llm import classify
from app.config import env_int, env_on, settings
from app.digest import build_telegram_digest_blocks
from app.extract import (
    clean_fas_text,
    fetch_and_extract_text,
    is_bad_extracted_text,
    make_short_summary,
)
from app.fetch_rss import fetch_items, save_new_articles
from app.filtering import is_relevant
from app.models import Article, DigestRun
from app.notify_telegram import send_telegram_message_html
from app.published_at import fetch_published_at
from app.sources import SOURCES

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    created: int = 0
    existed: int = 0
    source_errors: int = 0


@dataclass
class ClassifyResult:
    processed: int = 0
    kept: int = 0
    rejected: int = 0
    errors: int = 0


@dataclass
class DigestResult:
    sent_count: int
    text: str
    sent_ids: list[int]
    window_start: datetime
    window_end: datetime
    digest_date: date_type
    run_id: int | None = None


def _resolve_digest_window(digest_date: date_type | None = None) -> tuple[datetime, datetime]:
    local_tz = ZoneInfo(settings.digest_tz)
    if digest_date is None:
        digest_date = datetime.now(local_tz).date() - timedelta(days=1)

    window_days = 3 if digest_date.weekday() == 0 else 1
    end_local = datetime.combine(digest_date, datetime.max.time(), tzinfo=local_tz)
    start_local = datetime.combine(
        digest_date - timedelta(days=window_days - 1),
        datetime.min.time(),
        tzinfo=local_tz,
    )
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def run_fetch_step(db: Session, *, debug: bool = False) -> FetchResult:
    result = FetchResult()
    now = datetime.now(timezone.utc)

    for source in SOURCES:
        try:
            items_raw = fetch_items(source)
        except Exception as exc:
            result.source_errors += 1
            logger.exception("Fetch failed for %s: %s", source["source_id"], exc)
            continue

        items_filtered = []
        for item in items_raw:
            keep = is_relevant(
                item["source_id"],
                item.get("title") or "",
                item.get("canonical_url") or item.get("url") or "",
            )
            if keep:
                items_filtered.append(item)
            elif debug:
                logger.info(
                    "[FILTER] %s | %s",
                    item["source_id"],
                    (item.get("title") or "")[:80],
                )

        cutoff_hours = int(source.get("cutoff_hours", 36) or 0)
        allow_no_date = bool(source.get("allow_no_date", False))
        if cutoff_hours > 0:
            cutoff = now - timedelta(hours=cutoff_hours)
            items = [
                item for item in items_filtered
                if (
                    (item.get("published_at") or None) is None and allow_no_date
                ) or (
                    item.get("published_at") is not None and item["published_at"] >= cutoff
                )
            ]
        else:
            items = items_filtered

        created, existed = save_new_articles(db, items)
        result.created += created
        result.existed += existed
        logger.info(
            "[FETCH] %s | new=%s existed=%s",
            source["source_name"],
            created,
            existed,
        )

    return result


def run_classify_step(
    db: Session,
    *,
    reclassify_all: bool = False,
    reclassify_days: int = 0,
    refetch_text: bool = False,
    debug: bool = False,
    debug_max: int = 1000,
) -> ClassifyResult:
    result = ClassifyResult()
    query = select(Article).order_by(Article.created_at.desc())

    if reclassify_all:
        if reclassify_days > 0:
            since = datetime.now(timezone.utc) - timedelta(days=reclassify_days)
            query = query.where(Article.created_at >= since)
    else:
        query = query.where(Article.fetched_at.is_(None))

    to_process = db.execute(query).scalars().all()
    if debug and debug_max and len(to_process) > debug_max:
        to_process = to_process[:debug_max]
        logger.info("[DEBUG] ограничено до %s статей", debug_max)

    logger.info("Обрабатываем %s статей через GigaChat...", len(to_process))

    for index, article in enumerate(to_process, start=1):
        result.processed += 1
        article.processing_status = "processing"
        article.fetch_error = None
        article.classify_error = None

        need_fetch = refetch_text or (article.fetched_at is None)
        try:
            if need_fetch:
                text = fetch_and_extract_text(article.canonical_url)
                if text:
                    if article.source_id.startswith("fas_"):
                        text = clean_fas_text(text)
                    if not text:
                        article.summary = article.summary or ""
                    else:
                        article.raw_text = text

                    if text and article.published_at is None:
                        dt = fetch_published_at(article.canonical_url)
                        if dt and (dt.year < 2023 or dt.year > datetime.now(timezone.utc).year + 1):
                            dt = None
                        if dt:
                            article.published_at = dt

                    if text:
                        if is_bad_extracted_text(text):
                            article.summary = ""
                            article.processing_status = "extract_bad_text"
                            article.fetch_error = "bad_extracted_text"
                        else:
                            article.summary = make_short_summary(text, max_chars=700)
                            article.processing_status = "text_ready"
                    elif article.processing_status == "processing":
                        article.processing_status = "extract_empty"
                        article.fetch_error = "empty_after_clean"
                else:
                    article.summary = article.summary or ""
                    article.processing_status = "extract_failed"
                    article.fetch_error = "no_text"

            classify_text = article.raw_text or article.summary or ""
            classified = classify(
                article.source_id,
                article.title,
                classify_text,
                article.canonical_url,
            )

            article.event_type = classified.event_type
            article.tags = classified.tags
            article.score = classified.score
            article.keep = classified.keep
            article.topic = classified.event_type
            article.decision_source = classified.decision_source
            if classified.summary:
                article.llm_summary = classified.summary
            if classified.reason:
                article.llm_reason = classified.reason

            article.processing_status = "classified"
            article.last_processed_at = datetime.now(timezone.utc)
            if article.fetched_at is None or refetch_text or reclassify_all:
                article.fetched_at = article.last_processed_at

            verdict = "✓" if classified.keep else "✗"
            if classified.keep:
                result.kept += 1
            else:
                result.rejected += 1

            if debug:
                logger.info(
                    "%s/%s %s [%s] [%s] %s",
                    index,
                    len(to_process),
                    verdict,
                    classified.event_type,
                    article.source_id,
                    article.title[:65],
                )
                if classified.reason:
                    logger.info("    -> %s", classified.reason)
            elif classified.keep or classified.reason:
                logger.info(
                    "%s/%s %s [%s] [%s] %s",
                    index,
                    len(to_process),
                    verdict,
                    classified.event_type,
                    article.source_id,
                    article.title[:65],
                )
                if classified.reason:
                    logger.info("    -> %s", classified.reason)
            elif index % 10 == 0 or index == len(to_process):
                logger.info("%s/%s обработано...", index, len(to_process))
        except Exception as exc:
            result.errors += 1
            article.processing_status = "classify_failed"
            article.classify_error = str(exc)[:1000]
            article.last_processed_at = datetime.now(timezone.utc)
            logger.exception("Ошибка обработки статьи id=%s url=%s", article.id, article.canonical_url)

        if index % 10 == 0:
            db.commit()

    db.commit()
    logger.info("Обработано: %s", len(to_process))
    return result


def build_digest_step(db: Session, *, digest_date: date_type | None = None) -> DigestResult:
    if digest_date is None:
        local_tz = ZoneInfo(settings.digest_tz)
        digest_date = datetime.now(local_tz).date() - timedelta(days=1)

    window_start, window_end = _resolve_digest_window(digest_date=digest_date)
    text, sent_ids = build_telegram_digest_blocks(
        db,
        limit=500,
        window=(window_start, window_end),
    )
    run = DigestRun(
        digest_date=digest_date,
        status="built" if sent_ids else "empty",
        article_count=len(sent_ids),
        sent_count=0,
        window_start=window_start,
        window_end=window_end,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(
        "[DIGEST] статей в дайджесте: %s | окно: %s-%s UTC",
        len(sent_ids),
        window_start.strftime("%d.%m %H:%M"),
        window_end.strftime("%d.%m %H:%M"),
    )
    return DigestResult(
        sent_count=len(sent_ids),
        text=text,
        sent_ids=sent_ids,
        window_start=window_start,
        window_end=window_end,
        digest_date=digest_date,
        run_id=run.id,
    )


def send_digest_step(db: Session, digest: DigestResult) -> int:
    run = db.get(DigestRun, digest.run_id) if digest.run_id else None
    if not digest.sent_ids:
        logger.info("[TG] нечего отправлять")
        if run is not None:
            run.status = "empty"
            run.sent_count = 0
            run.error_message = None
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
        return 0

    logger.info("[TG] отправляем...")
    try:
        send_telegram_message_html(digest.text)
    except Exception as exc:
        if run is not None:
            run.status = "failed"
            run.error_message = str(exc)[:2000]
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
        raise
    logger.info("[TG] отправлено")

    now = datetime.now(timezone.utc)
    rows = db.execute(select(Article).where(Article.id.in_(digest.sent_ids))).scalars().all()
    for article in rows:
        article.sent_at = now
        article.processing_status = "sent"
        article.last_processed_at = now
    if run is not None:
        run.status = "sent"
        run.sent_count = len(rows)
        run.error_message = None
        run.finished_at = now
    db.commit()
    logger.info("Помечено sent_at: %s", len(rows))
    return len(rows)


def retry_digest_run(db: Session, run_id: int) -> tuple[int, int]:
    original_run = db.get(DigestRun, run_id)
    if original_run is None:
        raise ValueError(f"digest_run_not_found:{run_id}")

    text, sent_ids = build_telegram_digest_blocks(
        db,
        limit=500,
        window=(original_run.window_start, original_run.window_end),
    )
    retry_run = DigestRun(
        digest_date=original_run.digest_date,
        status="built" if sent_ids else "empty",
        article_count=len(sent_ids),
        sent_count=0,
        window_start=original_run.window_start,
        window_end=original_run.window_end,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    db.add(retry_run)
    db.commit()
    db.refresh(retry_run)

    digest = DigestResult(
        sent_count=len(sent_ids),
        text=text,
        sent_ids=sent_ids,
        window_start=original_run.window_start,
        window_end=original_run.window_end,
        digest_date=original_run.digest_date,
        run_id=retry_run.id,
    )
    sent_count = send_digest_step(db, digest)
    return retry_run.id, sent_count


def run_full_pipeline(db: Session) -> dict[str, int]:
    settings.validate_runtime()
    debug = env_on("DIGEST_DEBUG")
    debug_max = env_int("DIGEST_DEBUG_MAX", 1000)
    reclassify_all = env_on("RECLASSIFY_ALL")
    reclassify_days = env_int("RECLASSIFY_DAYS", 0)
    refetch_text = env_on("REFETCH_TEXT")

    fetch_result = run_fetch_step(db, debug=debug)
    classify_result = run_classify_step(
        db,
        reclassify_all=reclassify_all,
        reclassify_days=reclassify_days,
        refetch_text=refetch_text,
        debug=debug,
        debug_max=debug_max,
    )
    digest_result = build_digest_step(db)
    sent_count = send_digest_step(db, digest_result)

    return {
        "created": fetch_result.created,
        "existed": fetch_result.existed,
        "source_errors": fetch_result.source_errors,
        "processed": classify_result.processed,
        "kept": classify_result.kept,
        "rejected": classify_result.rejected,
        "classify_errors": classify_result.errors,
        "sent": sent_count,
    }
