import pytest

from research.dcf import Assumptions, implied_growth, project, sensitivity, value

# Simple enough to check with a calculator: no growth, no reinvestment.
FLAT = Assumptions(
    years=2, growth_start=0.0, growth_end=0.0, ebit_margin=0.20, tax_rate=0.25,
    da_pct=0.0, capex_pct=0.0, nwc_pct=0.0, wacc=0.10, terminal_growth=0.0,
)


def test_flat_company_by_hand():
    # Revenue 1000 -> operating profit 200 -> after tax 150 a year, forever.
    result = value(base_revenue=1000, net_debt=100, shares=10, a=FLAT)
    assert result["forecast"]["free_cash_flow"].tolist() == [150, 150]
    assert result["pv_forecast"] == pytest.approx(150 / 1.1 + 150 / 1.21)
    assert result["terminal_value"] == pytest.approx(150 / 0.10)
    # A perpetuity of 150 at 10% is worth 1500 however you slice the years.
    assert result["enterprise_value"] == pytest.approx(1500)
    assert result["equity_value"] == pytest.approx(1400)
    assert result["value_per_share"] == pytest.approx(140)


def test_growth_fades_in_a_straight_line_and_cash_flow_adds_up():
    a = Assumptions(
        years=3, growth_start=0.10, growth_end=0.04, ebit_margin=0.20, tax_rate=0.25,
        da_pct=0.05, capex_pct=0.06, nwc_pct=0.10, wacc=0.09, terminal_growth=0.02,
    )
    forecast = project(1000, a)
    assert forecast["growth"].tolist() == pytest.approx([0.10, 0.07, 0.04])
    year1 = forecast.loc[1]
    assert year1["revenue"] == pytest.approx(1100)
    # 1100*0.2*0.75 = 165, plus D&A 55, minus capex 66, minus working capital 100*0.1 = 10.
    assert year1["free_cash_flow"] == pytest.approx(165 + 55 - 66 - 10)


def test_discount_rate_must_exceed_terminal_growth():
    bad = Assumptions(**{**FLAT.to_dict(), "wacc": 0.03, "terminal_growth": 0.03})
    with pytest.raises(ValueError):
        value(1000, 0, 10, bad)


def test_sensitivity_centre_matches_base_case_and_moves_the_right_way():
    a = Assumptions(**{**FLAT.to_dict(), "terminal_growth": 0.02})
    grid = sensitivity(1000, 100, 10, a)
    assert grid.shape == (5, 5)
    assert grid.iloc[2, 2] == pytest.approx(value(1000, 100, 10, a)["value_per_share"])
    assert grid.iloc[0, 2] > grid.iloc[4, 2]   # lower discount rate, higher value
    assert grid.iloc[2, 4] > grid.iloc[2, 0]   # higher terminal growth, higher value


def test_implied_growth_recovers_the_growth_that_produced_the_price():
    a = Assumptions(
        years=5, growth_start=0.12, growth_end=0.03, ebit_margin=0.25, tax_rate=0.21,
        da_pct=0.03, capex_pct=0.04, nwc_pct=0.05, wacc=0.09, terminal_growth=0.025,
    )
    price = value(1000, 50, 10, a)["value_per_share"]
    wrong_start = Assumptions(**{**a.to_dict(), "growth_start": 0.0})
    assert implied_growth(1000, 50, 10, wrong_start, price) == pytest.approx(0.12, abs=1e-6)


def test_implied_growth_is_none_when_out_of_range():
    assert implied_growth(1000, 0, 10, FLAT, price=1e9) is None
