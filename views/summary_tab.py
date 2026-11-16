"""Summary tab: every valuation method on one chart (a "football field")."""

import altair as alt
import pandas as pd
import streamlit as st

from research import comps

from .formatting import dollars


def build_ranges(data: dict, dcf_output, comps_result) -> pd.DataFrame:
    """One row per method: the low, middle and high value per share."""
    rows = []
    history = data["price_history"]
    if history is not None:
        year = history.tail(252)  # about one year of trading days
        rows.append({"method": "52-week trading range", "low": year.min(),
                     "mid": float(history.iloc[-1]), "high": year.max()})
    if dcf_output:
        result = dcf_output[0]
        grid = result["sensitivity"].stack().dropna()
        rows.append({"method": "DCF (sensitivity range)", "low": grid.min(),
                     "mid": result["value_per_share"], "high": grid.max()})
    if comps_result is not None and not comps_result["implied"].empty:
        for multiple, row in comps_result["implied"].iterrows():
            rows.append({"method": f"Peers: {comps.MULTIPLES[multiple]}",
                         "low": row["low"], "mid": row["median"], "high": row["high"]})
    ranges = pd.DataFrame(rows)
    if not ranges.empty:
        # A negative value per share just means "worth nothing" on that method.
        ranges[["low", "mid", "high"]] = ranges[["low", "mid", "high"]].clip(lower=0)
    return ranges


def render(data: dict, dcf_output, comps_result) -> None:
    ranges = build_ranges(data, dcf_output, comps_result)
    if ranges.empty or data["valuation"] is None:
        st.info("Not enough data to compare valuation methods.")
        return
    price = data["valuation"]["price"]

    st.caption(
        "Each bar is the range of value per share one method gives; the tick is its central "
        "estimate and the vertical line is today's price. Where the methods disagree is "
        "where the thinking needs to happen."
    )
    order = ranges["method"].tolist()
    base = alt.Chart(ranges).encode(y=alt.Y("method:N", sort=order, title=None, axis=alt.Axis(labelLimit=260)))
    bars = base.mark_bar(height=22, color="#7aa6d6").encode(
        x=alt.X("low:Q", title="Value per share ($)", scale=alt.Scale(zero=False)),
        x2="high:Q",
        tooltip=[alt.Tooltip("method:N", title="Method"),
                 alt.Tooltip("low:Q", format="$,.2f", title="Low"),
                 alt.Tooltip("mid:Q", format="$,.2f", title="Central"),
                 alt.Tooltip("high:Q", format="$,.2f", title="High")],
    )
    ticks = base.mark_tick(thickness=3, size=30, color="#1f3a5f").encode(x="mid:Q")
    rule = alt.Chart(pd.DataFrame({"price": [price]})).mark_rule(
        color="#d1495b", strokeWidth=2, strokeDash=[6, 4]
    ).encode(x="price:Q")
    st.altair_chart((bars + ticks + rule).properties(height=60 + 48 * len(ranges)),
                    width="stretch")

    shown = pd.DataFrame(
        {
            "Method": ranges["method"],
            "Low": ranges["low"].map(dollars),
            "Central": ranges["mid"].map(dollars),
            "High": ranges["high"].map(dollars),
            "Central vs price": (ranges["mid"] / price - 1).map(lambda x: f"{x:+.0%}"),
        }
    )
    st.dataframe(shown, hide_index=True, width="stretch")
    st.caption(f"Share price today: {dollars(price)}. DCF range is the spread across the "
               "sensitivity table; peer ranges run from the 25th to the 75th percentile multiple.")
