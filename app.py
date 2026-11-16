"""The app: search a company, or open your watchlist.

Run it with:  streamlit run app.py
"""

import streamlit as st

from research import report, store
from research.edgar import TickerNotFound
from views import comps_tab, dcf_tab, memo_tab, overview, summary_tab, watchlist

st.set_page_config(page_title="Equity Research", page_icon="📊", layout="wide")


@st.cache_data(ttl=3600, show_spinner=False)
def load(ticker: str) -> dict:
    return report.run(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def load_comps(ticker: str, peers: tuple) -> dict:
    return report.run_comps(load(ticker), list(peers))


def open_company(ticker: str) -> None:
    st.session_state["ticker"] = ticker.strip().upper()
    st.session_state["page"] = "company"


# A link like ?ticker=AAPL opens that company directly.
if "page" not in st.session_state:
    st.session_state["page"] = "company"
    st.session_state["ticker"] = st.query_params.get("ticker", "").upper()

with st.sidebar:
    st.title("Equity Research")
    with st.form("search", border=False):
        typed = st.text_input("Ticker", placeholder="e.g. AAPL", max_chars=10)
        if st.form_submit_button("Analyse", type="primary", width="stretch") and typed.strip():
            open_company(typed)

    st.divider()
    st.subheader("Watchlist")
    followed = store.get_watchlist()
    if st.button("Overview of all", width="stretch", disabled=not followed):
        st.session_state["page"] = "watchlist"
    for followed_ticker in followed:
        st.button(followed_ticker, key=f"open_{followed_ticker}", width="stretch",
                  on_click=open_company, args=(followed_ticker,))
    if not followed:
        st.caption("Companies you follow appear here.")

if st.session_state["page"] == "watchlist":
    watchlist.render()
    st.stop()

ticker = st.session_state.get("ticker", "")
if not ticker:
    st.header("Search a company to begin")
    st.write(
        "Type a US-listed company's ticker in the sidebar. The tool pulls its SEC filings and "
        "share price, then runs the metrics, a DCF and a peer comparison."
    )
    st.stop()

try:
    with st.spinner(f"Pulling filings and prices for {ticker}…"):
        data = load(ticker)
except (TickerNotFound, ValueError) as error:
    st.error(str(error))
    st.stop()
except Exception as error:  # noqa: BLE001
    st.error(f"Couldn't load {ticker}: {error}")
    st.stop()

profile, statements = data["profile"], data["statements"]
title, follow = st.columns([5, 1])
title.header(f"{profile['name']} ({ticker})")
if ticker in followed:
    if follow.button("Unfollow", width="stretch"):
        store.remove_from_watchlist(ticker)
        st.rerun()
elif follow.button("☆ Follow", type="primary", width="stretch"):
    store.add_to_watchlist(ticker)
    st.rerun()

st.caption(
    f"{profile['industry']} · latest fiscal year ended {statements.index[-1]:%d %b %Y} · "
    "source: SEC filings (annual reports) and Yahoo Finance prices"
)
if profile["is_financial"]:
    st.warning(
        "This is a financial company (bank, insurer or similar). Debt is its raw material "
        "rather than its funding, so margins, free cash flow, EV multiples and leverage "
        "are not meaningful. Net income, return on equity and P/E still are."
    )
if data["price_error"]:
    st.warning(f"Share price unavailable right now, so valuation is blank. ({data['price_error']})")

tabs = st.tabs(["Overview", "DCF", "Comps", "Valuation summary", "AI memo"])
with tabs[0]:
    overview.render(data)
with tabs[1]:
    dcf_output = dcf_tab.render(data)
with tabs[2]:
    comps_result = comps_tab.render(data, load_comps)
with tabs[3]:
    summary_tab.render(data, dcf_output, comps_result)
with tabs[4]:
    memo_tab.render(data, dcf_output, comps_result)

st.caption(
    "Figures are matched automatically from company filings, so some are approximations: "
    "total debt mostly excludes leases, and market cap uses the latest fiscal year's "
    "average diluted share count. Nothing here is investment advice."
)
