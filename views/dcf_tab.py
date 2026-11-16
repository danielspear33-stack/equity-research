"""DCF tab: editable assumptions, the forecast, the answer and its sensitivity."""

import pandas as pd
import streamlit as st

from research import dcf, report, store

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

    st.caption(
        "The starting values are mechanical: averages of the last three years, with growth "
        "fading to the terminal rate. They are a baseline to argue with, not a forecast."
        + (" You are currently seeing your saved assumptions." if saved else "")
    )

    with st.expander("Assumptions", expanded=True):
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
    cols = st.columns(5)
    cols[0].metric("DCF value per share", dollars(result["value_per_share"]))
    cols[1].metric("Share price", dollars(price))
    cols[2].metric("DCF vs price", signed_percent(result["upside"]))
    cols[3].metric("Growth the price implies",
                   percent(result["implied_growth"]) if result["implied_growth"] is not None else "out of range",
                   help="Reverse DCF: the year-1 growth rate at which this model's value "
                        "equals today's price, keeping every other assumption as set.")
    cols[4].metric("Terminal value share", percent(result["terminal_share"]),
                   help="How much of the value comes from the years after the forecast.")

    if result["terminal_share"] is not None and result["terminal_share"] > 0.75:
        st.warning("More than three-quarters of the value comes from the terminal value, so the "
                   "answer rests almost entirely on the discount rate and terminal growth.")
    if assumptions.ebit_margin <= 0:
        st.warning("With a negative operating margin the company never generates cash in this "
                   "model, so the value is not meaningful. Set the margin you expect it to reach.")

    left, right = st.columns([3, 2])
    with left:
        st.subheader("From enterprise value to value per share")
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
                    f"{data['statements']['diluted_shares'].iloc[-1] / 1e9:,.2f}B",
                    dollars(result["value_per_share"]),
                ],
            }
        )
        st.dataframe(bridge, hide_index=True, width="stretch")
    with right:
        st.subheader("Where the default discount rate comes from")
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

    st.subheader("Forecast")
    forecast = result["forecast"]
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

    st.subheader("Sensitivity: value per share")
    grid = result["sensitivity"]
    table = grid.map(dollars)
    table.index = [f"WACC {w:.1%}" for w in grid.index]
    table.columns = [f"Growth {g:.1%}" for g in grid.columns]
    st.dataframe(table, width="stretch")
    st.caption(f"Rows are discount rates, columns are terminal growth rates. "
               f"The share price today is {dollars(price)}.")

    return result, assumptions, wacc_parts, bool(saved)
