"""The most recent picture: single quarters and the trailing twelve months.

Annual reports come out once a year, so by the time you read one it can be
many months old. Quarterly reports (10-Q) fill the gap. From them we build:

  * each single quarter's figures, to see the latest trend
  * the "trailing twelve months" (TTM): the last four quarters added up, which
    is the most up-to-date full-year figure available

Quarterly reports mostly give year-to-date totals (six months, nine months)
rather than single quarters, and never give the fourth quarter on its own, so
single quarters are worked out by subtraction.
"""

from datetime import date

import pandas as pd

from .statements import BALANCE_TAGS, FLOW_TAGS, add_derived_lines

FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A"}

QUARTER_LINES = ["revenue", "gross_profit", "operating_income", "net_income",
                 "cash_from_operations", "capex"]


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _periods(facts: dict, tags: list) -> dict:
    """{(start, end): value} for the first tag that has each period.

    The same period is repeated in later filings as a comparison, so the most
    recently filed value is kept.
    """
    merged = {}
    for tag in tags:
        entry = facts.get("facts", {}).get("us-gaap", {}).get(tag)
        if not entry:
            continue
        latest = {}
        for rows in entry["units"].values():
            for row in rows:
                if row.get("form") not in FORMS or "start" not in row:
                    continue
                key = (row["start"], row["end"])
                if key not in latest or row["filed"] > latest[key][0]:
                    latest[key] = (row["filed"], row["val"])
        for key, (_, value) in latest.items():
            merged.setdefault(key, value)
    return merged


def _balances(facts: dict, tags: list) -> dict:
    """{date: value} for balance sheet figures, which are measured on one day."""
    merged = {}
    for tag in tags:
        entry = facts.get("facts", {}).get("us-gaap", {}).get(tag)
        if not entry:
            continue
        latest = {}
        for rows in entry["units"].values():
            for row in rows:
                if row.get("form") not in FORMS or "start" in row:
                    continue
                end = row["end"]
                if end not in latest or row["filed"] > latest[end][0]:
                    latest[end] = (row["filed"], row["val"])
        for end, (_, value) in latest.items():
            merged.setdefault(end, value)
    return merged


def single_quarters(periods: dict, additive: bool = True) -> dict:
    """{quarter end: value} for every quarter that can be worked out.

    A quarter is either reported directly (a period of about 90 days) or, for
    dollar figures, found by subtraction: nine months minus six months gives
    the third quarter, and the full year minus nine months gives the fourth.
    """
    quarters = {end: value for (start, end), value in periods.items()
                if 80 <= _days(start, end) <= 100}
    if not additive:
        return quarters

    by_start = {}
    for (start, end), value in periods.items():
        by_start.setdefault(start, []).append((end, value))
    for runs in by_start.values():
        runs.sort()
        for (shorter_end, shorter), (longer_end, longer) in zip(runs, runs[1:]):
            if 80 <= _days(shorter_end, longer_end) <= 100:
                quarters.setdefault(longer_end, longer - shorter)
    return quarters


def trailing_twelve_months(periods: dict, as_of: str):
    """The total for the twelve months ending on `as_of`, or None if it can't be built."""
    # Some companies report the trailing year directly.
    for (start, end), value in periods.items():
        if end == as_of and 350 <= _days(start, end) <= 380:
            return value

    # Otherwise add up the last four quarters, checking none is missing.
    quarters = single_quarters(periods)
    ends = sorted((end for end in quarters if end <= as_of), reverse=True)[:4]
    if len(ends) < 4 or ends[0] != as_of:
        return None
    if any(not 80 <= _days(later_start, later) <= 100 for later_start, later in zip(ends[1:], ends)):
        return None
    return sum(quarters[end] for end in ends)


def _a_year_before(periods: dict, as_of: str):
    """The period end closest to one year before `as_of` (fiscal quarters shift by a few days)."""
    target = date.fromisoformat(as_of).replace(year=date.fromisoformat(as_of).year - 1)
    ends = {end for _, end in periods}
    near = [end for end in ends if abs((date.fromisoformat(end) - target).days) <= 10]
    return min(near, key=lambda end: abs((date.fromisoformat(end) - target).days)) if near else None


def build_latest(facts: dict, annual: pd.DataFrame) -> dict:
    """The most recent twelve months of results and the latest balance sheet.

    Returns a dict with:
      statements  one row of figures, same columns as the annual table
      as_of       the date the figures run to
      is_ttm      True if this is newer than the last annual report
      revenue_growth  growth against the twelve months before, if known

    If no quarterly report has come out since the last annual report (or the
    quarters can't be pieced together), this is just the latest fiscal year.
    """
    fiscal_year = {
        "statements": annual.iloc[-1].copy(),
        "as_of": annual.index[-1],
        "is_ttm": False,
        "revenue_growth": None,
    }
    flows = {name: _periods(facts, tags) for name, tags in FLOW_TAGS.items()}

    # The latest period the company has reported sales or profit for.
    ends = [end for name in ("revenue", "net_income") for _, end in flows[name]]
    if not ends:
        return fiscal_year
    as_of = max(ends)
    if pd.Timestamp(as_of) <= annual.index[-1]:
        return fiscal_year

    row = {}
    for name, periods in flows.items():
        if name == "diluted_shares":
            # Use the share count from the latest quarter, not a sum.
            row[name] = single_quarters(periods, additive=False).get(as_of)
        elif name in ("eps_diluted", "dividends_per_share"):
            # Per-share figures: adding four quarters is a close approximation.
            quarters = single_quarters(periods)
            last_four = sorted((end for end in quarters if end <= as_of), reverse=True)[:4]
            complete = len(last_four) == 4 and last_four[0] == as_of
            row[name] = sum(quarters[end] for end in last_four) if complete else None
        else:
            row[name] = trailing_twelve_months(periods, as_of)
    if row["revenue"] is None and row["net_income"] is None:
        return fiscal_year

    for name, tags in BALANCE_TAGS.items():
        row[name] = _balances(facts, tags).get(as_of)

    table = pd.DataFrame([row], index=[pd.Timestamp(as_of)], dtype="float64")
    table = table.reindex(columns=[c for c in annual.columns if c in table.columns])
    latest = add_derived_lines(table).iloc[0]
    # Anything that couldn't be rebuilt keeps the last annual figure for the
    # share count only; a stale profit figure would be misleading.
    if pd.isna(latest["diluted_shares"]):
        latest["diluted_shares"] = annual["diluted_shares"].iloc[-1]

    growth = None
    year_ago = _a_year_before(flows["revenue"], as_of)
    if year_ago and row["revenue"]:
        earlier = trailing_twelve_months(flows["revenue"], year_ago)
        if earlier and earlier > 0:
            growth = row["revenue"] / earlier - 1

    return {"statements": latest, "as_of": pd.Timestamp(as_of), "is_ttm": True,
            "revenue_growth": growth}


def build_quarters(facts: dict, count: int = 8) -> pd.DataFrame:
    """One row per recent quarter, newest last, with growth against the same quarter a year before."""
    columns = {}
    for name in QUARTER_LINES:
        columns[name] = single_quarters(_periods(facts, FLOW_TAGS[name]))
    # The fourth quarter's earnings per share is the year's minus the first nine
    # months', which is very slightly off when the share count moves.
    columns["eps_diluted"] = single_quarters(_periods(facts, FLOW_TAGS["eps_diluted"]))
    cost = single_quarters(_periods(facts, FLOW_TAGS["cost_of_revenue"]))

    ends = sorted(set(columns["revenue"]) | set(columns["net_income"]))
    if not ends:
        return pd.DataFrame()
    table = pd.DataFrame(columns, index=ends, dtype="float64")
    table["gross_profit"] = table["gross_profit"].fillna(
        table["revenue"] - pd.Series(cost, dtype="float64").reindex(ends)
    )
    table["free_cash_flow"] = table["cash_from_operations"] - table["capex"]
    table["operating_margin"] = table["operating_income"] / table["revenue"]

    # Compare each quarter with the same one a year earlier, which removes seasonality.
    table["revenue_growth"] = table["revenue"].pct_change(4, fill_method=None)
    earlier = table["net_income"].shift(4)
    table["net_income_growth"] = (table["net_income"] / earlier - 1).where(earlier > 0)

    table.index = pd.to_datetime(table.index)
    table.index.name = "quarter_end"
    return table.tail(count)
