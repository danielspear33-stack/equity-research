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
from .prices import get_long_price_history as long_prices

PUBLICATION_LAG_DAYS = 90
HOLDING_DAYS = 365
GROUPS = ["Lowest fifth", "Second", "Middle", "Fourth", "Highest fifth"]

# The measures tested. Each is something this tool shows for a company; the
# question is whether a high reading was followed by a better year.
SIGNALS = {
    "dcf_gap": "DCF value against price",
    "fcf_yield": "Free cash flow yield",
    "earnings_yield": "Earnings yield (profit / market value)",
    "return_on_capital": "Return on invested capital",
    "operating_margin": "Operating margin",
    "revenue_growth": "Sales growth",
    "momentum": "Share price change over the year before",
}


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
        market_cap = price * latest["diluted_shares"]
        year_metrics = known_metrics.iloc[-1]
        year_before = _price_on(prices, entry - pd.Timedelta(days=365))

        def per_market_cap(amount):
            return amount / market_cap if pd.notna(amount) and market_cap > 0 else None

        stock_return = later_price / price - 1
        market_return = index_later / index_then - 1
        rows.append({
            "ticker": ticker, "fiscal_year_end": year_end.date().isoformat(),
            "entry_date": entry.date().isoformat(), "entry_year": entry.year,
            "price": price, "dcf_value": value, "dcf_gap": value / price - 1,
            "fcf_yield": per_market_cap(year_metrics["free_cash_flow"]),
            "earnings_yield": per_market_cap(latest["net_income"]),
            "return_on_capital": year_metrics["return_on_invested_capital"],
            "operating_margin": year_metrics["operating_margin"],
            "revenue_growth": year_metrics["revenue_growth"],
            "momentum": price / year_before - 1 if year_before else None,
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


def add_groups(table: pd.DataFrame, signal: str = "dcf_gap") -> pd.DataFrame:
    """Rank each year's companies by `signal` and split them into five equal groups."""
    table = table.dropna(subset=[signal]).copy()
    rank = table.groupby("entry_year")[signal].rank(pct=True)
    table["group"] = pd.cut(rank, [0, 0.2, 0.4, 0.6, 0.8, 1.0], labels=GROUPS, include_lowest=True)
    return table


def summarise(table: pd.DataFrame, signal: str = "dcf_gap") -> dict:
    """The headline numbers for one signal: results by group, by year, and how strong the link is."""
    table = add_groups(table, signal)
    by_group = table.groupby("group", observed=True).agg(
        observations=("excess_return", "size"),
        typical_reading=(signal, "median"),
        average_return=("stock_return", "mean"),
        average_excess_return=("excess_return", "mean"),
        beat_the_market=("excess_return", lambda x: (x > 0).mean()),
    ).reindex(GROUPS)

    high = table[table["group"].isin(GROUPS[3:])]
    low = table[table["group"].isin(GROUPS[:2])]
    by_year = pd.DataFrame({
        "companies": table.groupby("entry_year").size(),
        "high_excess": high.groupby("entry_year")["excess_return"].mean(),
        "low_excess": low.groupby("entry_year")["excess_return"].mean(),
    })
    by_year["high_minus_low"] = by_year["high_excess"] - by_year["low_excess"]

    # Rank correlation within each year, averaged: +1 would mean the signal
    # ordered the companies perfectly, 0 that it told you nothing.
    yearly = table.groupby("entry_year").apply(
        lambda year: year[signal].rank().corr(year["excess_return"].rank()),
        include_groups=False,
    ).dropna()
    spread = (by_group.loc[GROUPS[-1], "average_excess_return"]
              - by_group.loc[GROUPS[0], "average_excess_return"])
    return {
        "signal": signal,
        "by_group": by_group,
        "by_year": by_year,
        "spread": float(spread),
        "rank_correlation": float(yearly.mean()) if not yearly.empty else float("nan"),
        "years_high_won": int((by_year["high_minus_low"] > 0).sum()),
        "years": int(by_year["high_minus_low"].notna().sum()),
        "observations": len(table),
        "companies": table["ticker"].nunique(),
        "first_year": int(table["entry_year"].min()),
        "last_year": int(table["entry_year"].max()),
    }


def compare_signals(table: pd.DataFrame) -> pd.DataFrame:
    """One row per signal: how the highest fifth did against the lowest, best first."""
    rows = []
    for signal, name in SIGNALS.items():
        if signal not in table.columns or table[signal].notna().sum() < 50:
            continue
        summary = summarise(table, signal)
        rows.append({"signal": signal, "name": name, "spread": summary["spread"],
                     "years_high_won": summary["years_high_won"], "years": summary["years"],
                     "rank_correlation": summary["rank_correlation"],
                     "verdict": grade(summary)})
    return pd.DataFrame(rows).sort_values("spread", ascending=False).reset_index(drop=True)


def grade(summary: dict) -> str:
    """ "Worked", "Backwards" or "No signal", from the size and consistency of the gap."""
    spread, won, years = summary["spread"], summary["years_high_won"], summary["years"]
    if abs(spread) < 0.03:
        return "No signal"
    if spread > 0:
        return "Worked" if won * 2 > years else "Inconsistent"
    return "Backwards" if won * 2 < years else "Inconsistent"


def verdict(summary: dict) -> str:
    """One honest sentence on what the test found for a signal."""
    name = SIGNALS[summary["signal"]]
    name = name if name.startswith("DCF") else name[0].lower() + name[1:]
    spread, won, years = summary["spread"], summary["years_high_won"], summary["years"]
    detail = (f"companies in the highest fifth for {name} {'beat' if spread > 0 else 'lagged'} "
              f"those in the lowest fifth by {abs(spread):.1%} a year on average, and the higher "
              f"half came out ahead in {won} of {years} years")
    outcome = grade(summary)
    if outcome == "No signal":
        return f"No useful signal: {detail}."
    if outcome == "Worked":
        return (f"This one held up: {detail}. Suggestive, not proven; see the limitations below.")
    if outcome == "Backwards":
        if summary["signal"] == "dcf_gap":
            return (f"The signal pointed the wrong way: {detail}. Shares the default DCF called "
                    "cheap did worse, which is what happens when a model built on past averages "
                    "meets companies that keep growing faster than their history.")
        return f"The signal pointed the wrong way: {detail}."
    return f"Inconsistent: {detail}. Not steady enough to rely on."


def results_file():
    return config.USER_DATA_DIR / "backtest.csv"


def save(table: pd.DataFrame) -> None:
    config.USER_DATA_DIR.mkdir(exist_ok=True)
    table.to_csv(results_file(), index=False)


def load_saved():
    """The last saved run, or None."""
    return pd.read_csv(results_file()) if results_file().exists() else None
