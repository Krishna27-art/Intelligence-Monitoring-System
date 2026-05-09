import aiohttp
import asyncio
from bs4 import BeautifulSoup
import sqlite3
import os
import pandas as pd
from database.db_manager import get_connection
from utils.dedup_manager import DedupManager
from utils.time_filter import is_article_valid
from utils.ingestion import normalize_datetime, source_confidence, clean_text
from datetime import datetime

# Initialize Deduplication Manager
dedup = DedupManager()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Top 20 companies to prioritize for fast monitoring
TOP_COMPANIES = [
    ('RELIANCE', 'https://www.ril.com'),
    ('TCS', 'https://www.tcs.com'),
    ('HDFCBANK', 'https://www.hdfcbank.com'),
    ('INFY', 'https://www.infosys.com'),
    ('ICICIBANK', 'https://www.icicibank.com'),
    ('HINDUNILVR', 'https://www.hul.co.in'),
    ('ITC', 'https://www.itcportal.com'),
    ('SBIN', 'https://www.sbi.co.in'),
    ('BHARTIARTL', 'https://www.airtel.in'),
    ('BAJFINANCE', 'https://www.bajajfinserv.in'),
    ('KOTAKBANK', 'https://www.kotak.com'),
    ('LT', 'https://www.larsentoubro.com'),
    ('AXISBANK', 'https://www.axisbank.com'),
    ('ASIANPAINT', 'https://www.asianpaints.com'),
    ('MARUTI', 'https://www.marutisuzuki.com'),
    ('TITAN', 'https://www.titancompany.in'),
    ('SUNPHARMA', 'https://www.sunpharma.com'),
    ('ADANIENT', 'https://www.adani.com'),
    ('ULTRACEMCO', 'https://www.ultratechcement.com'),
    ('NESTLEIND', 'https://www.nestle.in'),
]

async def fetch_url(session, url, timeout=10):
    """Asynchronously fetches page content"""
    try:
        async with session.get(url, headers=HEADERS, timeout=timeout) as response:
            if response.status == 200:
                return await response.text()
    except Exception:
        return None
    return None

# Keywords for important announcements
ANNOUNCEMENT_KEYWORDS = [
    'profit', 'loss', 'earnings', 'result', 'dividend', 'bonus', 'split', 
    'acquisition', 'merger', 'deal', 'partnership', 'contract', 'order',
    'board meeting', 'record date', 'ex-dividend', 'rights issue',
    'quarterly results', 'annual results', 'financial results',
    'revenue', 'sales', 'growth', 'expansion', 'investment', 
    'q1', 'q2', 'q3', 'q4', 'fy24', 'fy25', 'fy26',
    'outcome', 'approved', 'declared', 'announced'
]

async def scan_company_press_releases(session, ticker, website):
    """Scan company press releases and announcements pages"""
    if not website or str(website) == 'nan':
        return []
    
    signals = []
    
    # Common investor relations paths
    ir_paths = [
        '/investors/press-releases',
        '/investors/announcements',
        '/investors/news',
        '/investor/press-releases',
        '/investor/news',
        '/media/press-releases',
        '/newsroom',
        '/press',
        '/about/news',
        '/corporate/investors/news',
    ]
    
    for path in ir_paths[:3]:  # Limit to 3 paths per company for speed
        try:
            url = f"{website.rstrip('/')}{path}"
            content = await fetch_url(session, url, timeout=8)
            if not content:
                continue
            
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for article/news items
            article_selectors = [
                'article', '.news-item', '.press-release', '.announcement',
                '.media-item', '.news-list li', '.press-list li',
                '[class*="news"]', '[class*="press"]', '[class*="announcement"]'
            ]
            
            articles = []
            for selector in article_selectors:
                articles = soup.select(selector)
                if articles:
                    break
            
            # Also try finding links with keywords
            if not articles:
                all_links = soup.find_all('a', href=True)
                for link in all_links[:15]:  # Check first 15 links
                    link_text = clean_text(link.get_text())
                    if any(keyword in link_text.lower() for keyword in ANNOUNCEMENT_KEYWORDS):
                        if len(link_text) > 15 and len(link_text) < 200:
                            articles.append(link)
            
            for article in articles[:5]:  # Process max 5 articles
                try:
                    # Extract title
                    title_elem = article.find(['h1', 'h2', 'h3', 'h4']) or article
                    title = clean_text(title_elem.get_text())
                    
                    if len(title) < 15 or len(title) > 300:
                        continue
                    
                    # Check if it has announcement keywords
                    has_keywords = any(keyword in title.lower() for keyword in ANNOUNCEMENT_KEYWORDS)
                    if not has_keywords:
                        continue
                    
                    # Get URL
                    link_elem = article if article.name == 'a' else article.find('a', href=True)
                    if not link_elem:
                        continue
                    
                    article_url = link_elem.get('href', '')
                    if article_url.startswith('/'):
                        article_url = f"{website.rstrip('/')}{article_url}"
                    elif not article_url.startswith('http'):
                        continue
                    
                    # Deduplication
                    if dedup.is_seen(article_url):
                        continue
                    
                    signals.append({
                        "ticker": ticker,
                        "headline": title,
                        "source": f"{ticker} Website",
                        "text": title,
                        "url": article_url,
                        "published_at": datetime.now(),
                        "confidence": 85,  # High confidence for direct company source
                    })
                    
                except Exception:
                    continue
                    
        except Exception:
            continue
    
    return signals

async def scan_batch_async(batch_size=20):
    """Main entry point for async batch scanning - prioritizes top companies"""
    
    # Start with top companies first
    companies_to_scan = TOP_COMPANIES[:min(10, batch_size)]
    
    # If batch_size > 10, add random companies from CSV
    if batch_size > 10:
        csv_path = os.path.join("data", "master_companies.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            df = df.dropna(subset=['website'])
            # Exclude already selected top companies
            df = df[~df['ticker'].isin([c[0] for c in TOP_COMPANIES])]
            if len(df) > 0:
                additional = df.sample(n=min(batch_size - 10, len(df)))
                for _, row in additional.iterrows():
                    companies_to_scan.append((row['ticker'], row['website']))
    
    print(f"🕷️ Launching High-Speed Async Scan across {len(companies_to_scan)} companies (Top 10 prioritized)...")
    
    all_signals = []
    async with aiohttp.ClientSession() as session:
        tasks = [scan_company_press_releases(session, ticker, website) for ticker, website in companies_to_scan]
        results = await asyncio.gather(*tasks)
        
        for result in results:
            if result:
                all_signals.extend(result)
                
    print(f"✅ Website scan found {len(all_signals)} press releases/announcements")
    return all_signals

if __name__ == "__main__":
    # Test run
    signals = asyncio.run(scan_batch_async(10))
    print(f"Found {len(signals)} signals.")
