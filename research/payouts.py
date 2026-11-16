"""What the company hands back to shareholders, and what it gives away in shares.

Three things move a shareholder's slice of the business besides the profits:
  * dividends: cash paid out
  * buybacks: the company buying its own shares, which makes each remaining
    share a bigger slice
  * stock-based pay: new shares given to staff, which makes each slice smaller
"""

import pandas as pd


def by_year(s: pd.DataFrame, m: pd.DataFrame) -> pd.DataFrame:
    """One row per fiscal year."""
    table = pd.DataFrame(index=s.index)
    table["dividends_paid"] = s["dividends_paid"]
    table["buybacks"] = s["buybacks"]
    table["total_returned"] = s[["dividends_paid", "buybacks"]].sum(axis=1, min_count=1)
    # How much of the year's profit and free cash flow that used up. Over 100%
    # means it was paid from savings or borrowing, which can't go on forever.
    table["share_of_net_income"] = (table["total_returned"] / s["net_income"]).where(s["net_income"] > 0)
    table["share_of_free_cash_flow"] = (
        table["total_returned"] / m["free_cash_flow"]).where(m["free_cash_flow"] > 0)
    table["dividends_per_share"] = s["dividends_per_share"]
    table["diluted_shares"] = s["diluted_shares"]
    table["share_count_change"] = s["diluted_shares"].pct_change(fill_method=None)
    table["stock_comp"] = s["stock_comp"]
    table["stock_comp_share_of_revenue"] = s["stock_comp"] / s["revenue"]
    return table


def today(latest_s: pd.Series, market_cap: float) -> dict:
    """Yields on today's market value, from the latest twelve months."""
    def figure(name):
        value = latest_s.get(name)
        return None if value is None or pd.isna(value) else float(value)

    dividends, buybacks, stock_comp = figure("dividends_paid"), figure("buybacks"), figure("stock_comp")
    usable = market_cap is not None and not pd.isna(market_cap) and market_cap > 0

    def yield_on(amount):
        return amount / market_cap if usable and amount is not None else None

    returned = (dividends or 0.0) + (buybacks or 0.0)
    return {
        "dividends_paid": dividends,
        "buybacks": buybacks,
        "stock_comp": stock_comp,
        "dividend_yield": yield_on(dividends),
        "buyback_yield": yield_on(buybacks),
        "shareholder_yield": yield_on(returned) if dividends is not None or buybacks is not None else None,
        # Buybacks that only mop up shares handed to staff don't shrink the count.
        "net_buyback_yield": yield_on((buybacks or 0.0) - (stock_comp or 0.0))
        if buybacks is not None else None,
    }
