# app/send_daily_digest.py
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from sqlalchemy import select
from dotenv import load_dotenv

from app.db import SessionLocal
from app.migrate import main as migrate
from app.fetch_rss import fetch_items, save_new_articles
from app.digest import build_telegram_digest_blocks
from app.extract import (
    fetch_and_extract_text,
    make_short_summary,
    is_bad_extracted_text,
    clean_fas_text,
)
from app.classify import classify
from app.models import Article
from app.sources import SOURCES
from app.published_at import fetch_published_at
from app.notify_telegram import send_telegram_message_html
from app.filtering import is_relevant  # фильтр на входе

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")


def _env_on(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int = 0) -> int:
    v = (os.getenv(name, "") or "").strip()
    if not v:
        return default
    try:
        return int(v)
    except Exception:
        return default


def main() -> None:
    migrate()

    reclassify_all = _env_on("RECLASSIFY_ALL")
    reclassify_days = _env_int("RECLASSIFY_DAYS", 0)
    refetch_text = _env_on("REFETCH_TEXT")

    with SessionLocal() as db:
        # 1) fetch -> save (с фильтрацией до БД)
        for s in SOURCES:
            now = datetime.now(timezone.utc)

            try:
                items_raw = fetch_items(s)
            except Exception as e:
                print(str(e))
                continue

            # режем мусор ДО сохранения
            items_raw = [
                it for it in items_raw
                if is_relevant(
                    it["source_id"],
                    it.get("title") or "",
                    it.get("canonical_url") or it.get("url") or "",
                )
            ]

            cutoff_hours = int(s.get("cutoff_hours", 36) or 0)
            allow_no_date = bool(s.get("allow_no_date", False))

            if cutoff_hours > 0:
                cutoff = now - timedelta(hours=cutoff_hours)

                def _keep_by_cutoff(it: dict) -> bool:
                    dt = it.get("published_at")
                    if dt is None:
                        return allow_no_date
                    return dt >= cutoff

                items = [it for it in items_raw if _keep_by_cutoff(it)]
            else:
                items = items_raw

            save_new_articles(db, items)

        # 2) enrich + classify
        # ВАЖНО: НЕ режем limit=200, иначе часть статей остаётся keep=None/event_type=None и пролезает в дайджест.
        q = select(Article).order_by(Article.created_at.desc())

        if reclassify_all:
            if reclassify_days > 0:
                since = datetime.now(timezone.utc) - timedelta(days=reclassify_days)
                q = q.where(Article.created_at >= since)
            # иначе переклассифицируем всё (обычно после TRUNCATE это ок)
        else:
            q = q.where(Article.fetched_at.is_(None))

        to_process = db.execute(q).scalars().all()

        for a in to_process:
            # рефетчим текст либо для новых, либо если явно включили REFETCH_TEXT
            need_fetch = refetch_text or (a.fetched_at is None)

            if need_fetch:
                text = fetch_and_extract_text(a.canonical_url)
                if text:
                    if a.source_id.startswith("fas_"):
                        text = clean_fas_text(text)

                    a.raw_text = text

                    if a.published_at is None:
                        dt = fetch_published_at(a.canonical_url)
                        if dt and (dt.year < 2023 or dt.year > datetime.now(timezone.utc).year + 1):
                            dt = None
                        if dt:
                            a.published_at = dt

                    a.summary = "" if is_bad_extracted_text(text) else make_short_summary(text, max_chars=700)
                else:
                    a.summary = a.summary or ""

            c = classify(a.source_id, a.title, a.raw_text or "", a.canonical_url)

            a.event_type = c.event_type
            a.tags = c.tags
            a.score = c.score
            a.keep = c.keep
            a.topic = a.event_type  # у тебя topic сейчас дубль event_type — оставляю как было

            # фиксируем "обработанность" (важно для digest.py: он берёт только fetched_at != None)
            if a.fetched_at is None or refetch_text or reclassify_all:
                a.fetched_at = datetime.now(timezone.utc)

        db.commit()

        # 3) окно "вчера" в локальной TZ (за вчера календарно)
        local_tz = ZoneInfo(os.getenv("DIGEST_TZ", "Europe/Moscow"))
        today_local = datetime.now(local_tz).date()
        yesterday_local = today_local - timedelta(days=1)

        start_local = datetime.combine(yesterday_local, datetime.min.time(), tzinfo=local_tz)
        end_local = datetime.combine(today_local, datetime.min.time(), tzinfo=local_tz)
        window = (start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc))

        text, sent_ids = build_telegram_digest_blocks(db, limit=500, window=window)
        print(
            f"[DIGEST] text_len={len(text)} sent_ids={len(sent_ids)} "
            f"window_utc={window[0].isoformat()}..{window[1].isoformat()} "
            f"reclassify_all={reclassify_all}"
        )

        # 4) send
        if not sent_ids:
            return

        print("[TG] sending...")
        send_telegram_message_html(text)
        print("[TG] sent OK")

        # 5) mark sent
        now = datetime.now(timezone.utc)
        rows = db.execute(select(Article).where(Article.id.in_(sent_ids))).scalars().all()
        for a in rows:
            a.sent_at = now
        db.commit()


if __name__ == "__main__":
    main()