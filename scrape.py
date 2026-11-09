"""Collect recent stock-market news from RSS feeds.

The scraper is safe to run without credentials: it prints collected items as JSON.
When SUPABASE_URL and SUPABASE_KEY are provided, it upserts the items into the
Supabase `news` table.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

FEEDS = (
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC,%5EDJI,%5EIXIC&region=US&lang=en-US",
    "https://www.investing.com/rss/news_25.rss",
)


def fetch_feed(feed_url: str) -> list[dict[str, str]]:
    request = Request(feed_url, headers={"User-Agent": "stock-news-collector/1.0"})
    with urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())

    items: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue

        published = (item.findtext("pubDate") or "").strip()
        try:
            published_at = parsedate_to_datetime(published).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            published_at = datetime.now(timezone.utc).isoformat()

        source = (item.findtext("source") or "").strip() or feed_url.split("/")[2]
        summary = (item.findtext("description") or "").strip()
        items.append(
            {
                "title": title,
                "url": urljoin(feed_url, link),
                "source": source,
                "summary": summary,
                "published_at": published_at,
            }
        )
    return items


def save_to_supabase(items: list[dict[str, str]]) -> None:
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.environ.get("SUPABASE_KEY", "")
    if not supabase_url and not supabase_key:
        return
    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set together")

    request = Request(
        f"{supabase_url}/rest/v1/news?on_conflict=url",
        data=json.dumps(items).encode("utf-8"),
        headers={
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
        method="POST",
    )
    with urlopen(request, timeout=30):
        pass


def main() -> int:
    collected: list[dict[str, str]] = []
    failures: list[str] = []
    for feed_url in FEEDS:
        try:
            collected.extend(fetch_feed(feed_url))
        except (HTTPError, URLError, ET.ParseError, TimeoutError) as error:
            failures.append(f"{feed_url}: {error}")

    unique_items = {item["url"]: item for item in collected}
    items = list(unique_items.values())
    print(json.dumps(items, ensure_ascii=True, indent=2))

    if failures and not items:
        for failure in failures:
            print(f"Feed error: {failure}", file=sys.stderr)
        return 1

    save_to_supabase(items)
    if failures:
        for failure in failures:
            print(f"Feed warning: {failure}", file=sys.stderr)
    print(f"Collected {len(items)} news items.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
