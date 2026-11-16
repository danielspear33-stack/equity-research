"""Overview tab: valuation today, latest year, charts and statements."""

import pandas as pd
import streamlit as st

from .formatting import by_year, dollars, money, multiple, percent


def render(data: dict) -> None:
    s, m, v = data["statements"], data["metrics"], data["valuation"]
    latest_s, latest_m = s.iloc[-1], m.iloc[-1]

    st.subheader("Valuation today")
    cols = st.columns(6)
    cols[0].metric("Share price", dollars(v["price"]) if v else "–")
    cols[1].metric("Market cap", money(v["market_cap"]) if v else "–")
    cols[2].metric("Enterprise value", money(v["enterprise_value"]) if v else "–")
    cols[3].metric("P/E", multiple(v["price_to_earnings"]) if v else "–")
    cols[4].metric("EV / EBITDA", multiple(v["ev_to_ebitda"]) if v else "–")
    cols[5].metric("FCF yield", percent(v["fcf_yield"]) if v else "–")

    st.subheader(f"Latest fiscal year (FY{s.index[-1].year})")
    cols = st.columns(6)
    cols[0].metric("Revenue", money(latest_s["revenue"]), percent(latest_m["revenue_growth"]))
    cols[1].metric("Operating margin", percent(latest_m["operating_margin"]))
    cols[2].metric("Net income", money(latest_s["net_income"]))
    cols[3].metric("Free cash flow", money(latest_m["free_cash_flow"]))
    cols[4].metric("Return on invested capital", percent(latest_m["return_on_invested_capital"]))
    cols[5].metric("Net debt / EBITDA", multiple(latest_m["net_debt_to_ebitda"]))

    left, right = st.columns(2)
    with left:
        st.subheader("Revenue and free cash flow ($B)")
        chart = pd.DataFrame(
            {"Revenue": s["revenue"] / 1e9, "Free cash flow": m["free_cash_flow"] / 1e9}
        )
        chart.index = [f"FY{d.year}" for d in s.index]
        st.bar_chart(chart, stack=False)
    with right:
        st.subheader("Share price, 5 years")
        if data["price_history"] is not None:
            st.line_chart(data["price_history"])
        else:
            st.caption("No price data.")

    st.subheader("Margins and returns")
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

    st.subheader("Financial statements")
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

    if data["filings"]:
        st.subheader("Recent filings")
        st.dataframe(
            pd.DataFrame(data["filings"])[["filed", "form", "url"]].rename(
                columns={"filed": "Filed", "form": "Form", "url": "Document"}
            ),
            column_config={"Document": st.column_config.LinkColumn(display_text="Open on SEC.gov")},
            hide_index=True,
            width="stretch",
        )
