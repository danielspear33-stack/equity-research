"""The daily refresh: re-run every company on the watchlist and save a snapshot.

Run it yourself with:  python -m research.refresh
GitHub Actions runs it automatically every weekday (see .github/workflows).
"""

import sys

from . import config, report, store


def snapshot_for(ticker: str) -> dict:
    """Today's key numbers for one company."""
    data = report.run(ticker)
    v = data["valuation"] or {}
    row = {
        "ticker": ticker,
        "name": data["profile"]["name"],
        "price": v.get("price"),
        "market_cap": v.get("market_cap"),
        "enterprise_value": v.get("enterprise_value"),
        "price_to_earnings": v.get("price_to_earnings"),
        "ev_to_ebitda": v.get("ev_to_ebitda"),
        "fcf_yield": v.get("fcf_yield"),
        "dcf_value": None,
        "dcf_upside": None,
        "fiscal_year_end": data["statements"].index[-1].date().isoformat(),
        "latest_filing": None,
        "latest_filing_date": None,
    }
    if report.dcf_blocker(data) is None:
        try:
            result = report.run_dcf(data, report.saved_or_default_assumptions(data))
            row["dcf_value"], row["dcf_upside"] = result["value_per_share"], result["upside"]
        except ValueError:
            pass  # assumptions that don't produce a valid DCF: leave it blank
    if data["filings"]:
        row["latest_filing"] = data["filings"][0]["form"]
        row["latest_filing_date"] = data["filings"][0]["filed"]
    return row


def refresh_all(tickers=None) -> tuple:
    """Refresh every watchlist company. Returns (rows saved, {ticker: error})."""
    config.FORCE_REFRESH = True
    rows, errors = [], {}
    try:
        for ticker in tickers or store.get_watchlist():
            try:
                row = snapshot_for(ticker)
                store.save_snapshot(row)
                rows.append(row)
            except Exception as error:  # noqa: BLE001 - keep going with the others
                errors[ticker] = str(error)
    finally:
        config.FORCE_REFRESH = False
    return rows, errors


def main() -> int:
    watchlist = store.get_watchlist()
    if not watchlist:
        print("Watchlist is empty. Follow a company in the app first.")
        return 0
    rows, errors = refresh_all(watchlist)
    for row in rows:
        upside = f"{row['dcf_upside']:+.0%}" if row["dcf_upside"] is not None else "n/a"
        price = f"${row['price']:,.2f}" if row["price"] is not None else "n/a"
        print(f"{row['ticker']:<6} price {price:>10}   DCF vs price {upside:>6}   "
              f"latest filing {row['latest_filing']} {row['latest_filing_date']}")
    for ticker, error in errors.items():
        print(f"{ticker:<6} FAILED: {error}")
    # Fail the run only if nothing at all could be refreshed.
    return 1 if errors and not rows else 0


if __name__ == "__main__":
    sys.exit(main())
