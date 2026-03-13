from __future__ import annotations

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict
from typing import Optional, Tuple

import html
import os
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article

# ---------------------------------------------------------------------------
# LLM-кластеризация: группируем статьи об одном и том же событии
# ---------------------------------------------------------------------------

import json as _json
import httpx as _httpx
import urllib3 as _urllib3

_urllib3.disable_warnings()

_CLUSTER_SYSTEM = """Ты — ассистент редактора юридического дайджеста.
Тебе дан список новостей в формате: индекс | заголовок | краткое описание (если есть).

Задача: найди группы статей об одном и том же конкретном событии.

ВАЖНО:
- Группируй только когда это реально одно и то же событие.
- Не группируй статьи только потому, что они на близкую тему.
- Не группируй статьи только потому, что в них фигурирует один и тот же регулятор
  (например, КС, ВС, ФАС, ЦБ, Минцифры и т.п.).

Считать одним событием:
- одно конкретное судебное дело / один иск, освещённый разными СМИ;
- одно постановление КС/ВС/суда, описанное разными заголовками;
- один нормативный акт / законопроект, описанный с разных сторон;
- один и тот же спор вокруг одной компании / бренда / препарата.

Не считать одним событием:
- просто две новости о КС или ФАС;
- просто две новости о налогах, бизнесе, проверках, банках, IT, рекламе и т.п.;
- просто две новости, где есть похожая правовая лексика;
- две разные инициативы одного ведомства;
- две разные новости Минцифры;
- две разные новости про бизнес-контроль, проверки, свидетелей, профилактические визиты и т.п.

Примеры:
✓ "Кристалл хочет отсудить знак Trump" + "В России решили отсудить права на знак Trump" → одна группа
✓ "КС установил правила принудительных лицензий на Трикафту" + "Постановление КС N 13-П" + "КС: интересы патентообладателей не абсолютны" → одна группа
✓ "ВС отменил решения по спору Аксельфарма с ФАС" + "У дженериков выявили нарушения" [описание: «дело Аксельфарма / Axitinib / Pfizer»] → одна группа

✗ "Неявка свидетеля по повестке налоговой" + "Право бизнеса на профилактические визиты могут расширить" → НЕ одна группа
✗ "Минцифры поможет Сколково сохранить IT-ипотеку" + "На Госуслугах появится механизм разблокировки банковских карт" → НЕ одна группа
✗ "Суд ЕС разрешил блокировать активы компаний" + "Суд ЕС запретил участие в собраниях акционеров" → НЕ одна группа, если это разные дела

Ответь ТОЛЬКО валидным JSON и ничем больше:
[[0,3],[1,4,7]]
Если групп нет — пустой список: []"""


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
    "_other",
]

TAG_TITLES = {
    "pdn":           "Персональные данные",
    "advertising":   "Реклама",
    "competition":   "Антимонопольное",
    "banking":       "Банки и финансы",
    "telecom":       "Телеком",
    "it_platforms":  "IT и платформы",
    "cybersecurity": "Кибербезопасность",
    "ip":            "Интеллектуальная собственность",
    "consumers":     "Защита потребителей",
    "_other":        "Прочее",
}

EVENT_BADGE = {
    "LAW_DRAFT":    "📝",
    "LAW_ADOPTED":  "📄",
    "GUIDANCE":     "💬",
    "ENFORCEMENT":  "🗃️",
    "COURTS":       "⚖️",
    "MARKET_CASES": "📊",
}

SOURCE_LABELS = {
    "fas_news": "ФАС.Новости",
    "fas_clarifications": "ФАС.Разъяснения",
    "fas_acts": "ФАС.НПА",
    "fas_media": "ФАС.СМИ",
    "cbr_events": "Банк России.События",
    "cbr_press": "Банк России.Пресс-релизы",
    "rapsi_judicial": "РАПСИ",
    "rapsi_publications": "РАПСИ",
    "pravo_ru": "Право.ru",
    "drussia_all": "D-Russia",
    "consultant_hotdocs": "КонсультантПлюс",
    "consultant_law_news": "КонсультантПлюс",
    "consultant_law_drafts": "КонсультантПлюс",
    "fts_news": "ФТС",
    "gov_all": "Правительство",
    "rg_main": "Российская газета",
    "rpn_news": "Роспотребнадзор",
    "eg_online_news": "Экономика и жизнь",
}

TG_SUMMARY_MAX_CHARS = 320
TG_MAX_PER_SECTION = 15
TG_REASON_MAX_CHARS = 300

_FALLBACK_DT = datetime.min.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Кластеризация: строгий candidate stage
# ---------------------------------------------------------------------------

_CLUSTER_GENERIC_TOKENS = {
    "суд",
    "суда",
    "суде",
    "судом",
    "суды",
    "судебный",
    "судебного",
    "судебной",
    "судебную",
    "решение",
    "решения",
    "постановление",
    "постановления",
    "дело",
    "дела",
    "спор",
    "спора",
    "жалоба",
    "жалобы",
    "закон",
    "закона",
    "законопроект",
    "проекта",
    "проект",
    "правила",
    "право",
    "бизнес",
    "бизнеса",
    "компания",
    "компании",
    "компаний",
    "группа",
    "рынок",
    "рынка",
    "услуга",
    "услуги",
    "услуг",
    "механизм",
    "механизма",
    "порядок",
    "контроль",
    "контроля",
    "регулирование",
    "регулирования",
    "требования",
    "инициатива",
    "инициативы",
    "карты",
    "карт",
    "банковских",
    "банковские",
    "банковский",
    "госуслугах",
    "госуслуги",
    "налоговой",
    "налоговый",
    "свидетеля",
    "свидетель",
    "проверки",
    "проверка",
    "визиты",
    "визитов",
    "профилактические",
    "профилактический",
    "лицензии",
    "лицензия",
    "патент",
    "патента",
    "права",
    "прав",
    "товарный",
    "знак",
    "активы",
    "санкциями",
    "санкции",
    "санкционный",
    "комплаенс",
    "иностранными",
    "иностранных",
    "инвестициями",
    "инвестиции",
    "картель",
    "картеля",
    "монопольно",
    "владивостока",
    "аэропорта",
    "аэропорт",
    "фас",
    "кс",
    "вс",
    "цб",
    "минцифры",
    "роскомнадзор",
    "госдума",
    "правительства",
    "правительство",
    "россии",
    "российской",
    "российский",
    "рф",
}

_CLUSTER_STOPWORDS = {
    "и", "в", "во", "на", "по", "к", "ко", "с", "со", "о", "об", "от", "за",
    "из", "у", "для", "при", "над", "под", "или", "ли", "не", "но", "что",
    "как", "это", "его", "ее", "их", "а", "также", "так", "же", "до", "после",
    "если", "бы", "были", "был", "была", "быть", "может", "могут", "можно",
    "нельзя", "через", "между", "года", "году", "год", "лет", "летний",
    "один", "одного", "одной", "одну", "двух", "трех", "трёх", "новый",
    "нового", "новой", "новые", "новых", "об", "обо", "при", "без", "под",
    "над", "от", "вне", "тот", "та", "те", "эти", "этот", "эта", "этом",
}

_QUOTED_RE = re.compile(r"[«\"]([^»\"]{2,120})[»\"]")
_ACT_REF_RE = re.compile(
    r"""
    (?:
        \b\d{1,4}-[А-ЯA-ZЁёа-яa-z]{1,4}\b
        |
        \b[АA]\d{2,3}-\d+/\d{4}\b
        |
        \b\d{6,10}-\d+\b
        |
        \bN\s*\d{1,10}(?:-\d+)?(?:-[А-ЯA-ZЁёа-яa-z]{1,4})?\b
    )
    """,
    re.X | re.I,
)

_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9\-]{4,}")
_UPPER_ENTITY_RE = re.compile(
    r"""
    (?:
        [A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9&.\-]{2,}
    )
    """,
    re.X,
)


def _cluster_text(a: Article) -> str:
    title = (a.title or "").strip()
    summary = (getattr(a, "llm_summary", None) or getattr(a, "summary", None) or "").strip()
    if summary:
        return f"{title} {summary}"
    return title


def _normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _normalize_token(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = s.strip("«»\"'`()[]{}:;,.!?/\\")
    return s


def _extract_act_refs(text: str) -> set[str]:
    refs: set[str] = set()
    for m in _ACT_REF_RE.findall(text or ""):
        ref = _normalize_ws(str(m)).lower().replace("ё", "е")
        ref = ref.replace("№", "n").replace(" n ", " n ")
        refs.add(ref)
    return refs


def _extract_quoted_entities(text: str) -> set[str]:
    out: set[str] = set()
    for m in _QUOTED_RE.findall(text or ""):
        q = _normalize_token(m)
        if len(q) >= 4:
            out.add(q)
    return out


def _extract_upper_entities(text: str) -> set[str]:
    out: set[str] = set()
    for m in _UPPER_ENTITY_RE.findall(text or ""):
        tok = _normalize_token(m)
        if len(tok) < 4:
            continue
        if tok in _CLUSTER_STOPWORDS or tok in _CLUSTER_GENERIC_TOKENS:
            continue
        out.add(tok)
    return out


def _extract_anchor_tokens(text: str) -> set[str]:
    out: set[str] = set()
    for m in _TOKEN_RE.findall((text or "").replace("ё", "е")):
        tok = _normalize_token(m)
        if len(tok) < 4:
            continue
        if tok.isdigit():
            continue
        if tok in _CLUSTER_STOPWORDS or tok in _CLUSTER_GENERIC_TOKENS:
            continue
        out.add(tok)
    return out


def _article_cluster_features(a: Article) -> dict:
    text = _cluster_text(a)
    title = (a.title or "").strip()

    act_refs = _extract_act_refs(text)
    quoted = _extract_quoted_entities(text)
    upper = _extract_upper_entities(text)
    anchors = _extract_anchor_tokens(text)

    strong_entities = set(quoted) | {x for x in upper if len(x) >= 5}
    rare_anchors = {x for x in anchors if len(x) >= 5}

    return {
        "text": text,
        "title": title,
        "act_refs": act_refs,
        "quoted": quoted,
        "upper": upper,
        "anchors": anchors,
        "strong_entities": strong_entities,
        "rare_anchors": rare_anchors,
    }


def _is_strong_duplicate_candidate(f1: dict, f2: dict) -> bool:
    common_refs = f1["act_refs"] & f2["act_refs"]
    if common_refs:
        return True

    common_entities = f1["strong_entities"] & f2["strong_entities"]
    if len(common_entities) >= 2:
        return True

    if len(common_entities) >= 1:
        common_rare = f1["rare_anchors"] & f2["rare_anchors"]
        if len(common_rare) >= 2:
            return True
        if any(len(x) >= 7 for x in common_entities):
            return True

    common_rare = f1["rare_anchors"] & f2["rare_anchors"]
    if len(common_rare) >= 3:
        return True

    return False


def _build_candidate_components(articles: list[Article]) -> list[list[int]]:
    n = len(articles)
    if n < 2:
        return []

    feats = [_article_cluster_features(a) for a in articles]
    graph: list[set[int]] = [set() for _ in range(n)]

    for i in range(n):
        for j in range(i + 1, n):
            if _is_strong_duplicate_candidate(feats[i], feats[j]):
                graph[i].add(j)
                graph[j].add(i)

    seen = [False] * n
    components: list[list[int]] = []

    for i in range(n):
        if seen[i] or not graph[i]:
            continue
        stack = [i]
        seen[i] = True
        comp: list[int] = []
        while stack:
            v = stack.pop()
            comp.append(v)
            for to in graph[v]:
                if not seen[to]:
                    seen[to] = True
                    stack.append(to)
        comp.sort()
        if len(comp) >= 2:
            components.append(comp)

    return components


def _cluster_articles_llm_subset(articles: list[Article], component: list[int]) -> list[list[int]]:
    """
    component — список глобальных индексов статей.
    Возвращает список кластеров тоже в глобальных индексах.
    """
    if len(component) < 2:
        return []

    auth_key = os.environ.get("GIGACHAT_AUTH_KEY", "")
    if not auth_key:
        return []

    local_articles = [articles[i] for i in component]

    items: list[str] = []
    for local_idx, a in enumerate(local_articles):
        title = _normalize_ws((a.title or "").replace("\n", " "))
        summary = _normalize_ws((getattr(a, "llm_summary", None) or getattr(a, "summary", None) or "").replace("\n", " "))
        if summary:
            items.append(f"{local_idx} | {title} | {summary[:220]}")
        else:
            items.append(f"{local_idx} | {title}")

    user_msg = "Новости:\n" + "\n".join(items)

    if _dbg_enabled():
        print(f"[CLUSTER] component {component}:")
        for idx, line in enumerate(items):
            print(f"  {idx} | {line[:260]}")

    try:
        from app.classify_llm import _token_manager, _rate_limiter
        _rate_limiter.wait()
        token = _token_manager.get_token(auth_key)
    except Exception as e:
        if _dbg_enabled():
            print(f"[CLUSTER] token error: {e}")
        return []

    try:
        resp = _httpx.post(
            "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "model": "GigaChat",
                "max_tokens": 256,
                "messages": [
                    {"role": "system", "content": _CLUSTER_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
            },
            verify=False,
            timeout=20,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        if _dbg_enabled():
            print(f"[CLUSTER] api error: {e}")
        return []

    if _dbg_enabled():
        print(f"[CLUSTER] raw response: {raw[:400]}")

    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return []

    try:
        parsed = _json.loads(m.group())
    except Exception:
        return []

    if not isinstance(parsed, list):
        return []

    result: list[list[int]] = []
    used_local: set[int] = set()

    for group in parsed:
        if not isinstance(group, list) or len(group) < 2:
            continue

        valid_local: list[int] = []
        for idx in group:
            if isinstance(idx, int) and 0 <= idx < len(component) and idx not in used_local:
                valid_local.append(idx)
                used_local.add(idx)

        if len(valid_local) >= 2:
            result.append([component[idx] for idx in valid_local])

    return result


def _cluster_articles_llm(articles: list[Article]) -> list[list[int]]:
    """
    Возвращает список кластеров глобальных индексов.
    ВАЖНО:
    - candidate stage строгий;
    - если LLM не подтвердил кластер, ничего не склеиваем;
    - fallback'а больше нет.
    """
    if len(articles) < 2:
        return []

    components = _build_candidate_components(articles)

    if _dbg_enabled():
        print(f"[CLUSTER] candidate components: {components}")

    final_clusters: list[list[int]] = []
    used_global: set[int] = set()

    for comp in components:
        llm_groups = _cluster_articles_llm_subset(articles, comp)

        for group in llm_groups:
            cleaned = [idx for idx in group if idx not in used_global]
            if len(cleaned) >= 2:
                final_clusters.append(cleaned)
                used_global.update(cleaned)

    if _dbg_enabled():
        for g in final_clusters:
            titles = [articles[i].title or "" for i in g]
            print(f"[CLUSTER] final group {g}: {titles}")

    return final_clusters


# ---------------------------------------------------------------------------
# Digest helpers
# ---------------------------------------------------------------------------

def _article_tags(a: Article) -> list[str]:
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


def _format_materials_count(total: int) -> str:
    if total % 10 == 1 and total % 100 != 11:
        word = "материал"
    elif 2 <= total % 10 <= 4 and total % 100 not in range(12, 15):
        word = "материала"
    else:
        word = "материалов"
    return f"{total} {word}"


def _render_title(a: Article) -> str:
    url = (a.canonical_url or a.url or "").strip()
    ttl = _normalize_ws((a.title or "").strip())
    if len(ttl) > 100:
        ttl = ttl[:99].rstrip() + "…"

    ttl_html = html.escape(ttl)
    if url:
        return f'<a href="{html.escape(url)}">{ttl_html}</a>'
    return ttl_html


def _source_label(a: Article) -> str:
    source_id = (getattr(a, "source_id", None) or "").strip()
    if source_id and source_id in SOURCE_LABELS:
        return SOURCE_LABELS[source_id]

    source_name = _normalize_ws((getattr(a, "source_name", None) or "").strip())
    if source_name:
        if " — " in source_name:
            left, right = source_name.split(" — ", 1)
            if left and right:
                return f"{left}.{right.capitalize()}"
        return source_name

    return source_id or "Источник"


def _render_related_links(items: list[Article]) -> str:
    parts: list[str] = []
    seen_labels: set[str] = set()

    for s in items:
        label = html.escape(_source_label(s))
        url = (s.canonical_url or s.url or "").strip()

        # если один и тот же источник повторяется несколько раз, второй раз не дублируем
        unique_key = f"{label}|{url}"
        if unique_key in seen_labels:
            continue
        seen_labels.add(unique_key)

        if url:
            parts.append(f'<a href="{html.escape(url)}">{label}</a>')
        else:
            parts.append(label)

    return " • ".join(parts)


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
    lines.append(f"📌 <b>Юридический дайджест за {html.escape(day_str)} из {_format_materials_count(total)}</b>")

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

    clusters = _cluster_articles_llm(rows)

    cluster_of: dict[int, int] = {}
    cluster_pos: dict[int, int] = {}
    for ci, group in enumerate(clusters):
        for pos, idx in enumerate(group):
            aid = id(rows[idx])
            cluster_of[aid] = ci
            cluster_pos[aid] = pos

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
        lines.append(f"<b>→ {html.escape(TAG_TITLES[tag])}</b>")

        secondary_ids: set[int] = set()
        for a in items_sorted:
            if cluster_pos.get(id(a), 0) > 0:
                secondary_ids.add(id(a))

        cluster_secondaries: dict[int, list[Article]] = defaultdict(list)
        for a in items_sorted:
            if id(a) in secondary_ids:
                ci = cluster_of[id(a)]
                cluster_secondaries[ci].append(a)

        rendered_clusters: set[int] = set()

        for a in items_sorted:
            if id(a) in secondary_ids:
                continue

            badge = EVENT_BADGE.get(a.event_type or "", "")
            title_part = _render_title(a)

            lines.append("")
            lines.append(f"{badge} {title_part}" if badge else title_part)

            summary_text = _best_summary(a, TG_REASON_MAX_CHARS)
            if summary_text:
                lines.append(f"<blockquote>{html.escape(summary_text)}</blockquote>")

            ci = cluster_of.get(id(a))
            if ci is not None and ci not in rendered_clusters:
                siblings = cluster_secondaries.get(ci, [])
                if siblings:
                    rendered = _render_related_links(siblings)
                    if rendered:
                        lines.append(f"<i>📎 Другие материалы по теме: {rendered}</i>")
                rendered_clusters.add(ci)

    article_ids = [a.id for a in rows if a.id is not None]
    return ("\n".join(lines), article_ids)


# ---------------------------------------------------------------------------
# Digest filtering/debug
# ---------------------------------------------------------------------------

def _dbg_enabled() -> bool:
    return os.getenv("DIGEST_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _pass_threshold(a: Article) -> bool:
    keep = getattr(a, "keep", None)
    if keep is not None:
        return bool(keep)
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