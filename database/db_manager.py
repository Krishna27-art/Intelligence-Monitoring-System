import sqlite3
import os

from utils.ingestion import clean_text, format_db_datetime, make_event_id, source_confidence, utc_now

DB_PATH = os.path.join("data", "intelligence.db")

def get_connection():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create Companies Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS companies (
                        ticker TEXT PRIMARY KEY, name TEXT, sector TEXT, exchange TEXT, website TEXT)''')
    
    # Create Signals Table (Forced to have event_type and metric)
    cursor.execute('''CREATE TABLE IF NOT EXISTS signals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticker TEXT, headline TEXT, source TEXT, 
                        sentiment TEXT, score INTEGER, summary TEXT,
                        event_type TEXT DEFAULT 'NEWS',
                        metric TEXT DEFAULT '',
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(signals)").fetchall()}
    migrations = {
        "published_at": "ALTER TABLE signals ADD COLUMN published_at DATETIME",
        "ingested_at": "ALTER TABLE signals ADD COLUMN ingested_at DATETIME",
        "url": "ALTER TABLE signals ADD COLUMN url TEXT",
        "event_id": "ALTER TABLE signals ADD COLUMN event_id TEXT",
        "confidence": "ALTER TABLE signals ADD COLUMN confidence INTEGER DEFAULT 60",
    }
    for col, statement in migrations.items():
        if col not in existing_cols:
            cursor.execute(statement)

    cursor.execute("UPDATE signals SET published_at = COALESCE(published_at, timestamp)")
    cursor.execute("UPDATE signals SET ingested_at = COALESCE(ingested_at, timestamp)")
    cursor.execute("UPDATE signals SET confidence = COALESCE(confidence, 60)")
    
    # Create Snapshots Table
    cursor.execute('''CREATE TABLE IF NOT EXISTS website_snapshots (
                    ticker TEXT PRIMARY KEY, content_hash TEXT, last_checked DATETIME)''')
    
    # Advanced Website Bot Tracking Tables
    cursor.execute('''CREATE TABLE IF NOT EXISTS sitemap_urls (
                    ticker TEXT, url TEXT, UNIQUE(ticker, url))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS pdf_inventory (
                    ticker TEXT, pdf_url TEXT, UNIQUE(ticker, pdf_url))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS page_monitoring (
                    ticker TEXT, page_type TEXT, content_hash TEXT, last_updated DATETIME DEFAULT CURRENT_TIMESTAMP, UNIQUE(ticker, page_type))''')
    
    # Indexes for speed
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_time ON signals(timestamp DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_published ON signals(published_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(event_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_identity ON signals(ticker, headline, source)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_event_id ON signals(event_id) WHERE event_id IS NOT NULL")
    
    # --- POPULATE COMPANIES FROM CSV ---
    cursor.execute("SELECT COUNT(*) FROM companies")
    if cursor.fetchone()[0] == 0:
        import csv
        csv_path = os.path.join("data", "master_companies.csv")
        if os.path.exists(csv_path):
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                to_db = [(i['ticker'], i['name'], i['sector'], i['exchange'], i['website']) for i in reader]
                cursor.executemany("INSERT INTO companies (ticker, name, sector, exchange, website) VALUES (?, ?, ?, ?, ?)", to_db)
    
    conn.commit()
    conn.close()

def insert_signal(
    ticker,
    headline,
    source,
    sentiment,
    score,
    summary,
    event_type="NEWS",
    metric="",
    published_at=None,
    url=None,
    confidence=None,
    event_id=None,
):
    conn = None
    try:
        ticker = clean_text(ticker or "MARKET").upper()
        headline = clean_text(headline)
        source = clean_text(source or "")
        summary = clean_text(summary or "")
        metric = clean_text(metric or "")
        url = str(url or "").strip()
        published_at = format_db_datetime(published_at or utc_now())
        ingested_at = format_db_datetime(utc_now())
        confidence = int(confidence if confidence is not None else source_confidence(source))
        event_id = event_id or make_event_id(ticker, headline, published_at, url)

        if not headline:
            return False

        conn = get_connection()
        existing = conn.execute('''
            SELECT 1 FROM signals
            WHERE event_id = ? OR (ticker = ? AND headline = ? AND source = ?)
            LIMIT 1''', (event_id, ticker, headline, source)).fetchone()
        if existing:
            return False

        conn.execute('''
            INSERT INTO signals (
                ticker, headline, source, sentiment, score, summary, event_type, metric,
                timestamp, published_at, ingested_at, url, event_id, confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                ticker, headline, source, sentiment, score, summary, event_type, metric,
                published_at, published_at, ingested_at, url, event_id, confidence
            ))
        conn.commit()
        return True
    except Exception as e:
        print(f"DB Error: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_dashboard_data():
    conn = get_connection()
    cursor = conn.cursor()
    
    stats = cursor.execute(''' 
        SELECT 
            SUM(CASE WHEN sentiment = 'POSITIVE' THEN 1 ELSE 0 END) as pos,
            SUM(CASE WHEN sentiment = 'NEGATIVE' THEN 1 ELSE 0 END) as neg,
            SUM(CASE WHEN sentiment = 'NEUTRAL' THEN 1 ELSE 0 END) as neu,
            COUNT(*) as total
        FROM signals WHERE COALESCE(published_at, timestamp) >= datetime('now', '-1 day')''').fetchone()
        
    signals = cursor.execute(''' 
        SELECT s.ticker, c.sector, s.headline, s.source, s.sentiment, s.score, s.summary,
               COALESCE(s.published_at, s.timestamp) as timestamp, s.event_type, s.confidence, s.url
        FROM signals s
        LEFT JOIN companies c ON s.ticker = c.ticker
        WHERE COALESCE(s.published_at, s.timestamp) >= datetime('now', '-24 hours')
        ORDER BY COALESCE(s.published_at, s.timestamp) DESC LIMIT 50''').fetchall()
        
    sectors = cursor.execute('''
        SELECT c.sector, AVG(s.score) as avg_score 
        FROM signals s JOIN companies c ON s.ticker = c.ticker 
        WHERE COALESCE(s.published_at, s.timestamp) >= datetime('now', '-1 day')
        GROUP BY c.sector ORDER BY avg_score DESC''').fetchall()

    conn.close()
    return stats, signals, sectors
