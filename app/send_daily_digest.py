import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db import SessionLocal
from app.migrate import main as migrate
from app.fetch_rss import fetch_rss, save_new_articles
from app.digest import build_console_digest
from app.extract import fetch_and_extract_text, make_short_summary, is_bad_extracted_text, clean_fas_text
from app.topics import detect_topic
from app.models import Article
from app.sources import SOURCES
from app.published_at import fetch_published_at
from app.notify_telegram import send_telegram_message
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")


def main() -> None:
    migrate()

    with SessionLocal() as db:
        # 1) RSS -> save
        for s in SOURCES:
            now = datetime.now(timezone.utc)
            try:
                items_raw = fetch_rss(s["url"], s["source_id"], s["source_name"])
            except Exception as e:
                # важно: сообщаем в телегу только если хочешь шум; я бы пока логировал в stdout
                print(str(e))
                continue

            cutoff_hours = int(s.get("cutoff_hours", 36) or 0)
            allow_no_date = bool(s.get("allow_no_date", False))

            if cutoff_hours > 0:
                cutoff = now - timedelta(hours=cutoff_hours)

                def _keep(it: dict) -> bool:
                    dt = it.get("published_at")
                    if dt is None:
                        return allow_no_date
                    return dt >= cutoff

                items = [it for it in items_raw if _keep(it)]
            else:
                items = items_raw

            save_new_articles(db, items)

        # 2) enrich
        to_enrich = db.execute(
            select(Article)
            .where(Article.fetched_at.is_(None))
            .order_by(Article.created_at.desc())
            .limit(200)  # можно поднять, если надо
        ).scalars().all()

        for a in to_enrich:
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
                a.summary = ""

            a.topic = detect_topic(a.title, a.raw_text or "", a.source_id)
            a.fetched_at = datetime.now(timezone.utc)

        db.commit()

        # 3) build digest for "yesterday" in local TZ (за вчера календарно)
        local_tz = ZoneInfo(os.getenv("DIGEST_TZ", "Europe/Moscow"))
        today_local = datetime.now(local_tz).date()
        yesterday_local = today_local - timedelta(days=1)

        start_local = datetime.combine(yesterday_local, datetime.min.time(), tzinfo=local_tz)
        end_local = datetime.combine(today_local, datetime.min.time(), tzinfo=local_tz)
        window = (start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc))

        digest_text, sent_ids = build_console_digest(db, limit=500, window=window)

        # 4) send to Telegram
        # Если пусто — можно либо ничего не слать, либо слать "нет новых материалов"
        if "Новых материалов: 0" in digest_text:
            # решай сам — я бы слал короткую заглушку, чтобы было понятно что система жива
            pass

        send_telegram_message(digest_text)

        # 5) mark sent
        if sent_ids:
            now = datetime.now(timezone.utc)
            rows = db.execute(select(Article).where(Article.id.in_(sent_ids))).scalars().all()
            for a in rows:
                a.sent_at = now
            db.commit()


if __name__ == "__main__":
    main()