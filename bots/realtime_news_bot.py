import requests
import feedparser
import pandas as pd
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from database.db_manager import get_connection
from utils.dedup_manager import DedupManager
from utils.ingestion import clean_text, source_confidence
from utils.time_filter import is_content_fresh

# Initialize Deduplication Manager
dedup = DedupManager()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_company_list():
    """Get list of companies to monitor"""
    csv_path = os.path.join("data", "master_companies.csv")
    if not os.path.exists(csv_path):
        return []
    
    df = pd.read_csv(csv_path)
    # Focus on top 50 companies
    return df.head(50)[['ticker', 'name']].to_dict('records')

def scrape_economic_times_realtime():
    """Real-time Economic Times scraper using RSS feed"""
    try:
        # ET RSS feed for markets/stocks
        url = "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"
        response = requests.get(url, headers=HEADERS, timeout=15)
        feed = feedparser.parse(response.content)
        
        news_items = []
        companies = get_company_list()
        
        for entry in feed.entries[:20]:
            try:
                title = clean_text(entry.get('title', ''))
                if len(title) < 10:
                    continue
                    
                url = entry.get('link', '')
                if not url or dedup.is_seen(url):
                    continue
                
                # Parse published date
                published_at = datetime.now()
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_at = datetime(*entry.published_parsed[:6])
                
                # Check for company mentions
                matched_ticker = "MARKET"
                for company in companies[:20]:
                    if company['name'].lower() in title.lower() or company['ticker'].lower() in title.lower():
                        matched_ticker = company['ticker']
                        break
                
                # Only include if fresh (last 72 hours)
                if (datetime.now() - published_at).days > 3:
                    continue
                
                news_items.append({
                    "headline": title,
                    "source": "Economic Times",
                    "ticker": matched_ticker,
                    "text": clean_text(entry.get('summary', title)),
                    "url": url,
                    "published_at": published_at,
                    "confidence": 75 if matched_ticker != "MARKET" else 60,
                })
                
            except Exception:
                continue
                
        return news_items
    except Exception as e:
        print(f"ET RSS error: {e}")
        return []

def scrape_moneycontrol_realtime():
    """Real-time Moneycontrol scraper using RSS feed"""
    try:
        # Moneycontrol RSS feed for latest news
        url = "https://www.moneycontrol.com/rss/latestnews.xml"
        response = requests.get(url, headers=HEADERS, timeout=15)
        feed = feedparser.parse(response.content)
        
        news_items = []
        companies = get_company_list()
        
        for entry in feed.entries[:20]:
            try:
                title = clean_text(entry.get('title', ''))
                if len(title) < 10:
                    continue
                    
                url = entry.get('link', '')
                if not url or dedup.is_seen(url):
                    continue
                
                # Parse published date
                published_at = datetime.now()
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_at = datetime(*entry.published_parsed[:6])
                
                # Check for company mentions
                matched_ticker = "MARKET"
                for company in companies[:20]:
                    if company['name'].lower() in title.lower() or company['ticker'].lower() in title.lower():
                        matched_ticker = company['ticker']
                        break
                
                # Only include if fresh (last 72 hours)
                if (datetime.now() - published_at).days > 3:
                    continue
                
                news_items.append({
                    "headline": title,
                    "source": "Moneycontrol",
                    "ticker": matched_ticker,
                    "text": clean_text(entry.get('summary', title)),
                    "url": url,
                    "published_at": published_at,
                    "confidence": 75 if matched_ticker != "MARKET" else 60,
                })
                
            except Exception:
                continue
                
        return news_items
    except Exception as e:
        print(f"Moneycontrol RSS error: {e}")
        return []

def scrape_business_standard_realtime():
    """Real-time Business Standard scraper using RSS feed"""
    try:
        # Business Standard RSS feed for markets
        url = "https://www.business-standard.com/rss/markets-106.rss"
        response = requests.get(url, headers=HEADERS, timeout=15)
        feed = feedparser.parse(response.content)
        
        news_items = []
        companies = get_company_list()
        
        for entry in feed.entries[:20]:
            try:
                title = clean_text(entry.get('title', ''))
                if len(title) < 10:
                    continue
                    
                url = entry.get('link', '')
                if not url or dedup.is_seen(url):
                    continue
                
                # Parse published date
                published_at = datetime.now()
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_at = datetime(*entry.published_parsed[:6])
                
                # Check for company mentions
                matched_ticker = "MARKET"
                for company in companies[:20]:
                    if company['name'].lower() in title.lower() or company['ticker'].lower() in title.lower():
                        matched_ticker = company['ticker']
                        break
                
                # Only include if fresh (last 72 hours)
                if (datetime.now() - published_at).days > 3:
                    continue
                
                news_items.append({
                    "headline": title,
                    "source": "Business Standard",
                    "ticker": matched_ticker,
                    "text": clean_text(entry.get('summary', title)),
                    "url": url,
                    "published_at": published_at,
                    "confidence": 75 if matched_ticker != "MARKET" else 60,
                })
                
            except Exception:
                continue
                
        return news_items
    except Exception as e:
        print(f"Business Standard RSS error: {e}")
        return []

def scrape_mint_realtime():
    """Real-time Mint scraper using RSS feed"""
    try:
        # Mint RSS feed
        url = "https://www.livemint.com/rss/markets"
        response = requests.get(url, headers=HEADERS, timeout=15)
        feed = feedparser.parse(response.content)
        
        news_items = []
        companies = get_company_list()
        
        for entry in feed.entries[:20]:
            try:
                title = clean_text(entry.get('title', ''))
                if len(title) < 10:
                    continue
                    
                url = entry.get('link', '')
                if not url or dedup.is_seen(url):
                    continue
                
                # Parse published date
                published_at = datetime.now()
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_at = datetime(*entry.published_parsed[:6])
                
                # Check for company mentions
                matched_ticker = "MARKET"
                for company in companies[:20]:
                    if company['name'].lower() in title.lower() or company['ticker'].lower() in title.lower():
                        matched_ticker = company['ticker']
                        break
                
                # Only include if fresh (last 72 hours)
                if (datetime.now() - published_at).days > 3:
                    continue
                
                news_items.append({
                    "headline": title,
                    "source": "Mint",
                    "ticker": matched_ticker,
                    "text": clean_text(entry.get('summary', title)),
                    "url": url,
                    "published_at": published_at,
                    "confidence": 75 if matched_ticker != "MARKET" else 60,
                })
                
            except Exception:
                continue
                
        return news_items
    except Exception as e:
        print(f"Mint RSS error: {e}")
        return []

def get_realtime_indian_news():
    """Get real-time news from Indian financial platforms"""
    print("🔄 REAL-TIME: Scraping Indian financial news...")
    
    all_news = []
    
    # Scrape all platforms
    scrapers = [
        scrape_economic_times_realtime,
        scrape_moneycontrol_realtime,
        scrape_business_standard_realtime,
        scrape_mint_realtime
    ]
    
    for scraper in scrapers:
        try:
            news = scraper()
            all_news.extend(news)
            print(f"✅ {scraper.__name__}: {len(news)} articles")
        except Exception as e:
            print(f"❌ {scraper.__name__} error: {e}")
    
    # Filter for fresh content
    fresh_news = []
    for item in all_news:
        if is_content_fresh(item['headline']):
            fresh_news.append(item)
    
    print(f"📊 Total fresh articles: {len(fresh_news)}")
    return fresh_news

if __name__ == "__main__":
    news = get_realtime_indian_news()
    print(f"\n🔥 REAL-TIME NEWS RESULTS:")
    for item in news:
        print(f"{item['source']} | {item['ticker']} | {item['headline'][:80]}...")
        print(f"   🔗 {item['url']}")
        print()
