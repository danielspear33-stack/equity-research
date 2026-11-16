"""Watchlist page: every company you follow, from the latest daily snapshot."""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from research import refresh, store

from .formatting import dollars, money, multiple, signed_percent


def render() -> None:
    st.header("Watchlist")
    watchlist = store.get_watchlist()
    if not watchlist:
        st.info("You aren't following any companies yet. Search for one and click “Follow”.")
        return

    if st.button("Refresh now"):
        with st.spinner("Refreshing every company on the watchlist…"):
            _, errors = refresh.refresh_all(watchlist)
        st.cache_data.clear()
        for ticker, error in errors.items():
            st.warning(f"{ticker} could not be refreshed: {error}")

    snapshots = store.get_snapshots()
    if snapshots.empty:
        st.info("No snapshots yet. Click “Refresh now”, or wait for the daily refresh.")
        return
    latest = snapshots.sort_values("date").groupby("ticker").tail(1).set_index("ticker")
    latest = latest.reindex(watchlist)

    st.caption(f"Latest snapshot: {snapshots['date'].max():%d %b %Y}. "
               "The daily refresh adds one row per company each weekday.")

    recent_cutoff = (date.today() - timedelta(days=7)).isoformat()

    def filing(row):
        if pd.isna(row["latest_filing"]):
            return "–"
        new = " (new)" if str(row["latest_filing_date"]) >= recent_cutoff else ""
        return f"{row['latest_filing']} on {row['latest_filing_date']}{new}"

    table = pd.DataFrame(
        {
            "Company": latest["name"].fillna("not refreshed yet"),
            "Price": latest["price"].map(dollars),
            "Market cap": latest["market_cap"].map(money),
            "P/E": latest["price_to_earnings"].map(multiple),
            "EV / EBITDA": latest["ev_to_ebitda"].map(multiple),
            "DCF value": latest["dcf_value"].map(dollars),
            "DCF vs price": latest["dcf_upside"].map(signed_percent),
            "Latest filing": latest.apply(filing, axis=1),
        }
    )
    table.index.name = "Ticker"
    st.dataframe(table, width="stretch")
    st.caption("DCF value uses your saved assumptions where you have set them, otherwise the "
               "mechanical defaults. Open a company from the sidebar for the detail.")

    st.subheader("History")
    choice = st.selectbox("Company", watchlist)
    history = snapshots[snapshots["ticker"] == choice].set_index("date")[["price", "dcf_value"]]
    history = history.rename(columns={"price": "Share price", "dcf_value": "DCF value"})
    if len(history) < 2:
        st.caption("A chart appears here once there are at least two days of snapshots.")
    else:
        st.line_chart(history)
