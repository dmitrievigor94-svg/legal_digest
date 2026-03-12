# app/digest.py
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict
from typing import Optional, Tuple

import html
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article

TAG_ORDER = [
    "pdn",
    "advertising",
    "competition",
    "banking",
    "telecom",
    "it_platforms",
    "cybersecurity",
    "ip",
    "consumers",
    "_other",  # без тегов или нераспознанные
]

TAG_TITLES = {
    "pdn":          "Персональные данные",
    "advertising":  "Реклама",
    "competition":  "Антимонопольное",
    "banking":      "Банки и финансы",
    "telecom":      "Телеком",
    "it_platforms": "IT и платформы",
    "cybersecurity":"Кибербезопасность",
    "ip":           "Интеллектуальная собственность",
    "consumers":    "Защита потребителей",
    "_other":       "Прочее",
}

EVENT_BADGE = {
    "LAW_DRAFT":    "📝",
    "LAW_ADOPTED":  "📄",
    "GUIDANCE":     "💬",
    "ENFORCEMENT":  "🗃️",
    "COURTS":       "⚖️",
    "MARKET_CASES": "📊",
}

TG_SUMMARY_MAX_CHARS = 320
TG_MAX_PER_SECTION = 15
TG_REASON_MAX_CHARS = 300

_FALLBACK_DT = datetime.min.replace(tzinfo=timezone.utc)


def _article_tags(a: Article) -> list[str]:
    """Возвращает список тегов статьи из поля tags (JSON list) или пустой список."""
    raw = getattr(a, "tags", None)
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw]
    if isinstance(raw, str):
        import json
        try:
            return json.loads(raw)
        except Exception:
            return []
    return []


def _best_summary(a: Article, max_chars: int) -> str:
    """
    Выбирает лучший доступный текст для показа под заголовком:
    1. llm_summary — написан GigaChat, содержит конкретику сверх заголовка
    2. summary — make_short_summary из извлечённого текста страницы
    Возвращает пустую строку если ничего нет.
    """
    llm_s = (getattr(a, "llm_summary", None) or "").strip()
    if llm_s:
        if len(llm_s) > max_chars:
            llm_s = llm_s[:max_chars - 1].rstrip() + "…"
        return llm_s

    page_s = (getattr(a, "summary", None) or "").strip()
    if page_s:
        if len(page_s) > max_chars:
            page_s = page_s[:max_chars - 1].rstrip() + "…"
        return page_s

    return ""


def build_telegram_digest_blocks(
    db: Session,
    limit: int = 500,
    window: Optional[Tuple[datetime, datetime]] = None,
) -> tuple[str, list[int]]:
    rows = get_articles_for_digest(db, limit=max(limit, 800), window=window)

    _digest_tz = ZoneInfo(os.getenv("DIGEST_TZ", "Europe/Moscow"))
    _digest_date_env = os.getenv("DIGEST_DATE")
    if _digest_date_env:
        from datetime import date as _date
        _digest_day = _date.fromisoformat(_digest_date_env)
    else:
        _digest_day = (datetime.now(_digest_tz) - timedelta(days=1)).date()
    day_str = _digest_day.strftime("%d.%m.%Y")

    lines: list[str] = []

    if not rows:
        lines.append(f"📌 <b>Юридический дайджест за {html.escape(day_str)}</b>")
        lines.append("")
        lines.append("<i>Новых материалов нет.</i>")
        return ("\n".join(lines), [])

    total = len(rows)
    lines.append(f"📌 <b>Юридический дайджест за {html.escape(day_str)} из {total} материал{'а' if 2 <= total % 10 <= 4 and total % 100 not in range(11, 15) else 'ов' if total % 10 != 1 else ''}</b>")

    # Группируем по первому тегу статьи (приоритет по TAG_ORDER)
    grouped: dict[str, list[Article]] = defaultdict(list)
    for a in rows:
        tags = _article_tags(a)
        placed = False
        for tag in TAG_ORDER:
            if tag in tags:
                grouped[tag].append(a)
                placed = True
                break
        if not placed:
            grouped["_other"].append(a)

    for tag in TAG_ORDER:
        items = grouped.get(tag, [])
        if not items:
            continue

        items_sorted = sorted(
            items,
            key=lambda a: (
                a.published_at is not None,
                a.published_at or _FALLBACK_DT,
            ),
            reverse=True,
        )
        items_sorted = items_sorted[:TG_MAX_PER_SECTION]

        lines.append("")
        lines.append(f"<b>{html.escape(TAG_TITLES[tag])}</b>")

        for a in items_sorted:
            url = (a.canonical_url or a.url or "").strip()
            ttl = (a.title or "").strip()
            if len(ttl) > 100:
                ttl = ttl[:99].rstrip() + "…"
            badge = EVENT_BADGE.get(a.event_type or "", "")

            ttl_html = html.escape(ttl)
            if url:
                title_part = f'<a href="{html.escape(url)}">{ttl_html}</a>'
            else:
                title_part = ttl_html

            # Пустая строка перед каждой новостью внутри раздела
            lines.append("")
            line = f"{badge} {title_part}" if badge else f"{title_part}"
            lines.append(line)

            summary_text = _best_summary(a, TG_REASON_MAX_CHARS)
            if summary_text:
                lines.append(f"<blockquote>{html.escape(summary_text)}</blockquote>")

    article_ids = [a.id for a in rows if a.id is not None]
    return ("\n".join(lines), article_ids)


def _dbg_enabled() -> bool:
    return os.getenv("DIGEST_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _pass_threshold(a: Article) -> bool:
    keep = getattr(a, "keep", None)
    if keep is not None:
        return bool(keep)
    # legacy fallback
    if a.score is None:
        return False
    return a.score >= 1


def _decision_reasons(a: Article, window: Optional[Tuple[datetime, datetime]]) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if a.fetched_at is None:
        return False, ["not_processed: fetched_at is None"]

    if window is not None:
        start, end = window
        if a.published_at is None:
            return False, ["no_published_at (window enabled)"]
        if not (start <= a.published_at < end):
            return (
                False,
                [f"out_of_window: {a.published_at.isoformat()} not in [{start.isoformat()}..{end.isoformat()})"],
            )
        reasons.append("in_window")

    keep = getattr(a, "keep", None)
    if keep is not None:
        if keep:
            reasons.append("keep=True (classifier)")
            ok = True
        else:
            return False, ["keep=False (classifier)"]
    else:
        if a.score is None:
            return False, ["score=None (legacy fail)"]
        if a.score >= 1:
            reasons.append(f"legacy score={a.score} >=1")
            ok = True
        else:
            return False, [f"legacy score={a.score} <1"]

    if not a.event_type and not a.topic:
        reasons.append("no event_type/topic (will fallback to MARKET_CASES)")

    return ok, reasons


def _dbg_print_decisions(decisions: list[tuple[Article, bool, list[str]]], max_lines: int = 80) -> None:
    total = len(decisions)
    in_cnt = sum(1 for _, ok, _ in decisions if ok)
    out_cnt = total - in_cnt

    print(f"[DIGEST_DEBUG] decisions: total={total} IN={in_cnt} OUT={out_cnt}")

    ordered = sorted(decisions, key=lambda x: (x[1],), reverse=False)

    shown = 0
    for a, ok, reasons in ordered:
        if shown >= max_lines:
            print(f"[DIGEST_DEBUG] ... truncated, shown={max_lines} of {total}")
            break

        et = a.event_type or "-"
        src = a.source_id or "-"
        sc = "None" if a.score is None else str(a.score)
        kp = getattr(a, "keep", None)
        kp_s = "None" if kp is None else ("True" if kp else "False")
        dt = a.published_at.isoformat() if a.published_at else "None"
        ttl = (a.title or "").strip().replace("\n", " ")
        if len(ttl) > 140:
            ttl = ttl[:137] + "..."

        verdict = "IN " if ok else "OUT"
        print(f"[DIGEST_DEBUG] {verdict} | {dt} | src={src} keep={kp_s} score={sc} event={et} | {ttl}")
        for r in reasons:
            print(f"             - {r}")
        shown += 1


def get_articles_for_digest(
    db: Session,
    limit: int = 800,
    window: Optional[Tuple[datetime, datetime]] = None,
) -> list[Article]:
    q = (
        select(Article)
        .where(Article.fetched_at.is_not(None))
        .order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())
        .limit(limit)
    )
    rows = db.execute(q).scalars().all()

    if not _dbg_enabled():
        if window is not None:
            start, end = window
            rows = [a for a in rows if a.published_at is not None and start <= a.published_at < end]
        rows = [a for a in rows if _pass_threshold(a)]
        return rows

    debug_print_max = int(os.getenv("DIGEST_DEBUG_PRINT_MAX", "80"))
    decisions: list[tuple[Article, bool, list[str]]] = []
    filtered: list[Article] = []

    for a in rows:
        ok, reasons = _decision_reasons(a, window)
        decisions.append((a, ok, reasons))
        if ok:
            filtered.append(a)

    _dbg_print_decisions(decisions, max_lines=debug_print_max)
    return filtered