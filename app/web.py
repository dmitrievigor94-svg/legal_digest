# app/web.py — браузерный просмотр статей из БД
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, request, render_template_string
from sqlalchemy import select, func, or_

from app.db import SessionLocal
from app.models import Article

app = Flask(__name__)

LOCAL_TZ = ZoneInfo("Europe/Moscow")

PAGE_SIZE = 50

# ─── HTML-шаблон ──────────────────────────────────────────────────────────────

TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Legal Digest — просмотр статей</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       font-size: 13px; background: #f5f6fa; color: #222; }
header { background: #1a1a2e; color: #fff; padding: 14px 20px;
         display: flex; align-items: center; gap: 16px; }
header h1 { font-size: 16px; font-weight: 600; }
header .stats { font-size: 12px; opacity: .7; margin-left: auto; }

.filters { background: #fff; border-bottom: 1px solid #e0e0e0;
           padding: 10px 20px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.filters select, .filters input { border: 1px solid #ccc; border-radius: 4px;
                                   padding: 5px 8px; font-size: 12px; background: #fff; }
.filters button { background: #1a1a2e; color: #fff; border: none; border-radius: 4px;
                  padding: 5px 14px; font-size: 12px; cursor: pointer; }
.filters button:hover { background: #2d2d5e; }
.filters .reset { background: #eee; color: #555; }
.filters .reset:hover { background: #ddd; }

.summary-bar { padding: 8px 20px; font-size: 12px; color: #666;
               display: flex; gap: 20px; background: #fff; border-bottom: 1px solid #e8e8e8; }
.summary-bar span { font-weight: 600; }

table { width: 100%; border-collapse: collapse; }
thead th { background: #f0f1f5; text-align: left; padding: 8px 10px;
           font-size: 11px; font-weight: 600; color: #555; text-transform: uppercase;
           letter-spacing: .04em; border-bottom: 2px solid #ddd; position: sticky; top: 0; z-index: 1; }
tbody tr { border-bottom: 1px solid #eee; }
tbody tr:hover { background: #fafbff; }
td { padding: 7px 10px; vertical-align: top; }

.badge { display: inline-block; padding: 2px 7px; border-radius: 10px;
         font-size: 11px; font-weight: 500; white-space: nowrap; }
.keep-yes  { background: #d4f5e2; color: #1a6635; }
.keep-no   { background: #fde8e8; color: #9b2222; }
.keep-null { background: #f0f0f0; color: #999; }

.event-badge { background: #e8eeff; color: #3344bb; font-size: 11px;
               padding: 2px 6px; border-radius: 4px; white-space: nowrap; }
.tag { background: #f0f4ff; color: #4455cc; border-radius: 3px;
       padding: 1px 5px; font-size: 10px; margin: 1px; display: inline-block; }

.title-cell a { color: #1a1a2e; text-decoration: none; font-weight: 500; }
.title-cell a:hover { text-decoration: underline; color: #3344bb; }
.source-label { font-size: 11px; color: #888; margin-top: 2px; }

.reason { font-size: 11px; color: #666; font-style: italic; max-width: 260px; }
.summary { font-size: 12px; color: #333; max-width: 360px; line-height: 1.4; }

.sent-badge { background: #fff3cd; color: #856404; border-radius: 3px;
              padding: 1px 5px; font-size: 10px; }

.pagination { padding: 14px 20px; display: flex; gap: 6px; align-items: center;
              background: #fff; border-top: 1px solid #eee; }
.pagination a { padding: 5px 10px; border: 1px solid #ccc; border-radius: 4px;
                text-decoration: none; color: #333; font-size: 12px; }
.pagination a:hover { background: #f0f0f0; }
.pagination .current { background: #1a1a2e; color: #fff; border-color: #1a1a2e; }
.pagination .disabled { color: #ccc; pointer-events: none; border-color: #eee; }
.page-info { font-size: 12px; color: #666; margin-left: auto; }
</style>
</head>
<body>

<header>
  <h1>⚖️ Legal Digest</h1>
  <div class="stats">Всего в БД: {{ total_all }} статей</div>
</header>

<form method="get" action="/">
<div class="filters">
  <select name="keep">
    <option value="" {% if keep_filter == '' %}selected{% endif %}>Все решения</option>
    <option value="1" {% if keep_filter == '1' %}selected{% endif %}>✓ В дайджест</option>
    <option value="0" {% if keep_filter == '0' %}selected{% endif %}>✗ Отклонено</option>
    <option value="null" {% if keep_filter == 'null' %}selected{% endif %}>⏳ Не обработано</option>
  </select>

  <select name="source">
    <option value="">Все источники</option>
    {% for s in sources %}
    <option value="{{ s }}" {% if source_filter == s %}selected{% endif %}>{{ s }}</option>
    {% endfor %}
  </select>

  <select name="event_type">
    <option value="">Все типы</option>
    {% for et in event_types %}
    <option value="{{ et }}" {% if event_type_filter == et %}selected{% endif %}>{{ et }}</option>
    {% endfor %}
  </select>

  <select name="sent">
    <option value="" {% if sent_filter == '' %}selected{% endif %}>Все</option>
    <option value="1" {% if sent_filter == '1' %}selected{% endif %}>Отправлено в ТГ</option>
    <option value="0" {% if sent_filter == '0' %}selected{% endif %}>Не отправлено</option>
  </select>

  <input type="date" name="date_from" value="{{ date_from }}" placeholder="Дата с">
  <input type="date" name="date_to" value="{{ date_to }}" placeholder="Дата по">

  <input type="text" name="q" value="{{ q }}" placeholder="Поиск по заголовку..." style="width:200px">

  <button type="submit">Применить</button>
  <a href="/"><button type="button" class="reset">Сбросить</button></a>
</div>
</form>

<div class="summary-bar">
  Найдено: <span>{{ total }}</span> статей &nbsp;|&nbsp;
  В дайджест: <span style="color:#1a6635">{{ count_keep }}</span> &nbsp;|&nbsp;
  Отклонено: <span style="color:#9b2222">{{ count_reject }}</span> &nbsp;|&nbsp;
  Не обработано: <span style="color:#999">{{ count_null }}</span>
</div>

<div style="overflow-x:auto">
<table>
<thead>
  <tr>
    <th style="width:90px">Дата</th>
    <th>Заголовок / Источник</th>
    <th style="width:100px">Тип</th>
    <th style="width:110px">Теги</th>
    <th style="width:70px">Решение</th>
    <th style="width:220px">Причина / Резюме LLM</th>
  </tr>
</thead>
<tbody>
{% for a in articles %}
<tr>
  <td style="white-space:nowrap; color:#666; font-size:11px">
    {{ a.pub_date }}<br>
    {% if a.sent_at %}<span class="sent-badge">отправлено</span>{% endif %}
  </td>
  <td class="title-cell">
    <a href="{{ a.canonical_url }}" target="_blank">{{ a.title }}</a>
    <div class="source-label">{{ a.source_name }}</div>
  </td>
  <td>
    {% if a.event_type %}
    <span class="event-badge">{{ a.event_type }}</span>
    {% endif %}
  </td>
  <td>
    {% for tag in (a.tags or []) %}
    <span class="tag">{{ tag }}</span>
    {% endfor %}
  </td>
  <td>
    {% if a.keep is none %}
      <span class="badge keep-null">—</span>
    {% elif a.keep %}
      <span class="badge keep-yes">✓ взяли</span>
    {% else %}
      <span class="badge keep-no">✗ отклонено</span>
    {% endif %}
  </td>
  <td>
    {% if a.keep and a.llm_summary %}
      <div class="summary">{{ a.llm_summary }}</div>
    {% elif not a.keep and a.reason %}
      <div class="reason">{{ a.reason }}</div>
    {% endif %}
  </td>
</tr>
{% else %}
<tr><td colspan="6" style="text-align:center; padding:40px; color:#999">Статей не найдено</td></tr>
{% endfor %}
</tbody>
</table>
</div>

<div class="pagination">
  {% if page > 1 %}
    <a href="{{ page_url(page-1) }}">← Пред.</a>
  {% else %}
    <a class="disabled">← Пред.</a>
  {% endif %}

  {% for p in page_range %}
    {% if p == page %}
      <a class="current">{{ p }}</a>
    {% elif p == '...' %}
      <span style="padding:5px 4px; color:#ccc">…</span>
    {% else %}
      <a href="{{ page_url(p) }}">{{ p }}</a>
    {% endif %}
  {% endfor %}

  {% if page < total_pages %}
    <a href="{{ page_url(page+1) }}">След. →</a>
  {% else %}
    <a class="disabled">След. →</a>
  {% endif %}

  <span class="page-info">Страница {{ page }} из {{ total_pages }}</span>
</div>

</body>
</html>
"""


def _page_url(base_args: dict, p: int) -> str:
    args = {**base_args, "page": p}
    return "/?" + "&".join(f"{k}={v}" for k, v in args.items() if v not in (None, ""))


def _page_range(page: int, total_pages: int) -> list:
    if total_pages <= 9:
        return list(range(1, total_pages + 1))
    pages: list = []
    for p in range(1, total_pages + 1):
        if p == 1 or p == total_pages or abs(p - page) <= 2:
            pages.append(p)
        else:
            if pages and pages[-1] != "...":
                pages.append("...")
    return pages


@app.route("/")
def index():
    keep_filter = request.args.get("keep", "")
    source_filter = request.args.get("source", "")
    event_type_filter = request.args.get("event_type", "")
    sent_filter = request.args.get("sent", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    q = request.args.get("q", "").strip()
    page = max(1, int(request.args.get("page", 1) or 1))

    with SessionLocal() as db:
        # Списки для фильтров
        sources = [r[0] for r in db.execute(
            select(Article.source_id).distinct().order_by(Article.source_id)
        ).all()]
        event_types = [r[0] for r in db.execute(
            select(Article.event_type).where(Article.event_type.isnot(None)).distinct()
        ).all()]

        total_all = db.scalar(select(func.count()).select_from(Article))

        # Базовый запрос
        stmt = select(Article).order_by(Article.created_at.desc())

        if keep_filter == "1":
            stmt = stmt.where(Article.keep.is_(True))
        elif keep_filter == "0":
            stmt = stmt.where(Article.keep.is_(False))
        elif keep_filter == "null":
            stmt = stmt.where(Article.keep.is_(None))

        if source_filter:
            stmt = stmt.where(Article.source_id == source_filter)

        if event_type_filter:
            stmt = stmt.where(Article.event_type == event_type_filter)

        if sent_filter == "1":
            stmt = stmt.where(Article.sent_at.isnot(None))
        elif sent_filter == "0":
            stmt = stmt.where(Article.sent_at.is_(None))

        if date_from:
            dt = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
            stmt = stmt.where(Article.created_at >= dt)
        if date_to:
            dt = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc) + timedelta(days=1)
            stmt = stmt.where(Article.created_at < dt)

        if q:
            stmt = stmt.where(Article.title.ilike(f"%{q}%"))

        # Счётчики для summary bar
        sub = stmt.order_by(None).subquery()
        count_stmt = select(func.count(), sub.c.keep).group_by(sub.c.keep)
        count_keep = count_reject = count_null = 0
        for cnt, kp in db.execute(count_stmt).all():
            if kp is True:
                count_keep = cnt
            elif kp is False:
                count_reject = cnt
            else:
                count_null = cnt
        total = count_keep + count_reject + count_null

        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, total_pages)

        rows = db.execute(stmt.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).scalars().all()

        articles = []
        for a in rows:
            pub = (a.published_at or a.created_at)
            if pub and pub.tzinfo:
                pub = pub.astimezone(LOCAL_TZ)
            pub_str = pub.strftime("%d.%m.%Y") if pub else "—"

            reason = a.llm_reason or ""
            # llm_summary есть в модели
            articles.append({
                "id": a.id,
                "title": a.title,
                "canonical_url": a.canonical_url,
                "source_name": a.source_name,
                "source_id": a.source_id,
                "pub_date": pub_str,
                "event_type": a.event_type,
                "tags": a.tags or [],
                "keep": a.keep,
                "sent_at": a.sent_at,
                "llm_summary": a.llm_summary or "",
                "reason": reason,
            })

    base_args = {
        "keep": keep_filter, "source": source_filter, "event_type": event_type_filter,
        "sent": sent_filter, "date_from": date_from, "date_to": date_to, "q": q,
    }

    return render_template_string(
        TEMPLATE,
        articles=articles,
        total=total,
        total_all=total_all,
        count_keep=count_keep,
        count_reject=count_reject,
        count_null=count_null,
        page=page,
        total_pages=total_pages,
        page_range=_page_range(page, total_pages),
        page_url=lambda p: _page_url(base_args, p),
        sources=sources,
        event_types=event_types,
        keep_filter=keep_filter,
        source_filter=source_filter,
        event_type_filter=event_type_filter,
        sent_filter=sent_filter,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8002, debug=False)
