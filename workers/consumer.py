"""
⚙️ Redis Consumer Worker

Event-driven processor that:
1. Pulls events from Redis queue (blocking - zero CPU when idle)
2. Runs 3-Stage AI Pipeline (keyword filter -> rule scoring -> BERT for high-value only)
3. Saves to database
4. Sends Telegram alerts for critical signals

This runs 24/7 and uses 0% CPU while waiting for new events.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import redis
import asyncio
import signal
from datetime import datetime
from typing import Dict, Any

# Import our modules
from core.pipeline import process_event
from core.notifier import send_critical_alert, get_notifier
from database.db_manager import insert_signal

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
QUEUE_NAME = os.getenv("REDIS_QUEUE", "market_events")

# Alert thresholds
ALERT_SCORE_THRESHOLD = int(os.getenv("ALERT_THRESHOLD", 70))  # Only alert if |score| >= 70


class MarketDataConsumer:
    """Consumer that processes events from Redis queue"""
    
    def __init__(self):
        self.redis_client = None
        self.connected = False
        self.running = False
        self.telegram = get_notifier()
        
        # Statistics
        self.stats = {
            "total_processed": 0,
            "important_signals": 0,  # Passed Stage 1 filter
            "ai_processed": 0,        # Reached Stage 3 (BERT)
            "alerts_sent": 0,
            "filtered_out": 0,        # Rejected by Stage 1
            "errors": 0
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
            return False
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return False
    
    def process_single_event(self, event_json: str) -> bool:
        """
        Process one event through the 3-Stage Pipeline
        
        Stage 1: Fast regex filter (eliminates 80% of junk)
        Stage 2: Rule-based scoring
        Stage 3: BERT AI (only for high-value events)
        """
        try:
            event = json.loads(event_json)
            
            ticker = event.get('ticker', 'UNKNOWN')
            headline = event.get('headline', '')
            text = event.get('text', headline)
            source = event.get('source', 'Unknown')
            event_type = event.get('event_type', event.get('type', 'NEWS'))
            url = event.get('url', '')
            
            print(f"\n📥 Processing: {ticker} - {headline[:50]}...")
            
            # Run 3-Stage Pipeline
            result = process_event(text, ticker)
            
            # Update statistics
            self.stats["total_processed"] += 1
            
            if not result['is_important']:
                self.stats["filtered_out"] += 1
                print(f"   ❌ FILTERED (Stage 1): Not important")
                return True
            
            self.stats["important_signals"] += 1
            
            if result['ai_processed']:
                self.stats["ai_processed"] += 1
                print(f"   🧠 AI PROCESSED (Stage 3)")
            else:
                print(f"   ⚡ RULE-BASED (Stage 2)")
            
            # Save to database
            insert_signal(
                ticker=ticker,
                headline=headline,
                source=source,
                sentiment=result['sentiment'],
                score=result['score'],
                summary=result['summary'],
                event_type=event_type,
                metric="",  # Could extract from text
                published_at=event.get('published_at'),
                url=url,
                confidence=event.get('confidence', 70)
            )
            print(f"   💾 Saved to DB (Score: {result['score']})")
            
            # Send Telegram alert for high-priority signals
            if abs(result['score']) >= ALERT_SCORE_THRESHOLD:
                print(f"   📱 ALERT TRIGGERED (Score: {result['score']})")
                try:
                    # Run async telegram send
                    asyncio.run(send_critical_alert(
                        ticker=ticker,
                        headline=headline,
                        score=result['score'],
                        source=source,
                        event_type=event_type
                    ))
                    self.stats["alerts_sent"] += 1
                except Exception as e:
                    print(f"   ⚠️ Telegram alert failed: {e}")
            else:
                print(f"   💾 Saved only (Score {result['score']} < threshold {ALERT_SCORE_THRESHOLD})")
            
            return True
            
        except json.JSONDecodeError as e:
            print(f"❌ JSON decode error: {e}")
            self.stats["errors"] += 1
            return False
        except Exception as e:
            print(f"❌ Error processing event: {e}")
            self.stats["errors"] += 1
            return False
    
    def run(self):
        """
        Main consumer loop.
        Uses BRPOP (blocking pop) - consumes 0% CPU while waiting.
        """
        if not self.connected:
            print("❌ Cannot start consumer - Redis not connected")
            return
        
        self.running = True
        
        print(f"\n{'='*60}")
        print("⚙️ CONSUMER WORKER STARTED")
        print(f"{'='*60}")
        print(f"Connected to Redis: {REDIS_HOST}:{REDIS_PORT}")
        print(f"Queue: {QUEUE_NAME}")
        print(f"Alert threshold: |score| >= {ALERT_SCORE_THRESHOLD}")
        print(f"Telegram configured: {self.telegram.is_configured()}")
        print(f"\n✨ Consumer is now LISTENING...")
        print(f"   (Zero CPU usage while waiting)")
        print(f"   Press Ctrl+C to stop\n")
        print(f"{'='*60}\n")
        
        # Setup signal handlers for graceful shutdown
        def signal_handler(sig, frame):
            print("\n🛑 Shutdown signal received...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        while self.running:
            try:
                # BRPOP = Blocking Right Pop
                # Waits indefinitely (timeout=0) until an event appears
                # This is the key to event-driven architecture - no polling!
                result = self.redis_client.brpop(QUEUE_NAME, timeout=5)
                
                if result is None:
                    # Timeout occurred (no events in 5 seconds)
                    continue
                
                # result is a tuple: (queue_name, event_json)
                queue_name, event_json = result
                
                # Process the event
                self.process_single_event(event_json)
                
            except redis.ConnectionError as e:
                print(f"❌ Redis connection lost: {e}")
                self.running = False
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
                self.stats["errors"] += 1
        
        # Graceful shutdown
        self.print_stats()
        print("\n✅ Consumer stopped gracefully")
    
    def print_stats(self):
        """Print processing statistics"""
        print(f"\n{'='*60}")
        print("📊 CONSUMER STATISTICS")
        print(f"{'='*60}")
        print(f"Total events processed:     {self.stats['total_processed']}")
        print(f"Important signals:          {self.stats['important_signals']}")
        print(f"AI-processed (BERT):        {self.stats['ai_processed']}")
        print(f"Filtered out (junk):        {self.stats['filtered_out']}")
        print(f"Telegram alerts sent:       {self.stats['alerts_sent']}")
        print(f"Errors:                     {self.stats['errors']}")
        
        if self.stats['total_processed'] > 0:
            efficiency = (self.stats['filtered_out'] / self.stats['total_processed']) * 100
            print(f"\n🎯 Efficiency: {efficiency:.1f}% of events filtered before AI")
        
        print(f"{'='*60}\n")
    
    def drain_queue(self):
        """
        Process all events currently in queue (non-blocking)
        Useful for testing or catching up after downtime.
        """
        if not self.connected:
            print("❌ Not connected to Redis")
            return
        
        print(f"\n🌊 Draining queue...")
        count = 0
        
        while True:
            # Non-blocking pop
            result = self.redis_client.rpop(QUEUE_NAME)
            if result is None:
                break
            
            self.process_single_event(result)
            count += 1
        
        print(f"✅ Drained {count} events from queue")


def run_consumer():
    """Main entry point for consumer worker"""
    consumer = MarketDataConsumer()
    
    if not consumer.connect():
        print("❌ Failed to start - Redis connection failed")
        print("Make sure Redis is running:")
        print("  Local: redis-server")
        print("  Docker: docker run -p 6379:6379 -d redis")
        return
    
    consumer.run()


def run_drain():
    """Drain all events from queue (non-blocking)"""
    consumer = MarketDataConsumer()
    
    if not consumer.connect():
        print("❌ Redis connection failed")
        return
    
    consumer.drain_queue()
    consumer.print_stats()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Market Data Consumer")
    parser.add_argument("--drain", action="store_true", help="Drain all events and exit")
    args = parser.parse_args()
    
    if args.drain:
        run_drain()
    else:
        run_consumer()
