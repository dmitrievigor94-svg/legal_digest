# app/debug_rss.py
from __future__ import annotations

from datetime import datetime
from collections import Counter

from app.sources import SOURCES
from app.fetch_rss import fetch_items


def _fmt_dt(dt) -> str:
    if not dt:
        return "—"
    try:
        return dt.astimezone().strftime("%Y-%m-%d %H:%M %z")
    except Exception:
        return str(dt)


def main(limit_per_source: int = 20) -> None:
    print(f"FEEDS DEBUG • {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %z')}")
    print("")

    for s in SOURCES:
        print(f"=== {s['source_name']} ({s['source_id']}) kind={s.get('kind','rss')} ===")
        try:
            items = fetch_items(s)
        except Exception as e:
            print(f"[ERROR] {s['source_name']}: {e}")
            print("")
            continue

        print(f"items: {len(items)}")
        if not items:
            print("")
            continue

        with_dt = [it for it in items if it.get("published_at") is not None]
        no_dt = len(items) - len(with_dt)

        if with_dt:
            dts = sorted(it["published_at"] for it in with_dt)
            print(f"published_at: min={_fmt_dt(dts[0])} max={_fmt_dt(dts[-1])} | no_dt={no_dt}")
        else:
            print(f"published_at: none | no_dt={no_dt}")

        domains = []
        for it in items:
            url = (it.get("canonical_url") or it.get("url") or "").strip()
            if "://" in url:
                domains.append(url.split("://", 1)[1].split("/", 1)[0].lower())
        if domains:
            top_domains = Counter(domains).most_common(5)
            print("top domains:", ", ".join([f"{d}={c}" for d, c in top_domains]))

        print("")
        for i, it in enumerate(items[:limit_per_source], start=1):
            dt = it.get("published_at")
            title = (it.get("title") or "").strip().replace("\n", " ")
            url = (it.get("canonical_url") or it.get("url") or "").strip()
            print(f"{i:02d}. [{_fmt_dt(dt)}] {title}")
            print(f"    {url}")
        print("")


if __name__ == "__main__":
    main(limit_per_source=20)