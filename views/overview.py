"""Overview tab: the pictures first (price, valuation against its own history, ten-year
trends), with every table of numbers one click below."""

import altair as alt
import pandas as pd
import streamlit as st

from research import checks, payouts, prices, pricestats, valhistory

from . import style, visuals
from .formatting import by_year, dollars, money, multiple, percent, signed_percent

STATUS_LABELS = {checks.GOOD: "Good", checks.WATCH: "Watch", checks.WEAK: "Weak",
                 checks.UNKNOWN: "No data"}


def _valuation(data: dict) -> None:
    v = data["valuation"]
    financial = data["profile"]["is_financial"]
    st.subheader("Valuation today")
    cols = st.columns(6)
    # Share price and market value are in the strip at the top of the page.
    cols[0].metric("Enterprise value", money(v["enterprise_value"]) if v and not financial else
                   (money(v["market_cap"]) if v else "–"),
                   help="What it would cost to buy the whole business: the shares plus its debt, "
                        "minus its cash." if not financial else "The market value of all the shares.")
    cols[1].metric("EV / Sales" if not financial else "Share price",
                   (multiple(v["ev_to_sales"]) if not financial else dollars(v["price"])) if v else "–")
    cols[2].metric("P/E", multiple(v["price_to_earnings"]) if v else "–",
                   help="Share price divided by earnings per share: how many years of today's "
                        "profit you pay for the company.")
    if financial:
        cols[3].metric("Price / book", multiple(v["price_to_book"]) if v else "–",
                       help="Market value divided by shareholders' equity. The main yardstick for banks.")
        cols[4].metric("Dividend yield", percent(v["dividend_yield"]) if v else "–")
        cols[5].metric("Return on equity", percent(data["latest"]["metrics"]["return_on_equity"]))
    else:
        cols[3].metric("EV / EBITDA", multiple(v["ev_to_ebitda"]) if v else "–",
                       help="Enterprise value (shares plus debt minus cash) divided by EBITDA. "
                            "Compares companies regardless of how much debt they carry.")
        cols[4].metric("FCF yield", percent(v["fcf_yield"]) if v else "–",
                       help="Free cash flow divided by market cap: the cash return on today's price.")
        returned = payouts.today(data["latest"]["statements"], v["market_cap"]) if v else {}
        cols[5].metric("Shareholder yield", percent(returned.get("shareholder_yield")),
                       help="Dividends plus buybacks over the last twelve months, divided by market cap.")
    st.caption(f"Multiples compare today's price with results for the {data['latest']['label']}.")


def _latest_results(data: dict) -> None:
    latest_s, latest_m = data["latest"]["statements"], data["latest"]["metrics"]
    st.subheader(f"Latest results ({data['latest']['label']})")
    cols = st.columns(6)
    cols[0].metric("Revenue", money(latest_s["revenue"]),
                   percent(latest_m["revenue_growth"]) if pd.notna(latest_m["revenue_growth"]) else None)
    cols[2].metric("Net income", money(latest_s["net_income"]))
    if data["profile"]["is_financial"]:
        cols[1].metric("Net margin", percent(latest_m["net_margin"]))
        cols[3].metric("Earnings per share", dollars(latest_s["net_income"] / latest_s["diluted_shares"]))
        cols[4].metric("Return on equity", percent(latest_m["return_on_equity"]))
        cols[5].metric("Shareholders' equity", money(latest_s["equity"]))
    else:
        cols[1].metric("Operating margin", percent(latest_m["operating_margin"]))
        cols[3].metric("Free cash flow", money(latest_m["free_cash_flow"]))
        cols[4].metric("Return on invested capital", percent(latest_m["return_on_invested_capital"]))
        cols[5].metric("Net debt / EBITDA", multiple(latest_m["net_debt_to_ebitda"]))
    if data["latest"]["is_ttm"]:
        st.caption("These add up the last four quarters, so they are newer than the last annual "
                   f"report (fiscal year to {data['statements'].index[-1]:%d %b %Y}).")


def _health_check(data: dict) -> None:
    results = checks.run(data)
    counts = pd.Series([r["status"] for r in results]).value_counts()
    st.caption(
        f"{counts.get(checks.GOOD, 0)} good, {counts.get(checks.WATCH, 0)} to watch, "
        f"{counts.get(checks.WEAK, 0)} weak. Rules of thumb about the business, not about "
        "whether the share price is fair."
    )
    style.health_checks(results, STATUS_LABELS)


def _trends(data: dict) -> None:
    """Ten years at a glance: each card shows the latest figure and its trend line."""
    s, m = data["statements"], data["metrics"]
    st.subheader(f"Ten-year trends (fiscal years {s.index[0].year} to {s.index[-1].year})")
    if data["profile"]["is_financial"]:
        lines = [("Revenue", s["revenue"], money), ("Net income", s["net_income"], money),
                 ("Net margin", m["net_margin"], percent),
                 ("Return on equity", m["return_on_equity"], percent),
                 ("Shareholders' equity", s["equity"], money)]
    else:
        lines = [("Revenue", s["revenue"], money),
                 ("Operating margin", m["operating_margin"], percent),
                 ("Free cash flow", m["free_cash_flow"], money),
                 ("Return on invested capital", m["return_on_invested_capital"], percent),
                 ("Net debt", m["net_debt"], money)]
    for column, (label, series, formatter) in zip(st.columns(len(lines)), lines):
        known = series.dropna()
        if known.empty:
            column.metric(label, "–")
            continue
        column.metric(label, formatter(known.iloc[-1]), chart_data=known.tolist(), chart_type="line")
    st.caption("Each card shows the latest fiscal year and the line of every year before it.")


def _price(data: dict) -> None:
    history = data["price_history"]
    st.subheader("Share price")
    if history is None:
        st.caption("No price data.")
        return
    stats = pricestats.summary(history)
    price = float(history.iloc[-1])

    left, right = st.columns([3, 2])
    with left:
        lines = pd.DataFrame({
            "Price": history,
            "50-day average": history.rolling(50).mean(),
            "200-day average": history.rolling(200).mean(),
        }).rename_axis("date").reset_index().melt("date", var_name="line", value_name="value").dropna()
        chart = alt.Chart(lines).mark_line().encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("value:Q", title=None, scale=alt.Scale(zero=False), axis=alt.Axis(format="$,.0f")),
            color=alt.Color("line:N", title=None, legend=alt.Legend(orient="top"),
                            scale=alt.Scale(domain=["Price", "50-day average", "200-day average"],
                                            range=[style.BLUE, style.GOLD, style.GREY])),
            strokeWidth=alt.condition("datum.line == 'Price'", alt.value(2), alt.value(1.2)),
            tooltip=[alt.Tooltip("date:T", title="Date"), alt.Tooltip("line:N", title="Line"),
                     alt.Tooltip("value:Q", title="Value", format="$,.2f")],
        ).properties(height=300)
        st.altair_chart(chart, width="stretch")
    with right:
        st.caption("Where today's price sits in its 52-week range")
        visuals.range_bar(stats["low_52_week"], stats["high_52_week"], price,
                          f"Low {dollars(stats['low_52_week'])}", f"High {dollars(stats['high_52_week'])}")
        try:
            market = prices.get_price_history("^GSPC")
        except Exception:  # noqa: BLE001 - the comparison is a nice-to-have
            market = None
        table = pricestats.returns(history, market)
        shown = pd.DataFrame({data["ticker"]: table["stock"].map(signed_percent_1)})
        if market is not None:
            shown["S&P 500"] = table["market"].map(signed_percent_1)
            shown["Difference"] = table["difference"].map(signed_percent_1)
        st.dataframe(shown, width="stretch")
        st.caption(f"Price change to {stats['as_of']:%d %b %Y}, not counting dividends.")

    with st.expander("Show the numbers: averages, volatility and worst fall"):
        cols = st.columns(6)
        cols[0].metric("52-week high", dollars(stats["high_52_week"]), signed_percent(stats["below_high"]),
                       help="The change shown is today's price against the high.")
        cols[1].metric("52-week low", dollars(stats["low_52_week"]), signed_percent(stats["above_low"]),
                       help="The change shown is today's price against the low.")
        cols[2].metric("50-day average", dollars(stats["average_50_day"]))
        cols[3].metric("200-day average", dollars(stats["average_200_day"]),
                       signed_percent(stats["vs_200_day"]),
                       help="The average price over about ten months. Price above it means the "
                            "trend has been up.")
        cols[4].metric("Yearly volatility", percent(stats["volatility"]),
                       help="How much the price typically swings in a year. The S&P 500 is usually 15-20%.")
        cols[5].metric("Worst fall, 5 years", percent(stats["worst_fall"]),
                       help="The largest drop from a peak to a later low. A guide to how bad a bad "
                            "patch has been.")


@st.cache_data(ttl=3600, show_spinner=False)
def _multiples_history(ticker: str, statements: pd.DataFrame, metrics: pd.DataFrame) -> pd.DataFrame:
    return valhistory.history(statements, metrics, prices.get_long_price_history(ticker))


def _own_history(data: dict) -> None:
    """Is the share cheap or dear compared with its own past?"""
    v = data["valuation"]
    if v is None:
        return
    st.subheader("Cheap or dear against its own history")
    try:
        history = _multiples_history(data["ticker"], data["statements"], data["metrics"])
    except Exception as error:  # noqa: BLE001 - needs a second, longer price download
        st.caption(f"The longer price history couldn't be loaded. ({error})")
        return
    financial = data["profile"]["is_financial"]
    today = {"pe": v["price_to_earnings"], "ev_ebitda": v["ev_to_ebitda"],
             "pb": v["price_to_book"]}
    choices = ["pe", "pb"] if financial else ["pe", "ev_ebitda"]
    drawn = 0
    for column, name in zip(st.columns(len(choices)), choices):
        if history.empty or name not in history:
            continue
        where = valhistory.position(history[name], today[name])
        if where is None:
            continue
        drawn += 1
        label = valhistory.MULTIPLES[name]
        series = history[name].dropna()
        # The newest month uses today's figure, which is built from the latest results.
        series.iloc[-1] = where["current"]
        points = series.rename("value").rename_axis("date").reset_index()
        base = alt.Chart(points).encode(x=alt.X("date:T", title=None))
        band = alt.Chart(pd.DataFrame([where])).mark_rect(color=style.GOLD, opacity=0.13).encode(
            y="low:Q", y2="high:Q")
        middle = alt.Chart(pd.DataFrame([where])).mark_rule(color=style.GOLD, strokeDash=[5, 4]).encode(
            y="median:Q")
        line = base.mark_line(color=style.BLUE).encode(
            y=alt.Y("value:Q", title=None, scale=alt.Scale(zero=False), axis=alt.Axis(format=".0f")),
            tooltip=[alt.Tooltip("date:T", title="Month"), alt.Tooltip("value:Q", title=label, format=".1f")])
        dot = alt.Chart(points.tail(1)).mark_point(color=style.BLUE, size=110, filled=True).encode(
            x="date:T", y="value:Q")
        with column:
            gap = where["current"] / where["median"] - 1
            st.metric(f"{label} today", multiple(where["current"]),
                      f"{gap:+.0%} against its usual {where['median']:.1f}x", delta_color="inverse")
            st.altair_chart((band + middle + line + dot).properties(height=220), width="stretch")
            st.caption(valhistory.describe(label, where))
    if not drawn:
        st.caption("Not enough history with positive profits to compare today's multiples with the past.")
    else:
        st.caption("The line is the multiple at each month-end, using the results published by "
                   "then. The dashed line is its typical level and the shaded band covers the "
                   "middle 80% of months. Above the band is dear by its own standards; below is cheap.")


def signed_percent_1(value) -> str:
    return "–" if value is None or pd.isna(value) else f"{value:+.1%}"


def _announcements(data: dict) -> None:
    announcements = data.get("announcements") or []
    if not announcements:
        st.caption("No announcements found in the company's recent filings.")
        return
    results = [a["filed"] for a in announcements if a["is_earnings"]]
    if results:
        st.caption("Results were last announced on "
                   + ", ".join(f"{pd.Timestamp(d):%d %b %Y}" for d in results[:4])
                   + ". Companies usually report on a similar date each quarter.")
    st.dataframe(
        pd.DataFrame(announcements)[["filed", "what", "url"]].rename(
            columns={"filed": "Date", "what": "What happened", "url": "Document"}),
        column_config={"Document": st.column_config.LinkColumn(display_text="Open on SEC.gov")},
        hide_index=True, width="stretch",
    )


def render(data: dict) -> None:
    s, m = data["statements"], data["metrics"]

    _price(data)
    _own_history(data)
    _trends(data)

    st.subheader("Revenue and free cash flow by fiscal year ($B)")
    chart = pd.DataFrame(
        {"Revenue": s["revenue"] / 1e9, "Free cash flow": m["free_cash_flow"] / 1e9}
    )
    chart.index = [f"FY{d.year}" for d in s.index]
    st.bar_chart(chart, y=["Revenue", "Free cash flow"], color=[style.BLUE, style.GREEN], stack=False)

    # The full tables are one click away, so they don't crowd the page.
    st.subheader("Show the numbers")
    with st.expander("Valuation multiples and the latest results", expanded=True):
        _valuation(data)
        _latest_results(data)
    with st.expander("Health check, question by question"):
        _health_check(data)
    with st.expander("Margins and returns, year by year"):
        st.dataframe(
            by_year(
                m,
                {
                    "revenue_growth": "Revenue growth",
                    "gross_margin": "Gross margin",
                    "operating_margin": "Operating margin",
                    "net_margin": "Net margin",
                    "fcf_margin": "Free cash flow margin",
                    "return_on_equity": "Return on equity",
                    "return_on_invested_capital": "Return on invested capital",
                },
                percent,
            ),
            width="stretch",
        )
    with st.expander("Financial statements, year by year"):
        st.dataframe(
            by_year(
                s.join(m[["free_cash_flow", "ebitda", "net_debt"]]),
                {
                    "revenue": "Revenue",
                    "gross_profit": "Gross profit",
                    "operating_income": "Operating income",
                    "ebitda": "EBITDA",
                    "net_income": "Net income",
                    "cash_from_operations": "Cash from operations",
                    "capex": "Capital expenditure",
                    "free_cash_flow": "Free cash flow",
                    "cash_and_investments": "Cash and short-term investments",
                    "total_debt": "Total debt",
                    "net_debt": "Net debt",
                    "equity": "Shareholders' equity",
                },
                money,
            ),
            width="stretch",
        )
    with st.expander("Results dates and company announcements"):
        _announcements(data)
    if data["filings"]:
        with st.expander("Recent filings"):
            st.dataframe(
                pd.DataFrame(data["filings"])[["filed", "form", "url"]].rename(
                    columns={"filed": "Filed", "form": "Form", "url": "Document"}
                ),
                column_config={"Document": st.column_config.LinkColumn(display_text="Open on SEC.gov")},
                hide_index=True,
                width="stretch",
            )
