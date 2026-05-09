import time
import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db_manager import init_db, insert_signal, get_connection
from bots.news_bot import get_all_news
from bots.realtime_news_bot import get_realtime_indian_news
from bots.exchange_bot import scan_nse_filings
from bots.website_bot import scan_batch_async
from ai_engine.sentiment import analyze_headline, extract_metadata

def process_item(item):
    ticker = item['ticker']
    headline = item['headline']
    source = item['source']
    text = item.get('text', headline)
    
    # AI Processing with new keyword filter
    sentiment, score, summary = analyze_headline(text)
    
    # Use event_type from item if provided (for BSE/NSE data), otherwise extract from headline
    if item.get('event_type'):
        update_type = item['event_type']
        metric = item.get('metric', '')
    else:
        update_type, metric = extract_metadata(headline)
    
    insert_signal(
        ticker, headline, source, sentiment, score, summary, update_type, metric,
        published_at=item.get("published_at"), url=item.get("url"), confidence=item.get("confidence")
    )

async def main_loop():
    """Continuous loop with real-time monitoring for fast news detection"""
    init_db()
    
    cycle = 0
    print("🚀 STARTING REAL-TIME INTELLIGENCE ORCHESTRATOR...")
    
    while True:
        cycle += 1
        print(f"\n{'='*40}")
        print(f"⚡ CYCLE {cycle} - REAL-TIME SCAN")
        print(f"{'='*40}")
        
        # 1. Indian Financial News Platforms (Highest Priority)
        print("📊 Step 1: Scanning Indian Financial News (Real-time)...")
        indian_news = get_realtime_indian_news()
        for item in indian_news:
            process_item(item)
            
        # 2. Official Exchange Actions (Real-Time Source)
        print("🏛️ Step 2: Scanning Exchange Portals...")
        exchange_items = scan_nse_filings()
        for item in exchange_items:
            process_item(item)
            
        # 3. Global News Rotation (Secondary Source)
        print("🌍 Step 3: Scanning Global News Channels...")
        news_items = get_all_news()
        for item in news_items:
            process_item(item)
            
        # 4. High-Speed Async Website Scan (Backup Source)
        print("🕷️ Step 4: Launching Async Website Monitor...")
        website_signals = await scan_batch_async(batch_size=20)
        for item in website_signals:
            process_item(item)
            
        print(f"\n✅ Cycle {cycle} complete.")
        print(f"⚡ Sleeping for 10 seconds for faster updates...")
        await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\n🛑 Orchestrator stopped by user.")
