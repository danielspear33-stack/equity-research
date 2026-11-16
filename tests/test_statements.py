from research.statements import build_annual_statements


def fact(tag_rows):
    return {"units": {"USD": tag_rows}}


def year(end, val, filed, start=None, form="10-K"):
    row = {"end": end, "val": val, "filed": filed, "form": form}
    if start:
        row["start"] = start
    return row


FACTS = {
    "facts": {
        "us-gaap": {
            "Revenues": fact(
                [
                    year("2023-12-31", 100, "2024-02-01", start="2023-01-01"),
                    # 2023 restated in the following year's report: the newer filing wins.
                    year("2023-12-31", 110, "2025-02-01", start="2023-01-01"),
                    year("2024-12-31", 150, "2025-02-01", start="2024-01-01"),
                    # A single quarter reported inside the 10-K must be ignored.
                    year("2024-12-31", 40, "2025-02-01", start="2024-10-01"),
                    # Quarterly reports must be ignored.
                    year("2024-12-31", 999, "2025-02-01", start="2024-01-01", form="10-Q"),
                ]
            ),
            "CostOfRevenue": fact([year("2024-12-31", 90, "2025-02-01", start="2024-01-01")]),
            "NetIncomeLoss": fact([year("2024-12-31", 20, "2025-02-01", start="2024-01-01")]),
            "Depreciation": fact([year("2024-12-31", 8, "2025-02-01", start="2024-01-01")]),
            "AmortizationOfIntangibleAssets": fact(
                [year("2024-12-31", 2, "2025-02-01", start="2024-01-01")]
            ),
            "LongTermDebtNoncurrent": fact([year("2024-12-31", 30, "2025-02-01")]),
            "LongTermDebtCurrent": fact([year("2024-12-31", 5, "2025-02-01")]),
            # Combined figure only, for the earlier year.
            "LongTermDebt": fact(
                [year("2023-12-31", 33, "2024-02-01"), year("2024-12-31", 35, "2025-02-01")]
            ),
            "CashAndCashEquivalentsAtCarryingValue": fact([year("2024-12-31", 12, "2025-02-01")]),
            "ShortTermInvestments": fact([year("2024-12-31", 3, "2025-02-01")]),
        }
    }
}


def test_picks_full_year_values_and_latest_restatement():
    table = build_annual_statements(FACTS)
    assert list(table.index.strftime("%Y-%m-%d")) == ["2023-12-31", "2024-12-31"]
    assert table["revenue"].tolist() == [110, 150]


def test_derived_lines():
    latest = build_annual_statements(FACTS).iloc[-1]
    assert latest["gross_profit"] == 150 - 90
    assert latest["d_and_a"] == 8 + 2
    assert latest["total_debt"] == 30 + 5      # pieces summed
    assert latest["cash_and_investments"] == 12 + 3


def test_debt_falls_back_to_combined_figure():
    table = build_annual_statements(FACTS)
    assert table["total_debt"].iloc[0] == 33


def test_company_with_no_annual_reports_gives_empty_table():
    assert build_annual_statements({"facts": {}}).empty


def test_operating_income_rebuilt_when_not_reported():
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": fact([year("2024-12-31", 150, "2025-02-01", start="2024-01-01")]),
                "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": fact(
                    [year("2024-12-31", 40, "2025-02-01", start="2024-01-01")]
                ),
                "InterestExpense": fact([year("2024-12-31", 6, "2025-02-01", start="2024-01-01")]),
            }
        }
    }
    assert build_annual_statements(facts)["operating_income"].iloc[-1] == 46
