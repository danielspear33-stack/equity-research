"""Valuation tab for banks, insurers and brokers, which a DCF can't value."""

import pandas as pd
import streamlit as st

from research import financials, market

from .formatting import dollars, multiple, percent, signed_percent

# (field, label, lowest, highest, step, help text) - all shown as percentages.
FIELDS = [
    ("roe", "Return on equity it can sustain", 0.0, 40.0, 0.5,
     "Profit per dollar of shareholders' equity, in a normal year. The default is the average "
     "of the last three fiscal years."),
    ("cost_of_equity", "Return shareholders require", 4.0, 20.0, 0.1,
     "The cost of equity. The default is the 10-year Treasury yield plus beta times a 5% "
     "equity risk premium."),
    ("growth", "Long-run growth", 0.0, 5.0, 0.1,
     "Growth forever. Should not exceed long-run economic growth."),
    ("dividend_growth", "Payout growth, next 5 years", 0.0, 15.0, 0.5,
     "How fast dividends grow before settling at the long-run rate."),
]


def render(data: dict):
    """Draw the tab. Returns {"snapshot", "result", "assumptions"} or None."""
    ticker, v = data["ticker"], data["valuation"]
    if v is None:
        st.info("No share price available, so the valuation can't be worked out.")
        return None
    latest_s = data["latest"]["statements"]
    if pd.isna(latest_s["equity"]) or pd.isna(latest_s["net_income"]) or pd.isna(latest_s["diluted_shares"]):
        st.info("The filings are missing equity, net income or the share count.")
        return None
    price = v["price"]
    snap = financials.snapshot(latest_s, data["statements"], data["metrics"], price)

    st.caption(
        "A standard DCF doesn't work for banks, insurers and brokers: borrowing is their raw "
        "material, so free cash flow means nothing. They are valued on what shareholders own "
        "(book value) and what it earns (return on equity) instead. "
        f"Figures are for the {data['latest']['label']}."
    )

    cols = st.columns(6)
    cols[0].metric("Book value per share", dollars(snap["book_value_per_share"]),
                   help="Shareholders' equity, less preferred shares, per ordinary share.")
    cols[1].metric("Tangible book per share", dollars(snap["tangible_book_per_share"]),
                   help="Book value without goodwill and other intangibles, which couldn't be "
                        "sold in a crisis.")
    cols[2].metric("Price / book", multiple(snap["price_to_book"]))
    cols[3].metric("Price / tangible book", multiple(snap["price_to_tangible_book"]))
    cols[4].metric("Return on equity", percent(snap["return_on_equity"]))
    cols[5].metric("Return on tangible equity", percent(snap["return_on_tangible_equity"]))

    risk_free, risk_free_source = market.get_risk_free_rate()
    beta, beta_source = market.get_beta(data["price_history"])
    defaults = financials.default_assumptions(snap, beta, risk_free)
    if f"{ticker}_bank_roe" not in st.session_state:
        for field, *_ in FIELDS:
            st.session_state[f"{ticker}_bank_{field}"] = round(getattr(defaults, field) * 100, 2)

    with st.expander("Assumptions", expanded=True):
        cols = st.columns(len(FIELDS) + 1)
        for position, (field, label, low, high, step, tip) in enumerate(FIELDS):
            cols[position].number_input(f"{label} (%)", low, high, step=step,
                                        key=f"{ticker}_bank_{field}", help=tip)
        cols[-1].write("")
        cols[-1].write("")
        if cols[-1].button("Reset to defaults", key=f"{ticker}_bank_reset"):
            for field, *_ in FIELDS:
                st.session_state[f"{ticker}_bank_{field}"] = round(getattr(defaults, field) * 100, 2)
            st.rerun()
        st.caption(f"Default cost of equity: {percent(risk_free)} risk-free rate "
                   f"({risk_free_source}) + beta of {beta:.2f} ({beta_source}) × 5.0% premium.")
    assumptions = financials.Assumptions(
        **{field: st.session_state[f"{ticker}_bank_{field}"] / 100 for field, *_ in FIELDS})

    try:
        result = financials.value(snap, assumptions, price)
    except ValueError as error:
        st.error(str(error))
        return None

    st.subheader("What the shares are worth on each method")
    cols = st.columns(4)
    cols[0].metric("Share price", dollars(price))
    cols[1].metric("Justified price-to-book", dollars(result["value_by_book"]),
                   signed_percent(result["upside_by_book"]),
                   help="Book value per share × (ROE − growth) ÷ (required return − growth). "
                        f"The assumptions justify {result['justified_price_to_book']:.2f} times book.")
    cols[2].metric("Dividends only", dollars(result["value_by_dividends"]),
                   signed_percent(result["upside_by_dividends"]),
                   help="The value of future dividends alone. Usually low for banks, because "
                        "they return a lot of cash through buybacks instead.")
    cols[3].metric("Dividends plus buybacks", dollars(result["value_by_total_payout"]),
                   signed_percent(result["upside_by_total_payout"]),
                   help="The same sum, counting buybacks as cash returned to shareholders.")
    st.caption("The change under each value is its gap to today's share price.")

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Sensitivity: value per share on price-to-book")
        grid = result["sensitivity"]
        table = grid.map(dollars)
        table.index = [f"ROE {r:.1%}" for r in grid.index]
        table.columns = [f"Required {c:.1%}" for c in grid.columns]
        st.dataframe(table, width="stretch")
        st.caption("Rows are returns on equity, columns are the return shareholders require.")
    with right:
        st.subheader("What the price assumes")
        implied = result["implied_roe"]
        st.metric("Return on equity the price implies", percent(implied),
                  help="The ROE at which the justified price-to-book value equals today's price, "
                       "keeping the other assumptions as set.")
        st.dataframe(
            pd.DataFrame({
                "": ["Earnings per share", "P/E", "Dividend per share", "Dividend yield",
                     "Dividends as share of profit", "Dividends + buybacks as share of profit"],
                "Value": [dollars(snap["earnings_per_share"]), multiple(snap["price_to_earnings"]),
                          dollars(snap["dividend_per_share"]), percent(snap["dividend_yield"]),
                          percent(snap["payout_ratio"]), percent(snap["total_payout_ratio"])],
            }),
            hide_index=True, width="stretch",
        )

    history = snap["roe_history"]
    if not history.empty:
        st.subheader("Return on equity by fiscal year")
        shown = pd.DataFrame({"Return on equity": history.map(percent)}).T
        shown.columns = [f"FY{d.year}" for d in history.index]
        st.dataframe(shown, width="stretch")
    return {"snapshot": snap, "result": result, "assumptions": assumptions}
