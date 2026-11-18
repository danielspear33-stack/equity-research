import pytest

from research import lbo, merger

# A company simple enough to follow with a calculator: no growth, no tax,
# no reinvestment. EBITDA is 100 every year.
BASE = lbo.Base(revenue=1000, ebitda=100, net_debt=0, shares=100, price=8.0)
FLAT = lbo.Assumptions(
    premium=0.25, leverage=5.0, interest_rate=0.10, fees_pct=0.0, years=2,
    growth_start=0.0, growth_end=0.0, ebitda_margin=0.10, tax_rate=0.0,
    da_pct=0.0, capex_pct=0.0, nwc_pct=0.0, exit_multiple=10.0,
)


def test_lbo_by_hand():
    result = lbo.run(BASE, FLAT)
    # Bid 8 x 1.25 = 10 a share, so 1,000 for the company: 10x EBITDA.
    assert result["offer_price"] == 10 and result["enterprise_value"] == 1000
    assert result["entry_multiple"] == 10
    # 500 borrowed, so the buyer puts in 500.
    assert result["debt"] == 500 and result["sponsor_equity"] == 500
    # Year 1: interest 50, cash 50, debt 450. Year 2: interest 45, cash 55, debt 395.
    assert result["schedule"]["debt_end"].tolist() == pytest.approx([450, 395])
    # Sold for 10 x 100 = 1,000; after the 395 still owed, 605 to the buyer.
    assert result["exit_equity"] == pytest.approx(605)
    assert result["money_multiple"] == pytest.approx(1.21)
    assert result["irr"] == pytest.approx(0.10)
    # No growth and the same multiple, so the whole gain is debt paid down.
    assert result["gain_from_growth"] == 0 and result["gain_from_multiple"] == 0
    assert result["gain_from_debt"] == pytest.approx(105) == pytest.approx(result["gain"])


def test_lbo_gain_always_splits_exactly():
    a = lbo.Assumptions(
        premium=0.3, leverage=4.0, interest_rate=0.08, fees_pct=0.02, years=5,
        growth_start=0.08, growth_end=0.04, ebitda_margin=0.12, tax_rate=0.25,
        da_pct=0.03, capex_pct=0.04, nwc_pct=0.05, exit_multiple=9.0,
    )
    r = lbo.run(lbo.Base(1000, 115, 60, 100, 8.0), a)
    parts = r["gain_from_growth"] + r["gain_from_multiple"] + r["gain_from_debt"] + r["gain_lost_to_fees"]
    # Existing net debt is refinanced into the new debt, which the split treats as part of the price.
    assert parts == pytest.approx(r["gain"])


def test_lbo_surplus_cash_builds_once_debt_is_gone_and_counts_at_exit():
    a = lbo.Assumptions(**{**FLAT.to_dict(), "leverage": 0.5, "years": 3})
    result = lbo.run(BASE, a)
    assert result["schedule"]["debt_end"].iloc[-1] == 0
    assert result["exit_cash"] > 0
    assert result["exit_equity"] == pytest.approx(result["exit_value"] + result["exit_cash"])


def test_affordable_price_gives_back_the_target_return():
    a = lbo.Assumptions(**{**FLAT.to_dict(), "fees_pct": 0.02, "years": 4, "tax_rate": 0.2})
    price = lbo.affordable_price(BASE, a, target_irr=0.20)
    at_that_price = lbo.Assumptions(**{**a.to_dict(), "premium": price / BASE.price - 1})
    assert lbo.run(BASE, at_that_price)["irr"] == pytest.approx(0.20)
    # A buyer who wants a higher return can afford to pay less.
    assert lbo.affordable_price(BASE, a, 0.25) < price


def test_lbo_refuses_impossible_deals():
    with pytest.raises(ValueError, match="EBITDA"):
        lbo.run(lbo.Base(1000, -5, 0, 100, 8.0), FLAT)
    with pytest.raises(ValueError, match="leverage"):
        lbo.run(BASE, lbo.Assumptions(**{**FLAT.to_dict(), "leverage": 12.0}))


def test_lbo_sensitivity_moves_the_right_way():
    grid = lbo.sensitivity(BASE, FLAT)
    assert grid.iloc[0, 2] > grid.iloc[-1, 2]    # paying less, higher return
    assert grid.iloc[2, -1] > grid.iloc[2, 0]    # selling at a higher multiple, higher return
    assert grid.loc[FLAT.premium, FLAT.exit_multiple] == pytest.approx(0.10)


BUYER = merger.Company("BUY", "Buyer", price=100.0, shares=100, net_income=500, net_debt=0, ebitda=900)
TARGET = merger.Company("TGT", "Target", price=40.0, shares=50, net_income=100, net_debt=200, ebitda=250)


def test_all_share_deal_by_hand():
    deal = merger.Deal(premium=0.25, stock_share=1.0, debt_rate=0.06, synergies=0, tax_rate=0.25)
    r = merger.run(BUYER, TARGET, deal)
    # Bid 50 a share for 50 shares = 2,500, paid with 25 new shares at 100.
    assert r["offer_price"] == 50 and r["equity_value"] == 2500 and r["new_shares"] == 25
    assert r["enterprise_value"] == 2700
    # Profit 600 over 125 shares = 4.80, against 5.00 before: 4% dilutive.
    assert r["combined_eps"] == pytest.approx(4.80)
    assert r["accretion"] == pytest.approx(-0.04)
    # The buyer is on 20x earnings and paid 25x, which is why it dilutes.
    assert r["acquirer_pe"] == 20 and r["target_pe_paid"] == 25
    assert r["target_ownership"] == pytest.approx(0.2)
    # To stand still it needs 625 of profit: 25 more after tax, 33.33 before.
    assert r["breakeven_synergies"] == pytest.approx(25 / 0.75)


def test_all_cash_deal_by_hand():
    deal = merger.Deal(premium=0.25, stock_share=0.0, debt_rate=0.06, synergies=0, tax_rate=0.25)
    r = merger.run(BUYER, TARGET, deal)
    # Borrow 2,500 at 6%: 150 of interest, 112.50 after tax. No new shares.
    assert r["new_shares"] == 0 and r["interest_after_tax"] == pytest.approx(112.5)
    assert r["combined_eps"] == pytest.approx((500 + 100 - 112.5) / 100)
    assert r["accretion"] == pytest.approx(-0.025)
    assert r["combined_net_debt"] == 2700
    assert r["combined_leverage"] == pytest.approx(2700 / 1150)


def test_breakeven_synergies_really_break_even():
    deal = merger.Deal(premium=0.4, stock_share=0.5, debt_rate=0.07, synergies=0, tax_rate=0.21)
    needed = merger.run(BUYER, TARGET, deal)["breakeven_synergies"]
    with_them = merger.Deal(**{**deal.to_dict(), "synergies": needed})
    assert merger.run(BUYER, TARGET, with_them)["accretion"] == pytest.approx(0)


def test_merger_refuses_a_loss_making_buyer_and_grid_has_the_base_case():
    deal = merger.Deal(premium=0.25, stock_share=0.5, debt_rate=0.06, synergies=0, tax_rate=0.25)
    loss = merger.Company("BUY", "Buyer", 100.0, 100, -5, 0, 10)
    with pytest.raises(ValueError, match="loss-making"):
        merger.run(loss, TARGET, deal)
    grid = merger.sensitivity(BUYER, TARGET, deal)
    assert grid.loc[0.25, 0.5] == pytest.approx(merger.run(BUYER, TARGET, deal)["accretion"])
    assert grid.iloc[0, 2] > grid.iloc[-1, 2]   # paying less is always better for EPS
