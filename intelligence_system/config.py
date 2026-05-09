import os
from dotenv import load_dotenv


load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


SOURCES = {
    "bse": "https://www.bseindia.com/sensex/rss.xml",
    "et": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "moneycontrol": "https://www.moneycontrol.com/rss/MCtopnews.xml",
    "mint": "https://www.livemint.com/rss/markets",
    "biz_standard": "https://www.business-standard.com/rss/markets-106.rss",
}


KEYWORDS = [
    "profit",
    "revenue",
    "dividend",
    "order",
    "deal",
    "contract",
    "acquisition",
    "merger",
    "board meeting",
    "buyback",
    "stake sale",
    "guidance",
    "result",
    "earnings",
    "net profit",
    "loss",
]


USE_SQLITE = True


DB_CONFIG = {
    "sqlite_path": os.path.join(BASE_DIR, "intelligence.db"),
    "dedup_path": os.path.join(BASE_DIR, "seen_urls.db"),
    "postgres": {
        "dbname": os.getenv("DB_NAME", "postgres"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "password"),
        "host": os.getenv("DB_HOST", "localhost"),
    },
}


INTERVALS = {
    "exchange": 60,
    "news": 300,
    "dashboard": 60,
}


MAX_ARTICLE_AGE_HOURS = 6
