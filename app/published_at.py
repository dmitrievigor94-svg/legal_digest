# app/published_at.py
from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

try:
    from lxml import html as lxml_html
except Exception:  # pragma: no cover
    lxml_html = None

UA = "LegalAlertsBot/1.0"

MSK = timezone(timedelta(hours=3))

RU_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}

RE_DDMMYYYY = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b")
RE_RU_DATE = re.compile(
    r"\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})\b",
    flags=re.IGNORECASE,
)
RE_ISO = re.compile(
    r"\b(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2})(?::(\d{2}))?)?(Z|[+-]\d{2}:?\d{2})?\b"
)


def _parse_iso_dt(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _parse_ddmmyyyy(s: str) -> Optional[datetime]:
    m = RE_DDMMYYYY.search(s or "")
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return datetime(y, mo, d, 10, 0, tzinfo=MSK)
    except Exception:
        return None


def _parse_ru_text_date(s: str) -> Optional[datetime]:
    m = RE_RU_DATE.search((s or "").lower())
    if not m:
        return None
    d = int(m.group(1))
    mo = RU_MONTHS.get(m.group(2).lower())
    y = int(m.group(3))
    if not mo:
        return None
    try:
        return datetime(y, mo, d, 10, 0, tzinfo=MSK)
    except Exception:
        return None


def _find_time_datetime(html: str) -> Optional[datetime]:
    m = re.search(r'<time[^>]+datetime=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    if m:
        return _parse_iso_dt(m.group(1))
    return None


def _find_meta_dates(html: str) -> Optional[datetime]:
    for pat in (
        r'<meta[^>]+(?:property|name)=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+(?:property|name)=["\']og:published_time["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+(?:property|name)=["\']datePublished["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']date["\'][^>]+content=["\']([^"\']+)["\']',
    ):
        m = re.search(pat, html, flags=re.IGNORECASE)
        if m:
            dt = _parse_iso_dt(m.group(1)) or _parse_ddmmyyyy(m.group(1)) or _parse_ru_text_date(m.group(1))
            if dt:
                return dt
    return None


def _find_jsonld_date(html: str) -> Optional[datetime]:
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        raw = m.group(1).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue

        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            dp = obj.get("datePublished") or obj.get("dateCreated") or obj.get("dateModified")
            if isinstance(dp, str):
                dt = _parse_iso_dt(dp) or _parse_ddmmyyyy(dp) or _parse_ru_text_date(dp)
                if dt:
                    return dt
    return None


def _decode_html(url: str, content_bytes: bytes, content_type: str | None) -> str:
    url_l = (url or "").lower()
    ctype_l = (content_type or "").lower()
    head_l = content_bytes[:2000].lower()

    is_rpn = "rospotrebnadzor.ru" in url_l
    has_1251 = ("windows-1251" in ctype_l) or (b"windows-1251" in head_l) or (b"charset=windows-1251" in head_l)

    if is_rpn and has_1251:
        try:
            return content_bytes.decode("cp1251", errors="replace")
        except Exception:
            pass

    try:
        return content_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return content_bytes.decode("utf-8", errors="replace")


def _rpn_extract_date(html: str) -> Optional[datetime]:
    """
    ТОЛЬКО ДЛЯ rospotrebnadzor.ru:
    1) пробуем достать дату из типовых блоков/тайма
    2) если не нашли — ищем дату рядом со словами "опубликовано/дата"
    3) sanity: дата не должна быть сильно старше (иначе это мусор со страницы)
    """
    now_msk = datetime.now(MSK)
    too_old = now_msk - timedelta(days=60)  # РПН нам нужен как новостной поток, старьё считать ошибкой парсинга

    # 0) если есть lxml — вытащим по XPath (самый надёжный способ)
    if lxml_html is not None:
        try:
            doc = lxml_html.fromstring(html)
            xps = [
                # meta / time
                "//meta[@itemprop='datePublished']/@content",
                "//meta[@property='article:published_time']/@content",
                "//meta[@property='og:published_time']/@content",
                "//time/@datetime",
                "//time/text()",
                # типовые классы даты
                "//*[contains(@class,'date') or contains(@class,'news-date') or contains(@class,'article-date')]/text()",
            ]
            for xp in xps:
                vals = doc.xpath(xp) or []
                for v in vals:
                    v = " ".join(str(v).split())
                    dt = _parse_iso_dt(v) or _parse_ddmmyyyy(v) or _parse_ru_text_date(v)
                    if dt and dt >= too_old:
                        return dt
        except Exception:
            pass

    # 1) regex по ключевым словам (чтобы не ловить “левые” даты)
    m = re.search(
        r"\b(опубликован\w*|дата\s+публикац\w*|размещен\w*)\s*[:\-]?\s*(\d{1,2}\.\d{1,2}\.\d{4})\b",
        html,
        flags=re.IGNORECASE,
    )
    if m:
        dt = _parse_ddmmyyyy(m.group(2))
        if dt and dt >= too_old:
            return dt

    m = re.search(
        r"\b(опубликован\w*|дата\s+публикац\w*|размещен\w*)\s*[:\-]?\s*(\d{1,2}\s+[а-я]+?\s+\d{4})\b",
        html,
        flags=re.IGNORECASE,
    )
    if m:
        dt = _parse_ru_text_date(m.group(2))
        if dt and dt >= too_old:
            return dt

    # 2) последнее: словесная дата в “верхней” части текста (но с sanity)
    text = re.sub(r"<script.*?>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    head = text[:2500]

    dt = _parse_ru_text_date(head)
    if dt and dt >= too_old:
        return dt

    # dd.mm.yyyy без ключевых слов специально НЕ берём — слишком много ложных срабатываний.
    return None


def fetch_published_at(url: str, timeout: int = 20) -> Optional[datetime]:
    try:
        req = Request(url, headers={"User-Agent": UA})
        with urlopen(req, timeout=timeout) as resp:
            content_bytes = resp.read()
            content_type = resp.headers.get("Content-Type")
            html = _decode_html(url, content_bytes, content_type)
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None
    except Exception:
        return None

    # Точечное правило для РПН: сначала его спец-парсер
    if "rospotrebnadzor.ru" in (url or "").lower():
        dt = _rpn_extract_date(html)
        if dt:
            return dt

    # Общий пайплайн для остальных (как было)
    for fn in (_find_time_datetime, _find_meta_dates, _find_jsonld_date):
        dt = fn(html)
        if dt:
            return dt

    # Общая “русская” эвристика (если у вас она была раньше — оставляем простой вариант по ключевым словам)
    # ВАЖНО: dd.mm.yyyy без ключевых слов не берём.
    dt = None
    m = re.search(
        r"\b(опубликован\w*|дата\s+публикац\w*|размещен\w*)\s*[:\-]?\s*(\d{1,2}\.\d{1,2}\.\d{4})\b",
        html,
        flags=re.IGNORECASE,
    )
    if m:
        dt = _parse_ddmmyyyy(m.group(2))
    if dt:
        return dt

    return None