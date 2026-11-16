"""Market-wide inputs for the discount rate: the risk-free rate and beta."""

from . import config, prices


def get_risk_free_rate() -> tuple:
    """The 10-year US Treasury yield, as (rate, source description).

    Yahoo quotes the ^TNX index as the yield in percent (4.25 means 4.25%).
    """
    try:
        rate = float(prices.get_price_history("^TNX").iloc[-1]) / 100
        if 0 < rate < 0.2:
            return rate, "10-year US Treasury yield"
    except Exception:  # noqa: BLE001 - fall through to the stored assumption
        pass
    return config.FALLBACK_RISK_FREE_RATE, "fallback assumption (Treasury yield unavailable)"


def compute_beta(stock_prices, market_prices) -> float:
    """How much the share moves when the market moves 1%.

    Beta is the slope of the stock's weekly returns against the market's:
    covariance(stock, market) / variance(market). Weekly returns are used
    because daily ones are noisy.
    """
    stock = stock_prices.resample("W-FRI").last().pct_change()
    market = market_prices.resample("W-FRI").last().pct_change()
    both = stock.to_frame("stock").join(market.to_frame("market"), how="inner").dropna()
    if len(both) < 52:
        raise ValueError("Need at least a year of prices to estimate beta.")
    return float(both["stock"].cov(both["market"]) / both["market"].var())


def get_beta(stock_prices) -> tuple:
    """Beta against the S&P 500 over five years, as (beta, source description)."""
    try:
        beta = compute_beta(stock_prices, prices.get_price_history("^GSPC"))
        # Extreme estimates are usually noise, so keep beta in a sensible range.
        return min(max(beta, 0.5), 2.0), "5-year weekly returns vs S&P 500"
    except Exception:  # noqa: BLE001
        return 1.0, "assumed 1.0 (not enough price history)"
