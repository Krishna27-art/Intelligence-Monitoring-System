import hashlib
import html
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup


UTC = timezone.utc


def clean_text(value) -> str:
    """Return plain text suitable for storage and display."""
    if value is None:
        return ""
    unescaped = html.unescape(str(value))
    return BeautifulSoup(unescaped, "html.parser").get_text(" ", strip=True)


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def normalize_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        from utils.time_filter import parse_date

        dt = parse_date(value)
        if dt is None:
            return None
    elif isinstance(value, (tuple, list)) and len(value) >= 6:
        dt = datetime(*value[:6])
    else:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def format_db_datetime(value) -> str:
    dt = normalize_datetime(value) or utc_now()
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def is_fresh(value, max_hours_old=6) -> bool:
    dt = normalize_datetime(value)
    if dt is None:
        return False
    return utc_now() - dt <= timedelta(hours=max_hours_old)


def parse_feed_datetime(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None) or entry.get(attr)
        dt = normalize_datetime(parsed)
        if dt:
            return dt
    for attr in ("published", "updated"):
        raw = entry.get(attr)
        dt = normalize_datetime(raw)
        if dt:
            return dt
    return None


def make_event_id(ticker, headline, published_at=None, url=None) -> str:
    base_date = ""
    dt = normalize_datetime(published_at)
    if dt:
        base_date = dt.strftime("%Y-%m-%d")
    raw = "|".join([
        str(ticker or "MARKET").upper().strip(),
        clean_text(headline).lower().strip(),
        base_date,
        str(url or "").strip(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def source_confidence(source: str) -> int:
    source_lower = (source or "").lower()
    if "nse" in source_lower or "bse official" in source_lower:
        return 95
    if "sitemap" in source_lower or "company" in source_lower or source_lower.startswith("http"):
        return 85
    if "moneycontrol" in source_lower:
        return 75
    if "google news" in source_lower:
        return 40
    if "simulation" in source_lower or "system test" in source_lower:
        return 30
    return 60
