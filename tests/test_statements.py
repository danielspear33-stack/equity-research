import pandas as pd

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


def test_total_revenue_wins_over_a_tag_that_covers_only_part_of_it():
    facts = {"facts": {"us-gaap": {
        # Product sales only, and total revenue including partnership income.
        "RevenueFromContractWithCustomerExcludingAssessedTax": fact(
            [year("2024-12-31", 50, "2025-02-01", start="2024-01-01")]),
        "Revenues": fact([year("2024-12-31", 59, "2025-02-01", start="2024-01-01")]),
    }}}
    assert build_annual_statements(facts)["revenue"].iloc[-1] == 59


def test_cash_adds_both_kinds_of_investment_without_double_counting_the_breakdown():
    facts = {"facts": {"us-gaap": {
        "Revenues": fact([year("2024-12-31", 100, "2025-02-01", start="2024-01-01")]),
        "CashAndCashEquivalentsAtCarryingValue": fact([year("2024-12-31", 10, "2025-02-01")]),
        "OtherShortTermInvestments": fact([year("2024-12-31", 4, "2025-02-01")]),
        "MarketableSecurities": fact([year("2024-12-31", 2, "2025-02-01")]),
        # A breakdown of the lines above: must not be added on top.
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent": fact([year("2024-12-31", 3, "2025-02-01")]),
    }}}
    assert build_annual_statements(facts)["cash_and_investments"].iloc[-1] == 16
    only_breakdown = {"facts": {"us-gaap": {k: v for k, v in facts["facts"]["us-gaap"].items()
                                            if k not in ("OtherShortTermInvestments", "MarketableSecurities")}}}
    assert build_annual_statements(only_breakdown)["cash_and_investments"].iloc[-1] == 13


def test_an_implausible_worked_out_gross_profit_is_left_blank():
    def company(cost):
        return {"facts": {"us-gaap": {
            "Revenues": fact([year("2024-12-31", 100, "2025-02-01", start="2024-01-01")]),
            "CostOfRevenue": fact([year("2024-12-31", cost, "2025-02-01", start="2024-01-01")]),
        }}}
    assert build_annual_statements(company(60))["gross_profit"].iloc[-1] == 40
    # A "cost" of 5 on sales of 100 means most costs are tagged somewhere else.
    assert pd.isna(build_annual_statements(company(5))["gross_profit"].iloc[-1])


def test_outside_owners_share_is_taken_off_equity_when_only_the_total_is_tagged():
    facts = {"facts": {"us-gaap": {
        "Revenues": fact([year("2024-12-31", 100, "2025-02-01", start="2024-01-01")]),
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": fact(
            [year("2024-12-31", 100, "2025-02-01")]),
        "MinorityInterest": fact([year("2024-12-31", 6, "2025-02-01")]),
    }}}
    assert build_annual_statements(facts)["equity"].iloc[-1] == 94


def _debt_company(**tags):
    facts = {"Revenues": fact([year("2024-12-31", 100, "2025-02-01", start="2024-01-01")])}
    facts.update({tag: fact([year("2024-12-31", value, "2025-02-01")]) for tag, value in tags.items()})
    return build_annual_statements({"facts": {"us-gaap": facts}})["total_debt"].iloc[-1]


def test_debt_uses_the_larger_of_two_tags_for_the_same_piece():
    # The plain "current" tag is left at zero and the real figure is under the other.
    assert _debt_company(LongTermDebtAndCapitalLeaseObligations=38, LongTermDebtCurrent=0,
                         LongTermDebtAndCapitalLeaseObligationsCurrent=11) == 49


def test_debt_note_settles_whether_the_combined_tag_includes_the_current_part():
    # Used for the long-term part only: the note's total says to add the current part.
    assert _debt_company(LongTermDebt=55, DebtCurrent=23, DebtInstrumentCarryingAmount=79) == 78
    # Used as intended, already including the current part: don't add it again.
    assert _debt_company(LongTermDebt=78, DebtCurrent=10, DebtInstrumentCarryingAmount=78) == 78
    # No note to go on: take the tag at its word.
    assert _debt_company(LongTermDebt=55, DebtCurrent=23) == 55
