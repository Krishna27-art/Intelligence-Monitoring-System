"""
📥 Redis Producer Worker

Fetches market data from multiple sources and pushes raw events to Redis queue.
This is the "data ingestion" layer - it does NOT process data, just collects it.

This replaces the old while True loop in main_orchestrator.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import time
import redis
from datetime import datetime
from typing import List, Dict, Any

# Import our bots
from bots.realtime_news_bot import get_realtime_indian_news
from bots.exchange_bot import scan_nse_filings
from bots.website_bot import scan_batch_async
import asyncio

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
QUEUE_NAME = os.getenv("REDIS_QUEUE", "market_events")


class MarketDataProducer:
    """Producer that fetches market data and pushes to Redis"""
    
    def __init__(self):
        self.redis_client = None
        self.connected = False
        self.stats = {
            "total_pushed": 0,
            "cycles_completed": 0,
            "last_cycle_time": None
        }
        
    def connect(self) -> bool:
        """Establish Redis connection"""
        try:
            self.redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=5
            )
            # Test connection
            self.redis_client.ping()
            self.connected = True
            print(f"✅ Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
            return True
        except redis.ConnectionError as e:
            print(f"❌ Redis connection failed: {e}")
            print(f"   Make sure Redis is running: redis-server or docker run -p 6379:6379 redis")
            return False
        except Exception as e:
            print(f"❌ Unexpected error connecting to Redis: {e}")
            return False
    
    def push_event(self, event: Dict[str, Any]) -> bool:
        """Push a single event to Redis queue"""
        if not self.connected or not self.redis_client:
            return False
        
        try:
            # Add timestamp and unique ID
            event["_ingested_at"] = datetime.now().isoformat()
            event["_event_id"] = f"{event.get('ticker', 'UNKNOWN')}_{int(time.time() * 1000)}"
            
            # Push to Redis list (LPUSH = most recent first)
            self.redis_client.lpush(QUEUE_NAME, json.dumps(event))
            self.stats["total_pushed"] += 1
            return True
        except Exception as e:
            print(f"❌ Failed to push event: {e}")
            return False
    
    def fetch_nse_filings(self) -> List[Dict]:
        """Fetch NSE/BSE corporate actions"""
        print("🏛️ Fetching NSE/BSE corporate actions...")
        try:
            filings = scan_nse_filings()
            print(f"   ✅ Found {len(filings)} filings")
            return filings
        except Exception as e:
            print(f"   ⚠️ NSE filings fetch failed: {e}")
            return []
    
    def fetch_news_rss(self) -> List[Dict]:
        """Fetch Indian financial news from RSS feeds"""
        print("📰 Fetching RSS news (ET, Mint, MC, BS)...")
        try:
            news = get_realtime_indian_news()
            print(f"   ✅ Found {len(news)} news articles")
            return news
        except Exception as e:
            print(f"   ⚠️ RSS news fetch failed: {e}")
            return []
    
    async def fetch_company_websites(self) -> List[Dict]:
        """Fetch press releases from company websites"""
        print("🕷️ Fetching company website press releases...")
        try:
            signals = await scan_batch_async(batch_size=20)
            print(f"   ✅ Found {len(signals)} website signals")
            return signals
        except Exception as e:
            print(f"   ⚠️ Website fetch failed: {e}")
            return []
    
    def run_single_cycle(self) -> int:
        """
        Run one complete fetch cycle.
        Returns: Number of events pushed to Redis
        """
        if not self.connected:
            print("❌ Cannot run cycle - Redis not connected")
            return 0
        
        cycle_start = time.time()
        print(f"\n{'='*50}")
        print(f"🚀 PRODUCER CYCLE #{self.stats['cycles_completed'] + 1}")
        print(f"{'='*50}")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        total_pushed = 0
        
        # 1. Fetch NSE/BSE filings (corporate actions)
        filings = self.fetch_nse_filings()
        for item in filings:
            event = {
                "type": "NSE_FILING",
                "ticker": item.get('ticker', 'UNKNOWN'),
                "headline": item.get('headline', ''),
                "source": item.get('source', 'BSE'),
                "text": item.get('text', item.get('headline', '')),
                "url": item.get('url', ''),
                "event_type": item.get('event_type', 'NSE_FILING'),
                "confidence": item.get('confidence', 70)
            }
            if self.push_event(event):
                total_pushed += 1
        
        # 2. Fetch RSS news (async but we call synchronously here)
        news = self.fetch_news_rss()
        for item in news:
            event = {
                "type": "NEWS",
                "ticker": item.get('ticker', 'MARKET'),
                "headline": item.get('headline', ''),
                "source": item.get('source', 'RSS'),
                "text": item.get('text', item.get('headline', '')),
                "url": item.get('url', ''),
                "published_at": item.get('published_at', datetime.now().isoformat()),
                "confidence": item.get('confidence', 60)
            }
            if self.push_event(event):
                total_pushed += 1
        
        # 3. Fetch company website signals
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            website_signals = loop.run_until_complete(self.fetch_company_websites())
            for item in website_signals:
                event = {
                    "type": "WEBSITE",
                    "ticker": item.get('ticker', 'UNKNOWN'),
                    "headline": item.get('headline', ''),
                    "source": item.get('source', 'Company Website'),
                    "text": item.get('text', item.get('headline', '')),
                    "url": item.get('url', ''),
                    "published_at": item.get('published_at', datetime.now().isoformat()),
                    "confidence": item.get('confidence', 85)
                }
                if self.push_event(event):
                    total_pushed += 1
        finally:
            loop.close()
        
        # Update stats
        self.stats["cycles_completed"] += 1
        self.stats["last_cycle_time"] = datetime.now().isoformat()
        
        cycle_duration = time.time() - cycle_start
        print(f"\n{'='*50}")
        print(f"✅ CYCLE COMPLETE: {total_pushed} events pushed to Redis")
        print(f"⏱️ Duration: {cycle_duration:.2f}s")
        print(f"📊 Queue size: {self.redis_client.llen(QUEUE_NAME)}")
        print(f"{'='*50}\n")
        
        return total_pushed
    
    def run_continuous(self, interval_seconds: int = 60):
        """
        Run producer in continuous loop (legacy mode)
        For event-driven architecture, use run_single_cycle() triggered externally
        """
        print(f"🔄 Starting continuous producer (interval: {interval_seconds}s)")
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                self.run_single_cycle()
                print(f"⏳ Sleeping {interval_seconds}s...")
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\n🛑 Producer stopped by user")
            self.print_stats()
    
    def print_stats(self):
        """Print producer statistics"""
        print(f"\n📊 PRODUCER STATS:")
        print(f"   Total cycles: {self.stats['cycles_completed']}")
        print(f"   Total events pushed: {self.stats['total_pushed']}")
        print(f"   Last cycle: {self.stats['last_cycle_time']}")
        if self.connected:
            print(f"   Current queue size: {self.redis_client.llen(QUEUE_NAME)}")


def run_producer_once():
    """
    Run producer once and exit.
    This is the main entry point for event-driven architecture.
    """
    producer = MarketDataProducer()
    
    if not producer.connect():
        print("❌ Cannot start producer - Redis connection failed")
        return 0
    
    return producer.run_single_cycle()


def run_producer_continuous(interval: int = 60):
    """
    Run producer in continuous loop.
    Legacy mode - for testing only.
    """
    producer = MarketDataProducer()
    
    if not producer.connect():
        print("❌ Cannot start producer - Redis connection failed")
        return
    
    producer.run_continuous(interval)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Market Data Producer")
    parser.add_argument("--once", action="store_true", help="Run once and exit (event-driven mode)")
    parser.add_argument("--interval", type=int, default=60, help="Interval between cycles (continuous mode)")
    args = parser.parse_args()
    
    if args.once:
        # Event-driven mode: run once, exit
        count = run_producer_once()
        print(f"Pushed {count} events to Redis")
    else:
        # Legacy continuous mode
        run_producer_continuous(args.interval)
