"""DCF tab: editable assumptions, the forecast, the answer and its sensitivity."""

import pandas as pd
import streamlit as st

from research import dcf, report, store

from . import style
from .formatting import dollars, money, percent, signed_percent

# (field, label, lowest, highest, step, help text) - all shown as percentages.
RATE_FIELDS = [
    ("growth_start", "Revenue growth, year 1", -20.0, 60.0, 0.5,
     "Growth in the first forecast year. It then moves in a straight line to the final-year rate."),
    ("growth_end", "Revenue growth, final year", -5.0, 20.0, 0.5,
     "Growth in the last forecast year."),
    ("ebit_margin", "Operating margin", -30.0, 70.0, 0.5,
     "Operating profit as a share of revenue, held constant through the forecast."),
    ("tax_rate", "Tax rate", 0.0, 40.0, 0.5, "Share of operating profit paid in tax."),
    ("da_pct", "D&A, % of revenue", 0.0, 40.0, 0.25,
     "Depreciation and amortisation: a non-cash cost, so it is added back."),
    ("capex_pct", "Capex, % of revenue", 0.0, 50.0, 0.25,
     "Spending on buildings and equipment needed to keep growing."),
    ("nwc_pct", "Working capital, % of new revenue", -20.0, 40.0, 0.5,
     "Cash tied up in stock and unpaid bills for each extra dollar of sales."),
    ("wacc", "Discount rate (WACC)", 4.0, 25.0, 0.1,
     "The return investors require. Higher means future cash is worth less today."),
    ("terminal_growth", "Terminal growth", 0.0, 5.0, 0.1,
     "Growth forever after the forecast. Should not exceed long-run economic growth."),
]


def _load_into_widgets(ticker: str, a: dcf.Assumptions) -> None:
    st.session_state[f"{ticker}_years"] = a.years
    for field, *_ in RATE_FIELDS:
        st.session_state[f"{ticker}_{field}"] = round(getattr(a, field) * 100, 2)


def render(data: dict):
    """Draw the tab. Returns (result, assumptions, wacc_parts, user_set) or None."""
    ticker = data["ticker"]
    blocker = report.dcf_blocker(data)
    if blocker:
        st.info(blocker)
        return None

    defaults, wacc_parts = report.dcf_defaults(data)
    saved = store.get_assumptions(ticker)
    if f"{ticker}_years" not in st.session_state:
        _load_into_widgets(ticker, dcf.Assumptions(**saved) if saved else defaults)

    style.own_analysis(
        "A discounted cash flow model: what the company's future cash is worth today. "
        + ("Using your saved assumptions." if saved else
           "Starting from mechanical defaults (three-year averages), a baseline to argue with.")
    )
    # The answer goes first; this space is filled in once it has been worked out.
    headline = st.container()

    with st.expander("Change the assumptions", expanded=False):
        st.caption(f"The forecast starts from revenue for the {data['latest']['label']}. "
                   "Every number here can be changed, and the whole page updates.")
        cols = st.columns(5)
        cols[0].number_input("Forecast years", 3, 15, step=1, key=f"{ticker}_years",
                             help="How many years to forecast before the terminal value.")
        for position, (field, label, low, high, step, tip) in enumerate(RATE_FIELDS, start=1):
            cols[position % 5].number_input(
                f"{label} (%)", low, high, step=step, key=f"{ticker}_{field}", help=tip
            )
        save, reset, _ = st.columns([1.3, 1.3, 4])
        assumptions = dcf.Assumptions(
            years=int(st.session_state[f"{ticker}_years"]),
            **{f: st.session_state[f"{ticker}_{f}"] / 100 for f, *_ in RATE_FIELDS},
        )
        if save.button("Save assumptions", key=f"{ticker}_save"):
            store.save_assumptions(ticker, assumptions.to_dict())
            st.toast("Saved. The daily refresh will use these.")
        if reset.button("Reset to defaults", key=f"{ticker}_reset"):
            store.clear_assumptions(ticker)
            _load_into_widgets(ticker, defaults)
            st.rerun()

    try:
        result = report.run_dcf(data, assumptions)
    except ValueError as error:
        st.error(str(error))
        return None

    price = data["valuation"]["price"]
    gap = result["upside"]
    with headline:
        style.cards([
            {"label": "DCF value per share", "value": dollars(result["value_per_share"]), "own": True,
             "note": (f"{abs(gap):.0%} {'above' if gap > 0 else 'below'} the price"
                      if result["value_per_share"] > 0 else "no value on these assumptions"),
             "tone": style.tone(gap)},
            {"label": "Share price today", "value": dollars(price)},
            {"label": "Growth the price implies", "own": True,
             "value": percent(result["implied_growth"]) if result["implied_growth"] is not None else "Out of range",
             "note": "year-1 sales growth at which this model's value equals the price"},
            {"label": "Discount rate (WACC)", "value": percent(assumptions.wacc),
             "note": f"terminal growth {percent(assumptions.terminal_growth)}"},
            {"label": "Value from after the forecast", "value": percent(result["terminal_share"]),
             "note": "share of value in the terminal value"},
        ])
        if result["terminal_share"] is not None and result["terminal_share"] > 0.75:
            st.warning("More than three-quarters of the value comes from the terminal value, so the "
                       "answer rests almost entirely on the discount rate and terminal growth.")
        if assumptions.ebit_margin <= 0:
            st.warning("With a negative operating margin the company never generates cash in this "
                       "model, so the value is not meaningful. Set the margin you expect it to reach.")

    st.subheader("Bear, base and bull cases")
    cases = result["scenarios"]
    style.cards([
        {"label": f"{name} case: growth {percent(row['growth_start'])}, margin "
                  f"{percent(row['ebit_margin'])}, discount rate {percent(row['wacc'])}",
         "value": dollars(row["value_per_share"]), "own": True,
         "note": f"{abs(row['value_per_share'] / price - 1):.0%} "
                 f"{'above' if row['value_per_share'] > price else 'below'} the price",
         "tone": style.tone(row["value_per_share"] / price - 1)}
        for name, row in cases.iterrows()
    ])
    st.caption("Base is the assumptions above. Bear and bull move growth, margin and the "
               "discount rate together: growth by 2 points (or 30% of itself if larger), margin "
               "by 15%, and the discount rate by 1 point. A rule of thumb for how far the "
               "answer moves, not a forecast of either outcome.")

    st.subheader("Sensitivity: value per share")
    grid = result["sensitivity"]

    def shade(value):
        """Green where the value is above today's price, red where below."""
        if pd.isna(value):
            return ""
        distance = value / price - 1
        strength = min(0.12 + abs(distance) * 0.6, 0.55)
        colour = "78,203,158" if distance >= 0 else "226,104,122"
        return f"background-color: rgba({colour},{strength:.2f})"

    table = grid.copy()
    table.index = [f"Discount rate {w:.1%}" for w in grid.index]
    table.columns = [f"Growth {g:.1%}" for g in grid.columns]
    st.dataframe(table.style.map(shade).format(dollars), width="stretch")
    st.caption("Rows are discount rates, columns are terminal growth rates. Green cells are "
               f"above today's price of {dollars(price)}, red cells below.")

    st.subheader("Forecast ($B)")
    forecast = result["forecast"]
    chart = pd.DataFrame({"Revenue": forecast["revenue"] / 1e9,
                          "Free cash flow": forecast["free_cash_flow"] / 1e9})
    chart.index = [f"Year {y:02d}" for y in forecast.index]
    st.bar_chart(chart, y=["Revenue", "Free cash flow"], color=[style.BLUE, style.GREEN], stack=False)

    st.subheader("The working")
    with st.expander("Forecast, line by line"):
        shown = pd.DataFrame(
            {
                "Revenue growth": forecast["growth"].map(percent),
                "Revenue": forecast["revenue"].map(money),
                "Operating profit": forecast["ebit"].map(money),
                "After-tax operating profit": forecast["after_tax_profit"].map(money),
                "Plus D&A": forecast["d_and_a"].map(money),
                "Less capex": forecast["capex"].map(money),
                "Less working capital": forecast["working_capital_change"].map(money),
                "Free cash flow": forecast["free_cash_flow"].map(money),
                "Present value": forecast["present_value"].map(money),
            }
        ).T
        shown.columns = [f"Year {y}" for y in forecast.index]
        st.dataframe(shown, width="stretch")
    with st.expander("From enterprise value to value per share"):
        bridge = pd.DataFrame(
            {
                "": [
                    "Present value of forecast cash flows",
                    "Present value of terminal value",
                    "Enterprise value",
                    "Less: net debt",
                    "Equity value",
                    "Diluted shares",
                    "Value per share",
                ],
                "Amount": [
                    money(result["pv_forecast"]),
                    money(result["pv_terminal"]),
                    money(result["enterprise_value"]),
                    money(result["net_debt"]),
                    money(result["equity_value"]),
                    f"{report.dcf_inputs(data)[2] / 1e9:,.2f}B",
                    dollars(result["value_per_share"]),
                ],
            }
        )
        st.dataframe(bridge, hide_index=True, width="stretch")
    with st.expander("Where the default discount rate comes from"):
        parts = pd.DataFrame(
            {
                "": [
                    "Risk-free rate", "Beta", "Equity risk premium", "Cost of equity",
                    "Cost of debt (before tax)", "Weight of equity", "Weight of debt",
                    "Default WACC",
                ],
                "Value": [
                    percent(wacc_parts["risk_free_rate"]), f"{wacc_parts['beta']:.2f}",
                    percent(wacc_parts["equity_risk_premium"]), percent(wacc_parts["cost_of_equity"]),
                    percent(wacc_parts["cost_of_debt"]), percent(wacc_parts["weight_equity"]),
                    percent(wacc_parts["weight_debt"]), percent(wacc_parts["wacc"]),
                ],
            }
        )
        st.dataframe(parts, hide_index=True, width="stretch")
        st.caption(f"Risk-free rate: {wacc_parts['risk_free_source']}. "
                   f"Beta: {wacc_parts['beta_source']}. The equity risk premium is an assumption.")

    return result, assumptions, wacc_parts, bool(saved)
