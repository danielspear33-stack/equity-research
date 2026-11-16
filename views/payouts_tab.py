"""Payouts and insiders tab: cash returned to shareholders, dilution, and insider trades."""

import pandas as pd
import streamlit as st

from research import insiders, payouts

from .formatting import by_year, dollars, money, percent


def _signed(value) -> str:
    return "–" if value is None or pd.isna(value) else f"{value:+.1%}"


def _shares(value) -> str:
    if value is None or pd.isna(value):
        return "–"
    return f"{value / 1e9:,.2f}B" if value >= 1e9 else f"{value / 1e6:,.0f}M"


def _payouts(data: dict) -> None:
    s, m, v = data["statements"], data["metrics"], data["valuation"]
    now = payouts.today(data["latest"]["statements"], v["market_cap"] if v else None)

    st.subheader("Cash returned to shareholders")
    st.caption(f"Yields are for the {data['latest']['label']}, against today's market value.")
    cols = st.columns(5)
    cols[0].metric("Dividends paid", money(now["dividends_paid"]))
    cols[1].metric("Dividend yield", percent(now["dividend_yield"]))
    cols[2].metric("Buybacks", money(now["buybacks"]))
    cols[3].metric("Buyback yield", percent(now["buyback_yield"]))
    cols[4].metric("Total shareholder yield", percent(now["shareholder_yield"]),
                   help="Dividends plus buybacks, divided by market value.")
    if now["dividends_paid"] is None and now["buybacks"] is None:
        st.caption("No dividends or buybacks are reported in the filings for this period.")

    table = payouts.by_year(s, m)
    st.dataframe(
        pd.concat([
            by_year(table, {"dividends_paid": "Dividends paid", "buybacks": "Buybacks",
                            "total_returned": "Total returned"}, money),
            by_year(table, {"share_of_net_income": "Total returned, share of net income",
                            "share_of_free_cash_flow": "Total returned, share of free cash flow"},
                    percent),
            by_year(table, {"dividends_per_share": "Dividend per share"}, dollars),
        ]),
        width="stretch",
    )
    st.caption("Returning more than 100% of profit or free cash flow means paying from "
               "savings or borrowing, which can't continue indefinitely.")

    st.subheader("Share count and pay in shares")
    cols = st.columns(3)
    cols[0].metric("Stock-based pay", money(now["stock_comp"]),
                   help="Shares and options given to staff over the last twelve months.")
    cols[1].metric("Buybacks net of stock pay", percent(now["net_buyback_yield"]),
                   help="Buybacks minus stock-based pay, as a share of market value. Buybacks "
                        "that only replace shares handed to staff don't shrink the share count.")
    shares = s["diluted_shares"].dropna()
    if len(shares) >= 2:
        years = len(shares) - 1
        cols[2].metric(f"Share count change, {years} years", _signed(shares.iloc[-1] / shares.iloc[0] - 1),
                       help="Negative is good for shareholders: each share is a bigger slice.")
    st.dataframe(
        pd.concat([
            by_year(table, {"diluted_shares": "Diluted shares"}, _shares),
            by_year(table, {"share_count_change": "Change on the year before"}, _signed),
            by_year(table, {"stock_comp": "Stock-based pay"}, money),
            by_year(table, {"stock_comp_share_of_revenue": "Stock-based pay, share of revenue"},
                    percent),
        ]),
        width="stretch",
    )


def _insiders(data: dict, load_insiders) -> dict:
    st.subheader("Insider trades")
    st.caption(
        "Directors and executives must report trades in their own company's shares within two "
        "business days. Buying on the open market is the stronger signal. Selling is weaker: "
        "people sell to pay tax or diversify, and sales under a pre-arranged plan were "
        "scheduled months before."
    )
    try:
        with st.spinner("Reading insider filings…"):
            trades = load_insiders(data["cik"])
    except Exception as error:  # noqa: BLE001
        st.warning(f"Insider filings couldn't be loaded. {error}")
        return None
    if trades.empty:
        st.info("No recent insider filings could be read for this company.")
        return None

    summary = insiders.summarise(trades)
    cols = st.columns(5)
    cols[0].metric("Bought on the open market", money(summary["buy_value"]))
    cols[1].metric("Insiders buying", summary["buyers"])
    cols[2].metric("Sold on the open market", money(summary["sell_value"]))
    cols[3].metric("Insiders selling", summary["sellers"])
    cols[4].metric("Sales under a pre-arranged plan", percent(summary["planned_share_of_sales"]),
                   help="Share of the value sold that was scheduled in advance under a "
                        "10b5-1 plan, so it says little about what the insider thinks today.")
    st.caption(f"From the company's latest insider filings, covering trades between "
               f"{summary['from']:%d %b %Y} and {summary['to']:%d %b %Y}.")

    chosen = summary["open_market"]
    if chosen.empty:
        st.info("None of these filings is an open-market purchase or sale. They are routine: "
                "share awards, vesting and tax withholding.")
    else:
        # One filing often lists a sale in several lots; show one line per person per day.
        chosen = chosen.assign(day=chosen["date"].dt.date)
        grouped = chosen.groupby(["day", "insider", "role", "side", "planned", "page"], sort=False).agg(
            shares=("shares", "sum"), value=("value", "sum"), shares_after=("shares_after", "min")
        ).reset_index().sort_values("day", ascending=False)
        st.dataframe(
            pd.DataFrame({
                "Date": grouped["day"],
                "Insider": grouped["insider"],
                "Role": grouped["role"],
                "Trade": grouped["side"],
                "Shares": grouped["shares"].map(lambda x: f"{x:,.0f}"),
                "Average price": (grouped["value"] / grouped["shares"]).map(dollars),
                "Value": grouped["value"].map(money),
                "Shares held after": grouped["shares_after"].map(
                    lambda x: "–" if pd.isna(x) else f"{x:,.0f}"),
                "Pre-arranged plan": grouped["planned"].map({True: "Yes", False: "No"}),
                "Filing": grouped["page"],
            }),
            column_config={"Filing": st.column_config.LinkColumn(display_text="Open on SEC.gov")},
            hide_index=True, width="stretch",
        )

    with st.expander("All reported transactions, including routine ones"):
        st.dataframe(
            pd.DataFrame({
                "Date": trades["date"].dt.date,
                "Insider": trades["insider"],
                "Role": trades["role"],
                "What happened": trades["what"],
                "Shares": trades["shares"].map(lambda x: f"{x:,.0f}"),
                "Price": trades["price"].map(lambda x: "–" if pd.isna(x) or x == 0 else dollars(x)),
            }),
            hide_index=True, width="stretch",
        )
    return summary


def render(data: dict, load_insiders):
    """Draw the tab. Returns the insider summary, or None if it couldn't be loaded."""
    _payouts(data)
    st.divider()
    return _insiders(data, load_insiders)
