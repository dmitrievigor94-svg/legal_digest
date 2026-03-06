# app/fetch_rss.py
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable, Optional

import feedparser
import httpx
from lxml import etree, html
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Article

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X) legal_digest/1.0"

ABS_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _ensure_http(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return u
    if ABS_URL_RE.match(u):
        return u
    # если подсунули "rkn.gov.ru/news/" без схемы
    return "https://" + u.lstrip("/")


def _normalize_url(url: str) -> str:
    return _ensure_http((url or "").strip())


def _hash_text(s: str) -> str:
    s_norm = " ".join((s or "").split()).strip().lower()
    return hashlib.sha256(s_norm.encode("utf-8")).hexdigest()


def _parse_published(entry) -> Optional[datetime]:
    t = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not t:
        return None
    return datetime(*t[:6], tzinfo=timezone.utc)


def _download(url: str, ssl_verify: bool = True) -> tuple[bytes, str, str]:
    url = _ensure_http(url)
    with httpx.Client(
        follow_redirects=True,
        timeout=25,
        verify=ssl_verify,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.9, */*;q=0.8",
        },
    ) as client:
        r = client.get(url)
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
    if not content:
        return []

    head = content[:600].lstrip().lower()
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

    # RSS
    for item in root.xpath(".//*[local-name()='item']"):
        title = "".join(item.xpath("./*[local-name()='title']//text()")).strip()
        link = "".join(item.xpath("./*[local-name()='link']//text()")).strip()
        pub = "".join(item.xpath("./*[local-name()='pubDate']//text()")).strip()

        if not title or not link:
            continue

        url = _normalize_url(link)
        published_at = _safe_parse_dt(pub)

        items.append(
            {
                "title": title,
                "url": url,
                "canonical_url": url,
                "published_at": published_at,
                "content_hash": _hash_text(f"{title} {url}"),
            }
        )

    if items:
        return items

    # Atom
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

        url = _normalize_url(link)
        published_at = _safe_parse_dt(published) or _safe_parse_dt(updated)

        items.append(
            {
                "title": title,
                "url": url,
                "canonical_url": url,
                "published_at": published_at,
                "content_hash": _hash_text(f"{title} {url}"),
            }
        )

    return items


def fetch_rss(feed_url: str, source_id: str, source_name: str, ssl_verify: bool = True) -> list[dict]:
    try:
        content, content_type, final_url = _download(feed_url, ssl_verify=ssl_verify)
    except Exception as e:
        raise RuntimeError(f"[RSS ERROR] {source_name}: не удалось скачать RSS: {e}") from e

    head = (content or b"").lstrip()[:600].lower()
    looks_like_html = (
        "text/html" in (content_type or "")
        or head.startswith(b"<!doctype html")
        or head.startswith(b"<html")
        or b"<html" in head
    )

    # Некоторые сайты отдают RSS с content-type=text/html — сначала пробуем парсить
    if looks_like_html:
        feed = feedparser.parse(content)
        entries = getattr(feed, "entries", []) or []
        if entries:
            out: list[dict] = []
            for e in entries:
                title = (getattr(e, "title", "") or "").strip()
                url = _normalize_url(getattr(e, "link", "") or "")
                if not url or not title:
                    continue

                published_at = _parse_published(e)
                content_hash = _hash_text(f"{title} {url}")

                out.append(
                    dict(
                        source_id=source_id,
                        source_name=source_name,
                        title=title,
                        url=url,
                        canonical_url=url,
                        published_at=published_at,
                        content_hash=content_hash,
                    )
                )
            print(f"[RSS WARN] {source_name}: content-type={content_type} выглядит как HTML, но entries распарсились (url={final_url})")
            return out

        fb = _fallback_parse_rss_items(content)
        if fb:
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
            print(f"[RSS WARN] {source_name}: content-type={content_type} выглядит как HTML, но fallback XML дал items (url={final_url})")
            return out

        raise RuntimeError(
            f"[RSS ERROR] {source_name}: получен HTML вместо RSS "
            f"(content-type={content_type}, url={final_url})"
        )

    # обычная валидация
    looks_like_xmlish = any(x in (content_type or "") for x in ["xml", "rss", "atom"]) or head.startswith(b"<?xml")
    if not looks_like_xmlish:
        raise RuntimeError(
            f"[RSS ERROR] {source_name}: не похоже на RSS/XML "
            f"(content-type={content_type}, url={final_url})"
        )

    feed = feedparser.parse(content)
    entries = getattr(feed, "entries", []) or []

    if entries:
        out: list[dict] = []
        for e in entries:
            title = (getattr(e, "title", "") or "").strip()
            url = _normalize_url(getattr(e, "link", "") or "")
            if not url or not title:
                continue
            published_at = _parse_published(e)
            content_hash = _hash_text(f"{title} {url}")
            out.append(
                dict(
                    source_id=source_id,
                    source_name=source_name,
                    title=title,
                    url=url,
                    canonical_url=url,
                    published_at=published_at,
                    content_hash=content_hash,
                )
            )
        return out

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


def fetch_html_list(
    page_url: str,
    source_id: str,
    source_name: str,
    *,
    link_xpath: str,
    base_url: str | None = None,
    ssl_verify: bool = True,
) -> list[dict]:
    """
    Достаём новости с HTML-страницы (без RSS):
    - link_xpath должен возвращать <a> элементы или href-атрибуты.
    - title берём из текста ссылки.
    """
    try:
        content, content_type, final_url = _download(page_url, ssl_verify=ssl_verify)
    except Exception as e:
        raise RuntimeError(f"[HTML ERROR] {source_name}: не удалось скачать страницу: {e}") from e

    try:
        doc = html.fromstring(content)
    except Exception as e:
        raise RuntimeError(f"[HTML ERROR] {source_name}: не смог распарсить HTML (url={final_url}): {e}") from e

    nodes = doc.xpath(link_xpath) or []
    out: list[dict] = []

    def _abs(href: str) -> str:
        href = (href or "").strip()
        if not href:
            return ""
        if ABS_URL_RE.match(href):
            return href
        b = (base_url or final_url or "").rstrip("/")
        if href.startswith("/"):
            # вытащим схему+хост из base
            m = re.match(r"^(https?://[^/]+)", b)
            host = m.group(1) if m else b
            return host + href
        return b + "/" + href

    for n in nodes[:200]:
        href = ""
        title = ""

        if isinstance(n, str):
            href = n
            title = n
        else:
            href = (n.get("href") or "").strip()
            title = (" ".join((n.text_content() or "").split())).strip()

        url = _abs(href)
        if not url:
            continue
        if not title:
            title = url

        out.append(
            dict(
                source_id=source_id,
                source_name=source_name,
                title=title[:500],
                url=_normalize_url(url),
                canonical_url=_normalize_url(url),
                published_at=None,  # дату потом доберём через fetch_published_at при необходимости
                content_hash=_hash_text(f"{title} {url}"),
            )
        )

    if not out:
        raise RuntimeError(f"[HTML ERROR] {source_name}: не нашёл ссылок по xpath (url={final_url})")

    return out


def fetch_items(source: dict) -> list[dict]:
    kind = (source.get("kind") or "rss").strip().lower()
    source_id = source["source_id"]
    source_name = source["source_name"]
    url = source["url"]
    ssl_verify = bool(source.get("ssl_verify", True))

    if kind == "rss":
        return fetch_rss(url, source_id, source_name, ssl_verify=ssl_verify)

    if kind == "html":
        link_xpath = source.get("link_xpath")
        if not link_xpath:
            raise RuntimeError(f"[HTML ERROR] {source_name}: link_xpath обязателен для kind=html")
        base_url = source.get("base_url")
        return fetch_html_list(
            url,
            source_id,
            source_name,
            link_xpath=link_xpath,
            base_url=base_url,
            ssl_verify=ssl_verify,
        )

    raise RuntimeError(f"[SOURCE ERROR] {source_name}: неизвестный kind={kind}")


def save_new_articles(db: Session, items: Iterable[dict]) -> tuple[int, int]:
    items = list(items)
    if not items:
        return (0, 0)

    urls = [it["canonical_url"] for it in items if it.get("canonical_url")]
    if not urls:
        return (0, 0)

    existing_urls = set(
        r[0]
        for r in db.execute(select(Article.canonical_url).where(Article.canonical_url.in_(urls))).all()
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