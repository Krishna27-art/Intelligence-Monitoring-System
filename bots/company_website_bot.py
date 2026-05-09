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

import ssl
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# Create SSL context that ignores certificate verification for testing
SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

# Keywords that indicate important company announcements
ANNOUNCEMENT_KEYWORDS = [
    'profit', 'loss', 'earnings', 'result', 'dividend', 'bonus', 'split', 
    'acquisition', 'merger', 'deal', 'partnership', 'contract', 'order',
    'board meeting', 'record date', 'ex-dividend', 'rights issue',
    'quarterly results', 'annual results', 'financial results',
    'revenue', 'sales', 'growth', 'expansion', 'investment', 'q1', 'q2', 'q3', 'q4'
]

async def fetch_url(session, url):
    """Asynchronously fetches page content"""
    try:
        connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
        async with aiohttp.ClientSession(connector=connector, headers=HEADERS) as new_session:
            async with new_session.get(url, timeout=15) as response:
                if response.status == 200:
                    return await response.text()
    except Exception as e:
        print(f"Fetch error for {url}: {e}")
    return None

async def scan_reliance_industries(session):
    """Specific scanner for Reliance Industries - known patterns"""
    signals = []
    
    # Reliance investor page
    urls_to_check = [
        "https://www.ril.com/investors/financial-results/",
        "https://www.ril.com/investors/press-releases/",
        "https://www.ril.com/investors/announcements/"
    ]
    
    for url in urls_to_check:
        try:
            content = await fetch_url(session, url)
            if not content:
                continue
                
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for recent announcements
            links = soup.find_all('a', href=True)
            
            for link in links:
                try:
                    link_text = clean_text(link.get_text())
                    link_url = link['href']
                    
                    # Make URL absolute
                    if link_url.startswith('/'):
                        link_url = f"https://www.ril.com{link_url}"
                    elif not link_url.startswith('http'):
                        continue
                        
                    # Check for announcement keywords
                    if any(keyword.lower() in link_text.lower() for keyword in ANNOUNCEMENT_KEYWORDS):
                        if not dedup.is_seen(link_url):
                            signals.append({
                                "ticker": "RELIANCE",
                                "headline": f"📢 Reliance: {link_text}",
                                "source": "Company Website",
                                "text": link_text,
                                "url": link_url,
                                "published_at": datetime.now(),
                                "confidence": 85,
                            })
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"Reliance scan error: {e}")
            continue
            
    return signals

async def scan_tcs_website(session):
    """Specific scanner for TCS - known patterns"""
    signals = []
    
    # TCS investor page
    urls_to_check = [
        "https://www.tcs.com/investors/financial-results",
        "https://www.tcs.com/investors/press-releases",
        "https://www.tcs.com/investors/announcements"
    ]
    
    for url in urls_to_check:
        try:
            content = await fetch_url(session, url)
            if not content:
                continue
                
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for recent announcements
            links = soup.find_all('a', href=True)
            
            for link in links:
                try:
                    link_text = clean_text(link.get_text())
                    link_url = link['href']
                    
                    # Make URL absolute
                    if link_url.startswith('/'):
                        link_url = f"https://www.tcs.com{link_url}"
                    elif not link_url.startswith('http'):
                        continue
                        
                    # Check for announcement keywords
                    if any(keyword.lower() in link_text.lower() for keyword in ANNOUNCEMENT_KEYWORDS):
                        if not dedup.is_seen(link_url):
                            signals.append({
                                "ticker": "TCS",
                                "headline": f"📢 TCS: {link_text}",
                                "source": "Company Website",
                                "text": link_text,
                                "url": link_url,
                                "published_at": datetime.now(),
                                "confidence": 85,
                            })
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"TCS scan error: {e}")
            continue
            
    return signals

async def scan_hdfc_bank(session):
    """Specific scanner for HDFC Bank - known patterns"""
    signals = []
    
    # HDFC Bank investor page
    urls_to_check = [
        "https://www.hdfcbank.com/about-us/investor-relations/financial-results",
        "https://www.hdfcbank.com/about-us/investor-relations/press-releases",
        "https://www.hdfcbank.com/about-us/investor-relations/announcements"
    ]
    
    for url in urls_to_check:
        try:
            content = await fetch_url(session, url)
            if not content:
                continue
                
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for recent announcements
            links = soup.find_all('a', href=True)
            
            for link in links:
                try:
                    link_text = clean_text(link.get_text())
                    link_url = link['href']
                    
                    # Make URL absolute
                    if link_url.startswith('/'):
                        link_url = f"https://www.hdfcbank.com{link_url}"
                    elif not link_url.startswith('http'):
                        continue
                        
                    # Check for announcement keywords
                    if any(keyword.lower() in link_text.lower() for keyword in ANNOUNCEMENT_KEYWORDS):
                        if not dedup.is_seen(link_url):
                            signals.append({
                                "ticker": "HDFCBANK",
                                "headline": f"📢 HDFC Bank: {link_text}",
                                "source": "Company Website",
                                "text": link_text,
                                "url": link_url,
                                "published_at": datetime.now(),
                                "confidence": 85,
                            })
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"HDFC Bank scan error: {e}")
            continue
            
    return signals

async def scan_company_specific(session, ticker, website):
    """Scan specific company with tailored approach"""
    if not website or str(website) == 'nan':
        return []
        
    base_url = website.rstrip('/')
    
    # Use specific scanners for major companies
    if ticker == "RELIANCE":
        return await scan_reliance_industries(session)
    elif ticker == "TCS":
        return await scan_tcs_website(session)
    elif ticker == "HDFCBANK":
        return await scan_hdfc_bank(session)
    
    # Generic scanner for other companies
    signals = []
    
    # Common press release URL patterns
    press_urls = [
        f"{base_url}/investors",
        f"{base_url}/investor-relations",
        f"{base_url}/press-releases",
        f"{base_url}/announcements",
        f"{base_url}/financial-results"
    ]
    
    for press_url in press_urls:
        try:
            content = await fetch_url(session, press_url)
            if not content:
                continue
                
            soup = BeautifulSoup(content, 'html.parser')
            
            # Look for recent announcements
            links = soup.find_all('a', href=True)
            
            for link in links[:20]:  # Limit to first 20 links
                try:
                    link_text = clean_text(link.get_text())
                    link_url = link['href']
                    
                    # Make URL absolute
                    if link_url.startswith('/'):
                        link_url = f"{base_url}{link_url}"
                    elif not link_url.startswith('http'):
                        continue
                        
                    # Check for announcement keywords
                    if any(keyword.lower() in link_text.lower() for keyword in ANNOUNCEMENT_KEYWORDS):
                        if not dedup.is_seen(link_url):
                            signals.append({
                                "ticker": ticker,
                                "headline": f"📢 {ticker}: {link_text}",
                                "source": "Company Website",
                                "text": link_text,
                                "url": link_url,
                                "published_at": datetime.now(),
                                "confidence": 80,
                            })
                except Exception:
                    continue
                    
        except Exception:
            continue
            
    return signals

async def scan_top_companies_async():
    """Scan top companies for announcements"""
    csv_path = os.path.join("data", "master_companies.csv")
    if not os.path.exists(csv_path):
        return []
    
    df = pd.read_csv(csv_path)
    df = df.dropna(subset=['website'])
    
    # Focus on top 20 companies
    top_companies = df.head(20)
    
    print(f"🏢 Scanning top {len(top_companies)} companies for announcements...")
    
    all_signals = []
    async with aiohttp.ClientSession() as session:
        tasks = [scan_company_specific(session, row['ticker'], row['website']) 
                for _, row in top_companies.iterrows()]
        results = await asyncio.gather(*tasks)
        
        for result in results:
            if result:
                all_signals.extend(result)
    
    return all_signals

if __name__ == "__main__":
    signals = asyncio.run(scan_top_companies_async())
    print(f"Found {len(signals)} company announcements.")
    for signal in signals:
        print(f"{signal['ticker']}: {signal['headline'][:80]}...")
        print(f"URL: {signal['url']}")
