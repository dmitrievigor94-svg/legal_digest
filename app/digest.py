# app/digest.py
from datetime import datetime, timezone
from collections import defaultdict
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article
from app.filtering import is_relevant

TOPIC_ORDER = [
    "законодательство",
    "регуляторы",
    "штрафы",
    "судебная практика",
    "персональные данные",
    "интеллектуальная собственность",
    "потребители/реклама",
    "прочее",
]

def _fmt_dt(dt):
    if not dt:
        return "—"
    try:
        return dt.astimezone().strftime("%d.%m %H:%M")
    except Exception:
        return "—"

def _in_window(dt: Optional[datetime], window: Optional[Tuple[datetime, datetime]]) -> bool:
    if window is None:
        return True
    if dt is None:
        return False
    start, end = window
    return start <= dt < end

def get_unsent_articles(
    db: Session,
    limit: int = 500,
    window: Optional[Tuple[datetime, datetime]] = None,
) -> tuple[list[Article], dict]:
    """
    window = (start, end) в UTC
    """
    raw = db.execute(
        select(Article)
        .where(Article.sent_at.is_(None))
        .order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())
        .limit(limit)
    ).scalars().all()

    stats = {
        "raw": len(raw),
        "dropped_relevance": 0,
        "dropped_no_date": 0,
        "dropped_outside_window": 0,
    }

    # 1) фильтр полезности
    rel = []
    for a in raw:
        if is_relevant(a.source_id, a.title, a.canonical_url):
            rel.append(a)
        else:
            stats["dropped_relevance"] += 1

    # 2) фильтр по окну "вчера"
    if window is None:
        return (rel, stats)

    start, end = window
    out = []
    for a in rel:
        if a.published_at is None:
            stats["dropped_no_date"] += 1
            continue
        if not (start <= a.published_at < end):
            stats["dropped_outside_window"] += 1
            continue
        out.append(a)

    return (out, stats)

def build_console_digest(
    db: Session,
    limit: int = 200,
    window: Optional[Tuple[datetime, datetime]] = None,
) -> tuple[str, list[int]]:
    rows, stats = get_unsent_articles(db, limit=max(limit, 500), window=window)

    if not rows:
        lines = ["Новых материалов нет."]
        if window:
            start, end = window
            lines.append(f"Окно: {start.isoformat()} .. {end.isoformat()} (UTC)")
        lines.append(
            f"Сырых: {stats['raw']}, отфильтровано: "
            f"полезность={stats['dropped_relevance']}, "
            f"без даты={stats['dropped_no_date']}, "
            f"вне окна={stats['dropped_outside_window']}"
        )
        return ("\n".join(lines), [])

    grouped: dict[str, list[Article]] = defaultdict(list)
    for a in rows:
        grouped[a.topic or "прочее"].append(a)

    now_local = datetime.now().astimezone().strftime("%d.%m.%Y %H:%M")

    lines: list[str] = []
    lines.append(f"Ежедневный юридический дайджест • {now_local}")
    lines.append(f"Новых материалов: {len(rows)}")

    if window:
        start, end = window
        lines.append(f"Окно (UTC): {start.isoformat()} .. {end.isoformat()}")
        lines.append(
            f"Отсев: полезность={stats['dropped_relevance']}, "
            f"без даты={stats['dropped_no_date']}, "
            f"вне окна={stats['dropped_outside_window']}"
        )
    else:
        if stats["dropped_relevance"]:
            lines.append(f"Отфильтровано по полезности: {stats['dropped_relevance']}")

    lines.append("")

    for topic in TOPIC_ORDER:
        items = grouped.get(topic, [])
        if not items:
            continue

        lines.append(topic.upper())
        for a in items[:20]:
            # дату можно убрать из строки позже, но пока оставим компактно
            lines.append(f"- [{_fmt_dt(a.published_at)}] ({a.source_name}) {a.title}")
            if a.summary:
                lines.append(f"  {a.summary}")
            lines.append(f"  {a.canonical_url}")
        lines.append("")

    article_ids = [a.id for a in rows if a.id is not None]
    return ("\n".join(lines), article_ids)