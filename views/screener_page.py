"""Screener page: about 110 large companies and your watchlist, scored side by side."""

import pandas as pd
import streamlit as st

from research import config, scorecard, screener

SCORES = [name.lower() for name in scorecard.NAMES]
SORTS = {"overall": "Overall score", **{name.lower(): name for name in scorecard.NAMES},
         "fcf_yield": "Free cash flow yield", "revenue_growth": "Sales growth",
         "return_on_capital": "Return on invested capital", "market_cap": "Market value"}


def render(open_company) -> None:
    st.header("Screener")
    st.caption(
        "The built-in list of about 110 large US companies, plus your watchlist, scored on the "
        "same five measures as the shape at the top of each company page. Click a row to open "
        "that company."
    )
    if config.PUBLIC_DEMO:
        st.caption("Showing the last saved table. Refreshing is switched off on the public demo.")
    elif st.button("Refresh the table", help="Re-scores every company from its latest filings and "
                   "today's price. About a minute."):
        bar = st.progress(0.0, "Starting…")
        table, skipped = screener.build(
            progress=lambda done, total, ticker: bar.progress(done / total, f"{ticker} ({done} of {total})"))
        bar.empty()
        screener.save(table)
        if skipped:
            st.caption("Left out: " + "; ".join(f"{t} ({why})" for t, why in skipped.items()))

    table = screener.load_saved()
    if table is None or table.empty:
        st.info("The table hasn't been built yet. Click “Refresh the table”.")
        return

    left, middle, right = st.columns([2, 2, 3])
    order = left.selectbox("Sort by", list(SORTS), format_func=SORTS.get)
    industries = sorted(table["industry"].dropna().unique())
    chosen = middle.multiselect("Industry", industries, placeholder="All industries")
    minimum = right.slider("Minimum overall score", 0.0, 5.0, 0.0, 0.5)

    shown = table[table["overall"].fillna(0) >= minimum]
    if chosen:
        shown = shown[shown["industry"].isin(chosen)]
    shown = shown.sort_values(order, ascending=False, na_position="last").reset_index(drop=True)

    def score_column(label):
        return st.column_config.ProgressColumn(label, min_value=0, max_value=5, format="%.1f")

    display = pd.DataFrame({
        "Ticker": shown["ticker"], "Company": shown["name"],
        "Overall": shown["overall"],
        **{name: shown[name.lower()] for name in scorecard.NAMES},
        "P/E": shown["price_to_earnings"],
        "FCF yield": shown["fcf_yield"] * 100,
        "Sales growth": shown["revenue_growth"] * 100,
        "Operating margin": shown["operating_margin"] * 100,
        "DCF vs price": shown["dcf_gap"] * 100,
        "Market value ($B)": shown["market_cap"] / 1e9,
    })
    event = st.dataframe(
        display, hide_index=True, width="stretch", height=min(38 * len(display) + 40, 720),
        on_select="rerun", selection_mode="single-row",
        # A fresh key after each pick, so coming back to this page doesn't
        # find the old row still selected and reopen that company.
        key=f"screener_table_{st.session_state.get('screener_picks', 0)}",
        column_config={
            "Overall": score_column("Overall"),
            **{name: score_column(name) for name in scorecard.NAMES},
            "P/E": st.column_config.NumberColumn(format="%.1fx"),
            "FCF yield": st.column_config.NumberColumn(format="%.1f%%"),
            "Sales growth": st.column_config.NumberColumn(format="%+.1f%%"),
            "Operating margin": st.column_config.NumberColumn(format="%.1f%%"),
            "DCF vs price": st.column_config.NumberColumn(format="%+.0f%%"),
            "Market value ($B)": st.column_config.NumberColumn(format="%.0f"),
        },
    )
    rows = event.selection.rows if event and event.selection else []
    if rows:
        st.session_state["screener_picks"] = st.session_state.get("screener_picks", 0) + 1
        open_company(shown["ticker"].iloc[rows[0]])
        st.rerun()

    as_of = table["as_of"].iloc[0] if "as_of" in table else "an earlier date"
    st.caption(
        f"{len(shown)} of {len(table)} companies shown. Scored on {as_of}. Scores run from 0 to 5 "
        "on fixed scales and are for narrowing down where to look, not for deciding. The "
        "backtest page shows which of these measures have and haven't worked. The Value score "
        "here leaves out the peer comparison, so it can differ slightly from the company page."
    )
