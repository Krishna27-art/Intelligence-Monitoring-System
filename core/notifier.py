"""
📱 Telegram Notifier

Mobile-first interface for critical market alerts.
Send high-priority signals directly to your phone.

Setup:
1. Go to Telegram, search for @BotFather
2. Type /newbot, name your bot (e.g., "NSE_BSE_Alerts_Bot")
3. Copy the HTTP API Token
4. Send a message to your bot
5. Visit: https://api.telegram.org/bot<TOKEN>/getUpdates
6. Find your chat_id in the response
"""

import os
import asyncio
from typing import Optional

# ⚠️ CONFIGURATION: Set these via environment variables or edit directly
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_TELEGRAM_CHAT_ID_HERE")

# Import telegram bot library
try:
    from telegram import Bot
    from telegram.constants import ParseMode
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    print("⚠️ python-telegram-bot not installed. Run: pip install python-telegram-bot")


class TelegramNotifier:
    """Telegram bot wrapper for sending market alerts"""
    
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token or TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or TELEGRAM_CHAT_ID
        self.bot = None
        self.enabled = False
        
        # Validate configuration
        if not TELEGRAM_AVAILABLE:
            print("❌ Telegram library not available")
            return
            
        if self.token in ["YOUR_TELEGRAM_BOT_TOKEN_HERE", "", None]:
            print("⚠️ Telegram token not configured. Set TELEGRAM_BOT_TOKEN env variable.")
            return
            
        if self.chat_id in ["YOUR_TELEGRAM_CHAT_ID_HERE", "", None]:
            print("⚠️ Telegram chat ID not configured. Set TELEGRAM_CHAT_ID env variable.")
            return
        
        try:
            self.bot = Bot(token=self.token)
            self.enabled = True
            print("✅ Telegram bot initialized successfully")
        except Exception as e:
            print(f"❌ Telegram bot init failed: {e}")
    
    async def send_alert(self, ticker: str, headline: str, score: int, 
                         source: str, event_type: str = "NEWS") -> bool:
        """
        Send formatted alert to Telegram
        
        Args:
            ticker: Company ticker (e.g., RELIANCE)
            headline: News headline
            score: Sentiment score (-100 to +100)
            source: News source (e.g., Economic Times)
            event_type: NEWS, PROFIT, DEAL, DIVIDEND, NSE_FILING
        """
        if not self.enabled or not self.bot:
            print("⚠️ Telegram not configured. Alert not sent.")
            return False
        
        # Determine emoji based on score and event type
        if score >= 80:
            emoji = "🚀"  # Very positive
        elif score >= 50:
            emoji = "📈"  # Positive
        elif score <= -80:
            emoji = "🚨"  # Very negative
        elif score <= -50:
            emoji = "📉"  # Negative
        else:
            emoji = "📊"  # Neutral
        
        # Event type emoji
        type_emojis = {
            "PROFIT": "💰",
            "DEAL": "🤝",
            "DIVIDEND": "💵",
            "NSE_FILING": "🏛️",
            "NEWS": "📰"
        }
        type_emoji = type_emojis.get(event_type, "📰")
        
        # Format the message
        message = f"""
{emoji} <b>HIGH PRIORITY MARKET SIGNAL</b> {type_emoji}

<b>{ticker}</b>
<i>{headline}</i>

⚡ Score: <b>{score}/100</b>
📡 Source: {source}
🏷️ Type: {event_type}

<a href='https://www.google.com/search?q={ticker}+share+price'>Check Price ↗</a>
"""
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id, 
                text=message, 
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            print(f"📱 Telegram alert sent: {ticker} ({score})")
            return True
        except Exception as e:
            print(f"❌ Telegram send failed: {e}")
            return False
    
    async def send_test_message(self) -> bool:
        """Send test message to verify configuration"""
        if not self.enabled:
            print("⚠️ Cannot send test - Telegram not configured")
            return False
        
        test_msg = """
🧪 <b>Test Message</b>

Your NSE/BSE Intelligence bot is working!
You will receive alerts for high-priority market signals.
"""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=test_msg,
                parse_mode=ParseMode.HTML
            )
            print("✅ Test message sent successfully!")
            return True
        except Exception as e:
            print(f"❌ Test failed: {e}")
            return False
    
    def is_configured(self) -> bool:
        """Check if Telegram is properly configured"""
        return self.enabled


# Global notifier instance (lazy initialization)
_notifier_instance = None

def get_notifier() -> TelegramNotifier:
    """Get or create the global notifier instance"""
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = TelegramNotifier()
    return _notifier_instance


# Convenience function for quick alerts
async def send_critical_alert(ticker: str, headline: str, score: int, 
                              source: str, event_type: str = "NEWS") -> bool:
    """Quick function to send alert without managing notifier instance"""
    notifier = get_notifier()
    return await notifier.send_alert(ticker, headline, score, source, event_type)


if __name__ == "__main__":
    # Test the notifier
    print("📱 Testing Telegram Notifier...")
    print("=" * 50)
    
    # Check configuration
    notifier = get_notifier()
    
    if not notifier.is_configured():
        print("\n⚠️ Telegram not configured!")
        print("\nTo set up:")
        print("1. Message @BotFather on Telegram")
        print("2. Create a bot and get token")
        print("3. Set environment variables:")
        print("   export TELEGRAM_BOT_TOKEN='your_token'")
        print("   export TELEGRAM_CHAT_ID='your_chat_id'")
        print("\nOr edit core/notifier.py directly (not recommended)")
    else:
        # Run test
        asyncio.run(notifier.send_test_message())
        
        # Send sample alert
        asyncio.run(send_critical_alert(
            ticker="RELIANCE",
            headline="Reliance Industries reports record Q4 profit surge of 25% YoY",
            score=85,
            source="Economic Times",
            event_type="PROFIT"
        ))
