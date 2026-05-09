import asyncio
import sqlite3

import pandas as pd
import streamlit as st

import config
from engine import DedupManager, init_db, run_bot, save_to_db


st.set_page_config(page_title="Intelligence Terminal", layout="wide")

st.title("NSE/BSE Intelligence Terminal")


st.sidebar.header("Controls")

if st.sidebar.button("Run Manual Scan"):
    with st.spinner("Fetching signals..."):
        dedup = DedupManager()
        try:
            new_data = asyncio.run(run_bot(dedup))
            count = save_to_db(new_data)
            st.cache_data.clear()
        finally:
            dedup.close()

        st.toast(f"Done. {count} new items added.")


@st.cache_data(ttl=60)
def load_data():
    init_db()
    conn = sqlite3.connect(config.DB_CONFIG["sqlite_path"])
    df = pd.read_sql(
        """
        SELECT published, ingested_at, source, clean_headline, ticker, link, confidence
        FROM signals
        ORDER BY published DESC
        LIMIT 100
        """,
        conn,
    )
    conn.close()
    return df


df = load_data()

if df.empty:
    st.info("No data found. Run a scan first.")
    st.stop()

df["published"] = pd.to_datetime(df["published"], errors="coerce")

total = len(df)
bullish_count = df["clean_headline"].str.contains(
    "profit|deal|order|win|wins|growth|dividend|buyback", case=False, na=False
).sum()
bearish_count = df["clean_headline"].str.contains(
    "loss|fall|drop|fraud|penalty|fine|default", case=False, na=False
).sum()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Signals", total)
col2.metric("Potential Bullish", int(bullish_count))
col3.metric("Potential Bearish", int(bearish_count))
col4.metric("Avg Confidence", f"{df['confidence'].mean():.0f}")

tab1, tab2 = st.tabs(["Live Feed", "Settings"])

with tab1:
    st.subheader("Latest Intelligence")
    st.dataframe(
        df[["published", "source", "confidence", "clean_headline", "ticker", "link"]],
        use_container_width=True,
        hide_index=True,
        column_config={
            "link": st.column_config.LinkColumn("Link", display_text="Source"),
        },
    )

with tab2:
    st.subheader("System Configuration")
    st.json(config.SOURCES)
