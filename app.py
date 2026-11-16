"""The app: search a company, or open your watchlist.

Run it with:  streamlit run app.py
"""

import streamlit as st

from research import edgar, insiders, report, store
from research.edgar import TickerNotFound
from views import (bank_tab, comps_tab, dcf_tab, glance, memo_tab, overview, payouts_tab,
                   quarterly_tab, style, summary_tab, watchlist)

st.set_page_config(page_title="Equity Research", page_icon="📊", layout="wide")
style.apply()


@st.cache_data(ttl=3600, show_spinner=False)
def load(ticker: str) -> dict:
    return report.run(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def load_comps(ticker: str, peers: tuple) -> dict:
    return report.run_comps(load(ticker), list(peers))


@st.cache_data(ttl=3600, show_spinner=False)
def load_insiders(cik: int):
    return insiders.get_trades(cik)


def open_company(ticker: str) -> None:
    st.session_state["ticker"] = ticker.strip().upper()
    st.session_state["page"] = "company"


def open_picked_company() -> None:
    """Opens the company chosen in the start page's search box."""
    picked = st.session_state.get("start_search")
    if picked is not None:
        open_company(edgar.company_list()[picked][0])


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
    companies = edgar.company_list()
    st.header("Search a company")
    st.selectbox(
        "Company", range(len(companies)), index=None, key="start_search",
        format_func=lambda i: f"{companies[i][0]} · {companies[i][2]}",
        placeholder="Type a ticker or a company name", label_visibility="collapsed",
        on_change=open_picked_company,
    )
    st.caption(
        f"Covers every company with shares listed in the US: {len(companies):,} tickers, from "
        "the SEC's own list. The tool pulls the company's filings and share price, then shows "
        "its latest results, a health check, a DCF (or a bank valuation), a peer comparison, "
        "payouts to shareholders and insider trades."
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
    f"{profile['industry']} · latest figures: {data['latest']['label']} · "
    f"last annual report: fiscal year to {statements.index[-1]:%d %b %Y} · "
    "source: SEC filings and Yahoo Finance prices"
)
if profile["is_financial"]:
    st.warning(
        "This is a financial company (bank, insurer or similar). Debt is its raw material "
        "rather than its funding, so margins, free cash flow, EV multiples and leverage "
        "are not meaningful. It is valued on book value, return on equity and dividends "
        "instead: see the Bank valuation tab."
    )
if data["price_error"]:
    st.warning(f"Share price unavailable right now, so valuation is blank. ({data['price_error']})")

is_financial = profile["is_financial"]

# The handful of numbers that matter most. The space is reserved here and
# filled in below, once the valuation tabs have produced their results.
at_a_glance = st.container()

# Market data first, then this tool's own analysis (style.MARKET_DATA_TABS
# says where the split is, and colours the second group gold).
style.legend()
(overview_tab, quarterly, payouts, valuation, peers, summary, ai_memo) = st.tabs(
    ["Overview", "Quarterly", "Payouts & insiders",
     "Bank valuation" if is_financial else "DCF", "Comps", "Valuation summary", "AI memo"])

with overview_tab:
    overview.render(data)
with quarterly:
    quarterly_tab.render(data)
with payouts:
    insider_summary = payouts_tab.render(data, load_insiders)
with valuation:
    # Banks and insurers get their own valuation; everyone else gets the DCF.
    dcf_output = None if is_financial else dcf_tab.render(data)
    bank_output = bank_tab.render(data) if is_financial else None
with peers:
    comps_result = comps_tab.render(data, load_comps)
with summary:
    summary_tab.render(data, dcf_output, comps_result, bank_output)
with ai_memo:
    memo_tab.render(data, dcf_output, comps_result, bank_output, insider_summary)
with at_a_glance:
    glance.render(data, dcf_output, comps_result, bank_output)

st.caption(
    "Figures are matched automatically from company filings, so some are approximations: "
    "total debt mostly excludes leases, and market value uses the share count on the cover "
    "of the newest report where one is given. Nothing here is investment advice."
)
