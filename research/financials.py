"""Valuing banks, insurers and brokers.

A normal DCF doesn't work for these companies: borrowing and lending money is
their business, so "free cash flow" and "enterprise value" mean nothing. They
are valued on what shareholders own and earn instead:

  * Book value: shareholders' equity, i.e. assets minus everything owed.
    "Tangible" book value also takes out goodwill and other intangibles.
  * Return on equity (ROE): profit earned on each dollar of that equity.
  * Two valuation methods built on those:
      1. Justified price-to-book. A bank that earns exactly the return
         investors require is worth exactly its book value. One that earns
         more is worth more than book, in proportion.
      2. Dividend discount model. The shares are worth the dividends they
         will pay, discounted back to today.
"""

from dataclasses import asdict, dataclass

import pandas as pd

from . import config


@dataclass
class Assumptions:
    roe: float               # return on equity the company can sustain
    cost_of_equity: float    # return shareholders require
    growth: float            # long-run growth, forever
    dividend_growth: float   # dividend growth for the first five years

    def to_dict(self) -> dict:
        return asdict(self)


def snapshot(latest_s: pd.Series, annual: pd.DataFrame, annual_metrics: pd.DataFrame,
             price: float) -> dict:
    """Book value, returns and payout for the latest twelve months."""
    def figure(name):
        value = latest_s.get(name)
        return 0.0 if value is None or pd.isna(value) else float(value)

    shares = latest_s["diluted_shares"]
    common_equity = latest_s["equity"] - figure("preferred_equity")
    tangible_equity = common_equity - figure("goodwill") - figure("intangibles")
    net_income = latest_s["net_income"]
    dividends = figure("dividends_paid")
    buybacks = figure("buybacks")

    # Return on equity over the latest twelve months, against the average of
    # equity now and at the last year end.
    opening_equity = annual["equity"].iloc[-1] if latest_s.name not in annual.index else (
        annual["equity"].iloc[-2] if len(annual) > 1 else annual["equity"].iloc[-1])
    average_equity = (latest_s["equity"] + opening_equity) / 2
    return {
        "book_value_per_share": common_equity / shares,
        "tangible_book_per_share": tangible_equity / shares,
        "price_to_book": price / (common_equity / shares) if common_equity > 0 else None,
        "price_to_tangible_book": price / (tangible_equity / shares) if tangible_equity > 0 else None,
        "earnings_per_share": net_income / shares,
        "price_to_earnings": price / (net_income / shares) if net_income > 0 else None,
        "return_on_equity": net_income / average_equity if average_equity > 0 else None,
        "return_on_tangible_equity": net_income / tangible_equity if tangible_equity > 0 else None,
        "roe_history": annual_metrics["return_on_equity"].dropna().tail(5),
        "dividend_per_share": dividends / shares,
        "buyback_per_share": buybacks / shares,
        "payout_ratio": dividends / net_income if net_income > 0 else None,
        "total_payout_ratio": (dividends + buybacks) / net_income if net_income > 0 else None,
        "dividend_yield": dividends / shares / price,
    }


def default_assumptions(snap: dict, beta: float, risk_free: float) -> Assumptions:
    """A mechanical starting point: the last few years' ROE and the CAPM cost of equity."""
    history = snap["roe_history"].tail(3)
    roe = float(history.mean()) if not history.empty else (snap["return_on_equity"] or 0.10)
    roe = min(max(roe, 0.0), 0.30)
    cost_of_equity = risk_free + beta * config.EQUITY_RISK_PREMIUM
    growth = config.DEFAULT_TERMINAL_GROWTH

    # Profit that isn't paid out is reinvested and earns the ROE, which is what
    # lets the dividend grow. Capped, because no bank compounds fast for long.
    retained = 1 - (snap["payout_ratio"] or 0.0)
    dividend_growth = min(max(roe * retained, growth), 0.08)
    return Assumptions(roe, cost_of_equity, growth, dividend_growth)


def justified_price_to_book(a: Assumptions) -> float:
    """The price-to-book multiple the assumptions justify: (ROE - g) / (cost of equity - g)."""
    if a.cost_of_equity <= a.growth + 0.005:
        raise ValueError("The cost of equity must be above the long-run growth rate.")
    return (a.roe - a.growth) / (a.cost_of_equity - a.growth)


def dividend_discount(per_share: float, a: Assumptions, fast_years: int = 5) -> float:
    """Value of a stream of payouts: faster growth for a few years, then the long-run rate."""
    if a.cost_of_equity <= a.growth + 0.005:
        raise ValueError("The cost of equity must be above the long-run growth rate.")
    total, payout = 0.0, per_share
    for year in range(1, fast_years + 1):
        payout *= 1 + a.dividend_growth
        total += payout / (1 + a.cost_of_equity) ** year
    terminal = payout * (1 + a.growth) / (a.cost_of_equity - a.growth)
    return total + terminal / (1 + a.cost_of_equity) ** fast_years


def value(snap: dict, a: Assumptions, price: float) -> dict:
    """Both methods, the sensitivity of the first, and each one's gap to today's price."""
    multiple = justified_price_to_book(a)
    by_book = snap["book_value_per_share"] * multiple
    dividends_only = dividend_discount(snap["dividend_per_share"], a)
    with_buybacks = dividend_discount(snap["dividend_per_share"] + snap["buyback_per_share"], a)

    # Value per share for a grid of returns on equity (rows) and costs of equity (columns).
    roes = [a.roe + 0.02 * i for i in (-2, -1, 0, 1, 2)]
    costs = [a.cost_of_equity + 0.01 * i for i in (-2, -1, 0, 1, 2)]
    grid = {}
    for cost in costs:
        column = []
        for roe in roes:
            trial = Assumptions(roe, cost, a.growth, a.dividend_growth)
            try:
                column.append(snap["book_value_per_share"] * justified_price_to_book(trial))
            except ValueError:
                column.append(float("nan"))
        grid[cost] = column
    sensitivity = pd.DataFrame(grid, index=roes)
    sensitivity.index.name, sensitivity.columns.name = "roe", "cost_of_equity"

    return {
        "justified_price_to_book": multiple,
        "value_by_book": by_book,
        "value_by_dividends": dividends_only,
        "value_by_total_payout": with_buybacks,
        "upside_by_book": by_book / price - 1,
        "upside_by_dividends": dividends_only / price - 1,
        "upside_by_total_payout": with_buybacks / price - 1,
        "sensitivity": sensitivity,
        # Reverse view: the ROE at which book value times the multiple equals today's price.
        "implied_roe": a.growth + (price / snap["book_value_per_share"]) * (a.cost_of_equity - a.growth)
        if snap["book_value_per_share"] > 0 else None,
    }
