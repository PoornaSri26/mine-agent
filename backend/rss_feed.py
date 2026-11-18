"""Fetch the latest mine-safety bulletins for `GET /updates`.

Sources are ordered by reachability from a cloud host, not by prestige: the
direct publisher feeds (mining.com, miningweekly, mining-technology) answer
Cloudflare 403 to datacentre IPs, so the Google News queries run first. If every
source fails, the bundled snapshot in `data/bulletins_snapshot.json` is used so
the Updates screen still shows real bulletins instead of an empty page.
"""

import json
import os
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dateutil import parser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Kept outside `data/` on purpose: .dockerignore excludes the runtime data dir.
SNAPSHOT_PATH = os.path.join(BASE_DIR, "bulletins_snapshot.json")

# Ordered by how reliably they answer a cloud/datacentre IP.
RSS_SOURCES = [
    "https://news.google.com/rss/search?q=DGMS+mine+safety+India&hl=en-IN&gl=IN&ceid=IN:en",
    "https://news.google.com/rss/search?q=mine+accident+India+safety&hl=en-IN&gl=IN&ceid=IN:en",
    "https://www.mining.com/feed/",          # often blocked by Cloudflare
    "https://www.mining-technology.com/feed/",
    "https://www.miningweekly.com/page/rss",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _decode(raw: bytes) -> str:
    """Decode a feed body that is mostly UTF-8 but may carry stray cp1252 bytes.

    Google's feed ships `Workers’ Welfare` with the apostrophe as a lone 0x92,
    which fails a strict UTF-8 decode. Decoding the bad bytes one at a time keeps
    the rest of the document correct instead of replacing text wholesale.
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass

    parts: list[str] = []
    position = 0
    while position < len(raw):
        try:
            parts.append(raw[position:].decode("utf-8"))
            break
        except UnicodeDecodeError as exc:
            parts.append(raw[position:position + exc.start].decode("utf-8", errors="ignore"))
            parts.append(raw[position + exc.start:position + exc.start + 1].decode("cp1252", errors="ignore"))
            position += exc.start + 1
    return "".join(parts)


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node is not None else ""


def _entry(item) -> dict | None:
    title = _text(item.find("title"))
    if not title:
        return None

    link = _text(item.find("link"))
    if not link:
        link_node = item.find("link")
        link = link_node.get("href", "") if link_node is not None else ""

    published = _text(item.find("pubDate")) or _text(item.find("published")) or _text(item.find("updated"))
    if published:
        try:
            published = parser.parse(published).date().isoformat()
        except (ValueError, OverflowError, TypeError):
            published = ""

    return {"title": title, "link": link, "published": published}


def _parse_feed(body: str, limit: int) -> list[dict]:
    soup = BeautifulSoup(body, "xml")
    items = soup.find_all("item") or soup.find_all("entry")
    entries: list[dict] = []
    seen: set[str] = set()
    for item in items:
        entry = _entry(item)
        if entry and entry["title"] not in seen:
            seen.add(entry["title"])
            entries.append(entry)
        if len(entries) >= limit:
            break
    return entries


def load_snapshot(limit: int = 5) -> list[dict]:
    """Last known-good bulletins captured when the snapshot was written."""
    try:
        with open(SNAPSHOT_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        print(f"[rss] bulletin snapshot unavailable: {exc}")
        return []
    return list(data.get("updates", []))[:limit]


def fetch_dgms_updates(limit: int = 5):
    for src in RSS_SOURCES:
        try:
            response = requests.get(src, headers=HEADERS, timeout=10)
            response.raise_for_status()

            # Decode explicitly: requests falls back to ISO-8859-1 when a feed
            # omits the charset, which turned "Workers' Welfare" into "Workers®".
            body = _decode(response.content)
            updates = _parse_feed(body, limit)
            if updates:
                return updates

        except Exception as e:
            print(f"[rss] source failed ({src}): {e}")
            continue

    snapshot = load_snapshot(limit)
    if snapshot:
        print("[rss] all sources failed; serving the bundled bulletin snapshot")
        return snapshot

    return [{
        "title": "No updates available",
        "link": "",
        "published": "",
    }]
