import sys
import os
os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")

import html
from datetime import datetime

import streamlit as st
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

import pandas as pd
from database.db_manager import get_dashboard_data, init_db, get_connection
from bots.news_bot import get_all_news, match_ticker
from bots.exchange_bot import scan_nse_filings
from database.db_manager import insert_signal
from utils.ingestion import clean_text, source_confidence


# ==========================================
# 1. PAGE CONFIG & THEME
# ==========================================
st.set_page_config(page_title="Intelligence Terminal", layout="wide", page_icon="⚡", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .stApp { background-color: #0B0F19; color: #D1D5DB; }
    blockquote, p, span, div { color: #D1D5DB !important; }
    #MainMenu, footer, header { visibility: hidden; }
    
    .metric-card {
        background-color: #131722; border: 1px solid #1E293B; border-radius: 10px;
        padding: 20px; text-align: center;
    }
    .metric-value { font-size: 32px; font-weight: 700; margin: 0; }
    .metric-label { font-size: 13px; color: #6B7280; text-transform: uppercase; letter-spacing: 1px; margin-top: 5px; }
    
    .feed-card {
        background-color: #131722; border-left: 4px solid #1E293B;
        border-radius: 0 8px 8px 0; padding: 16px 20px; margin-bottom: 12px;
    }
    .feed-pos { border-left-color: #26A69A; }
    .feed-neg { border-left-color: #EF5350; }
    .feed-neu { border-left-color: #FF9800; }
    .feed-deal { border-left-color: #2962FF; }
    
    .ticker-badge { background-color: #1E293B; color: #3B82F6; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 13px; }
    .score-badge { padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 13px; float: right; }
    .source-text { font-size: 11px; color: #4B5563; margin-top: 8px; }
    
    .empty-state {
        text-align: center; padding: 60px 20px; background-color: #131722;
        border: 1px dashed #1E293B; border-radius: 15px; margin-top: 20px;
    }
    
    .stButton > button { background-color: #2962FF; color: white; border: none; border-radius: 8px; padding: 12px 24px; font-weight: bold; width: 100%; }
    .stButton > button:hover { background-color: #1E53E5; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 2. DATA LOGIC
# ==========================================
init_db()

def get_ai_helpers():
    from ai_engine.sentiment import analyze_headline, extract_metadata
    return analyze_headline, extract_metadata

def run_manual_scan():
    st.toast("🤖 Starting Bots...", icon="🚀")
    total_saved = 0
    total_scanned = 0
    analyze_headline, extract_metadata = get_ai_helpers()
    
    # --- 1. NEWS BOT ---
    try:
        news = get_all_news()
        for item in news:
            total_scanned += 1
            # Clean HTML before analysis and storage
            clean_headline = clean_text(item.get('headline', ''))
            clean_body = clean_text(item.get('text') or clean_headline)
            ticker = item.get('ticker') or match_ticker(clean_headline)
            
            try:
                sentiment, score, summary = analyze_headline(clean_body)
                event_type, metric = extract_metadata(clean_headline)
            except Exception as ai_err:
                print(f"⚠️ AI Error: {ai_err}. Using fallback.")
                sentiment, score, summary = "NEUTRAL", 0, clean_body[:50]
                event_type, metric = "NEWS", ""
                
            if insert_signal(
                ticker, clean_headline, item.get('source', 'News'), sentiment, score, summary,
                event_type, metric, published_at=item.get("published_at"), url=item.get("url"),
                confidence=item.get("confidence"),
            ):
                total_saved += 1
    except Exception as e:
        st.error(f"News Bot Failed: {e}")
        print(f"❌ NEWS BOT ERROR: {e}")

    # --- 2. NSE BOT ---
    try:
        filings = scan_nse_filings()
        for item in filings:
            total_scanned += 1
            clean_headline = clean_text(item.get('headline', ''))
            clean_body = clean_text(item.get('text') or clean_headline)
            try:
                sentiment, score, summary = analyze_headline(clean_body)
                event_type, metric = "NSE_FILING", extract_metadata(clean_headline)[1]
            except:
                sentiment, score, summary = "NEUTRAL", 0, clean_body[:50]
                event_type, metric = "NSE_FILING", ""
            if insert_signal(
                item.get('ticker', 'MARKET'), clean_headline, item.get('source', 'Exchange'),
                sentiment, score, summary, event_type, metric,
                published_at=item.get("published_at"), url=item.get("url"),
                confidence=item.get("confidence", source_confidence(item.get("source", "Exchange"))),
            ):
                total_saved += 1
    except Exception as e:
        st.error(f"NSE Bot Failed: {e}")
        print(f"❌ NSE BOT ERROR: {e}")

    # --- 3. WEBSITE DEAL BOT ---
    try:
        from bots.deal_crawler import run_deep_website_scan
        total_saved += run_deep_website_scan() or 0
    except Exception as e:
        st.error(f"Website Bot Failed: {e}")
        print(f"❌ WEBSITE BOT ERROR: {e}")

    # --- Note: Demo data injection removed to show only real RSS news ---
    if total_scanned == 0 and total_saved == 0:
        st.info("No new data found in this scan. Real-time RSS feeds are checked every cycle.")

    st.session_state['last_run'] = f"Live at {datetime.now().strftime('%H:%M:%S')} ({total_saved} new)"
    st.rerun()

def get_filtered_data(event_type=None, hours=24):
    conn = get_connection()
    cursor = conn.cursor()
    query = """SELECT ticker, headline, source, sentiment, score, summary,
                      COALESCE(published_at, timestamp) as timestamp,
                      ingested_at, event_type, metric, url, confidence, event_id
               FROM signals
               WHERE COALESCE(published_at, timestamp) >= datetime('now', '-{} hours')""".format(hours)
    params = []
    if event_type:
        if isinstance(event_type, (list, tuple, set)):
            placeholders = ", ".join("?" for _ in event_type)
            query += f" AND event_type IN ({placeholders})"
            params.extend(event_type)
        else:
            query += " AND event_type = ?"
            params.append(event_type)
    query += " ORDER BY COALESCE(published_at, timestamp) DESC LIMIT 50"
    data = cursor.execute(query, params).fetchall()
    conn.close()
    return data

# ==========================================
# 3. UI LAYOUT
# ==========================================
col_title, col_action = st.columns([4, 1])
with col_title:
    st.markdown("<h1 style='margin:0; color: white;'>⚡ Intelligence Terminal</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='margin:0; font-size:13px; color:#6B7280;'>NSE + BSE Market Monitor • {st.session_state.get('last_run', 'Not yet run')}</p>", unsafe_allow_html=True)
with col_action:
    st.markdown("<div style='height: 25px;'></div>", unsafe_allow_html=True)
    if st.button("⚡ Run Full Scan"):
        run_manual_scan()

st.markdown("<hr style='border: 1px solid #1F2937; margin: 10px 0 25px 0;'>", unsafe_allow_html=True)

stats, _, sectors = get_dashboard_data()

# KPI Metrics
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.markdown(f"<div class='metric-card'><p class='metric-value' style='color:#26A69A'>{stats['pos'] or 0}</p><p class='metric-label'>Positive</p></div>", unsafe_allow_html=True)
with kpi2:
    st.markdown(f"<div class='metric-card'><p class='metric-value' style='color:#EF5350'>{stats['neg'] or 0}</p><p class='metric-label'>Negative</p></div>", unsafe_allow_html=True)
with kpi3:
    st.markdown(f"<div class='metric-card'><p class='metric-value' style='color:#FF9800'>{stats['neu'] or 0}</p><p class='metric-label'>Neutral</p></div>", unsafe_allow_html=True)
with kpi4:
    st.markdown(f"<div class='metric-card'><p class='metric-value' style='color:#2962FF'>{stats['total'] or 0}</p><p class='metric-label'>Total Events</p></div>", unsafe_allow_html=True)

# FEED & SIDEBAR (Removed gap="20px" to fix your specific error)
col_feed, col_sidebar = st.columns([2.5, 1])

with col_feed:
    tab1, tab2, tab3, tab4 = st.tabs(["📰 All News", "💰 Profits & Deals", "🏛️ NSE Filings", "📊 Table View"])
    
    def render_feed(data):
        if not data:
            st.markdown("<div class='empty-state'><div style='font-size: 60px;'>📡</div><h3 style='color: white;'>Waiting for Data</h3><p style='color: #6B7280;'>Click 'Run Full Scan' to fetch live data.</p></div>", unsafe_allow_html=True)
            return
        for s in data:
            if s['event_type'] in ('DEAL', 'PROFIT', 'DIVIDEND', 'DEAL_PROFIT'): css_class = "feed-deal"
            elif s['sentiment'] == 'POSITIVE': css_class = "feed-pos"
            elif s['sentiment'] == 'NEGATIVE': css_class = "feed-neg"
            else: css_class = "feed-neu"
            
            score = s['score'] or 0
            score_color = "#26A69A" if score > 0 else ("#EF5350" if score < 0 else "#FF9800")
            ticker = html.escape(str(s['ticker'] or 'MARKET'))
            clean_headline = clean_text(str(s['headline'] or ''))
            headline = html.escape(clean_headline)
            source = html.escape(str(s['source'] or ''))
            timestamp = html.escape(str(s['timestamp'] or ''))
            confidence = int(s['confidence'] or 0)
            metric = html.escape(str(s["metric"] or ""))
            metric_html = f'<span style="color: #60A5FA; font-size: 12px; font-weight: bold;">{metric}</span>' if metric else ""
            
            # Add URL if available
            url = s['url'] if 'url' in s.keys() else None
            url_html = f'<a href="{url}" target="_blank" style="color: #60A5FA; text-decoration: none; font-size: 12px; margin-left: 8px;">🔗 View</a>' if url and str(url).strip() else ""
            
            # Color code sources
            source_colors = {
                'Economic Times': '#F97316',
                'Moneycontrol': '#2563EB',
                'Business Standard': '#16A34A',
                'Mint': '#8B5CF6',
                'BSE Official': '#DC2626',
                'NSE Official': '#DC2626',
            }
            source_color = source_colors.get(source, '#6B7280')
            
            # Format source for display
            display_source = source
            if ' Website' in source:
                display_source = f"📰 {source.replace(' Website', '')}"
            elif source in source_colors:
                display_source = f"📡 {source}"
            
            card_html = f"""<div class="feed-card {css_class}">
<div style="display: flex; justify-content: space-between; align-items: center;">
<div>
<span class="ticker-badge">{ticker}</span>
<span style="background-color: {source_color}30; color: {source_color}; font-size: 11px; padding: 2px 8px; border-radius: 4px; margin-left: 6px; font-weight: 500;">{display_source}</span>
{metric_html}
{url_html}
</div>
<span class="score-badge" style="background-color: {score_color}20; color: {score_color};">{score}/100</span>
</div>
<div style="font-size: 15px; margin-top: 12px; color: #E5E7EB;">{headline}</div>
<div class="source-text">Published {timestamp} • Confidence {confidence}</div>
</div>"""
            st.markdown(card_html, unsafe_allow_html=True)

    with tab1: render_feed(get_filtered_data())
    with tab2: render_feed(get_filtered_data(["DEAL", "PROFIT", "DIVIDEND", "DEAL_PROFIT"]))
    with tab3: render_feed(get_filtered_data("NSE_FILING"))
    with tab4:
        all_data = get_filtered_data()
        if all_data:
            # Convert list of rows to a DataFrame for Step 2 & 3 of your fix
            df = pd.DataFrame([dict(row) for row in all_data])
            # Ensure columns are cleaned as per your snippet
            df['clean_title'] = df['headline'].apply(clean_text)
            st.dataframe(
                df[['clean_title', 'ticker', 'sentiment', 'score', 'confidence', 'timestamp', 'ingested_at', 'source']],
                width='stretch',
                hide_index=True
            )
        else:
            st.info("No data available for table view.")

with col_sidebar:
    st.markdown("<h3 style='color: white;'>Sector Sentiment</h3>", unsafe_allow_html=True)
    if not sectors:
        st.info("Waiting for scan data...")
    else:
        for sec in sectors[:8]:
            if sec['sector']:
                score = sec['avg_score'] or 0
                bar_color = "#26A69A" if score > 10 else ("#EF5350" if score < -10 else "#FF9800")
                st.markdown(f"**{sec['sector']}**")
                st.markdown(f"<div style='background-color: #1E293B; height: 8px; border-radius: 4px; margin-bottom: 15px;'><div style='background-color: {bar_color}; height: 100%; width: {max(10, (score+100)/2)}%;'></div></div>", unsafe_allow_html=True)
