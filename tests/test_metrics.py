import pandas as pd
import pytest

from research.metrics import compute_annual_metrics, compute_valuation

# A made-up company, small enough to check every number by hand.
STATEMENTS = pd.DataFrame(
    {
        "revenue": [1000.0, 1200.0],
        "gross_profit": [400.0, 540.0],
        "operating_income": [200.0, 300.0],
        "pretax_income": [190.0, 280.0],
        "income_tax": [38.0, 70.0],          # 20% then 25%
        "net_income": [152.0, 210.0],
        "d_and_a": [50.0, 60.0],
        "cash_from_operations": [220.0, 310.0],
        "capex": [80.0, 100.0],
        "equity": [800.0, 1000.0],
        "total_debt": [300.0, 400.0],
        "cash_and_investments": [100.0, 200.0],
        "diluted_shares": [100.0, 100.0],
    },
    index=pd.to_datetime(["2023-12-31", "2024-12-31"]),
)


def test_annual_metrics_by_hand():
    m = compute_annual_metrics(STATEMENTS).iloc[-1]
    assert m["revenue_growth"] == pytest.approx(0.20)
    assert m["gross_margin"] == pytest.approx(0.45)
    assert m["operating_margin"] == pytest.approx(0.25)
    assert m["net_margin"] == pytest.approx(0.175)
    assert m["free_cash_flow"] == 210
    assert m["ebitda"] == 360
    assert m["return_on_equity"] == pytest.approx(210 / 900)
    # After-tax operating profit 300 * (1 - 0.25) = 225.
    # Invested capital: 2023 = 300 + 800 - 100 = 1000, 2024 = 400 + 1000 - 200 = 1200.
    assert m["return_on_invested_capital"] == pytest.approx(225 / 1100)
    assert m["net_debt"] == 200
    assert m["net_debt_to_ebitda"] == pytest.approx(200 / 360)


def test_first_year_has_no_growth_or_average_based_returns():
    m = compute_annual_metrics(STATEMENTS).iloc[0]
    assert pd.isna(m["revenue_growth"])
    assert pd.isna(m["return_on_equity"])


def test_valuation_by_hand():
    m = compute_annual_metrics(STATEMENTS)
    v = compute_valuation(STATEMENTS, m, price=42.0)
    assert v["market_cap"] == 4200
    assert v["enterprise_value"] == 4400          # 4200 + net debt of 200
    assert v["price_to_earnings"] == pytest.approx(20.0)
    assert v["ev_to_ebitda"] == pytest.approx(4400 / 360)
    assert v["ev_to_sales"] == pytest.approx(4400 / 1200)
    assert v["fcf_yield"] == pytest.approx(0.05)


def test_multiples_are_blank_for_loss_making_company():
    losing = STATEMENTS.copy()
    losing.loc[losing.index[-1], "net_income"] = -50.0
    v = compute_valuation(losing, compute_annual_metrics(losing), price=42.0)
    assert v["price_to_earnings"] is None
