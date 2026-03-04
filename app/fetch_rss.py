import hashlib
from datetime import datetime, timezone
from typing import Iterable, Optional
from email.utils import parsedate_to_datetime

import feedparser
import httpx
from lxml import etree
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Article

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X) legal_digest/1.0"


def _normalize_url(url: str) -> str:
    return (url or "").strip()


def _hash_text(s: str) -> str:
    s_norm = " ".join((s or "").split()).strip().lower()
    return hashlib.sha256(s_norm.encode("utf-8")).hexdigest()


def _parse_published(entry) -> Optional[datetime]:
    t = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not t:
        return None
    return datetime(*t[:6], tzinfo=timezone.utc)


def _download_feed(feed_url: str, ssl_verify: bool = True) -> tuple[bytes, str, str]:
    with httpx.Client(
        follow_redirects=True,
        timeout=25,
        verify=ssl_verify,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.9, */*;q=0.8",
        },
    ) as client:
        r = client.get(feed_url)
        r.raise_for_status()
        content_type = (r.headers.get("content-type") or "").lower()
        final_url = str(r.url)
        return r.content, content_type, final_url


def _safe_parse_dt(s: str) -> Optional[datetime]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _fallback_parse_rss_items(content: bytes) -> list[dict]:
    # если нам подсунули HTML или пустоту — сразу выходим
    if not content:
        return []
    head = content[:400].lstrip().lower()
    if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
        return []

    parser = etree.XMLParser(recover=True, no_network=True, huge_tree=True)

    try:
        root = etree.fromstring(content, parser=parser)
    except Exception:
        return []

    if root is None:
        return []

    items: list[dict] = []

    # RSS items
    for item in root.xpath(".//*[local-name()='item']"):
        title = "".join(item.xpath("./*[local-name()='title']//text()")).strip()
        link = "".join(item.xpath("./*[local-name()='link']//text()")).strip()
        pub = "".join(item.xpath("./*[local-name()='pubDate']//text()")).strip()

        if not title or not link:
            continue

        published_at = _safe_parse_dt(pub)

        items.append(
            {
                "title": title,
                "url": link,
                "canonical_url": link,
                "published_at": published_at,
                "content_hash": _hash_text(f"{title} {link}"),
            }
        )

    if items:
        return items

    # Atom entries
    for entry in root.xpath(".//*[local-name()='entry']"):
        title = "".join(entry.xpath("./*[local-name()='title']//text()")).strip()

        link = ""
        href = entry.xpath("./*[local-name()='link']/@href")
        if href:
            link = (href[0] or "").strip()
        else:
            link = "".join(entry.xpath("./*[local-name()='link']//text()")).strip()

        updated = "".join(entry.xpath("./*[local-name()='updated']//text()")).strip()
        published = "".join(entry.xpath("./*[local-name()='published']//text()")).strip()

        if not title or not link:
            continue

        published_at = _safe_parse_dt(published) or _safe_parse_dt(updated)

        items.append(
            {
                "title": title,
                "url": link,
                "canonical_url": link,
                "published_at": published_at,
                "content_hash": _hash_text(f"{title} {link}"),
            }
        )

    return items


def fetch_rss(feed_url: str, source_id: str, source_name: str, ssl_verify: bool = True) -> list[dict]:
    try:
        content, content_type, final_url = _download_feed(feed_url, ssl_verify=ssl_verify)
    except Exception as e:
        # ВАЖНО: не печатаем тут, а пробрасываем наружу
        raise RuntimeError(f"[RSS ERROR] {source_name}: не удалось скачать RSS: {e}") from e

    # Быстрый антибот/HTML-чек по content-type и по началу контента
    head = (content or b"").lstrip()[:400].lower()
    looks_like_html = (
        "text/html" in content_type
        or head.startswith(b"<!doctype html")
        or head.startswith(b"<html")
        or b"<html" in head
    )
    if looks_like_html:
        raise RuntimeError(
            f"[RSS ERROR] {source_name}: получен HTML вместо RSS "
            f"(content-type={content_type}, url={final_url})"
        )

    looks_like_xmlish = any(x in content_type for x in ["xml", "rss", "atom"]) or head.startswith(b"<?xml")
    if not looks_like_xmlish:
        raise RuntimeError(
            f"[RSS ERROR] {source_name}: не похоже на RSS/XML "
            f"(content-type={content_type}, url={final_url})"
        )

    feed = feedparser.parse(content)

    # 1) основной путь через feedparser
    entries = getattr(feed, "entries", []) or []
    if entries:
        out: list[dict] = []
        for e in entries:
            title = (getattr(e, "title", "") or "").strip()
            url = _normalize_url(getattr(e, "link", "") or "")
            if not url or not title:
                continue

            published_at = _parse_published(e)
            canonical_url = url
            content_hash = _hash_text(f"{title} {canonical_url}")

            out.append(
                dict(
                    source_id=source_id,
                    source_name=source_name,
                    title=title,
                    url=url,
                    canonical_url=canonical_url,
                    published_at=published_at,
                    content_hash=content_hash,
                )
            )
        return out

    # 2) fallback: feedparser не дал entries — пробуем XML
    if getattr(feed, "bozo", 0):
        print(f"[RSS WARN] {source_name}: feedparser bozo=1, пробую fallback-парсинг XML")
    else:
        print(f"[RSS INFO] {source_name}: feedparser не дал entries, пробую fallback-парсинг XML")

    fb = _fallback_parse_rss_items(content)
    out: list[dict] = []
    for it in fb:
        out.append(
            dict(
                source_id=source_id,
                source_name=source_name,
                title=it["title"],
                url=it["url"],
                canonical_url=it["canonical_url"],
                published_at=it["published_at"],
                content_hash=it["content_hash"],
            )
        )
    return out


def save_new_articles(db: Session, items: Iterable[dict]) -> tuple[int, int]:
    """
    Возвращает (created, existed_by_url)
    """
    items = list(items)
    if not items:
        return (0, 0)

    urls = [it["canonical_url"] for it in items if it.get("canonical_url")]
    if not urls:
        return (0, 0)

    existing_urls = set(
        r[0]
        for r in db.execute(
            select(Article.canonical_url).where(Article.canonical_url.in_(urls))
        ).all()
        if r and r[0]
    )

    new_items = [it for it in items if it.get("canonical_url") and it["canonical_url"] not in existing_urls]
    existed = len(items) - len(new_items)

    if not new_items:
        return (0, existed)

    rows = [Article(**it) for it in new_items]
    db.add_all(rows)

    try:
        db.commit()
        return (len(rows), existed)
    except IntegrityError:
        # возможны гонки/дубликаты по content_hash — откат и “дожим” поштучно
        db.rollback()
        created = 0
        for it in new_items:
            db.add(Article(**it))
            try:
                db.commit()
                created += 1
            except IntegrityError:
                db.rollback()
        return (created, existed)