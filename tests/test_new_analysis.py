import pandas as pd
import pytest

from research import checks, dcf, financials, insiders, payouts, pricestats


# ---- Bear, base and bull cases ----

def test_scenarios_bracket_the_base_case():
    a = dcf.Assumptions(years=5, growth_start=0.10, growth_end=0.03, ebit_margin=0.20,
                        tax_rate=0.25, da_pct=0.03, capex_pct=0.04, nwc_pct=0.05,
                        wacc=0.09, terminal_growth=0.025)
    cases = dcf.scenarios(1000.0, 100.0, 50.0, a)
    base = dcf.value(1000.0, 100.0, 50.0, a)["value_per_share"]
    assert cases.loc["Base", "value_per_share"] == pytest.approx(base)
    assert cases.loc["Bear", "value_per_share"] < base < cases.loc["Bull", "value_per_share"]
    # Growth moves by 30% of itself (3 points, which beats the 2-point minimum),
    # margin by 15% and the discount rate by one point.
    assert cases.loc["Bear", "growth_start"] == pytest.approx(0.07)
    assert cases.loc["Bull", "ebit_margin"] == pytest.approx(0.23)
    assert cases.loc["Bear", "wacc"] == pytest.approx(0.10)


# ---- Bank valuation ----

def test_bank_earning_exactly_its_cost_of_equity_is_worth_book_value():
    a = financials.Assumptions(roe=0.10, cost_of_equity=0.10, growth=0.03, dividend_growth=0.03)
    assert financials.justified_price_to_book(a) == pytest.approx(1.0)
    better = financials.Assumptions(roe=0.17, cost_of_equity=0.10, growth=0.03, dividend_growth=0.03)
    assert financials.justified_price_to_book(better) == pytest.approx(2.0)


def test_dividend_discount_with_constant_growth_matches_the_textbook_formula():
    # With the same growth throughout, the answer is next year's dividend / (r - g).
    a = financials.Assumptions(roe=0.12, cost_of_equity=0.09, growth=0.04, dividend_growth=0.04)
    assert financials.dividend_discount(2.0, a) == pytest.approx(2.0 * 1.04 / (0.09 - 0.04))


def test_bank_snapshot_by_hand():
    index = pd.to_datetime(["2023-12-31", "2024-12-31"])
    annual = pd.DataFrame({"equity": [900.0, 1100.0]}, index=index)
    annual_metrics = pd.DataFrame({"return_on_equity": [float("nan"), 0.12]}, index=index)
    latest = pd.Series({"equity": 1100.0, "preferred_equity": 100.0, "goodwill": 150.0,
                        "intangibles": 50.0, "net_income": 120.0, "diluted_shares": 10.0,
                        "dividends_paid": 30.0, "buybacks": 60.0}, name=index[-1])
    snap = financials.snapshot(latest, annual, annual_metrics, price=150.0)
    assert snap["book_value_per_share"] == pytest.approx(100.0)        # (1100 - 100) / 10
    assert snap["tangible_book_per_share"] == pytest.approx(80.0)      # less 200 of intangibles
    assert snap["price_to_book"] == pytest.approx(1.5)
    assert snap["return_on_equity"] == pytest.approx(120 / 1000)       # on average equity
    assert snap["payout_ratio"] == pytest.approx(0.25)
    assert snap["total_payout_ratio"] == pytest.approx(0.75)

    a = financials.Assumptions(roe=0.17, cost_of_equity=0.10, growth=0.03, dividend_growth=0.03)
    result = financials.value(snap, a, price=150.0)
    assert result["value_by_book"] == pytest.approx(200.0)             # 2.0 x book value
    assert result["upside_by_book"] == pytest.approx(200 / 150 - 1)
    # At 1.5 times book the price needs an ROE of 3% + 1.5 x 7% = 13.5%.
    assert result["implied_roe"] == pytest.approx(0.135)
    assert result["sensitivity"].iloc[2, 2] == pytest.approx(200.0)    # centre of the grid


# ---- Payouts ----

def test_payout_yields_by_hand():
    latest = pd.Series({"dividends_paid": 20.0, "buybacks": 50.0, "stock_comp": 10.0})
    now = payouts.today(latest, market_cap=1000.0)
    assert now["dividend_yield"] == pytest.approx(0.02)
    assert now["shareholder_yield"] == pytest.approx(0.07)
    assert now["net_buyback_yield"] == pytest.approx(0.04)             # 50 bought, 10 handed out


def test_payouts_missing_are_blank_not_zero():
    now = payouts.today(pd.Series({"stock_comp": 10.0}), market_cap=1000.0)
    assert now["dividend_yield"] is None and now["shareholder_yield"] is None


# ---- Share price statistics ----

def test_price_statistics_by_hand():
    days = pd.bdate_range("2024-01-01", periods=300)
    prices = pd.Series([100.0] * 100 + [200.0] * 100 + [150.0] * 100, index=days)
    stats = pricestats.summary(prices)
    assert stats["high_52_week"] == 200.0 and stats["low_52_week"] == 100.0
    assert stats["below_high"] == pytest.approx(-0.25)
    assert stats["worst_fall"] == pytest.approx(-0.25)                 # 200 down to 150
    assert stats["average_50_day"] == 150.0
    table = pricestats.returns(prices)
    assert table.loc["1 month", "stock"] == pytest.approx(0.0)
    assert table.loc["1 year", "stock"] == pytest.approx(0.5)          # 100 to 150


# ---- Insider trades ----

FORM_4 = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerCik>0000000042</issuerCik></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>DOE JANE</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>0</isDirector><isOfficer>1</isOfficer><officerTitle>Chief Executive</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <aff10b5One>true</aff10b5One>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-03-02</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>50</value></transactionPricePerShare>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>9000</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-03-01</value></transactionDate>
      <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>500</value></transactionShares>
        <transactionPricePerShare><value>0</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_form_4_is_read_into_rows():
    rows = insiders.parse_form4(FORM_4, cik=42)
    assert len(rows) == 2
    sale = rows[0]
    assert sale["insider"] == "Doe Jane" and sale["role"] == "Chief Executive"
    assert sale["code"] == "S" and sale["value"] == 50000 and sale["planned"]
    assert rows[1]["what"] == "Share award from the company"
    # A filing about a different company's shares is ignored.
    assert insiders.parse_form4(FORM_4, cik=7) == []


def test_insider_summary_counts_only_open_market_trades():
    trades = pd.DataFrame(insiders.parse_form4(FORM_4, cik=42))
    trades["date"] = pd.to_datetime(trades["date"])
    summary = insiders.summarise(trades)
    assert summary["sell_value"] == 50000 and summary["buy_value"] == 0
    assert summary["sellers"] == 1 and summary["buyers"] == 0
    assert summary["planned_share_of_sales"] == 1.0
    assert len(summary["open_market"]) == 1        # the share award is routine, so left out


# ---- Health check ----

def _report(latest_s, latest_m, financial=False):
    index = pd.to_datetime(["2021-12-31", "2022-12-31", "2023-12-31", "2024-12-31"])
    statements = pd.DataFrame({"net_income": [80.0, 90.0, 100.0, 110.0],
                               "cash_from_operations": [90.0, 100.0, 120.0, 130.0],
                               "diluted_shares": [100.0, 99.0, 98.0, 97.0]}, index=index)
    metrics = pd.DataFrame({"revenue_growth": [0.05] * 4, "operating_margin": [0.20] * 4}, index=index)
    return {"statements": statements, "metrics": metrics, "profile": {"is_financial": financial},
            "latest": {"statements": pd.Series(latest_s), "metrics": pd.Series(latest_m),
                       "label": "12 months to 30 Jun 2025"}}


def test_health_check_flags_the_weak_spots():
    report = _report(
        {"net_income": 110.0, "operating_income": 150.0, "interest_expense": 100.0,
         "revenue": 1000.0, "stock_comp": 200.0},
        {"revenue_growth": -0.04, "free_cash_flow": -20.0, "operating_margin": 0.15,
         "return_on_invested_capital": 0.20, "net_debt": 900.0, "ebitda": 180.0},
    )
    results = {c["question"]: c["status"] for c in checks.run(report)}
    assert results["Are sales growing?"] == checks.WEAK
    assert results["Is it profitable?"] == checks.GOOD
    assert results["Does it generate cash after reinvesting?"] == checks.WEAK
    assert results["Is profit backed by cash?"] == checks.GOOD            # 350 cash vs 300 profit
    assert results["Are profit margins holding up?"] == checks.WEAK       # 15% against 20%
    assert results["Is debt manageable?"] == checks.WEAK                  # 5 times EBITDA
    assert results["Can it comfortably pay its interest?"] == checks.WEAK  # covered 1.5 times
    assert results["Is pay in shares kept modest?"] == checks.WEAK        # 20% of revenue
    assert results["Is your slice of the company being protected?"] == checks.GOOD  # count falling


def test_health_check_for_a_bank_skips_cash_flow_and_debt():
    report = _report({"net_income": 110.0, "dividends_paid": 33.0},
                     {"revenue_growth": 0.08, "return_on_equity": 0.15}, financial=True)
    results = {c["question"]: c["status"] for c in checks.run(report)}
    assert "Is debt manageable?" not in results
    assert results["Does it earn a good return on shareholders' money?"] == checks.GOOD
    assert results["Is the dividend comfortably covered by profit?"] == checks.GOOD
