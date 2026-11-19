"""Checks this tool's figures against an independent source.

The app builds its numbers by picking tagged values out of SEC filings. That
matching can go wrong, so this script compares the result, company by company
and line by line, with the figures Yahoo Finance publishes (which come from a
separate commercial data provider). Agreement between two independent routes
to the same number is good evidence that both are right.

Run it with:  python -m tools.validate
It prints a summary and rewrites docs/VALIDATION.md.
"""

import json
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from research import edgar, statements
from research.cache import GENERIC_CLIENT_NAME

COMPANIES = ["AAPL", "MSFT", "GOOGL", "NVDA", "KO", "COST", "XOM", "TSLA", "HPQ", "DPZ",
             "UNH", "CAT", "PFE", "DIS", "JPM"]
YEARS_TO_CHECK = 3
TOLERANCE = 0.01   # differences under 1% count as agreeing

# Our name for each line, and Yahoo's. These lines mean the same thing in both
# sources, so a gap here is an error in one of them.
SAME_MEANING = [
    ("revenue", "TotalRevenue"),
    ("net_income", "NetIncome"),
    ("cash_from_operations", "OperatingCashFlow"),
    ("cash_and_investments", "CashCashEquivalentsAndShortTermInvestments"),
    ("equity", "StockholdersEquity"),
    ("diluted_shares", "DilutedAverageShares"),
    ("total_debt", "DebtExcludingLeases"),
]
# These are defined differently on purpose, so gaps are expected. This tool
# shows operating income as the company reports it, including one-off charges
# that Yahoo strips out; Yahoo's capital expenditure includes equipment bought
# to lease to customers; and gross profit is not a line every company reports.
DIFFERENT_MEANING = [
    ("operating_income", "OperatingIncome"),
    ("gross_profit", "GrossProfit"),
    ("capex", "CapitalExpenditure"),
]
# For banks and insurers only these lines are comparable.
FINANCIAL_LINES = {"net_income", "equity", "diluted_shares"}

YAHOO_TYPES = ["TotalRevenue", "GrossProfit", "OperatingIncome", "NetIncome", "OperatingCashFlow",
               "CapitalExpenditure", "TotalDebt", "CapitalLeaseObligations",
               "CashCashEquivalentsAndShortTermInvestments", "StockholdersEquity",
               "DilutedAverageShares"]
LABELS = {"revenue": "Revenue", "gross_profit": "Gross profit", "operating_income": "Operating income",
          "net_income": "Net income", "cash_from_operations": "Cash from operations",
          "capex": "Capital expenditure", "total_debt": "Total debt, leases excluded",
          "cash_and_investments": "Cash and short-term investments",
          "equity": "Shareholders' equity", "diluted_shares": "Diluted shares"}

# Written after reading the disagreements from the run of 19 November 2026.
# Update these when a later run changes the list.
REVIEW_NOTES = [
    "- **Nvidia, cash, latest year:** this tool is too low. Nvidia changed how it tags its "
    "marketable securities and the new tag isn't one the tool reads, so about $52B of "
    "investments is missing from its cash for that year. Not yet fixed.",
    "- **Caterpillar, debt:** this tool is too low. The part of its long-term debt due within "
    "a year is filed under a tag the tool doesn't read. Not yet fixed.",
    "- **Alphabet, debt:** this tool is higher because it counts commercial paper and the "
    "part of long-term debt due within a year, which Yahoo's figure leaves out.",
    "- **Exxon, revenue and debt:** this tool's revenue is Exxon's \"total revenues and other "
    "income\", about 3% above the sales figure Yahoo uses. Its debt is higher because Exxon's "
    "long-term debt tag includes finance leases, which can't be separated out.",
    "- **Tesla, diluted shares:** the two sources disagree in both directions and the cause "
    "hasn't been established.",
    "- **Costco and Pfizer, debt:** gaps of 1-2%, from small items one source counts as debt "
    "and the other doesn't.",
    "",
    "The first run of this check found four errors in how the tool read filings, all since "
    "fixed: revenue that left out partnership income (Pfizer), cash that missed a second line "
    "of investments (Coca-Cola, Pfizer), a made-up gross profit where costs were only partly "
    "tagged (UnitedHealth, Caterpillar), and equity that included outside owners' share "
    "(UnitedHealth). It also led to two fixes to how debt is added up (Domino's, Tesla).",
]

URL = ("https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{ticker}"
       "?type={types}&period1=1400000000&period2=2000000000")
SAVED = Path(__file__).resolve().parent.parent / ".cache"


def yahoo_annual(ticker: str) -> pd.DataFrame:
    """Yahoo's annual figures: one row per fiscal year end, one column per line."""
    saved = SAVED / f"validate_{ticker}.json"
    if saved.exists() and time.time() - saved.stat().st_mtime < 24 * 3600:
        payload = json.loads(saved.read_text())
    else:
        types = ",".join(f"annual{name}" for name in YAHOO_TYPES)
        for attempt in range(4):
            response = requests.get(URL.format(ticker=ticker, types=types),
                                    headers={"User-Agent": GENERIC_CLIENT_NAME}, timeout=30)
            if response.status_code != 429:
                break
            time.sleep(20 * (attempt + 1))   # asked to slow down: wait, then try again
        response.raise_for_status()
        payload = response.json()
        SAVED.mkdir(exist_ok=True)
        saved.write_text(json.dumps(payload))
    columns = {}
    for series in payload["timeseries"]["result"]:
        name = series["meta"]["type"][0]
        columns[name.removeprefix("annual")] = {
            point["asOfDate"]: point["reportedValue"]["raw"] for point in series.get(name, []) if point
        }
    table = pd.DataFrame(columns)
    table.index = pd.to_datetime(table.index)
    table = table.sort_index()
    # Yahoo counts lease obligations as debt and this tool mostly does not, so
    # compare against Yahoo's debt with its leases taken out.
    if "TotalDebt" in table:
        leases = table["CapitalLeaseObligations"].fillna(0) if "CapitalLeaseObligations" in table else 0
        table["DebtExcludingLeases"] = table["TotalDebt"] - leases
    if "CapitalExpenditure" in table:
        table["CapitalExpenditure"] = -table["CapitalExpenditure"]   # Yahoo shows spending as negative
    return table


def compare(ticker: str) -> list:
    """Every (company, year, line) where both sources have a figure."""
    cik = edgar.lookup_cik(ticker)
    financial = edgar.get_profile(cik)["is_financial"]
    ours = statements.build_annual_statements(edgar.get_company_facts(cik))
    theirs = yahoo_annual(ticker)
    rows = []
    for year_end in ours.index[-YEARS_TO_CHECK:]:
        # Fiscal year ends can be recorded a few days apart by the two sources.
        near = theirs.index[abs(theirs.index - year_end) <= pd.Timedelta(days=7)]
        if near.empty:
            continue
        for same, lines in ((True, SAME_MEANING), (False, DIFFERENT_MEANING)):
            for line, yahoo_name in lines:
                if financial and line not in FINANCIAL_LINES:
                    continue
                mine = ours.loc[year_end, line]
                other = theirs.loc[near[0]].get(yahoo_name)
                if pd.isna(mine) or other is None or pd.isna(other) or other == 0:
                    continue
                rows.append({"ticker": ticker, "year_end": year_end.date(), "line": line,
                             "same_meaning": same, "ours": mine, "yahoo": other,
                             "difference": mine / other - 1})
    return rows


def _summary_table(table: pd.DataFrame) -> list:
    by_line = table.groupby("line", sort=False).agg(
        compared=("agrees", "size"), agree=("agrees", "sum"),
        largest_gap=("difference", lambda d: d.abs().max()))
    out = ["| Line | Figures compared | Agree within 1% | Largest gap |", "| --- | ---: | ---: | ---: |"]
    for line, row in by_line.iterrows():
        out.append(f"| {LABELS[line]} | {int(row['compared'])} | {int(row['agree'])} | {row['largest_gap']:.1%} |")
    return out


def _gap_table(misses: pd.DataFrame) -> list:
    if misses.empty:
        return ["None."]
    out = ["| Company | Fiscal year end | Line | This tool | Yahoo Finance | Gap |",
           "| --- | --- | --- | ---: | ---: | ---: |"]
    for _, row in misses.sort_values("difference", key=abs, ascending=False).iterrows():
        out.append(f"| {row['ticker']} | {row['year_end']} | {LABELS[row['line']]} | "
                   f"{row['ours'] / 1e9:,.2f}B | {row['yahoo'] / 1e9:,.2f}B | {row['difference']:+.1%} |")
    return out


def main() -> int:
    rows, failed = [], {}
    for ticker in COMPANIES:
        try:
            rows += compare(ticker)
        except Exception as error:  # noqa: BLE001 - report it and carry on
            failed[ticker] = str(error).split(" for url")[0]
        time.sleep(2)   # be polite to both servers
    if not rows:
        print("Nothing could be compared:", failed)
        return 1

    table = pd.DataFrame(rows)
    table["agrees"] = table["difference"].abs() <= TOLERANCE
    same, different = table[table["same_meaning"]], table[~table["same_meaning"]]
    total, agreeing = len(same), int(same["agrees"].sum())
    out = [
        "# Validation: this tool's figures against an independent source",
        "",
        f"Last run {date.today():%d %B %Y} with `python -m tools.validate`.",
        "",
        "The app builds its numbers by picking tagged values out of SEC filings. To check that "
        "matching, this compares them with the annual figures published by Yahoo Finance, which "
        "come from a separate commercial data provider. Two independent routes arriving at the "
        "same number is good evidence that both are right.",
        "",
        f"Compared: {table['ticker'].nunique()} companies, their last {YEARS_TO_CHECK} fiscal years.",
        "",
        "## Lines that mean the same thing in both sources",
        "",
        f"**{agreeing} of {total} figures ({agreeing / total:.0%}) agree to within {TOLERANCE:.0%}.**",
        "",
        *_summary_table(same),
        "",
        "### Every disagreement",
        "",
        *_gap_table(same[~same["agrees"]]),
        "",
        "### What the remaining disagreements are",
        "",
        *REVIEW_NOTES,
        "",
        "## Lines the two sources define differently",
        "",
        "Gaps here are expected and are not errors. This tool shows operating income as the "
        "company reports it, including one-off charges such as restructuring that Yahoo takes "
        "out, and where a company reports no operating income it uses profit before tax plus "
        "interest. Yahoo's capital expenditure includes equipment bought to lease to customers. "
        "Gross profit is worked out by each source for companies that don't report it.",
        "",
        *_summary_table(different),
        "",
        "### Gaps over 10%",
        "",
        *_gap_table(different[different["difference"].abs() > 0.10]),
    ]
    if failed:
        out += ["", "## Not compared", ""] + [f"- {ticker}: {why}" for ticker, why in failed.items()]
    text = "\n".join(out) + "\n"
    target = Path(__file__).resolve().parent.parent / "docs" / "VALIDATION.md"
    target.parent.mkdir(exist_ok=True)
    target.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
