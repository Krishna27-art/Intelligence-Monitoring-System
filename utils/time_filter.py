from datetime import datetime, timedelta, timezone
import re

def is_article_valid(publish_date_str, max_hours_old=24):
    """
    Checks if an article is fresh enough to care about.
    """
    if not publish_date_str:
        return False
        
    # 1. Calculate the cutoff time (The "Barrier")
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_hours_old)
    
    # 2. Parse the incoming date string
    article_date = parse_date(publish_date_str)
    
    if article_date is None:
        # If we can't parse the date, assume invalid to be safe against spam
        return False

    # 3. Compare
    if article_date.tzinfo is None:
        article_date = article_date.replace(tzinfo=timezone.utc)
    else:
        article_date = article_date.astimezone(timezone.utc)
    return article_date >= cutoff_time

def parse_date(date_str):
    """Handles multiple date formats commonly found on Indian news sites."""
    date_str = date_str.strip()
    
    # Format 1: Standard ISO (2026-05-06T10:00:00+05:30)
    if "T" in date_str:
        try:
            clean_str = date_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except:
            pass
            
    # Format 2: "06 May 2026, 10:30 AM"
    try:
        return datetime.strptime(date_str, "%d %b %Y, %I:%M %p").replace(tzinfo=timezone.utc)
    except:
        pass

    # Format 3: "May 06, 2026"
    try:
        return datetime.strptime(date_str, "%b %d, %Y").replace(tzinfo=timezone.utc)
    except:
        pass
        
    # Format 4: "06-05-2026"
    try:
        return datetime.strptime(date_str, "%d-%m-%Y").replace(tzinfo=timezone.utc)
    except:
        pass
        
    # Format 5: RSS standard format (e.g., Wed, 06 May 2026 10:00:00 GMT)
    try:
        # Simplified parser for RSS dates
        import email.utils
        dt_tuple = email.utils.parsedate_tz(date_str)
        if dt_tuple:
            return datetime.fromtimestamp(email.utils.mktime_tz(dt_tuple), tz=timezone.utc)
    except:
        pass
        
    return None

def is_content_fresh(headline: str) -> bool:
    """
    Scans the headline for mentions of past months or dates.
    If a headline mentions a date from a previous month, it's likely stale.
    Example: 'Stocks to Watch (April 24)' when it's May.
    """
    now = datetime.now()
    months = ['january', 'february', 'march', 'april', 'may', 'june', 
              'july', 'august', 'september', 'october', 'november', 'december',
              'jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
    
    current_month_idx = now.month - 1
    # Check for previous months (only for the last 3 months to avoid over-filtering)
    previous_months = []
    for i in range(1, 4):
        prev_idx = (current_month_idx - i) % 12
        previous_months.append(months[prev_idx])
        previous_months.append(months[prev_idx + 12]) # Short versions
        
    headline_lower = headline.lower()
    for month in previous_months:
        # Match month followed by a day, e.g., "April 24"
        if re.search(rf'\b{month}\s+\d{{1,2}}\b', headline_lower):
            return False
            
    return True
