# app/digest.py
from __future__ import annotations

from datetime import datetime
from collections import defaultdict
from typing import Optional, Tuple

import html

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article

EVENT_ORDER = [
    "LAW_DRAFT",
    "LAW_ADOPTED",
    "GUIDANCE",
    "ENFORCEMENT",
    "COURTS",
    "MARKET_CASES",
]

EVENT_TITLES = {
    "LAW_DRAFT": "ЗАКОНОПРОЕКТЫ / ПРОЕКТЫ НПА",
    "LAW_ADOPTED": "ПРИНЯТО / ОПУБЛИКОВАНО",
    "GUIDANCE": "РАЗЪЯСНЕНИЯ / ПОЗИЦИИ",
    "ENFORCEMENT": "КОНТРОЛЬ / ШТРАФЫ / ДЕЛА",
    "COURTS": "СУДЕБНАЯ ПРАКТИКА",
    "MARKET_CASES": "КЕЙСЫ РЫНКА",
}

TG_SUMMARY_MAX_CHARS = 320
TG_MAX_PER_SECTION = 25  # можно поднять/опустить

OFFICIAL_SOURCES = {
    "fas_news", "fas_acts", "fas_clarifications", "fas_analytics", "fas_media",
    "cbr_events", "cbr_press",
    "rkn_news", "fstec_news", "pravo_gov", "regulation_gov",
}

MEDIA_SOURCES = {"drussia_all", "rapsi_judicial", "rapsi_publications"}


def _pass_threshold(a: Article) -> bool:
    """
    Средняя точность:
    - official: score>=1
    - media: score>=4
    - если score ещё None (старые записи) — пропускаем, чтобы не "обнулить" историю
    """
    if a.score is None:
        return True

    if a.source_id in MEDIA_SOURCES:
        return a.score >= 4
    return a.score >= 1


def get_articles_for_digest(
    db: Session,
    limit: int = 800,
    window: Optional[Tuple[datetime, datetime]] = None,
) -> list[Article]:
    q = (
        select(Article)
        # .where(Article.sent_at.is_(None))  # ВРЕМЕННО ОТКЛЮЧЕНО: шлём повторно всё
        .order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())
        .limit(limit)
    )
    rows = db.execute(q).scalars().all()

    # окно по дате
    if window is not None:
        start, end = window
        rows = [a for a in rows if a.published_at is not None and start <= a.published_at < end]

    # scoring-фильтр
    rows = [a for a in rows if _pass_threshold(a)]

    return rows


def build_telegram_digest_blocks(
    db: Session,
    limit: int = 500,
    window: Optional[Tuple[datetime, datetime]] = None,
) -> tuple[str, list[int]]:
    rows = get_articles_for_digest(db, limit=max(limit, 800), window=window)

    day_str = datetime.now().astimezone().strftime("%d.%m.%Y")

    lines: list[str] = []
    lines.append(f"<b>Юридический дайджест</b> • <b>{html.escape(day_str)}</b>")
    lines.append("")

    if not rows:
        lines.append("<i>Новых материалов нет.</i>")
        return ("\n".join(lines), [])

    grouped: dict[str, list[Article]] = defaultdict(list)
    for a in rows:
        key = (a.event_type or a.topic or "MARKET_CASES")  # fallback
        grouped[key].append(a)

    first_section = True

    for event_type in EVENT_ORDER:
        items = grouped.get(event_type, [])
        if not items:
            continue

        if not first_section:
            lines.append("")  # один пустой абзац между секциями

        lines.append(f"<b>{html.escape(EVENT_TITLES.get(event_type, event_type))}</b>")
        lines.append("")

        first_section = False

        # сортировка уже в запросе, но на всякий случай
        items_sorted = sorted(
            items,
            key=lambda a: (
                a.published_at is None,
                a.published_at or datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo),
                a.created_at,
            ),
            reverse=True,
        )[:TG_MAX_PER_SECTION]

        for i, a in enumerate(items_sorted, start=1):
            url = (a.canonical_url or a.url or "").strip()
            ttl = (a.title or "").strip()
            ttl_html = html.escape(ttl)

            if url:
                line = f"{i}. <a href=\"{html.escape(url)}\">{ttl_html}</a>"
            else:
                line = f"{i}. {ttl_html}"

            lines.append(line)

            s = (a.summary or "").strip()
            if s:
                if len(s) > TG_SUMMARY_MAX_CHARS:
                    s = s[: TG_SUMMARY_MAX_CHARS - 1].rstrip() + "…"
                lines.append(f"<blockquote>{html.escape(s)}</blockquote>")

            if i != len(items_sorted):
                lines.append("")  # один пустой абзац между новостями

    article_ids = [a.id for a in rows if a.id is not None]
    return ("\n".join(lines), article_ids)