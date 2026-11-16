"""Is the share cheap or dear compared with its own past?

A company can look expensive next to its peers and still be cheap by its own
standards, or the reverse. This rebuilds the company's valuation multiples at
each month-end using the share price then and the latest annual results that
had been published by then (taken as 90 days after the fiscal year ended).
"""

import pandas as pd

PUBLICATION_LAG_DAYS = 90
MULTIPLES = {"pe": "P/E", "ev_ebitda": "EV / EBITDA", "ps": "Price / sales",
             "pb": "Price / book"}


def history(annual: pd.DataFrame, annual_metrics: pd.DataFrame, prices: pd.Series) -> pd.DataFrame:
    """One row per month-end with the multiples as they stood. Blank where profit was negative."""
    known_from = annual.index + pd.Timedelta(days=PUBLICATION_LAG_DAYS)
    monthly = prices.resample("ME").last().dropna()
    rows = {}
    for day, price in monthly.items():
        published = known_from <= day
        if not published.any():
            continue
        year, m = annual[published].iloc[-1], annual_metrics[published].iloc[-1]
        shares = year["diluted_shares"]
        if pd.isna(shares) or shares <= 0:
            continue
        market_cap = price * shares
        net_debt = m["net_debt"] if pd.notna(m["net_debt"]) else 0.0

        def over(top, bottom):
            return top / bottom if pd.notna(bottom) and bottom > 0 else float("nan")

        rows[day] = {
            "pe": over(market_cap, year["net_income"]),
            "ev_ebitda": over(market_cap + net_debt, m["ebitda"]),
            "ps": over(market_cap, year["revenue"]),
            "pb": over(market_cap, year["equity"]),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def position(series: pd.Series, current) -> dict:
    """Where today's multiple sits in its own history.

    `percentile` is the share of past months that were cheaper than today:
    0.9 means it has been cheaper than this 90% of the time.
    """
    past = series.dropna()
    if len(past) < 12 or current is None or pd.isna(current):
        return None
    return {
        "current": float(current),
        "median": float(past.median()),
        "low": float(past.quantile(0.1)),
        "high": float(past.quantile(0.9)),
        "percentile": float((past < current).mean()),
        "years": round(len(past) / 12, 1),
    }


def describe(name: str, where: dict) -> str:
    """One plain sentence, e.g. "P/E of 38.7x is higher than in 92% of the last 9 years"."""
    ratio = where["current"] / where["median"] - 1
    return (f"{name} of {where['current']:.1f}x against a typical {where['median']:.1f}x: "
            f"{abs(ratio):.0%} {'above' if ratio > 0 else 'below'} its own norm, and higher than "
            f"in {where['percentile']:.0%} of months over the last {where['years']:.0f} years.")
