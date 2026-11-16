"""Backtest page: which of this tool's measures would have pointed you the right way in the past?"""

import altair as alt
import streamlit as st

from research import backtest, config

from . import style
from .formatting import signed_percent

GRADE_COLOURS = {"Worked": style.GREEN, "Backwards": style.RED, "Inconsistent": style.GOLD,
                 "No signal": style.GREY}


def _run() -> None:
    bar = st.progress(0.0, "Starting…")
    table, skipped = backtest.run(
        progress=lambda done, total, ticker: bar.progress(done / total, f"{ticker} ({done} of {total})"))
    bar.empty()
    if table.empty:
        st.error("The backtest produced no results. Check the internet connection and try again.")
        return
    backtest.save(table)
    if skipped:
        st.caption("Left out: " + "; ".join(f"{t} ({why})" for t, why in skipped.items()))


def _all_signals(table) -> None:
    comparison = backtest.compare_signals(table)
    st.subheader("Which measures worked")
    chart = alt.Chart(comparison).mark_bar().encode(
        y=alt.Y("name:N", sort=comparison["name"].tolist(), title=None,
                axis=alt.Axis(labelLimit=320)),
        x=alt.X("spread:Q", title="Highest fifth minus lowest fifth, return over the next year",
                axis=alt.Axis(format="+%")),
        color=alt.Color("verdict:N", title=None, legend=alt.Legend(orient="top"),
                        scale=alt.Scale(domain=list(GRADE_COLOURS), range=list(GRADE_COLOURS.values()))),
        tooltip=[alt.Tooltip("name:N", title="Measure"),
                 alt.Tooltip("spread:Q", title="Highest minus lowest fifth", format="+.1%"),
                 alt.Tooltip("years_high_won:Q", title="Years the higher half won"),
                 alt.Tooltip("years:Q", title="Years tested"),
                 alt.Tooltip("verdict:N", title="Result")],
    ).properties(height=38 * len(comparison) + 40)
    st.altair_chart(chart, width="stretch")
    st.caption("A bar to the right means companies scoring high on that measure went on to do "
               "better than those scoring low. Green also needs the higher half to have won in "
               "most years, not just on average.")


def _one_signal(table, signal: str) -> None:
    summary = backtest.summarise(table, signal)
    style.verdict(backtest.verdict(summary))
    style.cards([
        {"label": "Company-years tested", "value": f"{summary['observations']:,}",
         "note": f"{summary['companies']} companies, {summary['first_year']} to {summary['last_year']}"},
        {"label": "Highest fifth minus lowest fifth", "value": signed_percent(summary["spread"]),
         "note": "average return over the next year, against the S&P 500",
         "tone": style.tone(summary["spread"]), "own": True},
        {"label": "Years the higher half won",
         "value": f"{summary['years_high_won']} of {summary['years']}", "own": True},
        {"label": "Rank correlation", "value": f"{summary['rank_correlation']:+.2f}",
         "note": "+1 perfect ordering, 0 no information, -1 backwards", "own": True},
    ])

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
    ).properties(height=280)
    st.altair_chart(chart, width="stretch")
    st.caption("Each year's companies are ranked on the measure and split into five equal "
               "groups, so every group holds companies from every year.")

    with st.expander("Show the numbers: by group and by year"):
        shown = summary["by_group"].rename(columns={
            "observations": "Company-years", "typical_reading": "Typical reading",
            "average_return": "Average return", "average_excess_return": "Above the S&P 500",
            "beat_the_market": "Share that beat the S&P 500"})
        st.dataframe(shown.style.format({
            "Typical reading": "{:+.0%}", "Average return": "{:+.1%}",
            "Above the S&P 500": "{:+.1%}", "Share that beat the S&P 500": "{:.0%}"}), width="stretch")
        by_year = summary["by_year"].rename(columns={
            "companies": "Companies", "high_excess": "Higher two-fifths vs S&P 500",
            "low_excess": "Lower two-fifths vs S&P 500", "high_minus_low": "Higher minus lower"})
        by_year.index = by_year.index.rename("Bought in")
        st.dataframe(by_year.style.format({c: "{:+.1%}" for c in by_year.columns[1:]}), width="stretch")


def render() -> None:
    st.header("Do the tool's measures work? A backtest")
    st.caption(
        "For each company and each past year, every measure is worked out using only the annual "
        "reports that existed then and the share price 90 days after the year ended. The "
        "question for each: did companies that scored high go on to beat those that scored low "
        "over the next twelve months?"
    )
    if config.PUBLIC_DEMO:
        st.caption("Showing the owner's last saved run. Re-running is switched off on the public demo.")
    elif st.button("Run the backtest", help="Downloads the filings and 15 years of prices for "
                   "about 110 companies. A few minutes the first time, quicker after."):
        _run()

    table = backtest.load_saved()
    if table is None or table.empty:
        st.info("No backtest has been run yet.")
        return
    if "fcf_yield" not in table.columns:
        st.info("The saved run is from an older version. Run the backtest again to test every measure.")
        return

    _all_signals(table)

    st.subheader("One measure in detail")
    signal = st.selectbox("Measure", list(backtest.SIGNALS), format_func=backtest.SIGNALS.get,
                          label_visibility="collapsed")
    _one_signal(table, signal)

    st.subheader("What this test can and can't tell you")
    st.markdown(
        "- **Survivorship bias.** The companies are today's large, well-known ones. Any that "
        "shrank or failed along the way are missing, which flatters every group and "
        "especially the fast growers.\n"
        "- **A short, unusual period.** Seven years dominated by large technology companies "
        "is one sample, not a law. Growth beating value is what this stretch looked like.\n"
        "- **Mechanical DCF assumptions.** The DCF uses three-year averages, not an analyst's "
        "view. This tests that baseline, not what you could do by changing the assumptions.\n"
        "- **One discount-rate shortcut.** Every company is given a beta of 1, because today's "
        "beta would be hindsight. The Treasury yield is the one from each date.\n"
        "- **Restated figures.** Where a company later restated its accounts, the restated "
        "numbers are used.\n"
        "- **Price returns.** Dividends are left out for both the shares and the index."
    )
    with st.expander("Every company-year"):
        st.dataframe(table, width="stretch", hide_index=True)
        st.download_button("Download as CSV", table.to_csv(index=False), "backtest.csv")
