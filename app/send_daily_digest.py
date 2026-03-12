# app/send_daily_digest.py
from __future__ import annotations

import os
import time
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
from app.classify_llm import classify          # ← заменили classify.py на classify_llm.py
from app.models import Article
from app.sources import SOURCES
from app.published_at import fetch_published_at
from app.notify_telegram import send_telegram_message_html
from app.filtering import is_relevant

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")


def _env_on(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int = 0) -> int:
    v = (os.getenv(name, "") or "").strip()
    try:
        return int(v) if v else default
    except Exception:
        return default


def main() -> None:
    migrate()

    # Проверяем ключ сразу — не хотим узнать об отсутствии через 5 минут работы
    if not os.environ.get("GIGACHAT_AUTH_KEY", "").strip():
        raise EnvironmentError("GIGACHAT_AUTH_KEY не задан — добавь в .env")

    reclassify_all = _env_on("RECLASSIFY_ALL")
    reclassify_days = _env_int("RECLASSIFY_DAYS", 0)
    refetch_text = _env_on("REFETCH_TEXT")
    debug = _env_on("DIGEST_DEBUG")
    debug_max = _env_int("DIGEST_DEBUG_MAX", 1000)

    with SessionLocal() as db:

        # -----------------------------------------------------------------
        # 1) Fetch → save (с фильтрацией до БД)
        # -----------------------------------------------------------------
        now = datetime.now(timezone.utc)
        for s in SOURCES:

            try:
                items_raw = fetch_items(s)
            except Exception as e:
                print(str(e))
                continue

            # Режем мусор ДО сохранения в БД
            items_filtered = []
            for it in items_raw:
                keep = is_relevant(
                    it["source_id"],
                    it.get("title") or "",
                    it.get("canonical_url") or it.get("url") or "",
                )
                if keep:
                    items_filtered.append(it)
                elif debug:
                    print(f"  [FILTER] {it['source_id']} | {(it.get('title') or '')[:80]}")
            items_raw = items_filtered

            cutoff_hours = int(s.get("cutoff_hours", 36) or 0)
            allow_no_date = bool(s.get("allow_no_date", False))

            if cutoff_hours > 0:
                cutoff = now - timedelta(hours=cutoff_hours)
                items = [
                    it for it in items_raw
                    if (it.get("published_at") or None) is None and allow_no_date
                    or (it.get("published_at") is not None and it["published_at"] >= cutoff)
                ]
            else:
                items = items_raw

            created, existed = save_new_articles(db, items)
            print(f"[OK] {s['source_name']} | new={created} existed={existed}")

        # -----------------------------------------------------------------
        # 2) Enrich + classify через GigaChat
        # -----------------------------------------------------------------
        q = select(Article).order_by(Article.created_at.desc())

        if reclassify_all:
            if reclassify_days > 0:
                since = datetime.now(timezone.utc) - timedelta(days=reclassify_days)
                q = q.where(Article.created_at >= since)
        else:
            q = q.where(Article.fetched_at.is_(None))

        to_process = db.execute(q).scalars().all()
        if debug and debug_max and len(to_process) > debug_max:
            to_process = to_process[:debug_max]
            print(f"\n[DEBUG] ограничено до {debug_max} статей")
        print(f"\nОбрабатываем {len(to_process)} статей через GigaChat...")

        for i, a in enumerate(to_process, start=1):
            need_fetch = refetch_text or (a.fetched_at is None)

            if need_fetch:
                text = fetch_and_extract_text(a.canonical_url)
                if text:
                    if a.source_id.startswith("fas_"):
                        text = clean_fas_text(text)
                    if not text:
                        if debug:
                            print(f"     [EMPTY AFTER CLEAN] {a.canonical_url[:70]}")
                        a.summary = a.summary or ""
                    else:
                        a.raw_text = text

                    if text and a.published_at is None:
                        dt = fetch_published_at(a.canonical_url)
                        if dt and (dt.year < 2023 or dt.year > datetime.now(timezone.utc).year + 1):
                            dt = None
                        if dt:
                            a.published_at = dt

                    if text:
                        if is_bad_extracted_text(text):
                            if debug:
                                print(f"     [BAD TEXT] len={len(text)} {a.canonical_url[:70]}")
                            a.summary = ""
                        else:
                            a.summary = make_short_summary(text, max_chars=700)
                else:
                    if debug:
                        print(f"     [NO TEXT] {a.canonical_url[:80]}")
                    a.summary = a.summary or ""

            # Классификация через GigaChat
            c = classify(
                a.source_id,
                a.title,
                a.raw_text or "",
                a.canonical_url,
                )

            a.event_type = c.event_type
            a.tags = c.tags
            a.score = c.score
            a.keep = c.keep
            a.topic = c.event_type
            if c.summary:
                a.llm_summary = c.summary

            if a.fetched_at is None or refetch_text or reclassify_all:
                a.fetched_at = datetime.now(timezone.utc)

            verdict = "✓" if c.keep else "✗"
            if debug:
                # debug: показываем всё, включая ✗ без reason
                print(f"  {i}/{len(to_process)} {verdict} [{c.event_type}] [{a.source_id}] {a.title[:65]}")
                if c.reason:
                    print(f"     → {c.reason}")
            elif c.keep or c.reason:
                # обычный режим: только ✓ и ✗ с пояснением
                print(f"  {i}/{len(to_process)} {verdict} [{c.event_type}] [{a.source_id}] {a.title[:65]}")
                if c.reason:
                    print(f"     → {c.reason}")
            else:
                # тихий прогресс каждые 10 статей
                if i % 10 == 0 or i == len(to_process):
                    print(f"  {i}/{len(to_process)} обработано...")

            # Периодический commit — не терять прогресс при падении
            if i % 50 == 0:
                db.commit()

        db.commit()
        print(f"\nОбработано: {len(to_process)}")

        # -----------------------------------------------------------------
        # 3) Окно дайджеста в локальной TZ
        # По умолчанию — "вчера". Можно переопределить через DIGEST_DATE=2026-03-06
        # -----------------------------------------------------------------
        local_tz = ZoneInfo(os.getenv("DIGEST_TZ", "Europe/Moscow"))

        digest_date_str = os.getenv("DIGEST_DATE", "").strip()
        if digest_date_str:
            digest_date = datetime.strptime(digest_date_str, "%Y-%m-%d").date()
        else:
            digest_date = datetime.now(local_tz).date() - timedelta(days=1)

        # Понедельник (weekday=0) — расширяем окно на пятницу+сб+вс (3 дня).
        # Так все пятничные новости попадают в понедельничный дайджест.
        # Праздничный день после выходных тоже обрабатывается правильно,
        # если запуск происходит на следующий рабочий день.
        if digest_date.weekday() == 0:  # понедельник
            window_days = 3  # пт+сб+вс
        else:
            window_days = 1

        end_local = datetime.combine(digest_date, datetime.max.time(), tzinfo=local_tz)
        start_local = datetime.combine(digest_date - timedelta(days=window_days - 1),
                                       datetime.min.time(), tzinfo=local_tz)
        window = (start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc))

        text, sent_ids = build_telegram_digest_blocks(db, limit=500, window=window)
        print(
            f"\n[DIGEST] статей в дайджесте: {len(sent_ids)} "
            f"| окно: {window[0].strftime('%d.%m %H:%M')}–{window[1].strftime('%d.%m %H:%M')} UTC"
        )

        # -----------------------------------------------------------------
        # 4) Отправка в Telegram
        # -----------------------------------------------------------------
        if not sent_ids:
            print("[TG] нечего отправлять")
            return

        print("[TG] отправляем...")
        send_telegram_message_html(text)
        print("[TG] отправлено ✓")

        # -----------------------------------------------------------------
        # 5) Помечаем как отправленное
        # -----------------------------------------------------------------
        now = datetime.now(timezone.utc)
        rows = db.execute(select(Article).where(Article.id.in_(sent_ids))).scalars().all()
        for a in rows:
            a.sent_at = now
        db.commit()
        print(f"Помечено sent_at: {len(sent_ids)}")


if __name__ == "__main__":
    main()