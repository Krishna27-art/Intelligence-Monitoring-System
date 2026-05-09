import asyncio
import email.utils
import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

import aiohttp
import feedparser
import pandas as pd
from bs4 import BeautifulSoup

import config


UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def clean_text(value) -> str:
    if value is None:
        return ""
    return BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)


def parse_datetime(value) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (tuple, list)) and len(value) >= 6:
        dt = datetime(*value[:6], tzinfo=UTC)
    else:
        raw = str(value).strip()
        if not raw:
            return None

        try:
            dt = email.utils.parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            dt = None

        if dt is None:
            for fmt in ("%d %b %Y", "%d %b %Y, %I:%M %p", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(raw.replace("Z", ""), fmt)
                    break
                except ValueError:
                    pass

        if dt is None:
            return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def entry_published_at(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        dt = parse_datetime(entry.get(key))
        if dt:
            return dt

    for key in ("published", "updated"):
        dt = parse_datetime(entry.get(key))
        if dt:
            return dt

    return None


def db_time(value) -> str:
    dt = parse_datetime(value) or utc_now()
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def is_recent(published_at, max_hours=None) -> bool:
    max_hours = max_hours or config.MAX_ARTICLE_AGE_HOURS
    dt = parse_datetime(published_at)
    if dt is None:
        return False
    return utc_now() - dt <= timedelta(hours=max_hours)


def is_important(text) -> bool:
    text = clean_text(text).lower()
    return any(keyword in text for keyword in config.KEYWORDS)


def source_confidence(source_name: str) -> int:
    source = source_name.lower()
    if source in {"bse", "nse"}:
        return 95
    if source == "et":
        return 80
    if source == "moneycontrol":
        return 75
    if source in {"mint", "biz_standard"}:
        return 70
    return 50


def make_event_id(item) -> str:
    raw = "|".join(
        [
            str(item.get("ticker") or "N/A").upper(),
            clean_text(item.get("headline")).lower(),
            str(item.get("link") or ""),
            db_time(item.get("published")),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class DedupManager:
    def __init__(self, db_path=None):
        self.conn = sqlite3.connect(db_path or config.DB_CONFIG["dedup_path"])
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("CREATE TABLE IF NOT EXISTS seen (hash TEXT PRIMARY KEY)")

    def is_seen(self, value) -> bool:
        value = str(value or "").strip()
        if not value:
            return True

        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
        try:
            self.conn.execute("INSERT INTO seen (hash) VALUES (?)", (digest,))
            self.conn.commit()
            return False
        except sqlite3.IntegrityError:
            return True

    def close(self):
        self.conn.close()


def init_db():
    conn = sqlite3.connect(config.DB_CONFIG["sqlite_path"])
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE,
            headline TEXT NOT NULL,
            clean_headline TEXT NOT NULL,
            link TEXT,
            published DATETIME NOT NULL,
            ingested_at DATETIME NOT NULL,
            source TEXT NOT NULL,
            ticker TEXT DEFAULT 'N/A',
            confidence INTEGER DEFAULT 50
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_published ON signals(published DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source)")
    conn.close()


async def fetch_rss(session, url, source_name):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=12)) as response:
            if response.status != 200:
                print(f"[{source_name}] HTTP {response.status}")
                return []

            content = await response.text()
    except Exception as exc:
        print(f"[{source_name}] Fetch error: {exc}")
        return []

    feed = feedparser.parse(content)
    results = []

    for entry in feed.entries:
        headline = clean_text(entry.get("title", ""))
        published_at = entry_published_at(entry)

        if not headline or not published_at:
            continue
        if not is_recent(published_at):
            continue
        if not is_important(headline):
            continue

        item = {
            "headline": headline,
            "clean_headline": headline,
            "link": entry.get("link", ""),
            "published": db_time(published_at),
            "source": source_name,
            "ticker": "N/A",
            "confidence": source_confidence(source_name),
        }
        item["event_id"] = make_event_id(item)
        results.append(item)

    return results


async def run_bot(dedup_manager):
    print(f"\n--- Starting Cycle at {utc_now().strftime('%H:%M:%S')} UTC ---")
    all_fresh_data = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) IntelligenceSystem/1.0"
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = [fetch_rss(session, url, name) for name, url in config.SOURCES.items()]
        results = await asyncio.gather(*tasks)

    for source_data in results:
        for item in source_data:
            dedup_key = item.get("link") or item["event_id"]
            if not dedup_manager.is_seen(dedup_key):
                all_fresh_data.append(item)

    print(f"Cycle complete. New items found: {len(all_fresh_data)}")
    return all_fresh_data


def save_to_db(data):
    init_db()
    if not data:
        return 0

    df = pd.DataFrame(data)
    conn = sqlite3.connect(config.DB_CONFIG["sqlite_path"])
    saved = 0

    for row in df.to_dict("records"):
        try:
            conn.execute(
                """
                INSERT INTO signals (
                    event_id, headline, clean_headline, link, published,
                    ingested_at, source, ticker, confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("event_id") or make_event_id(row),
                    clean_text(row.get("headline")),
                    clean_text(row.get("clean_headline") or row.get("headline")),
                    row.get("link", ""),
                    db_time(row.get("published")),
                    db_time(utc_now()),
                    row.get("source", "unknown"),
                    row.get("ticker", "N/A"),
                    int(row.get("confidence", source_confidence(row.get("source", "")))),
                ),
            )
            saved += 1
        except sqlite3.IntegrityError:
            continue

    conn.commit()
    conn.close()
    return saved


if __name__ == "__main__":
    init_db()
    dedup = DedupManager()
    try:
        items = asyncio.run(run_bot(dedup))
        print(f"Saved {save_to_db(items)} rows")
    finally:
        dedup.close()
