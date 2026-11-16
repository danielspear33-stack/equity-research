import pandas as pd
import pytest

from research import quarterly
from research.statements import adjust_for_splits, build_annual_statements


def period(start, end, val, filed, form="10-Q"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form}


def point(end, val, filed, form="10-Q"):
    return {"end": end, "val": val, "filed": filed, "form": form}


# A made-up company with a December year end. Revenue is reported the way real
# filings do it: quarterly reports give the quarter and the year to date, and
# the annual report gives only the full year, so the fourth quarter is missing.
REVENUE = [
    period("2024-01-01", "2024-03-31", 100, "2024-05-01"),
    period("2024-04-01", "2024-06-30", 110, "2024-08-01"),
    period("2024-01-01", "2024-06-30", 210, "2024-08-01"),
    period("2024-01-01", "2024-09-30", 330, "2024-11-01"),     # nine months: Q3 is 120
    period("2024-01-01", "2024-12-31", 460, "2025-02-01", "10-K"),  # full year: Q4 is 130
    period("2025-01-01", "2025-03-31", 150, "2025-05-01"),
    period("2025-01-01", "2025-06-30", 310, "2025-08-01"),     # six months: Q2 is 160
]
FACTS = {"facts": {"us-gaap": {
    "Revenues": {"units": {"USD": REVENUE}},
    "NetIncomeLoss": {"units": {"USD": [
        period("2024-01-01", "2024-12-31", 46, "2025-02-01", "10-K"),
        # Reported directly as a trailing year, as some companies do.
        period("2024-07-01", "2025-06-30", 70, "2025-08-01"),
    ]}},
    "StockholdersEquity": {"units": {"USD": [
        point("2024-12-31", 500, "2025-02-01", "10-K"), point("2025-06-30", 540, "2025-08-01"),
    ]}},
    "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [
        period("2024-01-01", "2024-12-31", 100, "2025-02-01", "10-K"),
        period("2025-04-01", "2025-06-30", 98, "2025-08-01"),
    ]}},
}}}


def test_single_quarters_are_found_by_subtraction():
    quarters = quarterly.single_quarters(quarterly._periods(FACTS, ["Revenues"]))
    assert quarters["2024-06-30"] == 110   # reported directly
    assert quarters["2024-09-30"] == 120   # nine months minus six months
    assert quarters["2024-12-31"] == 130   # full year minus nine months
    assert quarters["2025-06-30"] == 160


def test_trailing_twelve_months_adds_the_last_four_quarters():
    periods = quarterly._periods(FACTS, ["Revenues"])
    # Q3 2024 + Q4 2024 + Q1 2025 + Q2 2025.
    assert quarterly.trailing_twelve_months(periods, "2025-06-30") == 120 + 130 + 150 + 160
    # Only three quarters are known up to this date, so no total can be built.
    assert quarterly.trailing_twelve_months(periods, "2024-09-30") is None


def test_latest_uses_the_newest_quarter_and_balance_sheet():
    annual = build_annual_statements(FACTS)
    latest = quarterly.build_latest(FACTS, annual)
    assert latest["is_ttm"] and latest["as_of"] == pd.Timestamp("2025-06-30")
    row = latest["statements"]
    assert row["revenue"] == 560
    assert row["net_income"] == 70          # the directly reported trailing year
    assert row["equity"] == 540             # balance sheet at the latest quarter end
    assert row["diluted_shares"] == 98      # the latest quarter's count, not a sum


def test_latest_is_the_fiscal_year_when_nothing_newer_is_filed():
    only_annual = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [REVENUE[4]]}}}}}
    annual = build_annual_statements(only_annual)
    latest = quarterly.build_latest(only_annual, annual)
    assert not latest["is_ttm"] and latest["statements"]["revenue"] == 460


def test_quarter_table_compares_with_a_year_earlier():
    table = quarterly.build_quarters(FACTS)
    assert table.loc["2025-03-31", "revenue_growth"] == pytest.approx(150 / 100 - 1)
    assert table.loc["2025-06-30", "revenue_growth"] == pytest.approx(160 / 110 - 1)


def test_share_counts_before_a_split_are_rescaled():
    index = pd.to_datetime(["2020-12-31", "2021-12-31", "2022-12-31", "2023-12-31"])
    table = pd.DataFrame({
        "diluted_shares": [50.0, 51.0, 1010.0, 1000.0],   # 20-for-1 split during 2022
        "eps_diluted": [40.0, 60.0, 2.0, 3.0],
        "dividends_per_share": [float("nan")] * 4,
    }, index=index)
    adjusted = adjust_for_splits(table)
    assert adjusted["diluted_shares"].tolist() == [1000.0, 1020.0, 1010.0, 1000.0]
    assert adjusted["eps_diluted"].tolist() == [2.0, 3.0, 2.0, 3.0]
