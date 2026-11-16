"""Backtest page: would the model's "cheap" and "expensive" calls have been right in the past?"""

import altair as alt
import streamlit as st

from research import backtest, config

from . import style
from .formatting import signed_percent


def render() -> None:
    st.header("Does the model work? A backtest")
    st.caption(
        "For each company and each past year, the DCF is re-run using only the annual reports "
        "that existed then, with its mechanical default assumptions, and compared with the "
        "share price 90 days after the year ended. The question: did the shares it called cheap "
        "beat the ones it called expensive over the next twelve months?"
    )

    if config.PUBLIC_DEMO:
        st.caption("Showing the owner's last saved run. Re-running is switched off on the public demo.")
    elif st.button("Run the backtest", help="Downloads the filings and 15 years of prices for "
                   "about 110 companies. A few minutes the first time, quicker after."):
        bar = st.progress(0.0, "Starting…")
        table, skipped = backtest.run(
            progress=lambda done, total, ticker: bar.progress(done / total, f"{ticker} ({done} of {total})"))
        bar.empty()
        if table.empty:
            st.error("The backtest produced no results. Check the internet connection and try again.")
        else:
            backtest.save(table)
            if skipped:
                st.caption("Left out: " + "; ".join(f"{t} ({why})" for t, why in skipped.items()))

    table = backtest.load_saved()
    if table is None or table.empty:
        st.info("No backtest has been run yet.")
        return

    summary = backtest.summarise(table)
    style.verdict(backtest.verdict(summary))
    style.cards([
        {"label": "Company-years tested", "value": f"{summary['observations']:,}",
         "note": f"{summary['companies']} companies, {summary['first_year']} to {summary['last_year']}"},
        {"label": "Cheapest fifth minus most expensive fifth",
         "value": signed_percent(summary["spread"]),
         "note": "average return over the next year, against the S&P 500",
         "tone": style.tone(summary["spread"]), "own": True},
        {"label": "Years the cheaper half won",
         "value": f"{summary['years_cheap_won']} of {summary['years']}", "own": True},
        {"label": "Rank correlation", "value": f"{summary['rank_correlation']:+.2f}",
         "note": "+1 perfect ordering, 0 no information, -1 backwards", "own": True},
    ])

    st.subheader("Return over the next year, by how cheap the model said the share was")
    groups = summary["by_group"].reset_index()
    chart = alt.Chart(groups).mark_bar().encode(
        x=alt.X("group:N", sort=backtest.GROUPS, title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("average_excess_return:Q", title="Average return above the S&P 500",
                axis=alt.Axis(format="+%")),
        color=alt.condition("datum.average_excess_return >= 0", alt.value(style.GREEN),
                            alt.value(style.RED)),
        tooltip=[alt.Tooltip("group:N", title="Group"),
                 alt.Tooltip("average_excess_return:Q", title="Above the S&P 500", format="+.1%"),
                 alt.Tooltip("observations:Q", title="Company-years")],
    ).properties(height=300)
    st.altair_chart(chart, width="stretch")
    st.caption("Each year's companies are ranked by the gap between DCF value and price and "
               "split into five equal groups, so every group holds companies from every year.")

    shown = summary["by_group"].rename(columns={
        "observations": "Company-years", "typical_dcf_gap": "Typical DCF value vs price",
        "average_return": "Average return", "average_excess_return": "Above the S&P 500",
        "beat_the_market": "Share that beat the S&P 500"})
    st.dataframe(shown.style.format({
        "Typical DCF value vs price": "{:+.0%}", "Average return": "{:+.1%}",
        "Above the S&P 500": "{:+.1%}", "Share that beat the S&P 500": "{:.0%}"}), width="stretch")

    st.subheader("Year by year")
    by_year = summary["by_year"].rename(columns={
        "companies": "Companies", "cheap_half_excess": "Cheaper two-fifths vs S&P 500",
        "expensive_half_excess": "Dearer two-fifths vs S&P 500",
        "cheap_minus_expensive": "Cheaper minus dearer"})
    by_year.index = by_year.index.rename("Bought in")
    st.dataframe(by_year.style.format({c: "{:+.1%}" for c in by_year.columns[1:]}), width="stretch")

    st.subheader("What this test can and can't tell you")
    st.markdown(
        "- **Survivorship bias.** The companies are today's large, well-known ones. Any that "
        "shrank or failed along the way are missing, which flatters every group.\n"
        "- **Mechanical assumptions.** The DCF uses three-year averages, not an analyst's view. "
        "This tests that baseline, not what you could do by changing the assumptions.\n"
        "- **One discount-rate shortcut.** Every company is given a beta of 1, because today's "
        "beta would be hindsight. The Treasury yield is the one from each date.\n"
        "- **Restated figures.** Where a company later restated its accounts, the restated "
        "numbers are used.\n"
        "- **Price returns.** Dividends are left out for both the shares and the index.\n"
        "- **A short, unusual period.** A decade dominated by large technology companies is "
        "one sample, not a law."
    )
    with st.expander("Every company-year"):
        st.dataframe(table, width="stretch", hide_index=True)
        st.download_button("Download as CSV", table.to_csv(index=False), "backtest.csv")
