"""Discounted cash flow valuation.

The idea: a business is worth the cash it will hand its owners in future,
with later cash counted for less because money today is worth more than money
tomorrow. The steps are:

  1. Forecast revenue, then the free cash flow that revenue produces.
  2. Discount each year's cash flow back to today at the WACC.
  3. Add a "terminal value" for all the years after the forecast ends.
  4. That total is enterprise value. Subtract net debt to get the value of
     the shares, and divide by the share count for a value per share.
"""

from dataclasses import asdict, dataclass

import pandas as pd

from . import config


@dataclass
class Assumptions:
    years: int               # length of the explicit forecast
    growth_start: float      # revenue growth in forecast year 1
    growth_end: float        # revenue growth in the final forecast year
    ebit_margin: float       # operating profit as a share of revenue
    tax_rate: float
    da_pct: float            # depreciation & amortisation, share of revenue
    capex_pct: float         # capital expenditure, share of revenue
    nwc_pct: float           # working capital needed per extra dollar of revenue
    wacc: float              # discount rate
    terminal_growth: float   # growth forever after the forecast

    def to_dict(self) -> dict:
        return asdict(self)


def _recent_average(series: pd.Series, default: float, low: float, high: float) -> float:
    """Average of the last three years, kept inside a sensible range."""
    values = series.dropna().tail(3)
    if values.empty:
        return default
    return float(min(max(values.mean(), low), high))


def estimate_wacc(statements, valuation, beta: float, risk_free: float, tax_rate: float) -> dict:
    """Weighted average cost of capital, with every ingredient shown.

    Shareholders and lenders both fund the company and both expect a return.
    WACC blends the two, weighted by how much funding each provides.
    """
    latest = statements.iloc[-1]

    # Cost of equity (CAPM): the safe rate plus a premium for market risk,
    # scaled by how risky this particular share is.
    cost_of_equity = risk_free + beta * config.EQUITY_RISK_PREMIUM

    # Cost of debt: the interest the company actually pays on its borrowings.
    debt = latest["total_debt"] if pd.notna(latest["total_debt"]) else 0.0
    interest = latest.get("interest_expense")
    if debt > 0 and pd.notna(interest) and interest > 0:
        cost_of_debt = min(max(interest / debt, risk_free + 0.005), 0.10)
    else:
        cost_of_debt = risk_free + 0.015

    equity = valuation["market_cap"]
    total = equity + debt
    weight_equity, weight_debt = equity / total, debt / total

    # Interest is tax-deductible, so debt's true cost is lower by the tax rate.
    wacc = weight_equity * cost_of_equity + weight_debt * cost_of_debt * (1 - tax_rate)
    return {
        "risk_free_rate": risk_free,
        "beta": beta,
        "equity_risk_premium": config.EQUITY_RISK_PREMIUM,
        "cost_of_equity": cost_of_equity,
        "cost_of_debt": cost_of_debt,
        "tax_rate": tax_rate,
        "weight_equity": weight_equity,
        "weight_debt": weight_debt,
        "wacc": wacc,
    }


def default_assumptions(statements, metrics, valuation, beta: float, risk_free: float) -> tuple:
    """A starting point built from the company's own recent history.

    These are mechanical defaults, not forecasts. They assume the next few
    years look like the last few, which is exactly the judgement an analyst is
    supposed to challenge.
    """
    s, m = statements, metrics
    terminal_growth = config.DEFAULT_TERMINAL_GROWTH

    tax = (s["income_tax"] / s["pretax_income"]).where(s["pretax_income"] > 0)
    tax_rate = _recent_average(tax, 0.21, 0.10, 0.35)

    wacc_parts = estimate_wacc(s, valuation, beta, risk_free, tax_rate)

    revenue = s["revenue"].dropna()
    working_capital = s["working_capital"].iloc[-1] / revenue.iloc[-1]
    assumptions = Assumptions(
        years=config.DEFAULT_FORECAST_YEARS,
        growth_start=_recent_average(m["revenue_growth"], 0.05, -0.05, 0.30),
        growth_end=terminal_growth,
        ebit_margin=_recent_average(m["operating_margin"], 0.10, -0.20, 0.60),
        tax_rate=tax_rate,
        da_pct=_recent_average(s["d_and_a"] / s["revenue"], 0.03, 0.0, 0.30),
        capex_pct=_recent_average(s["capex"] / s["revenue"], 0.04, 0.0, 0.40),
        nwc_pct=0.0 if pd.isna(working_capital) else float(min(max(working_capital, -0.15), 0.30)),
        wacc=float(wacc_parts["wacc"]),
        terminal_growth=terminal_growth,
    )
    return assumptions, wacc_parts


def project(base_revenue: float, a: Assumptions) -> pd.DataFrame:
    """Year-by-year forecast of revenue and free cash flow."""
    rows = []
    revenue = base_revenue
    for year in range(1, a.years + 1):
        # Growth slides in a straight line from the starting rate to the ending rate.
        progress = (year - 1) / (a.years - 1) if a.years > 1 else 1.0
        growth = a.growth_start + (a.growth_end - a.growth_start) * progress
        previous, revenue = revenue, revenue * (1 + growth)

        ebit = revenue * a.ebit_margin
        after_tax_profit = ebit * (1 - a.tax_rate) if ebit > 0 else ebit
        d_and_a = revenue * a.da_pct
        capex = revenue * a.capex_pct
        working_capital_change = (revenue - previous) * a.nwc_pct

        # Free cash flow to all funders: after-tax operating profit, plus the
        # non-cash depreciation charge, minus what must be reinvested.
        free_cash_flow = after_tax_profit + d_and_a - capex - working_capital_change

        discount_factor = 1 / (1 + a.wacc) ** year
        rows.append(
            {
                "year": year,
                "growth": growth,
                "revenue": revenue,
                "ebit": ebit,
                "after_tax_profit": after_tax_profit,
                "d_and_a": d_and_a,
                "capex": capex,
                "working_capital_change": working_capital_change,
                "free_cash_flow": free_cash_flow,
                "discount_factor": discount_factor,
                "present_value": free_cash_flow * discount_factor,
            }
        )
    return pd.DataFrame(rows).set_index("year")


def value(base_revenue: float, net_debt: float, shares: float, a: Assumptions) -> dict:
    """Run the whole DCF and return the answer with its building blocks."""
    if a.wacc <= a.terminal_growth + 0.005:
        raise ValueError(
            "The discount rate must be above the terminal growth rate, otherwise the "
            "terminal value formula gives an infinite or negative answer."
        )
    forecast = project(base_revenue, a)
    final_cash_flow = forecast["free_cash_flow"].iloc[-1]

    # Terminal value (Gordon growth): the value, as at the end of the forecast,
    # of cash flows growing at a constant rate forever.
    terminal_value = final_cash_flow * (1 + a.terminal_growth) / (a.wacc - a.terminal_growth)
    pv_terminal = terminal_value * forecast["discount_factor"].iloc[-1]
    pv_forecast = forecast["present_value"].sum()

    enterprise_value = pv_forecast + pv_terminal
    equity_value = enterprise_value - net_debt
    return {
        "forecast": forecast,
        "pv_forecast": pv_forecast,
        "terminal_value": terminal_value,
        "pv_terminal": pv_terminal,
        "terminal_share": pv_terminal / enterprise_value if enterprise_value > 0 else None,
        "enterprise_value": enterprise_value,
        "net_debt": net_debt,
        "equity_value": equity_value,
        "value_per_share": equity_value / shares,
    }


def sensitivity(base_revenue, net_debt, shares, a: Assumptions, step: float = 0.005) -> pd.DataFrame:
    """Value per share for a grid of discount rates (rows) and terminal growth rates (columns).

    The two inputs the answer is most sensitive to are also the two nobody can
    know, so the honest output of a DCF is this table, not one number.
    """
    waccs = [a.wacc + step * 2 * i for i in (-2, -1, 0, 1, 2)]
    growths = [a.terminal_growth + step * i for i in (-2, -1, 0, 1, 2)]
    grid = {}
    for growth in growths:
        column = []
        for wacc in waccs:
            trial = Assumptions(**{**a.to_dict(), "wacc": wacc, "terminal_growth": growth})
            try:
                column.append(value(base_revenue, net_debt, shares, trial)["value_per_share"])
            except ValueError:
                column.append(float("nan"))
        grid[growth] = column
    table = pd.DataFrame(grid, index=waccs)
    table.index.name, table.columns.name = "wacc", "terminal_growth"
    return table


def scenarios(base_revenue, net_debt, shares, a: Assumptions) -> pd.DataFrame:
    """Value per share in a pessimistic, central and optimistic case.

    The bear and bull cases move the three assumptions that matter most, all
    in the same direction at once:
      * year-1 growth: down or up by 2 points, or 30% of itself if that is more
      * operating margin: 15% lower or higher
      * discount rate: 1 point higher or lower
    The sizes are a rule of thumb, not a forecast. The point is to see how far
    the answer moves when things go somewhat worse or better than the base case.
    """
    growth_shift = max(0.02, 0.30 * abs(a.growth_start))
    margin_shift = 0.15 * abs(a.ebit_margin)
    cases = {
        "Bear": (-growth_shift, -margin_shift, +0.01),
        "Base": (0.0, 0.0, 0.0),
        "Bull": (+growth_shift, +margin_shift, -0.01),
    }
    rows = {}
    for name, (growth, margin, wacc) in cases.items():
        trial = Assumptions(**{
            **a.to_dict(),
            "growth_start": a.growth_start + growth,
            "ebit_margin": a.ebit_margin + margin,
            # Keep the discount rate clear of terminal growth so the maths still works.
            "wacc": max(a.wacc + wacc, a.terminal_growth + 0.01),
        })
        try:
            per_share = value(base_revenue, net_debt, shares, trial)["value_per_share"]
        except ValueError:
            per_share = float("nan")
        rows[name] = {"growth_start": trial.growth_start, "ebit_margin": trial.ebit_margin,
                      "wacc": trial.wacc, "value_per_share": per_share}
    return pd.DataFrame(rows).T


def implied_growth(base_revenue, net_debt, shares, a: Assumptions, price: float):
    """Reverse DCF: the starting growth rate at which the DCF value equals today's price.

    Rather than asking "what is it worth?", this asks "what does the market
    have to believe for the current price to be right?". Found by bisection:
    value rises with growth, so keep halving the range the answer must be in.
    Returns None if no growth rate between -20% and +60% a year does it.
    """
    def gap(growth):
        trial = Assumptions(**{**a.to_dict(), "growth_start": growth})
        return value(base_revenue, net_debt, shares, trial)["value_per_share"] - price

    low, high = -0.20, 0.60
    if gap(low) > 0 or gap(high) < 0:
        return None
    for _ in range(50):
        middle = (low + high) / 2
        if gap(middle) > 0:
            high = middle
        else:
            low = middle
    return (low + high) / 2
