import requests
import feedparser
import pandas as pd
import os
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from database.db_manager import get_connection
from utils.dedup_manager import DedupManager
from utils.ingestion import clean_text, is_fresh, parse_feed_datetime, source_confidence
from utils.time_filter import is_content_fresh

# Initialize Deduplication Manager
dedup = DedupManager()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_company_batch(batch_size=50):
    """Reads master CSV and returns a batch of companies to search"""
    csv_path = os.path.join("data", "master_companies.csv")
    if not os.path.exists(csv_path): return []
    df = pd.read_csv(csv_path)
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS website_snapshots (
                    ticker TEXT PRIMARY KEY, content_hash TEXT, last_checked DATETIME)''')
    cursor.execute('''SELECT ticker FROM website_snapshots 
                      WHERE last_checked IS NULL 
                         OR last_checked < datetime('now', '-3 hours')
                      ORDER BY last_checked ASC NULLS FIRST LIMIT ?''', (batch_size,))
    rows_to_check = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    if not rows_to_check: 
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ticker FROM companies LIMIT ?", (batch_size,))
        rows_to_check = [row[0] for row in cursor.fetchall()]
        conn.close()
    
    if not rows_to_check: return []
    
    batch_df = df[df['ticker'].isin(rows_to_check)]
    return batch_df[['ticker', 'name']].to_dict('records')

def mark_batch_as_checked(batch):
    conn = get_connection()
    cursor = conn.cursor()
    for row in batch:
        cursor.execute('''INSERT INTO website_snapshots (ticker, content_hash, last_checked)
                          VALUES (?, 'news', datetime('now'))
                          ON CONFLICT(ticker) DO UPDATE SET last_checked=datetime('now')''', 
                       (row['ticker'],))
    conn.commit()
    conn.close()

async def fetch_feed(session, url, row):
    try:
        async with session.get(url, headers=HEADERS, timeout=15) as response:
            content = await response.read()
            return content, row
    except Exception:
        return None, row

async def search_google_news_async(batch):
    if not batch: return []
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for row in batch:
            # BUG 4 FIX: Individual company queries instead of massive OR query!
            name_encoded = row['name'].replace(" ", "+")
            url = f"https://news.google.com/rss/search?q=%22{name_encoded}%22+NSE+when:1d&hl=en-IN&gl=IN&ceid=IN:en"
            tasks.append(fetch_feed(session, url, row))
        
        results = await asyncio.gather(*tasks)
        
    news_items = []
    now_utc = datetime.now(timezone.utc)
    
    for content, row in results:
        if not content: continue
        try:
            feed = feedparser.parse(content)
            for entry in feed.entries[:10]:
                # BUG 2 FIX: Extract actual published time from RSS
                published_at = parse_feed_datetime(entry)
                if not published_at: continue
                
                # BUG 3 FIX: Date filter (skip if older than 6 hours)
                if (now_utc - published_at).total_seconds() > 6 * 3600:
                    continue
                
                url = entry.get("link", "")
                
                # BUG 3 FIX: Deduplication check
                if url and dedup.is_seen(url):
                    continue
                    
                # BUG 1 FIX: HTML stripping using BeautifulSoup
                raw_summary = entry.get('summary', entry.get('title', ''))
                clean_summary = BeautifulSoup(raw_summary, "html.parser").get_text(" ", strip=True)
                clean_title = BeautifulSoup(entry.get('title', ''), "html.parser").get_text(" ", strip=True)
                
                news_items.append({
                    "headline": clean_title,
                    "source": "Google News",
                    "ticker": row["ticker"], # Exactly mapped!
                    "text": clean_summary,
                    "url": url,
                    "published_at": published_at,
                    "confidence": 85,
                })
        except Exception:
            continue
            
    mark_batch_as_checked(batch)
    return news_items

def get_all_news():
    print("🔄 Fetching company-specific news via Parallel Asyncio...")
    batch = get_company_batch(batch_size=50)
    if not batch:
        print("⏳ No companies to check right now.")
        return []
        
    print(f"🔍 Scanning Google News for batch of {len(batch)} companies...")
    
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    if loop.is_running():
        # Fallback to sync if already in event loop (streamlit sometimes does this)
        print("⚠️ Event loop is already running. Using sync fallback.")
        import requests
        news_items = []
        for row in batch:
            name_encoded = row['name'].replace(" ", "+")
            url = f"https://news.google.com/rss/search?q=%22{name_encoded}%22+NSE+when:1d&hl=en-IN&gl=IN&ceid=IN:en"
            try:
                res = requests.get(url, headers=HEADERS, timeout=10)
                feed = feedparser.parse(res.content)
                now_utc = datetime.now(timezone.utc)
                for entry in feed.entries[:10]:
                    published_at = parse_feed_datetime(entry)
                    if not published_at or (now_utc - published_at).total_seconds() > 6 * 3600: continue
                    url = entry.get("link", "")
                    if url and dedup.is_seen(url): continue
                    raw_summary = entry.get('summary', entry.get('title', ''))
                    clean_summary = BeautifulSoup(raw_summary, "html.parser").get_text(" ", strip=True)
                    clean_title = BeautifulSoup(entry.get('title', ''), "html.parser").get_text(" ", strip=True)
                    news_items.append({
                        "headline": clean_title, "source": "Google News", "ticker": row["ticker"],
                        "text": clean_summary, "url": url, "published_at": published_at, "confidence": 85
                    })
            except Exception: pass
        mark_batch_as_checked(batch)
        return news_items
    else:
        news = loop.run_until_complete(search_google_news_async(batch))
        print(f"✅ Found {len(news)} relevant articles for this batch.")
        return news

def match_ticker(headline: str) -> str:
    # Kept for compatibility but mostly obsolete now due to strict mapping
    return "MARKET"
