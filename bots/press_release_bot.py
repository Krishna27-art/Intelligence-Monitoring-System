import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup
import hashlib
import sqlite3
import os
import time
import pandas as pd
from datetime import datetime, timedelta
from database.db_manager import get_connection
from utils.dedup_manager import DedupManager
from utils.ingestion import clean_text, source_confidence
from utils.time_filter import is_content_fresh

# Initialize Deduplication Manager
dedup = DedupManager()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Keywords that indicate important company announcements
ANNOUNCEMENT_KEYWORDS = [
    'profit', 'loss', 'earnings', 'result', 'dividend', 'bonus', 'split', 
    'acquisition', 'merger', 'deal', 'partnership', 'contract', 'order',
    'board meeting', 'record date', 'ex-dividend', 'rights issue',
    'quarterly results', 'annual results', 'financial results',
    'revenue', 'sales', 'growth', 'expansion', 'investment'
]

async def fetch_url(session, url):
    """Asynchronously fetches page content"""
    try:
        async with session.get(url, headers=HEADERS, timeout=15) as response:
            if response.status == 200:
                return await response.text()
    except Exception:
        pass
    return None

async def scan_press_releases(session, ticker, base_url):
    """Scan company website for press releases/investor announcements"""
    signals = []
    
    # Common press release URL patterns
    press_urls = [
        f"{base_url.rstrip('/')}/press-releases",
        f"{base_url.rstrip('/')}/investors",
        f"{base_url.rstrip('/')}/investor-relations",
        f"{base_url.rstrip('/')}/news",
        f"{base_url.rstrip('/')}/media",
        f"{base_url.rstrip('/')}/announcements",
        f"{base_url.rstrip('/')}/financial-results",
        f"{base_url.rstrip('/')}/corporate-announcements"
    ]
    
    for press_url in press_urls:
        try:
            content = await fetch_url(session, press_url)
            if not content:
                continue
                
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for recent announcements (links with dates or titles)
            links = soup.find_all('a', href=True)
            
            for link in links:
                try:
                    link_text = clean_text(link.get_text())
                    link_url = link['href']
                    
                    # Make URL absolute
                    if link_url.startswith('/'):
                        link_url = f"{base_url.rstrip('/')}{link_url}"
                    elif not link_url.startswith('http'):
                        continue
                        
                    # Skip if already seen
                    if dedup.is_seen(link_url):
                        continue
                        
                    # Check if link contains announcement keywords
                    if not any(keyword.lower() in link_text.lower() for keyword in ANNOUNCEMENT_KEYWORDS):
                        continue
                        
                    # Try to extract date from link text or nearby elements
                    date_match = re.search(r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{2,4}[-/]\d{1,2}[-/]\d{1,2})', link_text)
                    published_at = datetime.now()
                    if date_match:
                        try:
                            date_str = date_match.group(1)
                            # Try different date formats
                            for fmt in ['%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d', '%m-%d-%Y']:
                                try:
                                    published_at = datetime.strptime(date_str, fmt)
                                    # Only use if within last 30 days
                                    if (datetime.now() - published_at).days > 30:
                                        continue
                                    break
                                except:
                                    continue
                        except:
                            pass
                    
                    signals.append({
                        "ticker": ticker,
                        "headline": f"📢 Company Announcement: {link_text}",
                        "source": "Company Website",
                        "text": link_text,
                        "url": link_url,
                        "published_at": published_at,
                        "confidence": source_confidence("Company Website"),
                    })
                    
                except Exception:
                    continue
                    
        except Exception:
            continue
            
    return signals

async def scan_investor_presentations(session, ticker, base_url):
    """Scan for investor presentations and PDF filings"""
    signals = []
    
    # Common investor section URLs
    investor_urls = [
        f"{base_url.rstrip('/')}/investors/presentations",
        f"{base_url.rstrip('/')}/investor-relations/presentations",
        f"{base_url.rstrip('/')}/financial-results",
        f"{base_url.rstrip('/')}/shareholder-information"
    ]
    
    for investor_url in investor_urls:
        try:
            content = await fetch_url(session, investor_url)
            if not content:
                continue
                
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for PDF links
            pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.IGNORECASE))
            
            for pdf_link in pdf_links:
                try:
                    pdf_url = pdf_link['href']
                    pdf_text = clean_text(pdf_link.get_text())
                    
                    # Make URL absolute
                    if pdf_url.startswith('/'):
                        pdf_url = f"{base_url.rstrip('/')}{pdf_url}"
                    elif not pdf_url.startswith('http'):
                        continue
                        
                    # Skip if already seen
                    if dedup.is_seen(pdf_url):
                        continue
                        
                    # Check if PDF contains relevant keywords
                    if not any(keyword.lower() in pdf_text.lower() for keyword in ANNOUNCEMENT_KEYWORDS):
                        continue
                    
                    signals.append({
                        "ticker": ticker,
                        "headline": f"📄 Investor Document: {pdf_text}",
                        "source": "Company PDF",
                        "text": pdf_text,
                        "url": pdf_url,
                        "published_at": datetime.now(),
                        "confidence": source_confidence("Company PDF"),
                    })
                    
                except Exception:
                    continue
                    
        except Exception:
            continue
            
    return signals

async def scan_company_announcements(session, ticker, website):
    """Main function to scan a company for announcements"""
    if not website or str(website) == 'nan':
        return []
        
    base_url = website.rstrip('/')
    
    # Run both scans in parallel
    press_tasks = scan_press_releases(session, ticker, base_url)
    pdf_tasks = scan_investor_presentations(session, ticker, base_url)
    
    press_results = await press_tasks
    pdf_results = await pdf_tasks
    
    return press_results + pdf_results

async def scan_priority_companies_async(batch_size=20):
    """Scan high-priority companies more frequently"""
    csv_path = os.path.join("data", "master_companies.csv")
    if not os.path.exists(csv_path):
        return []
    
    df = pd.read_csv(csv_path)
    df = df.dropna(subset=['website'])
    
    # Focus on top companies by market cap (first 100 for now)
    priority_companies = df.head(100)
    
    # Get companies that haven't been checked recently
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS company_scan_log (
                      ticker TEXT PRIMARY KEY, last_scanned DATETIME)''')
    
    cursor.execute('''SELECT ticker FROM company_scan_log 
                      WHERE last_scanned IS NULL 
                         OR last_scanned < datetime('now', '-30 minutes')
                      ORDER BY last_scanned ASC NULLS FIRST
                      LIMIT ?''', (batch_size,))
    
    rows_to_check = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    if not rows_to_check:
        # If no pending companies, get the oldest ones
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ticker FROM companies ORDER BY RANDOM() LIMIT ?", (batch_size,))
        rows_to_check = [row[0] for row in cursor.fetchall()]
        conn.close()
    
    if not rows_to_check:
        return []
    
    # Filter priority companies
    batch_df = priority_companies[priority_companies['ticker'].isin(rows_to_check)]
    
    print(f"🏢 Scanning {len(batch_df)} priority companies for announcements...")
    
    all_signals = []
    async with aiohttp.ClientSession() as session:
        tasks = [scan_company_announcements(session, row['ticker'], row['website']) 
                for _, row in batch_df.iterrows()]
        results = await asyncio.gather(*tasks)
        
        for result in results:
            if result:
                all_signals.extend(result)
    
    # Update scan log
    conn = get_connection()
    cursor = conn.cursor()
    for _, row in batch_df.iterrows():
        cursor.execute('''INSERT INTO company_scan_log (ticker, last_scanned)
                          VALUES (?, datetime('now'))
                          ON CONFLICT(ticker) DO UPDATE SET last_scanned=datetime('now')''', 
                       (row['ticker'],))
    conn.commit()
    conn.close()
    
    return all_signals

if __name__ == "__main__":
    signals = asyncio.run(scan_priority_companies_async(10))
    print(f"Found {len(signals)} company announcements.")
    for signal in signals:
        print(f"{signal['ticker']}: {signal['headline'][:80]}...")
