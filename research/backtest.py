"""Would this tool's DCF have told you anything useful in the past?

For each company and each past fiscal year, the model is run using only the
annual reports that existed at the time, with its mechanical default
assumptions. That gives a "DCF value versus price" gap as it would have looked
then. The test is whether shares the model called cheap went on to beat the
shares it called expensive over the following year.

What keeps this honest:
  * Entry is 90 days after the fiscal year ends, when the results were public.
  * The discount rate uses the Treasury yield of that day, and a beta of 1 for
    every company (today's beta would be hindsight).
  * Companies are ranked against each other within the same year, so a good or
    bad year for the whole market doesn't decide the result.

What it can't fix, and the page says so:
  * The companies are today's large, well-known ones. Those that shrank or
    went bust in the meantime aren't in the list (survivorship bias).
  * Figures a company later restated are used as restated.
  * Returns are price changes; dividends are left out for shares and the index.
"""

import json
from datetime import date

import pandas as pd

from . import config, dcf, edgar, metrics, statements
from .cache import fetch_json

LONG_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=15y&interval=1d"
PUBLICATION_LAG_DAYS = 90
HOLDING_DAYS = 365
GROUPS = ["Most expensive", "Expensive", "Middle", "Cheap", "Cheapest"]


def long_prices(ticker: str) -> pd.Series:
    """Fifteen years of daily closing prices."""
    ticker = ticker.strip().upper().replace(".", "-")
    name = "prices_long_" + ticker.replace("^", "index_")
    raw = fetch_json(LONG_CHART_URL.format(ticker=ticker.replace("^", "%5E")), name,
                     config.FILINGS_MAX_AGE)
    result = raw["chart"]["result"][0]
    dates = pd.to_datetime(result["timestamp"], unit="s").normalize()
    return pd.Series(result["indicators"]["quote"][0]["close"], index=dates).dropna()


def universe() -> list:
    """The companies tested: everything in the built-in peer groups."""
    groups = json.loads(config.PEER_GROUPS_FILE.read_text())
    return sorted({ticker for tickers in groups.values() for ticker in tickers})


def _price_on(prices: pd.Series, day: pd.Timestamp):
    """The first closing price on or after `day`, or None if within a week there is none."""
    later = prices.loc[day:day + pd.Timedelta(days=7)]
    return float(later.iloc[0]) if not later.empty else None


def observations(ticker: str, annual: pd.DataFrame, prices: pd.Series, market: pd.Series,
                 yields: pd.Series, today: pd.Timestamp = None) -> list:
    """One row per past fiscal year for one company: what the model said, and what happened next."""
    today = today or pd.Timestamp(date.today())
    rows = []
    for position in range(3, len(annual) + 1):          # the defaults need three years of history
        known = annual.iloc[:position]
        year_end = known.index[-1]
        entry = year_end + pd.Timedelta(days=PUBLICATION_LAG_DAYS)
        exit_ = entry + pd.Timedelta(days=HOLDING_DAYS)
        if exit_ > today:
            continue
        price, later_price = _price_on(prices, entry), _price_on(prices, exit_)
        index_then, index_later = _price_on(market, entry), _price_on(market, exit_)
        risk_free = _price_on(yields, entry)
        if None in (price, later_price, index_then, index_later, risk_free):
            continue
        latest = known.iloc[-1]
        if pd.isna(latest["revenue"]) or pd.isna(latest["diluted_shares"]) or latest["revenue"] <= 0:
            continue
        try:
            known_metrics = metrics.compute_annual_metrics(known)
            valuation = metrics.compute_valuation(known, known_metrics, price)
            assumptions, _ = dcf.default_assumptions(known, known_metrics, valuation,
                                                     beta=1.0, risk_free=risk_free / 100)
            net_debt = known_metrics["net_debt"].iloc[-1]
            result = dcf.value(latest["revenue"], 0.0 if pd.isna(net_debt) else net_debt,
                               latest["diluted_shares"], assumptions)
        except (ValueError, ZeroDivisionError, KeyError):
            continue
        value = result["value_per_share"]
        if pd.isna(value):
            continue
        stock_return = later_price / price - 1
        market_return = index_later / index_then - 1
        rows.append({
            "ticker": ticker, "fiscal_year_end": year_end.date().isoformat(),
            "entry_date": entry.date().isoformat(), "entry_year": entry.year,
            "price": price, "dcf_value": value, "dcf_gap": value / price - 1,
            "stock_return": stock_return, "market_return": market_return,
            "excess_return": stock_return - market_return,
        })
    return rows


def run(tickers: list = None, progress=None) -> tuple:
    """Run the backtest. Returns (table of observations, {ticker: why it was skipped})."""
    tickers = tickers or universe()
    market, yields = long_prices("^GSPC"), long_prices("^TNX")
    rows, skipped = [], {}
    for done, ticker in enumerate(tickers, start=1):
        if progress:
            progress(done, len(tickers), ticker)
        try:
            cik = edgar.lookup_cik(ticker)
            if edgar.get_profile(cik)["is_financial"]:
                skipped[ticker] = "financial company (no DCF)"
                continue
            annual = statements.build_annual_statements(edgar.get_company_facts(cik))
            found = observations(ticker, annual, long_prices(ticker), market, yields)
            if found:
                rows.extend(found)
            else:
                skipped[ticker] = "not enough history"
        except Exception as error:  # noqa: BLE001 - one bad company shouldn't stop the run
            skipped[ticker] = str(error)[:120]
    return pd.DataFrame(rows), skipped


def add_groups(table: pd.DataFrame) -> pd.DataFrame:
    """Rank each year's companies by DCF gap and split them into five equal groups."""
    table = table.copy()
    rank = table.groupby("entry_year")["dcf_gap"].rank(pct=True)
    table["group"] = pd.cut(rank, [0, 0.2, 0.4, 0.6, 0.8, 1.0], labels=GROUPS, include_lowest=True)
    return table


def summarise(table: pd.DataFrame) -> dict:
    """The headline numbers: results by group, by year, and how strong the link is."""
    table = add_groups(table)
    by_group = table.groupby("group", observed=True).agg(
        observations=("excess_return", "size"),
        typical_dcf_gap=("dcf_gap", "median"),
        average_return=("stock_return", "mean"),
        average_excess_return=("excess_return", "mean"),
        beat_the_market=("excess_return", lambda x: (x > 0).mean()),
    ).reindex(GROUPS)

    cheap = table[table["group"].isin(GROUPS[3:])]
    expensive = table[table["group"].isin(GROUPS[:2])]
    by_year = pd.DataFrame({
        "companies": table.groupby("entry_year").size(),
        "cheap_half_excess": cheap.groupby("entry_year")["excess_return"].mean(),
        "expensive_half_excess": expensive.groupby("entry_year")["excess_return"].mean(),
    })
    by_year["cheap_minus_expensive"] = by_year["cheap_half_excess"] - by_year["expensive_half_excess"]

    # Rank correlation within each year, averaged: +1 would mean the model
    # ordered the companies perfectly, 0 that it told you nothing.
    yearly = table.groupby("entry_year").apply(
        lambda year: year["dcf_gap"].rank().corr(year["excess_return"].rank()),
        include_groups=False,
    ).dropna()
    spread = (by_group.loc["Cheapest", "average_excess_return"]
              - by_group.loc["Most expensive", "average_excess_return"])
    return {
        "by_group": by_group,
        "by_year": by_year,
        "spread": float(spread),
        "rank_correlation": float(yearly.mean()) if not yearly.empty else float("nan"),
        "years_cheap_won": int((by_year["cheap_minus_expensive"] > 0).sum()),
        "years": int(by_year["cheap_minus_expensive"].notna().sum()),
        "observations": len(table),
        "companies": table["ticker"].nunique(),
        "first_year": int(table["entry_year"].min()),
        "last_year": int(table["entry_year"].max()),
    }


def verdict(summary: dict) -> str:
    """One honest sentence on what the test found."""
    spread, correlation = summary["spread"], summary["rank_correlation"]
    won, years = summary["years_cheap_won"], summary["years"]
    detail = (f"the cheapest fifth {'beat' if spread > 0 else 'lagged'} the most expensive fifth "
              f"by {abs(spread):.1%} a year on average, and the cheaper half came out ahead in "
              f"{won} of {years} years")
    if abs(spread) < 0.03:
        return (f"No useful signal: {detail}. On its mechanical default assumptions the DCF gap "
                "did not separate winners from losers.")
    if spread > 0 and correlation > 0 and won * 2 > years:
        return (f"Some signal: {detail}. Treat this as suggestive, not proven; see the "
                "limitations below.")
    if spread < 0:
        return (f"The signal pointed the wrong way: {detail}. Shares the default DCF called "
                "expensive tended to do better, which is what happens when a model built on "
                "past averages meets companies that keep growing faster than their history.")
    return f"Mixed: {detail}. Not consistent enough to rely on."


def results_file():
    return config.USER_DATA_DIR / "backtest.csv"


def save(table: pd.DataFrame) -> None:
    config.USER_DATA_DIR.mkdir(exist_ok=True)
    table.to_csv(results_file(), index=False)


def load_saved():
    """The last saved run, or None."""
    return pd.read_csv(results_file()) if results_file().exists() else None
