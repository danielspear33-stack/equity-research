"""Share prices from Yahoo Finance's chart feed.

This feed is unofficial: Yahoo doesn't promise it will keep working. The app
treats a price failure as non-fatal and still shows the filing-based numbers.
"""

from urllib.parse import quote

import pandas as pd

from . import config
from .cache import fetch_json

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5y&interval=1d"


def get_price_history(ticker: str) -> pd.Series:
    """Daily closing prices for the last five years, indexed by date."""
    ticker = ticker.strip().upper().replace(".", "-")
    cache_name = "prices_" + ticker.replace("^", "index_")
    raw = fetch_json(CHART_URL.format(ticker=quote(ticker)), cache_name, config.PRICES_MAX_AGE)
    result = raw["chart"]["result"][0]
    dates = pd.to_datetime(result["timestamp"], unit="s").normalize()
    closes = result["indicators"]["quote"][0]["close"]
    return pd.Series(closes, index=dates, name="close").dropna()


LONG_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=15y&interval=1d"


def get_long_price_history(ticker: str) -> pd.Series:
    """Fifteen years of daily closing prices, for looking at a share's own past."""
    ticker = ticker.strip().upper().replace(".", "-")
    cache_name = "prices_long_" + ticker.replace("^", "index_")
    raw = fetch_json(LONG_CHART_URL.format(ticker=quote(ticker)), cache_name, config.FILINGS_MAX_AGE)
    result = raw["chart"]["result"][0]
    dates = pd.to_datetime(result["timestamp"], unit="s").normalize()
    closes = result["indicators"]["quote"][0]["close"]
    return pd.Series(closes, index=dates, name="close").dropna()
