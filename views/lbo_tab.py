"""LBO tab: what a buyout firm could pay for the company, and the return it would make."""

import altair as alt
import pandas as pd
import streamlit as st

from research import lbo, market, report

from . import style
from .formatting import dollars, money, multiple, percent

# The biggest buyouts ever done were around this size, so anything far larger
# is an exercise in the mechanics rather than a deal that could happen.
LARGEST_REALISTIC_BUYOUT = 60e9

# (field, label, lowest, highest, step, scale, help text). Scale 100 means the
# box shows a percentage; scale 1 means it shows the number itself.
FIELDS = [
    ("premium", "Bid premium (%)", 0.0, 150.0, 5.0, 100,
     "How far above today's share price the buyer bids. Takeovers usually pay 20-40% more."),
    ("leverage", "Debt (x EBITDA)", 0.0, 10.0, 0.5, 1,
     "How much the buyer borrows, as a multiple of yearly EBITDA. Typical buyouts use 4-6 times."),
    ("interest_rate", "Interest rate (%)", 1.0, 20.0, 0.25, 100,
     "The rate on the buyout debt. Riskier than ordinary company debt, so it costs more."),
    ("fees_pct", "Deal fees (% of value)", 0.0, 6.0, 0.25, 100,
     "Bankers, lawyers and lenders. Paid on day one and never recovered."),
    ("exit_multiple", "Sale multiple (x EBITDA)", 1.0, 60.0, 0.5, 1,
     "The EV/EBITDA multiple the company is sold at. The default is the multiple paid, "
     "so the return isn't flattered by assuming a richer price later."),
    ("growth_start", "Revenue growth, year 1 (%)", -20.0, 60.0, 0.5, 100, "Growth in the first year."),
    ("growth_end", "Revenue growth, final year (%)", -10.0, 40.0, 0.5, 100, "Growth in the last year."),
    ("ebitda_margin", "EBITDA margin (%)", 1.0, 80.0, 0.5, 100,
     "EBITDA as a share of revenue, held constant. Buyers often plan to raise this."),
]


def _base(data: dict) -> lbo.Base:
    latest = data["latest"]
    return lbo.Base(
        revenue=float(latest["statements"]["revenue"]),
        ebitda=float(latest["metrics"]["ebitda"]),
        net_debt=float(latest["metrics"]["net_debt"]),
        shares=float(latest["statements"]["diluted_shares"]),
        price=float(data["valuation"]["price"]),
    )


def blocker(data: dict):
    """Why an LBO can't sensibly be run for this company, or None if it can."""
    reason = report.dcf_blocker(data)
    if reason:
        return ("A buyout model doesn't apply to banks and insurers, which already run on borrowed "
                "money." if data["profile"]["is_financial"] else reason)
    ebitda = data["latest"]["metrics"]["ebitda"]
    if pd.isna(ebitda) or ebitda <= 0:
        return ("A buyout is funded by borrowing against EBITDA, and this company's EBITDA is "
                "negative or missing, so no lender would fund one.")
    return None


def render(data: dict, dcf_output):
    """Draw the tab. Returns {"result", "prices"} for the summary chart, or None."""
    ticker = data["ticker"]
    reason = blocker(data)
    if reason:
        st.info(reason)
        return None

    base = _base(data)
    # Tax, D&A, capex and working capital follow whatever is set on the DCF tab.
    operating = dcf_output[1] if dcf_output else report.dcf_defaults(data)[0]
    defaults = lbo.default_assumptions(base, operating, market.get_risk_free_rate()[0])

    def load_defaults() -> None:
        st.session_state[f"{ticker}_lbo_years"] = defaults.years
        st.session_state[f"{ticker}_lbo_target"] = 20.0
        for field, _, low, high, _, scale, _ in FIELDS:
            value = round(getattr(defaults, field) * scale, 2)
            st.session_state[f"{ticker}_lbo_{field}"] = min(max(value, low), high)

    if f"{ticker}_lbo_years" not in st.session_state:
        load_defaults()

    style.own_analysis(
        "A leveraged buyout model: what a private equity buyer could pay for this company, "
        "and where its return would come from. A check on the other valuations, not a prediction "
        "that anyone will bid."
    )
    headline = st.container()

    with st.expander("Change the assumptions", expanded=False):
        st.caption("Tax, depreciation, capital spending and working capital follow the DCF tab.")
        cols = st.columns(5)
        cols[0].number_input("Years held", 3, 10, step=1, key=f"{ticker}_lbo_years",
                             help="How long the buyer owns the company before selling. Usually 4-6.")
        cols[1].number_input("Return the buyer wants (%)", 5.0, 40.0, step=1.0, key=f"{ticker}_lbo_target",
                             help="Buyout firms typically aim for about 20% a year.")
        for position, (field, label, low, high, step, _, tip) in enumerate(FIELDS, start=2):
            cols[position % 5].number_input(label, low, high, step=step,
                                            key=f"{ticker}_lbo_{field}", help=tip)
        if st.button("Reset to defaults", key=f"{ticker}_lbo_reset"):
            load_defaults()
            st.rerun()

    assumptions = lbo.Assumptions(
        years=int(st.session_state[f"{ticker}_lbo_years"]),
        tax_rate=operating.tax_rate, da_pct=operating.da_pct,
        capex_pct=operating.capex_pct, nwc_pct=operating.nwc_pct,
        **{field: st.session_state[f"{ticker}_lbo_{field}"] / scale
           for field, _, _, _, _, scale, _ in FIELDS},
    )
    target = st.session_state[f"{ticker}_lbo_target"] / 100
    try:
        result = lbo.run(base, assumptions)
    except ValueError as error:
        st.error(str(error))
        return None

    # What a buyer could pay: at the target return, and five points either side.
    prices = {"low": lbo.affordable_price(base, assumptions, target + 0.05),
              "mid": lbo.affordable_price(base, assumptions, target),
              "high": lbo.affordable_price(base, assumptions, max(target - 0.05, 0.01))}
    gap = prices["mid"] / base.price - 1

    with headline:
        style.cards([
            {"label": f"A buyer wanting {target:.0%} a year could pay", "own": True,
             "value": dollars(max(prices["mid"], 0)),
             "note": f"{abs(gap):.0%} {'above' if gap > 0 else 'below'} the price",
             "tone": style.tone(gap)},
            {"label": f"Return on a bid at {dollars(result['offer_price'])}", "own": True,
             "value": percent(result["irr"]) + " a year",
             "note": f"{result['money_multiple']:.1f}x the money in {assumptions.years} years",
             "tone": style.tone(result["irr"] - target)},
            {"label": "Price paid", "value": multiple(result["entry_multiple"]) + " EBITDA",
             "note": f"{money(result['enterprise_value'])} for the whole company"},
            {"label": "Funded with debt", "value": percent(result["debt_share"]),
             "note": f"{money(result['debt'])} borrowed, {money(result['sponsor_equity'])} of the buyer's money"},
            {"label": "Tightest interest cover", "value": multiple(result["min_interest_cover"]),
             "note": "EBITDA divided by interest; under 2x is strained",
             "tone": "down" if result["min_interest_cover"] < 2 else None},
        ])
        if result["enterprise_value"] > LARGEST_REALISTIC_BUYOUT:
            st.warning(
                f"At {money(result['enterprise_value'])} this would be far larger than any buyout ever "
                "done (the biggest have been around $50 billion), so read it as a way to see the "
                "mechanics, not as a deal that could happen."
            )
        if gap < 0:
            st.caption("A buyer could not pay today's price and still hit that return on these "
                       "assumptions, so the share price isn't being held up by takeover value.")

    left, right = st.columns(2)
    with left:
        st.subheader("How the purchase is funded")
        st.dataframe(
            pd.DataFrame({
                "": ["Buying the shares", "Repaying existing net debt", "Deal fees", "Total needed",
                     "New debt", "Buyer's own money"],
                "Amount": [money(result["equity_price"]), money(base.net_debt), money(result["fees"]),
                           money(result["enterprise_value"] + result["fees"]),
                           money(result["debt"]), money(result["sponsor_equity"])],
            }),
            hide_index=True, width="stretch",
        )
    with right:
        st.subheader("Where the buyer's gain comes from")
        parts = pd.DataFrame({
            "source": ["Profit growth", "Change in multiple", "Debt paid down", "Fees"],
            "amount": [result["gain_from_growth"] / 1e9, result["gain_from_multiple"] / 1e9,
                       result["gain_from_debt"] / 1e9, result["gain_lost_to_fees"] / 1e9],
        })
        chart = alt.Chart(parts).mark_bar(cornerRadiusEnd=4, height=24).encode(
            x=alt.X("amount:Q", title="$ billions"),
            y=alt.Y("source:N", sort=parts["source"].tolist(), title=None, axis=alt.Axis(labelLimit=200)),
            color=alt.condition(alt.datum.amount >= 0, alt.value(style.GREEN), alt.value(style.RED)),
            tooltip=[alt.Tooltip("source:N", title="Source"),
                     alt.Tooltip("amount:Q", format="$,.2f", title="$ billions")],
        )
        st.altair_chart(chart.properties(height=190), width="stretch")
        st.caption(f"Together these make the buyer's gain of {money(result['gain'])}: "
                   f"{money(result['sponsor_equity'])} in, {money(max(result['exit_equity'], 0))} out.")

    st.subheader("Debt outstanding at each year end ($B)")
    schedule = result["schedule"]
    debt = pd.DataFrame({"Debt": [result["debt"] / 1e9] + (schedule["debt_end"] / 1e9).tolist()})
    debt.index = ["At purchase"] + [f"Year {year}" for year in schedule.index]
    st.bar_chart(debt, color=style.BLUE)

    st.subheader("Sensitivity: the buyer's yearly return")
    grid = result_grid = lbo.sensitivity(base, assumptions)

    def shade(value):
        """Green at or above the target return, red well below it."""
        if pd.isna(value):
            return ""
        if value >= target:
            return "background-color: rgba(78,203,158,0.35)"
        if value >= target - 0.05:
            return "background-color: rgba(242,184,75,0.25)"
        return "background-color: rgba(226,104,122,0.30)"

    table = grid.copy()
    table.index = [f"Bid {premium:.0%} above the price" for premium in result_grid.index]
    table.columns = [f"Sold at {exit_multiple:.1f}x" for exit_multiple in result_grid.columns]
    st.dataframe(table.style.map(shade).format(percent), width="stretch")
    st.caption(f"Green meets the {target:.0%} target, amber is within five points of it, red is below.")

    with st.expander("The buyout year by year"):
        shown = pd.DataFrame({
            "Revenue": schedule["revenue"].map(money),
            "EBITDA": schedule["ebitda"].map(money),
            "Less interest": schedule["interest"].map(money),
            "Less tax": schedule["tax"].map(money),
            "Less capex": schedule["capex"].map(money),
            "Less working capital": schedule["working_capital_change"].map(money),
            "Cash left to repay debt": schedule["free_cash_flow"].map(money),
            "Debt at year end": schedule["debt_end"].map(money),
            "Debt / EBITDA": schedule["leverage"].map(multiple),
            "EBITDA / interest": schedule["interest_cover"].map(multiple),
        }).T
        shown.columns = [f"Year {year}" for year in schedule.index]
        st.dataframe(shown, width="stretch")
        st.caption("Interest is charged on the debt owed at the start of each year, and every "
                   "dollar of spare cash repays debt. Real buyouts layer several kinds of debt "
                   "with different terms; this treats it as one loan.")

    return {"result": result, "prices": prices, "target": target}
