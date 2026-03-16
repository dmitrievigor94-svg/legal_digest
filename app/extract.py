# app/extract.py
import io
import re
import httpx
import trafilatura

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X) legal_digest/1.0"


def _extract_pdf_text(content: bytes) -> str | None:
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(io.BytesIO(content))
    except Exception:
        return None
    if not text:
        return None
    # убираем мусорные символы (■, □ и прочие артефакты PDF)
    text = re.sub(r"[■□▪▫◆◇●○]", "", text)
    text = " ".join(text.split())
    return text or None


def _extract_rtf_text(content: bytes) -> str | None:
    try:
        from striprtf.striprtf import rtf_to_text
        text = rtf_to_text(content.decode("cp1251", errors="replace"))
    except Exception:
        return None
    text = " ".join(text.split())
    return text or None


def _is_pdf(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    if "pdf" in content_type:
        return True
    final_url = str(response.url).split("?")[0].split("#")[0]
    return final_url.endswith(".pdf")


def _is_rtf(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    if "rtf" in content_type:
        return True
    final_url = str(response.url).split("?")[0].split("#")[0]
    return final_url.endswith(".rtf")


def fetch_and_extract_text(url: str) -> str | None:
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=25,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            r = client.get(url)
            r.raise_for_status()
    except Exception:
        return None

    if _is_pdf(r):
        return _extract_pdf_text(r.content)

    if _is_rtf(r):
        return _extract_rtf_text(r.content)

    text = trafilatura.extract(
        r.text,
        include_comments=False,
        include_tables=False,
        include_links=False,
        favor_recall=True,
    )
    if not text:
        return None

    text = " ".join(text.split())
    return text or None


def make_short_summary(text: str, max_chars: int = 700) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    # Fix #15: режем по границе слова, не посередине
    return text[:max_chars].rsplit(' ', 1)[0].rstrip() + "…"


def is_bad_extracted_text(text: str) -> bool:
    t = (text or "").lower()
    if not t:
        return True
    bad_markers = [
        "о фас россии",
        "миссия, цели, ценности",
        "противодействие коррупции",
        "государственная служба",
        "политика в области качества",
    ]
    hits = sum(1 for m in bad_markers if m in t)
    return hits >= 2


def clean_fas_text(text: str) -> str:
    if not text:
        return text
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    cleaned = []
    for ln in lines:
        if ln.lower().startswith("свобода конкуренции"):
            continue
        if ln.lower() == "свобода конкуренции и эффективная защита предпринимательства ради будущего россии":
            continue
        cleaned.append(ln)

    dedup = []
    prev = None
    for ln in cleaned:
        if ln == prev:
            continue
        dedup.append(ln)
        prev = ln

    return " ".join(dedup)