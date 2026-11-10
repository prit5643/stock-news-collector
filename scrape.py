"""Collect recent NSE Bharat Electronics (BEL) news and store it in MongoDB Atlas."""

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

from pymongo import ASCENDING, MongoClient, ReplaceOne

STOCK_SYMBOL = "BEL"
STOCK_NAME = "Bharat Electronics"
FEED_URL = (
    "https://news.google.com/rss/search?q="
    + quote(f"NSE {STOCK_SYMBOL} {STOCK_NAME}")
    + "&hl=en-IN&gl=IN&ceid=IN:en"
)
NEWS_DATABASE = "stock_news"
NEWS_COLLECTION = "news"
NEWS_TTL_SECONDS = 7776000  # 90 days


def parse_published(published: str) -> datetime:
    try:
        return parsedate_to_datetime(published).astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return datetime.now(timezone.utc)


def fetch_feed(feed_url: str) -> list[dict[str, object]]:
    request = Request(feed_url, headers={"User-Agent": "stock-news-collector/1.0"})
    with urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())

    items: list[dict[str, object]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue

        source = (item.findtext("source") or "").strip() or "Google News"
        summary = (item.findtext("description") or "").strip()
        items.append(
            {
                "title": title,
                "url": urljoin(feed_url, link),
                "source": source,
                "summary": summary,
                "published_at": parse_published((item.findtext("pubDate") or "").strip()),
            }
        )
    return items


def save_to_mongodb(items: list[dict[str, object]]) -> None:
    mongo_uri = os.environ.get("MONGODB_URI", "")
    if not mongo_uri:
        return

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=10000)
    collection = client[NEWS_DATABASE][NEWS_COLLECTION]
    collection.create_index([("url", ASCENDING)], unique=True)
    collection.create_index(
        [("published_at", ASCENDING)], expireAfterSeconds=NEWS_TTL_SECONDS
    )
    collection.bulk_write(
        [ReplaceOne({"url": item["url"]}, item, upsert=True) for item in items]
    )


def main() -> int:
    try:
        items = list({item["url"]: item for item in fetch_feed(FEED_URL)}.values())
    except (HTTPError, URLError, ET.ParseError, TimeoutError) as error:
        print(f"Feed error: {error}", file=sys.stderr)
        return 1

    print(json.dumps(items, default=str, ensure_ascii=True, indent=2))
    save_to_mongodb(items)
    print(f"Collected {len(items)} {STOCK_SYMBOL} ({STOCK_NAME}) news items.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
