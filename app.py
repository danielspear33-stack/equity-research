"""The app: search a company, or open your watchlist.

Run it with:  streamlit run app.py
"""

import streamlit as st

from research import edgar, insiders, report, store
from research.edgar import TickerNotFound
from views import (backtest_page, bank_tab, changes_tab, comps_tab, dcf_tab, earnings_tab, glance,
                   memo_tab, overview, payouts_tab, quarterly_tab, screener_page, style, summary_tab,
                   watchlist)

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


def company_search(key: str, label: str, show_label: bool = True) -> None:
    """A search box over every US-listed company.

    Suggestions narrow as you type a name or a ticker, biggest companies
    first. Picking one shows its ticker in the box and opens the company.
    """
    companies = edgar.company_list()

    def open_picked() -> None:
        picked = st.session_state.get(key)
        if picked is not None:
            open_company(companies[picked][0])

    st.selectbox(
        label, range(len(companies)), index=None, key=key,
        format_func=lambda i: f"{companies[i][0]} · {companies[i][2]}",
        placeholder="Type a name, e.g. Microsoft",
        label_visibility="visible" if show_label else "collapsed",
        # Plain "contains what you typed", in the list's own order, so the
        # biggest companies come first: "m" leads with Microsoft.
        filter_mode="contains",
        on_change=open_picked,
    )


# A link like ?ticker=AAPL opens that company directly.
if "page" not in st.session_state:
    st.session_state["page"] = "company"
    st.session_state["ticker"] = st.query_params.get("ticker", "").upper()

with st.sidebar:
    st.title("Equity Research")
    company_search("sidebar_search", "Find a company by name")
    with st.form("search", border=False):
        typed = st.text_input("Or type a ticker", placeholder="e.g. AAPL", max_chars=10)
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

    st.divider()
    if st.button("Screener", width="stretch",
                 help="About 110 large companies and your watchlist, scored side by side."):
        st.session_state["page"] = "screener"
    if st.button("Backtest", width="stretch",
                 help="Which of this tool's measures would have pointed you the right way in the past?"):
        st.session_state["page"] = "backtest"
    if memo_tab.can_write_here():
        st.toggle(
            "Run AI analysis automatically", value=store.get_setting("auto_ai", True), key="auto_ai",
            on_change=lambda: store.save_setting("auto_ai", st.session_state["auto_ai"]),
            help="When you open a company, Claude starts writing its memo, reading its latest "
                 "results announcement and comparing its last two annual reports straight away, "
                 "in the background. Saved results are reused "
                 "until the company reports again. Turn this off when flicking through many "
                 "companies, to save your Claude usage.",
        )

if st.session_state["page"] == "watchlist":
    watchlist.render()
    st.stop()
if st.session_state["page"] == "backtest":
    backtest_page.render()
    st.stop()
if st.session_state["page"] == "screener":
    screener_page.render(open_company)
    st.stop()

ticker = st.session_state.get("ticker", "")
if not ticker:
    st.header("Search a company")
    company_search("start_search", "Company", show_label=False)
    st.caption(
        f"Covers every company with shares listed in the US: {len(edgar.company_list()):,} tickers, from "
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
(overview_tab, quarterly, payouts, valuation, peers, summary, ai_analysis) = st.tabs(
    ["Overview", "Quarterly", "Payouts & insiders",
     "Bank valuation" if is_financial else "DCF", "Comps", "Valuation summary", "AI analysis"])

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
with ai_analysis:
    # All three are drawn every time, so each can start its own background work
    # as soon as the company is opened.
    memo_view, earnings_view, changes_view = st.tabs(
        ["Research memo", "Latest results announcement", "What changed in the annual report"])
    with memo_view:
        memo_tab.render(data, dcf_output, comps_result, bank_output, insider_summary)
    with earnings_view:
        earnings_tab.render(data)
    with changes_view:
        changes_tab.render(data)
with at_a_glance:
    glance.render(data, dcf_output, comps_result, bank_output)

st.caption(
    "Figures are matched automatically from company filings, so some are approximations: "
    "total debt mostly excludes leases, and market value uses the share count on the cover "
    "of the newest report where one is given. Nothing here is investment advice."
)
