"""Quarterly tab: the last eight quarters and the trailing twelve months."""

import pandas as pd
import streamlit as st

from .formatting import dollars, money, percent


def _signed(value) -> str:
    return "–" if value is None or pd.isna(value) else f"{value:+.1%}"


def render(data: dict) -> None:
    quarters = data["quarters"]
    if quarters.empty:
        st.info("No quarterly figures could be built from this company's filings.")
        return
    latest, annual, m = data["latest"], data["statements"], data["metrics"]
    financial = data["profile"]["is_financial"]

    st.caption(
        "Annual reports come out once a year, so this is where the newest numbers are. "
        "Growth compares each quarter with the same quarter a year earlier, which takes "
        "out seasonal swings. Fourth quarters are worked out as the full year minus the "
        "first nine months."
    )

    labels = [f"{d:%b %Y}" for d in quarters.index]
    left, right = st.columns(2)
    with left:
        st.subheader("Revenue and net income by quarter ($B)")
        chart = pd.DataFrame({"Revenue": (quarters["revenue"] / 1e9).values,
                              "Net income": (quarters["net_income"] / 1e9).values},
                             index=pd.CategoricalIndex(labels, categories=labels, ordered=True))
        st.bar_chart(chart.dropna(axis=1, how="all"), stack=False)
    with right:
        st.subheader("Growth against a year earlier")
        growth = pd.DataFrame({"Revenue": (quarters["revenue_growth"] * 100).values,
                               "Net income": (quarters["net_income_growth"] * 100).values},
                              index=pd.CategoricalIndex(labels, categories=labels, ordered=True))
        st.line_chart(growth.dropna(axis=1, how="all"), y_label="%")

    st.subheader("Quarter by quarter")
    rows = {
        "Revenue": quarters["revenue"].map(money),
        "Revenue growth (vs a year earlier)": quarters["revenue_growth"].map(_signed),
        "Gross profit": quarters["gross_profit"].map(money),
        "Operating income": quarters["operating_income"].map(money),
        "Operating margin": quarters["operating_margin"].map(percent),
        "Net income": quarters["net_income"].map(money),
        "Net income growth (vs a year earlier)": quarters["net_income_growth"].map(_signed),
        "Earnings per share": quarters["eps_diluted"].map(dollars),
        "Cash from operations": quarters["cash_from_operations"].map(money),
        "Free cash flow": quarters["free_cash_flow"].map(money),
    }
    if financial:
        for name in ("Gross profit", "Operating income", "Operating margin",
                     "Cash from operations", "Free cash flow"):
            rows.pop(name)
    table = pd.DataFrame(rows).T
    table.columns = [f"Quarter to {label}" for label in labels]
    st.dataframe(table, width="stretch")

    if not latest["is_ttm"]:
        st.caption("The latest annual report is the newest filing, so the last twelve months "
                   "are the same as the last fiscal year.")
        return

    st.subheader("Last twelve months against the last fiscal year")
    last_s, last_m = annual.iloc[-1], m.iloc[-1]
    now_s, now_m = latest["statements"], latest["metrics"]

    def change(now, before):
        if pd.isna(now) or pd.isna(before) or before <= 0:
            return "–"
        return f"{now / before - 1:+.1%}"

    lines = [("Revenue", now_s["revenue"], last_s["revenue"]),
             ("Net income", now_s["net_income"], last_s["net_income"])]
    if not financial:
        lines[1:1] = [("Operating income", now_s["operating_income"], last_s["operating_income"]),
                      ("EBITDA", now_m["ebitda"], last_m["ebitda"])]
        lines += [("Free cash flow", now_m["free_cash_flow"], last_m["free_cash_flow"]),
                  ("Net debt", now_m["net_debt"], last_m["net_debt"])]
    lines.append(("Shareholders' equity", now_s["equity"], last_s["equity"]))
    st.dataframe(
        pd.DataFrame({
            "": [name for name, _, _ in lines],
            latest["label"].capitalize(): [money(now) for _, now, _ in lines],
            f"Fiscal year to {annual.index[-1]:%d %b %Y}": [money(before) for _, _, before in lines],
            "Change": [change(now, before) for _, now, before in lines],
        }),
        hide_index=True, width="stretch",
    )
