import httpx
import trafilatura

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X) legal_digest/1.0"

def fetch_and_extract_text(url: str) -> str | None:
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=25,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            r = client.get(url)
            r.raise_for_status()
            html = r.text
    except Exception:
        return None

    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        include_links=False,
        favor_recall=True,
    )
    if not text:
        return None

    # чуть чистим пробелы
    text = " ".join(text.split())
    return text or None

def make_short_summary(text: str, max_chars: int = 700) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"

def is_bad_extracted_text(text: str) -> bool:
    t = (text or "").lower()
    if not t:
        return True
    # явные признаки меню/навигации
    bad_markers = [
        "о фас россии",
        "миссия, цели, ценности",
        "противодействие коррупции",
        "государственная служба",
        "политика в области качества",
    ]
    hits = sum(1 for m in bad_markers if m in t)
    return hits >= 2  # если совпали 2+ маркера — это почти точно не статья

def clean_fas_text(text: str) -> str:
    if not text:
        return text
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    cleaned = []
    for ln in lines:
        # выкидываем типовой слоган/шапку
        if ln.lower().startswith("свобода конкуренции"):
            continue
        if ln.lower() == "свобода конкуренции и эффективная защита предпринимательства ради будущего россии":
            continue
        cleaned.append(ln)

    # убираем подряд идущие дубли строк
    dedup = []
    prev = None
    for ln in cleaned:
        if ln == prev:
            continue
        dedup.append(ln)
        prev = ln

    return " ".join(dedup)