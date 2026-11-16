"""A table of many companies at once, ranked by this tool's own measures.

Everything else here starts from a company you already have in mind. The
screener works the other way round: it scores a list of companies so you can
see which are worth opening. It covers the built-in list of about 110 large
companies plus anything on your watchlist.
"""

from datetime import date

import pandas as pd

from . import backtest, config, report, scorecard, store


def row_for(ticker: str) -> dict:
    """One company's line in the table."""
    data = report.run(ticker)
    v = data["valuation"] or {}
    m = data["latest"]["metrics"]

    dcf_value = None
    if report.dcf_blocker(data) is None:
        try:
            dcf_value = report.run_dcf(data, report.saved_or_default_assumptions(data))["value_per_share"]
        except ValueError:
            pass
    scores = scorecard.scores(data, dcf_value=dcf_value)
    row = {
        "ticker": ticker,
        "name": data["profile"]["name"],
        "industry": data["profile"]["industry"],
        "overall": scorecard.overall(scores),
        **{s["name"].lower(): s["score"] for s in scores},
        "price": v.get("price"),
        "market_cap": v.get("market_cap"),
        "price_to_earnings": v.get("price_to_earnings"),
        "fcf_yield": v.get("fcf_yield"),
        "revenue_growth": m["revenue_growth"],
        "operating_margin": m["operating_margin"],
        "return_on_capital": m["return_on_invested_capital"],
        "dcf_gap": dcf_value / v["price"] - 1 if dcf_value and v.get("price") else None,
    }
    return row


def tickers() -> list:
    return sorted(set(backtest.universe()) | set(store.get_watchlist()))


def build(progress=None) -> tuple:
    """Score every company. Returns (table, {ticker: why it was left out})."""
    names, rows, skipped = tickers(), [], {}
    for done, ticker in enumerate(names, start=1):
        if progress:
            progress(done, len(names), ticker)
        try:
            rows.append(row_for(ticker))
        except Exception as error:  # noqa: BLE001 - one bad company shouldn't stop the rest
            skipped[ticker] = str(error)[:120]
    table = pd.DataFrame(rows)
    table["as_of"] = date.today().isoformat()
    return table, skipped


def results_file():
    return config.USER_DATA_DIR / "screener.csv"


def save(table: pd.DataFrame) -> None:
    config.USER_DATA_DIR.mkdir(exist_ok=True)
    table.to_csv(results_file(), index=False)


def load_saved():
    """The last saved table, or None."""
    return pd.read_csv(results_file()) if results_file().exists() else None
