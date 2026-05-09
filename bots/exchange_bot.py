import pandas as pd
import os
import requests
from io import StringIO
from datetime import datetime
from utils.dedup_manager import DedupManager
from utils.ingestion import source_confidence, utc_now

# Initialize Deduplication Manager
dedup = DedupManager()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.bseindia.com/markets/marketinfo/corp_actions.aspx'
}

def scan_bse_corporate_actions():
    """Fetches real Corporate Actions (Dividends, Splits, Results) from BSE"""
    print("🏛️ Fetching Real-Time BSE Corporate Actions...")
    
    # BSE Corporate Actions page
    url = "https://www.bseindia.com/corporates/corporate_act.aspx"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"⚠️ BSE Portal returned {response.status_code}")
            return []

        # Try to parse HTML tables
        try:
            tables = pd.read_html(StringIO(response.text), flavor="lxml")
        except ValueError:
            # No tables found - website structure changed
            print("⚠️ BSE website structure changed - no tables found")
            return []
        
        if not tables:
            return []
        
        df = tables[0] # Usually the first table
        
        # Check if this looks like a corporate actions table
        if len(df.columns) < 3:
            print("⚠️ BSE table format unexpected")
            return []
        
        filings = []
        for _, row in df.head(20).iterrows():
            try:
                # Try different column names that BSE might use
                ticker = str(row.get('Security Name', row.get('Security', row.get('Name', 'Unknown')))).split(' ')[0]
                purpose = str(row.get('Purpose', row.get('Purpose of Corporate Action', row.get('Type', 'General Update'))))
                ex_date = str(row.get('Ex Date', row.get('Ex-Date', row.get('Date', 'N/A'))))
                
                # Create a unique URL-like key for deduplication
                unique_key = f"bse_{ticker}_{purpose}_{ex_date}"
                
                if dedup.is_seen(unique_key):
                    continue
                
                filings.append({
                    "ticker": ticker,
                    "headline": f"[BSE Action] {purpose} | Ex-Date: {ex_date}",
                    "source": "BSE Official",
                    "text": f"Corporate Action for {ticker}: {purpose}. Ex-Date listed as {ex_date}.",
                    "url": url,
                    "published_at": utc_now(),
                    "confidence": source_confidence("BSE Official"),
                    "event_type": "NSE_FILING",
                })
            except Exception:
                continue
            
        print(f"✅ Extracted {len(filings)} live actions from BSE.")
        return filings

    except Exception as e:
        message = str(e).replace("\n", " ")
        print(f"❌ BSE Scraper Error: {type(e).__name__}: {message[:240]}")
        return []

def get_simulated_filings():
    """High-quality simulated fallback"""
    csv_path = os.path.join("data", "master_companies.csv")
    if not os.path.exists(csv_path): return []
    df = pd.read_csv(csv_path)
    sample = df.sample(n=min(5, len(df)))
    
    simulated = []
    for _, row in sample.iterrows():
        simulated.append({
            "ticker": row['ticker'],
            "headline": f"[SIMULATED] Outcome of Board Meeting - {row['name']}",
            "source": "Exchange Simulation",
            "text": f"Financial results for {row['name']} were discussed in the recent board meeting.",
            "published_at": utc_now(),
            "confidence": source_confidence("Exchange Simulation"),
        })
    return simulated

def scan_nse_filings():
    """Wrapper to stay compatible with main_orchestrator"""
    # For now, we prioritize BSE as it is more scrape-friendly than NSE
    return scan_bse_corporate_actions()

if __name__ == "__main__":
    actions = scan_bse_corporate_actions()
    for a in actions:
        print(a['headline'])
