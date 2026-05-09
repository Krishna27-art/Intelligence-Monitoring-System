# ⚡ Intelligence Monitoring System - Complete Documentation

## 📋 SYSTEM 1: Intelligence Monitoring System (News & Fundamentals)

---

### 1. What the System Does

**Purpose:** Real-time market intelligence terminal that monitors 8,000+ NSE/BSE companies for financial signals before they hit mainstream news.

**Core Functions:**
- **News Aggregation:** Scrapes Economic Times, Mint, Moneycontrol, Business Standard via RSS feeds
- **Exchange Monitoring:** Scrapes BSE corporate actions (dividends, board meetings, results)
- **Company Website Monitoring:** Async scanning of 20 top company IR pages for press releases
- **AI Sentiment Analysis:** BERT-based sentiment scoring (-100 to +100) with smart financial keyword filtering
- **Event Classification:** Categorizes signals as PROFIT, DEAL, DIVIDEND, NEWS
- **Dashboard Display:** Bloomberg-style Streamlit UI with color-coded source badges

**Key Value:** Catches company announcements (profits, deals, dividends) within minutes of release on company websites or exchange portals.

---

### 2. Programming Language & Framework

```
Language: Python 3.10+
Framework: Streamlit (Dashboard), Asyncio (Scraping)
AI/ML: HuggingFace Transformers (BERT sentiment)
Database: SQLite3 with WAL mode
```

**Key Dependencies (requirements.txt):**
```
streamlit          # Dashboard UI
feedparser         # RSS feed parsing
transformers       # BERT sentiment analysis
torch/torchvision  # PyTorch backend
pandas             # Data processing
requests           # HTTP requests
beautifulsoup4     # HTML parsing
lxml               # XML parsing
aiohttp            # Async HTTP
pdfplumber         # PDF text extraction
xmltodict          # XML to dict conversion
schedule           # Scheduling (if needed)
plotly             # Charts (if needed)
```

---

### 3. Folder Structure

```
/Users/pandu/Desktop/Intelligence Monitoring System/
│
├── main_orchestrator.py          # ENTRY POINT - Async orchestrator
│
├── bots/                         # DATA INGESTION LAYER
│   ├── __init__.py
│   ├── news_bot.py              # Google News RSS aggregator
│   ├── realtime_news_bot.py     # ET, Mint, MC, BS RSS scrapers (ACTIVE)
│   ├── exchange_bot.py          # BSE corporate actions scraper
│   ├── website_bot.py           # Async company website scanner (20 top companies)
│   ├── company_website_bot.py   # Specific company IR page scanners
│   ├── deal_crawler.py          # Deep website crawler
│   ├── press_release_bot.py     # Press release detector
│   └── indian_news_bot.py       # Legacy HTML scraper (replaced by RSS)
│
├── ai_engine/                    # INTELLIGENCE LAYER
│   ├── __init__.py
│   └── sentiment.py             # BERT sentiment + keyword filtering
│
├── database/                     # PERSISTENCE LAYER
│   ├── __init__.py
│   └── db_manager.py            # SQLite operations + migrations
│
├── utils/                        # UTILITY LAYER
│   ├── dedup_manager.py         # MD5 URL deduplication
│   ├── time_filter.py          # Date validation (24h filter)
│   └── ingestion.py            # HTML cleaning, confidence scoring
│
├── dashboard/                    # VISUALIZATION LAYER
│   ├── __init__.py
│   ├── app.py                   # ENTRY POINT - Streamlit dashboard
│   └── .streamlit/              # Streamlit config
│
├── data/                         # DATA STORAGE
│   ├── intelligence.db          # SQLite database (signals, companies)
│   ├── master_companies.csv     # 8,000 NSE/BSE companies
│   ├── seen_urls.txt            # Deduplication cache (MD5 hashes)
│   └── scan_state.txt           # Scraper state tracking
│
├── .venv/                        # Virtual environment
├── .venv-1/                      # Backup virtual environment
│
├── requirements.txt             # Python dependencies
├── README.md                    # This file
└── RUN_INSTRUCTIONS.md          # Quick start guide
```

---

### 4. Entry Point Files

**Primary Orchestrator (Background Data Collection):**
```python
# File: main_orchestrator.py
# Command: python3 main_orchestrator.py

Key Components:
- process_item()           # Processes each news item through AI pipeline
- main_loop()              # Async infinite loop (10s sleep)
  - Step 1: realtime_news_bot (RSS feeds - ET, Mint, MC, BS)
  - Step 2: exchange_bot (BSE corporate actions)
  - Step 3: news_bot (Google News backup)
  - Step 4: website_bot (Company IR pages - 20 top companies)
```

**Dashboard UI (Frontend):**
```python
# File: dashboard/app.py
# Command: streamlit run dashboard/app.py

Key Components:
- render_feed()            # Renders news cards with color-coded sources
- get_filtered_data()      # 24-hour time filter on SQLite queries
- run_manual_scan()        # Manual trigger for full scan
- 4 Tabs: All News, Profits & Deals, NSE Filings, Table View
```

---

### 5. APIs / Brokers / Data Sources Used

**RSS Feeds (Primary News Sources):**
```
Economic Times:  https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms
Mint:            https://www.livemint.com/rss/markets
Moneycontrol:    https://www.moneycontrol.com/rss/latestnews.xml
Business Std:    https://www.business-standard.com/rss/markets-106.rss
```

**Exchange Portals (Corporate Actions):**
```
BSE: https://www.bseindia.com/corporates/corporate_act.aspx
```

**Company Websites Monitored (Top 20 Priority):**
```
RELIANCE    - https://www.ril.com/investors/
TCS         - https://www.tcs.com/investors/
HDFCBANK    - https://www.hdfcbank.com/investor/
INFY        - https://www.infosys.com/investors/
ICICIBANK   - https://www.icicibank.com/investor/
HINDUNILVR  - https://www.hul.co.in/investors/
ITC         - https://www.itcportal.com/investor/
SBIN        - https://www.sbi.co.in/web/investor-relations
BHARTIARTL  - https://www.airtel.in/about-bharti/investors/
BAJFINANCE  - https://www.bajajfinserv.in/investor-relations
KOTAKBANK   - https://www.kotak.com/en/investor-relations.html
LT          - https://www.larsentoubro.com/investor/
AXISBANK    - https://www.axisbank.com/investor-relations
ASIANPAINT  - https://www.asianpaints.com/investors/
MARUTI      - https://www.marutisuzuki.com/investor-relations
TITAN       - https://www.titancompany.in/investors/
SUNPHARMA   - https://www.sunpharma.com/investor-relations
ADANIENT    - https://www.adani.com/investors
ULTRACEMCO  - https://www.ultratechcement.com/investor-relations
NESTLEIND   - https://www.nestle.in/investors
```

**Google News RSS (Backup):**
```
Uses RSS with company ticker queries
```

---

### 6. Database Structure (SQLite3)

**File:** `data/intelligence.db`

**Schema:**
```sql
-- Main signals table
CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT,                    -- Company ticker (RELIANCE, TCS)
    headline TEXT,                  -- News headline
    source TEXT,                    -- Source (Economic Times, BSE Official)
    sentiment TEXT,                 -- POSITIVE, NEGATIVE, NEUTRAL
    score INTEGER,                  -- -100 to +100
    summary TEXT,                   -- AI-generated summary
    event_type TEXT DEFAULT 'NEWS', -- NEWS, PROFIT, DEAL, DIVIDEND, NSE_FILING
    metric TEXT DEFAULT '',         -- Extracted metrics (Rs 500 Cr, 25%)
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    published_at DATETIME,          -- Original publication time
    ingested_at DATETIME,           -- When we captured it
    url TEXT,                       -- Link to full article
    event_id TEXT,                  -- Unique event hash
    confidence INTEGER DEFAULT 60   -- Data reliability score
);

-- Companies master list
CREATE TABLE companies (
    ticker TEXT PRIMARY KEY,
    name TEXT,
    sector TEXT,
    exchange TEXT,
    website TEXT
);

-- Tracking tables
CREATE TABLE website_snapshots (ticker TEXT PRIMARY KEY, content_hash TEXT, last_checked DATETIME);
CREATE TABLE sitemap_urls (ticker TEXT, url TEXT, UNIQUE(ticker, url));
CREATE TABLE pdf_inventory (ticker TEXT, pdf_url TEXT, UNIQUE(ticker, pdf_url));
```

---

### 7. Current Running Mode

**Independent Operation:** ✅ YES

```bash
# Terminal 1 - Background scraper (runs 24/7)
python3 main_orchestrator.py

# Terminal 2 - Dashboard (user interface)
streamlit run dashboard/app.py
```

**Cycle Time:** 10 seconds (configurable in main_orchestrator.py)
**Database:** Local SQLite (file-based, no server needed)
**Port:** Streamlit runs on port 8502 (configurable)

---

### 8. How It Should Work With Other Trading Systems

**Proposed Integration Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                    MASTER ORCHESTRATOR                        │
│              (Coordinates all 3 systems)                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
┌──────────────┐ ┌──────────┐ ┌──────────────┐
│  SYSTEM 1    │ │ SYSTEM 2 │ │  SYSTEM 3    │
│ Intelligence │ │  Price   │ │   Order      │
│ Monitoring   │ │ Action   │ │  Execution   │
│ (News/Funda) │ │ (Tech)   │ │  (Broker)    │
└──────┬───────┘ └────┬─────┘ └──────┬───────┘
       │              │              │
       │              │              │
       └──────────────┼──────────────┘
                      │
                      ▼
            ┌─────────────────┐
            │  SHARED SIGNAL  │
            │     BUS /       │
            │  EVENT QUEUE    │
            └─────────────────┘
```

**Integration Points:**

1. **Signal Export:** System 1 generates BUY/SELL signals based on news sentiment
2. **Risk Manager:** Shared module validates signals before execution
3. **Unified Database:** All 3 systems write to central PostgreSQL (currently SQLite)
4. **Dashboard:** Single UI showing news + technical + positions
5. **Event Bus:** Redis/Queue for real-time signal distribution

---

### 9. Conflicts & Issues Already Noticed

**Current Issues:**

1. **BSE Scraper Unreliable:**
   - BSE website changes structure frequently
   - `pd.read_html()` fails when tables not found
   - Needs fallback to alternative data sources

2. **Moneycontrol/Business Standard RSS:**
   - Sometimes returns 0 articles (needs retry logic)
   - Rate limiting not implemented

3. **Company Website SSL Issues:**
   - Many Indian company websites have SSL cert problems
   - Currently using `ssl.CERT_NONE` as workaround (security risk)

4. **No Real Broker Integration:**
   - Currently just monitoring, no actual trading
   - Missing order execution layer

5. **SQLite Concurrency:**
   - WAL mode helps but SQLite not ideal for multi-system writes
   - Should migrate to PostgreSQL for unified system

6. **Dependency Conflicts:**
   - `transformers` + `torch` = large memory footprint (~2GB)
   - `pdfplumber` + `pypdfium2` can have version conflicts
   - `aiohttp` and `requests` both used (redundant)

7. **No Authentication/Security:**
   - Dashboard has no login
   - No API keys for data sources
   - Database is unencrypted file

**Resolved Issues:**
- ✅ Fixed old data problem (now 24h filter only)
- ✅ Fixed dashboard error (sqlite3.Row access)
- ✅ Fixed source links (clickable URLs now work)
- ✅ Added color-coded source badges
- ✅ Prioritized top 20 companies for website scanning
- ✅ Reduced cycle time from 60s → 10s

---

## 🚀 QUICK START

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Initialize database
python3 -c "from database.db_manager import init_db; init_db()"

# 3. Start orchestrator (Terminal 1)
python3 main_orchestrator.py

# 4. Start dashboard (Terminal 2)
streamlit run dashboard/app.py

# Dashboard opens at: http://localhost:8502
```

---

## 📊 System Status

| Component | Status | Notes |
|-----------|--------|-------|
| RSS Feeds | ✅ Working | ET + Mint pulling fresh data |
| BSE Scraper | ⚠️ Partial | Structure changes, needs fix |
| Website Bot | ✅ Working | 20 top companies monitored |
| AI Sentiment | ✅ Working | BERT-based, optional |
| Dashboard | ✅ Working | 4 tabs, source badges |
| Database | ✅ Working | SQLite with 24h filter |

---

*End of System 1 Documentation - Ready for integration with Systems 2 & 3*
