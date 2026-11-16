"""Comparable-company analysis ("comps").

Instead of forecasting cash flows, ask what investors currently pay for
similar businesses. If peers trade at 20x EBITDA, a company with $10B of
EBITDA is "worth" about $200B on that yardstick. It is a cross-check on the
DCF, and it is only as good as the choice of peers.
"""

import json
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import config

MULTIPLES = {
    "ev_to_ebitda": "EV / EBITDA",
    "ev_to_sales": "EV / Sales",
    "price_to_earnings": "P/E",
}


def suggest_peers(ticker: str, limit: int = 6) -> tuple:
    """Suggest peers as (group name, tickers).

    First choice is a hand-picked group. Failing that, fall back to companies
    in the same official industry code, which is a much cruder match.
    """
    ticker = ticker.upper()
    groups = json.loads(config.PEER_GROUPS_FILE.read_text())
    for name, members in groups.items():
        if ticker in members:
            return name, [m for m in members if m != ticker][:limit]

    sic = json.loads(config.SEED_SIC_FILE.read_text())
    code = sic.get(ticker)
    if code:
        same = [t for t, c in sic.items() if c == code and t != ticker]
        if same:
            return f"Same industry code ({code})", same[:limit]
    return "No suggestion", []


def build_peer_table(peer_tickers: list, run_report) -> tuple:
    """Run the full pipeline for each peer. Returns (table, {ticker: error})."""
    rows, errors = {}, {}

    def load(ticker):
        try:
            return ticker, run_report(ticker), None
        except Exception as error:  # noqa: BLE001 - one bad peer shouldn't sink the rest
            return ticker, None, str(error)

    # A few at a time, to stay well inside the SEC's request limits.
    with ThreadPoolExecutor(max_workers=3) as pool:
        for ticker, report, error in pool.map(load, peer_tickers):
            if error or report["valuation"] is None:
                errors[ticker] = error or report["price_error"] or "no price data"
                continue
            v, m = report["valuation"], report["latest"]["metrics"]
            rows[ticker] = {
                "name": report["profile"]["name"],
                "market_cap": v["market_cap"],
                "enterprise_value": v["enterprise_value"],
                "ev_to_ebitda": v["ev_to_ebitda"],
                "ev_to_sales": v["ev_to_sales"],
                "price_to_earnings": v["price_to_earnings"],
                "revenue_growth": m["revenue_growth"],
                "operating_margin": m["operating_margin"],
                "return_on_invested_capital": m["return_on_invested_capital"],
            }
    table = pd.DataFrame.from_dict(rows, orient="index")
    return table, errors


def summarise_multiples(peer_table: pd.DataFrame) -> pd.DataFrame:
    """Low (25th percentile), median and high (75th percentile) of each multiple."""
    summary = {}
    for column in MULTIPLES:
        values = pd.to_numeric(peer_table.get(column), errors="coerce").dropna()
        if len(values) >= 2:
            summary[column] = {
                "low": values.quantile(0.25),
                "median": values.median(),
                "high": values.quantile(0.75),
                "peers_used": len(values),
            }
    return pd.DataFrame(summary).T


def implied_values(summary: pd.DataFrame, statements, metrics) -> pd.DataFrame:
    """What the target's shares would be worth at its peers' multiples."""
    s, m = statements.iloc[-1], metrics.iloc[-1]
    shares, net_debt = s["diluted_shares"], m["net_debt"]

    # Each multiple applies to a different figure. EV-based multiples value the
    # whole business, so net debt comes off to get to the shareholders' part.
    bases = {
        "ev_to_ebitda": (m["ebitda"], True),
        "ev_to_sales": (s["revenue"], True),
        "price_to_earnings": (s["net_income"], False),
    }
    rows = {}
    for multiple, (base, is_enterprise) in bases.items():
        if multiple not in summary.index or pd.isna(base) or base <= 0:
            continue
        row = {}
        for point in ("low", "median", "high"):
            total = summary.loc[multiple, point] * base
            equity = total - net_debt if is_enterprise else total
            row[point] = equity / shares
        rows[multiple] = row
    return pd.DataFrame(rows).T
