"""The core metrics, computed from the annual statements table.

Each formula is written out in plain arithmetic so it can be checked by hand.
"""

import pandas as pd


def compute_annual_metrics(s: pd.DataFrame) -> pd.DataFrame:
    """Profitability, growth, returns and leverage for every fiscal year."""
    m = pd.DataFrame(index=s.index)

    # Growth: how much bigger this year's sales are than last year's.
    m["revenue_growth"] = s["revenue"].pct_change(fill_method=None)

    # Margins: what share of each sales dollar is left at each stage.
    m["gross_margin"] = s["gross_profit"] / s["revenue"]
    m["operating_margin"] = s["operating_income"] / s["revenue"]
    m["net_margin"] = s["net_income"] / s["revenue"]

    # Free cash flow: cash the business generated minus what it had to reinvest
    # in buildings and equipment. This is what a DCF will value.
    m["free_cash_flow"] = s["cash_from_operations"] - s["capex"]
    m["fcf_margin"] = m["free_cash_flow"] / s["revenue"]

    # EBITDA: operating profit before the non-cash depreciation charge.
    m["ebitda"] = s["operating_income"] + s["d_and_a"]

    # Return on equity: profit per dollar of shareholders' money, using the
    # average of the year's opening and closing equity.
    average_equity = (s["equity"] + s["equity"].shift(1)) / 2
    m["return_on_equity"] = s["net_income"] / average_equity

    # Return on invested capital: after-tax operating profit per dollar that
    # lenders and shareholders have tied up in the business.
    tax_rate = (s["income_tax"] / s["pretax_income"]).clip(lower=0, upper=0.5)
    after_tax_operating_profit = s["operating_income"] * (1 - tax_rate)
    invested_capital = s["total_debt"].fillna(0) + s["equity"] - s["cash_and_investments"].fillna(0)
    average_invested = (invested_capital + invested_capital.shift(1)) / 2
    m["return_on_invested_capital"] = (after_tax_operating_profit / average_invested).where(
        average_invested > 0
    )

    # Leverage: how many years of EBITDA it would take to pay off debt net of cash.
    m["net_debt"] = s["total_debt"].fillna(0) - s["cash_and_investments"].fillna(0)
    m["net_debt_to_ebitda"] = (m["net_debt"] / m["ebitda"]).where(m["ebitda"] > 0)

    return m


def compute_valuation(s: pd.DataFrame, m: pd.DataFrame, price: float) -> dict:
    """Valuation multiples: today's price against the latest fiscal year's results."""
    latest_s, latest_m = s.iloc[-1], m.iloc[-1]

    # Market cap: what all the shares are worth at today's price.
    market_cap = price * latest_s["diluted_shares"]
    # Enterprise value: the price of the whole business, i.e. shares plus debt
    # minus the cash you would get with it.
    enterprise_value = market_cap + latest_m["net_debt"]

    def ratio(top, bottom):
        # A multiple of a negative or missing figure is meaningless, so show nothing.
        if pd.isna(top) or pd.isna(bottom) or bottom <= 0:
            return None
        return top / bottom

    return {
        "price": price,
        "market_cap": market_cap,
        "enterprise_value": enterprise_value,
        "price_to_earnings": ratio(market_cap, latest_s["net_income"]),
        "ev_to_ebitda": ratio(enterprise_value, latest_m["ebitda"]),
        "ev_to_sales": ratio(enterprise_value, latest_s["revenue"]),
        "fcf_yield": ratio(latest_m["free_cash_flow"], market_cap),
    }
