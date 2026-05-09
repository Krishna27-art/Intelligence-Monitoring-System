import requests
import feedparser
import pandas as pd
import os
import time
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

def scrape_economic_times():
    """Scrape latest news from Economic Times"""
    try:
        url = "https://economictimes.indiatimes.com/markets/stocks/news"
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        news_items = []
        articles = soup.find_all('div', class_='eachStory')
        
        for article in articles[:20]:  # Get latest 20 articles
            try:
                title_elem = article.find('h3')
                if not title_elem: continue
                
                title = clean_text(title_elem.get_text())
                link_elem = article.find('a')
                if not link_elem: continue
                
                url = "https://economictimes.indiatimes.com" + link_elem.get('href', '')
                if not url or dedup.is_seen(url): continue
                
                # Extract time if available
                time_elem = article.find('span', class_='date-format')
                published_at = datetime.now() if not time_elem else None
                
                news_items.append({
                    "headline": title,
                    "source": "Economic Times",
                    "ticker": "MARKET",
                    "text": title,
                    "url": url,
                    "published_at": published_at,
                    "confidence": source_confidence("Economic Times"),
                })
            except Exception as e:
                continue
                
        return news_items
    except Exception as e:
        print(f"ET scraping error: {e}")
        return []

def scrape_mint():
    """Scrape latest news from Mint"""
    try:
        url = "https://www.livemint.com/market/stock-market-news"
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        news_items = []
        articles = soup.find_all('div', class_='headlineSec')
        
        for article in articles[:20]:
            try:
                title_elem = article.find('h2')
                if not title_elem: continue
                
                title = clean_text(title_elem.get_text())
                link_elem = article.find('a')
                if not link_elem: continue
                
                url = "https://www.livemint.com" + link_elem.get('href', '')
                if not url or dedup.is_seen(url): continue
                
                news_items.append({
                    "headline": title,
                    "source": "Mint",
                    "ticker": "MARKET",
                    "text": title,
                    "url": url,
                    "published_at": datetime.now(),
                    "confidence": source_confidence("Mint"),
                })
            except Exception:
                continue
                
        return news_items
    except Exception as e:
        print(f"Mint scraping error: {e}")
        return []

def scrape_moneycontrol():
    """Scrape latest news from Moneycontrol"""
    try:
        url = "https://www.moneycontrol.com/news/business/markets/"
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        news_items = []
        articles = soup.find_all('li', class_='clearfix')
        
        for article in articles[:20]:
            try:
                title_elem = article.find('h2')
                if not title_elem: continue
                
                title = clean_text(title_elem.get_text())
                link_elem = article.find('a')
                if not link_elem: continue
                
                url = link_elem.get('href', '')
                if not url or dedup.is_seen(url): continue
                
                news_items.append({
                    "headline": title,
                    "source": "Moneycontrol",
                    "ticker": "MARKET",
                    "text": title,
                    "url": url,
                    "published_at": datetime.now(),
                    "confidence": source_confidence("Moneycontrol"),
                })
            except Exception:
                continue
                
        return news_items
    except Exception as e:
        print(f"Moneycontrol scraping error: {e}")
        return []

def scrape_business_standard():
    """Scrape latest news from Business Standard"""
    try:
        url = "https://www.business-standard.com/markets"
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        news_items = []
        articles = soup.find_all('div', class_='card-holder')
        
        for article in articles[:20]:
            try:
                title_elem = article.find('h2')
                if not title_elem: continue
                
                title = clean_text(title_elem.get_text())
                link_elem = article.find('a')
                if not link_elem: continue
                
                url = "https://www.business-standard.com" + link_elem.get('href', '')
                if not url or dedup.is_seen(url): continue
                
                news_items.append({
                    "headline": title,
                    "source": "Business Standard",
                    "ticker": "MARKET",
                    "text": title,
                    "url": url,
                    "published_at": datetime.now(),
                    "confidence": source_confidence("Business Standard"),
                })
            except Exception:
                continue
                
        return news_items
    except Exception as e:
        print(f"Business Standard scraping error: {e}")
        return []

def get_all_indian_news():
    """Aggregate news from all Indian financial news platforms"""
    print("🔄 Scraping Indian financial news platforms...")
    
    all_news = []
    
    # Scrape all platforms in parallel
    scrapers = [scrape_economic_times, scrape_mint, scrape_moneycontrol, scrape_business_standard]
    
    for scraper in scrapers:
        try:
            news = scraper()
            all_news.extend(news)
            time.sleep(1)  # Rate limiting
        except Exception as e:
            print(f"Scraper error: {e}")
    
    # Filter for fresh content
    fresh_news = []
    for item in all_news:
        if is_content_fresh(item['headline']):
            fresh_news.append(item)
    
    print(f"✅ Found {len(fresh_news)} fresh articles from Indian platforms.")
    return fresh_news

if __name__ == "__main__":
    news = get_all_indian_news()
    for item in news:
        print(f"{item['source']}: {item['headline'][:80]}...")
