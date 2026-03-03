# app/published_at.py
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

UA = "LegalAlertsBot/1.0 (+https://example.local)"

# Для Минюста/РФ чаще всего время не указано -> считаем МСК
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

def _find_time_datetime(html: str) -> Optional[datetime]:
    m = re.search(r'<time[^>]+datetime=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    if m:
        return _parse_iso_dt(m.group(1))
    return None

def _find_meta_dates(html: str) -> Optional[datetime]:
    # article:published_time
    m = re.search(
        r'<meta[^>]+(?:property|name)=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    if m:
        return _parse_iso_dt(m.group(1))

    # og:updated_time / article:modified_time
    m = re.search(
        r'<meta[^>]+(?:property|name)=["\'](?:og:updated_time|article:modified_time)["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    if m:
        return _parse_iso_dt(m.group(1))

    # meta name="date"
    m = re.search(
        r'<meta[^>]+name=["\']date["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    if m:
        return _parse_iso_dt(m.group(1))

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
                dt = _parse_iso_dt(dp)
                if dt:
                    return dt
    return None

def _find_russian_date_in_text(html: str) -> Optional[datetime]:
    """
    Аккуратный парсер даты из "видимого" текста.
    Ключевые правила:
    - берём только верх страницы (чтобы не ловить даты из футера/меню)
    - dd.mm.yyyy берём ТОЛЬКО если рядом есть слово "дата"/"опублик"
    - словесные месяцы (25 февраля 2026) — можно без ключевых слов
    """
    # чистим HTML -> текст
    text = re.sub(r"<script.*?>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()

    # берем только верх страницы, чтобы не ловить мусор
    head = text[:2500]

    # helper: базовая валидация года
    now_year = datetime.now(MSK).year
    def _valid_year(y: int) -> bool:
        return (now_year - 3) <= y <= (now_year + 1)

    # 1) "25 февраля 2026 г. 10:30" (самый точный)
    m = re.search(
        r"\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})\s*(?:г\.?)?\s+(\d{1,2}):(\d{2})\b",
        head,
        flags=re.IGNORECASE,
    )
    if m:
        day = int(m.group(1))
        month = RU_MONTHS.get(m.group(2), 0)
        year = int(m.group(3))
        hh = int(m.group(4))
        mm = int(m.group(5))
        if month and _valid_year(year):
            return datetime(year, month, day, hh, mm, tzinfo=MSK)

    # 2) "25 февраля 2026 г." / "25 февраля 2026"
    m = re.search(
        r"\b(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})\s*(?:г\.?)?\b",
        head,
        flags=re.IGNORECASE,
    )
    if m:
        day = int(m.group(1))
        month = RU_MONTHS.get(m.group(2), 0)
        year = int(m.group(3))
        if month and _valid_year(year):
            return datetime(year, month, day, 10, 0, tzinfo=MSK)

    # 3) "Дата публикации: 25.02.2026" / "Опубликовано: 25.02.2026"
    m = re.search(
        r"\b(дата\s+публикац\w*|опубликован\w*|размещен\w*)\s*[:\-]?\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\b",
        head,
        flags=re.IGNORECASE,
    )
    if m:
        day = int(m.group(2))
        month = int(m.group(3))
        year = int(m.group(4))
        if 1 <= month <= 12 and 1 <= day <= 31 and _valid_year(year):
            return datetime(year, month, day, 10, 0, tzinfo=MSK)

    # 4) просто dd.mm.yyyy — НЕ берём (слишком много мусора)
    return None

def fetch_published_at(url: str, timeout: int = 20) -> Optional[datetime]:
    try:
        req = Request(url, headers={"User-Agent": UA})
        with urlopen(req, timeout=timeout) as resp:
            content_bytes = resp.read()
            html = content_bytes.decode("utf-8", errors="ignore")
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None
    except Exception:
        return None

    # порядок важен: сначала точные структурированные, потом эвристика по русскому тексту
    for fn in (_find_time_datetime, _find_meta_dates, _find_jsonld_date, _find_russian_date_in_text):
        dt = fn(html)
        if dt:
            return dt
    return None