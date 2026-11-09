"""Collect recent NSE Bharat Electronics (BEL) news and store it in Supabase."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

STOCK_SYMBOL = "BEL"
STOCK_NAME = "Bharat Electronics"
FEED_URL = (
    "https://news.google.com/rss/search?q="
    + quote(f"NSE {STOCK_SYMBOL} {STOCK_NAME}")
    + "&hl=en-IN&gl=IN&ceid=IN:en"
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

        source = (item.findtext("source") or "").strip() or "Google News"
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
    try:
        items = list({item["url"]: item for item in fetch_feed(FEED_URL)}.values())
    except (HTTPError, URLError, ET.ParseError, TimeoutError) as error:
        print(f"Feed error: {error}", file=sys.stderr)
        return 1

    print(json.dumps(items, ensure_ascii=True, indent=2))
    save_to_supabase(items)
    print(f"Collected {len(items)} {STOCK_SYMBOL} ({STOCK_NAME}) news items.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
