from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db import SessionLocal
from app.migrate import main as migrate
from app.fetch_rss import fetch_rss, save_new_articles
from app.digest import build_console_digest
from app.extract import fetch_and_extract_text, make_short_summary
from app.topics import detect_topic
from app.models import Article
from app.extract import is_bad_extracted_text  # добавьте в импорты сверху
from app.extract import clean_fas_text
from app.sources import SOURCES
from app.published_at import fetch_published_at


def main() -> None:
    migrate()

    with SessionLocal() as db:
        total_new = 0

        # 1) Забираем RSS и сохраняем новые ссылки в БД
                # 1) Забираем RSS и сохраняем новые ссылки в БД
        for s in SOURCES:
            now = datetime.now(timezone.utc)

            try:
                items_raw = fetch_rss(s["url"], s["source_id"], s["source_name"])
            except Exception as e:
                print(str(e))
                # ВАЖНО: не печатать дальше [OK] с feed=0 — это вводит в заблуждение
                continue

            before_total = len(items_raw)
            before_with_dt = sum(1 for it in items_raw if it.get("published_at") is not None)
            before_no_dt = before_total - before_with_dt

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
                # cutoff_hours=0 => не режем по времени (используем для источников без даты)
                items = items_raw

            after_total = len(items)
            after_with_dt = sum(1 for it in items if it.get("published_at") is not None)
            after_no_dt = after_total - after_with_dt
            cutoff_drop = before_total - after_total

            created, existed = save_new_articles(db, items)

            print(
                f"[OK] {s['source_name']}\n"
                f"  feed={before_total} (dt={before_with_dt}, no_dt={before_no_dt}) | "
                f"keep={after_total} (dt={after_with_dt}, no_dt={after_no_dt}), drop={cutoff_drop} | "
                f"saved: existed={existed}, created={created}"
            )

            total_new += created

        print("")
        print(f"Итого новых: {total_new}")
        print("")

        # 2) Обогащаем записи: скачиваем страницу, вытаскиваем текст, делаем summary и тему
        #    Берём только те, где fetched_at ещё пустой (то есть мы их ещё не обрабатывали)
        to_enrich = db.execute(
            select(Article)
            .where(Article.fetched_at.is_(None))
            .order_by(Article.created_at.desc())
            .limit(50)
        ).scalars().all()

        enriched = 0
        filled_pub = 0
        filled_pub_minjust = 0
        for a in to_enrich:
            text = fetch_and_extract_text(a.canonical_url)
            if text:
                if a.source_id.startswith("fas_"):
                    text = clean_fas_text(text)

                a.raw_text = text  # <-- ВСЕГДА сохраняем как есть
                # если в RSS не было даты (Минюст часто такой), вытаскиваем со страницы
                if a.published_at is None:
                    dt = fetch_published_at(a.canonical_url)
                    if dt:
                    # если вдруг поймали мусорную дату — игнорируем
                        if dt.year < 2023 or dt.year > datetime.now(timezone.utc).year + 1:
                            dt = None
                    if dt:
                        a.published_at = dt
                        filled_pub += 1
                        if a.source_id.startswith("minjust_"):
                            filled_pub_minjust += 1
                if not is_bad_extracted_text(text):
                    a.summary = make_short_summary(text, max_chars=700)
                else:
                    a.summary = ""
            else:
                a.summary = ""

            a.topic = detect_topic(a.title, a.raw_text or "", a.source_id)
            a.fetched_at = datetime.now(timezone.utc)
            enriched += 1

        db.commit()
        print(f"Обогащено (текст/тема/summary): {enriched}")
        print(f"Восстановлено published_at со страниц: {filled_pub} (Минюст: {filled_pub_minjust})")
        print("")

        # 3) Печатаем дайджест "за вчера" (календарное окно)
        LOCAL_TZ = ZoneInfo("Europe/Moscow")  # у тебя таймзона пользователя/проекта
        today_local = datetime.now(LOCAL_TZ).date()
        yesterday_local = today_local - timedelta(days=1)

        start_local = datetime.combine(yesterday_local, datetime.min.time(), tzinfo=LOCAL_TZ)
        end_local = datetime.combine(today_local, datetime.min.time(), tzinfo=LOCAL_TZ)

        # храним/сравниваем published_at как tz-aware -> переводим окно в UTC
        window_start_utc = start_local.astimezone(timezone.utc)
        window_end_utc = end_local.astimezone(timezone.utc)

        digest_text, sent_ids = build_console_digest(
            db,
            limit=200,
            window=(window_start_utc, window_end_utc),
        )
        print(digest_text)

        if sent_ids:
            now = datetime.now(timezone.utc)
            rows = db.execute(select(Article).where(Article.id.in_(sent_ids))).scalars().all()
            for a in rows:
                a.sent_at = now
            db.commit()
            print(f"\nПомечено как отправленное: {len(sent_ids)}")

if __name__ == "__main__":
    main()