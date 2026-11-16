import pandas as pd
import pytest

from research import earnings, scorecard, valhistory


# ---- Scorecard ----

def test_scale_is_a_straight_line_capped_at_both_ends():
    assert scorecard._scale(0.10, 0.0, 0.20) == pytest.approx(2.5)
    assert scorecard._scale(0.50, 0.0, 0.20) == 5 and scorecard._scale(-0.1, 0.0, 0.20) == 0
    # A falling share count is good, so the scale can run downwards.
    assert scorecard._scale(-0.02, 0.02, -0.02) == 5 and scorecard._scale(0.0, 0.02, -0.02) == pytest.approx(2.5)
    assert scorecard._scale(None, 0, 1) is None


def test_value_score_averages_the_gaps_to_dcf_and_peers_with_the_cash_yield():
    report = {"valuation": {"price": 100.0, "fcf_yield": 0.0375, "price_to_earnings": 20.0},
              "profile": {"is_financial": False}}
    # DCF 25% above the price scores 3.75; peers level with it score 2.5;
    # a 3.75% cash yield is halfway to the 7.5% that scores 5.
    score, why = scorecard._value(report, dcf_value=125.0, peer_value=100.0, bank_value=None)
    assert score == pytest.approx((3.75 + 2.5 + 2.5) / 3)
    assert "DCF value +25%" in why and "free cash flow yield 3.8%" in why


def test_overall_ignores_scores_that_could_not_be_worked_out():
    results = [{"score": 4.0}, {"score": None}, {"score": 2.0}]
    assert scorecard.overall(results) == 3.0
    assert scorecard.overall([{"score": None}]) is None


# ---- Valuation against the company's own history ----

def test_multiples_use_only_results_published_by_each_month_end():
    index = pd.to_datetime(["2020-12-31", "2021-12-31"])
    annual = pd.DataFrame({"diluted_shares": [100.0, 100.0], "net_income": [500.0, 1000.0],
                           "revenue": [5000.0, 5000.0], "equity": [2000.0, 2000.0]}, index=index)
    metrics = pd.DataFrame({"net_debt": [0.0, 0.0], "ebitda": [1000.0, -50.0]}, index=index)
    days = pd.date_range("2021-01-01", "2022-06-30", freq="D")
    prices = pd.Series(100.0, index=days)

    history = valhistory.history(annual, metrics, prices)
    # Nothing until 90 days after the first year end.
    assert history.index[0] == pd.Timestamp("2021-03-31")
    # Market value 10,000 over profit of 500, until the next year's results are out.
    assert history.loc["2022-02-28", "pe"] == 20
    assert history.loc["2022-03-31", "pe"] == 10                 # day 90 after the second year end
    assert history.loc["2021-06-30", "ev_ebitda"] == 10
    assert pd.isna(history.loc["2022-04-30", "ev_ebitda"])       # negative EBITDA: no multiple


def test_position_says_how_today_compares_with_the_past():
    past = pd.Series([10.0] * 6 + [20.0] * 6 + [30.0] * 12)
    where = valhistory.position(past, 25.0)
    assert where["median"] == 25.0 and where["percentile"] == 0.5 and where["years"] == 2.0
    assert valhistory.position(past.head(6), 25.0) is None       # too little history to judge
    assert "25.0x" in valhistory.describe("P/E", where)


# ---- Finding the press release among a results filing's documents ----

def test_press_release_is_the_exhibit_99_page_not_the_cover_form(monkeypatch):
    listing = {"directory": {"item": [
        {"name": "abc-20261102.htm", "size": "40000"},              # the 8-K cover form
        {"name": "a8-kex991q42026.htm", "size": "11000"},
        {"name": "R1.htm", "size": "90000"},
        {"name": "0000320193-26-000024-index.html", "size": ""},
        {"name": "logo.jpg", "size": "5000"},
    ]}}
    monkeypatch.setattr(earnings, "fetch_json", lambda *args: listing)
    announcement = {"url": "https://www.sec.gov/Archives/edgar/data/1/000032019326000024/abc-20261102.htm"}
    assert earnings.press_release_url(announcement).endswith("/000032019326000024/a8-kex991q42026.htm")


def test_latest_announcement_picks_the_newest_results_filing():
    filed = [{"filed": "2026-11-10", "is_earnings": False}, {"filed": "2026-11-02", "is_earnings": True},
             {"filed": "2026-08-01", "is_earnings": True}]
    assert earnings.latest_announcement(filed)["filed"] == "2026-11-02"
    assert earnings.latest_announcement([]) is None
