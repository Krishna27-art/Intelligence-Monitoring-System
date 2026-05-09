import requests
import re
import os
import concurrent.futures
import hashlib
import pandas as pd
from database.db_manager import get_connection, insert_signal
from utils.ingestion import clean_text, source_confidence, utc_now

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

# Blazing fast keyword matcher
MONEY_KEYWORDS = re.compile(
    r'(profit|loss|revenue|deal|contract|crore|₹|rs\s\d|lakh|order\s*book|capacity|expansion|acquired|joint\s*venture)',
    re.IGNORECASE
)

def extract_text_fast(html):
    """Strips HTML tags instantly using regex"""
    return re.sub(r'<[^>]+>', ' ', html).lower()

def scan_single_company(row):
    """Scans one company's IR/Press page for financial events"""
    ticker, name = row['ticker'], row['name']
    website = str(row['website'])
    if website == 'nan' or not website: return None
    
    base_url = website.rstrip('/')
    
    # Common URL structures for Indian company announcements
    urls_to_check = [
        f"{base_url}/investors",
        f"{base_url}/investor-relations",
        f"{base_url}/press-releases",
        f"{base_url}/announcements",
        base_url
    ]
    
    for url in urls_to_check:
        try:
            response = requests.get(url, headers=HEADERS, timeout=5)
            if response.status_code != 200: continue
            
            raw_text = extract_text_fast(response.text)
            page_hash = hashlib.md5(raw_text.encode()).hexdigest()
            
            # Check if seen
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT content_hash FROM website_snapshots WHERE ticker=?", (ticker,))
            res = cursor.fetchone()
            
            if res and res[0] == page_hash:
                conn.close()
                continue
                
            # Search for money words
            match = MONEY_KEYWORDS.search(raw_text)
            
            if match:
                # Found something!
                match_start = max(0, match.start() - 150)
                match_end = min(len(raw_text), match.end() + 250)
                snippet = clean_text(raw_text[match_start:match_end].replace('\n', ' ').strip())
                
                # Save hash
                cursor.execute('''INSERT OR REPLACE INTO website_snapshots (ticker, content_hash, last_checked)
                                  VALUES (?, ?, datetime('now'))''', (ticker, page_hash))
                conn.commit()
                conn.close()
                
                return {
                    "ticker": ticker,
                    "headline": f"💰 Web Direct: {name} Update ({match.group().title()})",
                    "source": url,
                    "text": snippet,
                    "url": url,
                    "published_at": utc_now(),
                    "confidence": source_confidence(url),
                }
            else:
                cursor.execute('''INSERT OR REPLACE INTO website_snapshots (ticker, content_hash, last_checked)
                                  VALUES (?, ?, datetime('now'))''', (ticker, page_hash))
                conn.commit()
                conn.close()
        except Exception:
            continue
    return None

def run_deep_website_scan(batch_size=20):
    """Orchestrates scanning a batch of companies using Threads"""
    csv_path = os.path.join("data", "master_companies.csv")
    if not os.path.exists(csv_path):
        return 0
    
    df = pd.read_csv(csv_path)
    # Filter for companies we haven't checked recently
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ticker FROM website_snapshots WHERE last_checked < datetime('now', '-4 hours') OR last_checked IS NULL LIMIT ?", (batch_size,))
    tickers_to_scan = [r[0] for r in cursor.fetchall()]
    conn.close()
    
    if not tickers_to_scan:
        return 0
    
    companies = df[df['ticker'].isin(tickers_to_scan)].to_dict('records')
    print(f"🕷️ Launching Deep Financial Scan across {len(companies)} company websites...")
    
    saved_count = 0
    analyze_headline = None
    extract_metadata = None
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scan_single_company, row): row for row in companies}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
            except Exception as e:
                print(f"Website worker failed: {e}")
                continue
            if result:
                if analyze_headline is None or extract_metadata is None:
                    from ai_engine.sentiment import analyze_headline, extract_metadata
                sentiment, score, summary = analyze_headline(result['text'])
                update_type, metric = extract_metadata(result['text'])
                if insert_signal(result['ticker'], result['headline'], result['source'],
                                 sentiment, score, summary, update_type, metric,
                                 published_at=result.get("published_at"),
                                 url=result.get("url"),
                                 confidence=result.get("confidence")):
                    saved_count += 1
                    print(f"🚨 {result['ticker']}: Found financial data on website!")

    return saved_count
