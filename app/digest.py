# app/digest.py
from __future__ import annotations

from datetime import datetime
from collections import defaultdict
from typing import Optional, Tuple

import html
import os

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
    "LAW_DRAFT": "Проекты НПА",
    "LAW_ADOPTED": "Законы и подзаконные акты",
    "GUIDANCE": "Разъяснения регулятора",
    "ENFORCEMENT": "Административная практика",
    "COURTS": "Судебная практика",
    "MARKET_CASES": "Иное на рынке",
}

TG_SUMMARY_MAX_CHARS = 320
TG_MAX_PER_SECTION = 25


def _dbg_enabled() -> bool:
    return os.getenv("DIGEST_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _pass_threshold(a: Article) -> bool:
    """
    ГЛАВНОЕ:
    - если у статьи есть a.keep (новая логика) -> используем ТОЛЬКО keep
    - иначе fallback на старую логику (score)

    ВАЖНОЕ ИЗМЕНЕНИЕ:
    - если keep is None и score is None -> НЕ пропускаем (раньше пропускало и давало мусор)
    """
    keep = getattr(a, "keep", None)
    if keep is not None:
        return bool(keep)

    # legacy fallback (если keep ещё нет в БД/модели)
    if a.score is None:
        return False
    return a.score >= 1


def _decision_reasons(a: Article, window: Optional[Tuple[datetime, datetime]]) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    # 0) только обработанные
    if a.fetched_at is None:
        return False, ["not_processed: fetched_at is None"]

    # 1) окно дат
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

    # 2) решение keep/score
    keep = getattr(a, "keep", None)
    if keep is not None:
        if keep:
            reasons.append("keep=True (classifier)")
            ok = True
        else:
            return False, ["keep=False (classifier)"]
    else:
        # legacy
        if a.score is None:
            return False, ["score=None (legacy fail)"]
        if a.score >= 1:
            reasons.append(f"legacy score={a.score} >=1")
            ok = True
        else:
            return False, [f"legacy score={a.score} <1"]

    # 3) event/topic fallback
    if not a.event_type and not a.topic:
        reasons.append("no event_type/topic (will fallback to MARKET_CASES)")

    return ok, reasons


def _dbg_print_decisions(decisions: list[tuple[Article, bool, list[str]]], max_lines: int = 80) -> None:
    total = len(decisions)
    in_cnt = sum(1 for _, ok, _ in decisions if ok)
    out_cnt = total - in_cnt

    print(f"[DIGEST_DEBUG] decisions: total={total} IN={in_cnt} OUT={out_cnt}")

    # сначала OUT
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
    # ВАЖНО: берём только обработанные (fetched_at != None),
    # иначе в дайджест попадёт "сырьё" без keep/event_type.
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

    # debug режим
    decisions: list[tuple[Article, bool, list[str]]] = []
    filtered: list[Article] = []

    for a in rows:
        ok, reasons = _decision_reasons(a, window)
        decisions.append((a, ok, reasons))
        if ok:
            filtered.append(a)

    _dbg_print_decisions(decisions, max_lines=int(os.getenv("DIGEST_DEBUG_MAX", "80")))
    return filtered


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
        key = (a.event_type or a.topic or "MARKET_CASES")
        grouped[key].append(a)

    first_section = True

    for event_type in EVENT_ORDER:
        items = grouped.get(event_type, [])
        if not items:
            continue

        if not first_section:
            lines.append("")
        lines.append(f"<b>{html.escape(EVENT_TITLES.get(event_type, event_type))}</b>")
        lines.append("")
        first_section = False

        items_sorted = sorted(
            items,
            key=lambda a: (
                a.published_at is None,
                a.published_at
                or datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo),
                a.created_at,
            ),
            reverse=True,
        )

        items_sorted = items_sorted[:TG_MAX_PER_SECTION]

        for i, a in enumerate(items_sorted, start=1):
            url = (a.canonical_url or a.url or "").strip()
            ttl = (a.title or "").strip()
            ttl_html = html.escape(ttl)

            if url:
                line = f'{i}. <a href="{html.escape(url)}">{ttl_html}</a>'
            else:
                line = f"{i}. {ttl_html}"

            lines.append(line)

            s = (a.summary or "").strip()
            if s:
                if len(s) > TG_SUMMARY_MAX_CHARS:
                    s = s[: TG_SUMMARY_MAX_CHARS - 1].rstrip() + "…"
                lines.append(f"<blockquote>{html.escape(s)}</blockquote>")

            if i != len(items_sorted):
                lines.append("")

    article_ids = [a.id for a in rows if a.id is not None]
    return ("\n".join(lines), article_ids)