"""What the share price itself has been doing: returns, range, trend and bumpiness."""

import pandas as pd

PERIODS = {"1 month": 21, "3 months": 63, "6 months": 126, "1 year": 252, "3 years": 756}


def returns(prices: pd.Series, market: pd.Series = None) -> pd.DataFrame:
    """Price change over each period, next to the S&P 500's. Dividends are not included."""
    def changes(series):
        out = {}
        for label, days in PERIODS.items():
            out[label] = series.iloc[-1] / series.iloc[-1 - days] - 1 if len(series) > days else None
        this_year = series[series.index.year == series.index[-1].year]
        before = series[series.index.year < series.index[-1].year]
        out["This year so far"] = this_year.iloc[-1] / before.iloc[-1] - 1 if len(before) else None
        out["5 years"] = series.iloc[-1] / series.iloc[0] - 1 if len(series) > 1100 else None
        return out

    order = ["1 month", "3 months", "6 months", "This year so far", "1 year", "3 years", "5 years"]
    table = pd.DataFrame({"stock": changes(prices)}).reindex(order)
    if market is not None:
        table["market"] = pd.Series(changes(market)).reindex(order)
        table["difference"] = table["stock"].astype("float64") - table["market"].astype("float64")
    return table.astype("float64")


def summary(prices: pd.Series) -> dict:
    """Where the price sits in its range and against its own trend."""
    price = float(prices.iloc[-1])
    year = prices.tail(252)
    daily = prices.pct_change().dropna().tail(252)
    running_high = prices.cummax()
    average_50 = float(prices.tail(50).mean()) if len(prices) >= 50 else None
    average_200 = float(prices.tail(200).mean()) if len(prices) >= 200 else None
    return {
        "price": price,
        "as_of": prices.index[-1],
        "high_52_week": float(year.max()),
        "low_52_week": float(year.min()),
        "below_high": price / float(year.max()) - 1,
        "above_low": price / float(year.min()) - 1,
        "average_50_day": average_50,
        "average_200_day": average_200,
        "vs_200_day": price / average_200 - 1 if average_200 else None,
        # Typical yearly swing: the spread of daily moves, scaled up to a year.
        "volatility": float(daily.std() * 252 ** 0.5) if len(daily) > 60 else None,
        # Worst fall from a peak to a later low over the whole history shown.
        "worst_fall": float((prices / running_high - 1).min()),
    }
