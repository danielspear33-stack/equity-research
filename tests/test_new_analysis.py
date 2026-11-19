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


def test_cover_page_share_count_is_used_only_when_plausible():
    from research import statements

    def facts(*rows):
        return {"facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": list(rows)}}}}}

    older = {"end": "2024-01-15", "filed": "2024-02-01", "val": 990}
    newer = {"end": "2024-10-15", "filed": "2024-11-01", "val": 950}
    assert statements.latest_shares_outstanding(facts(older, newer), reference=1000) == 950
    # One share class out of several, or a count from before a split: ignore it.
    assert statements.latest_shares_outstanding(facts({**newer, "val": 300}), reference=1000) is None
    assert statements.latest_shares_outstanding({"facts": {}}, reference=1000) is None


def test_announcements_are_described_and_results_flagged(monkeypatch):
    from research import edgar

    profile = {"filings": {"recent": {
        "form": ["8-K", "10-Q", "8-K", "8-K"],
        "filingDate": ["2026-10-30", "2026-10-29", "2026-09-01", "2026-08-01"],
        "accessionNumber": ["0001-26-000003", "0001-26-000002", "0001-26-000001", "0001-26-000000"],
        "primaryDocument": ["a.htm", "b.htm", "c.htm", "d.htm"],
        "items": ["2.02,9.01", "", "5.02", "9.01"],
    }}}
    monkeypatch.setattr(edgar, "fetch_json", lambda *args: profile)
    found = edgar.get_announcements(123)
    assert [a["filed"] for a in found] == ["2026-10-30", "2026-09-01", "2026-08-01"]
    assert found[0]["what"] == "Results announced" and found[0]["is_earnings"]
    assert found[1]["what"] == "Director or executive change" and not found[1]["is_earnings"]
    assert found[2]["what"] == "Other news"
    assert found[0]["url"].endswith("/123/000126000003/a.htm")


def test_contact_details_go_only_to_the_sec(monkeypatch):
    from research import cache, config

    monkeypatch.setattr(config, "USER_AGENT", "Jane Doe jane@example.com")
    assert cache._headers("https://data.sec.gov/x.json")["User-Agent"] == "Jane Doe jane@example.com"
    assert cache._headers("https://www.sec.gov/Archives/x")["User-Agent"] == "Jane Doe jane@example.com"
    for other in ("https://query1.finance.yahoo.com/v8/x", "https://notsec.gov/x", "https://sec.gov.evil.com/x"):
        assert "jane" not in cache._headers(other)["User-Agent"]


def test_stale_copy_is_used_when_the_download_fails(monkeypatch, tmp_path):
    import os
    import requests
    from research import cache, config

    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    saved = tmp_path / "prices_X.json"
    saved.write_text('{"old": true}')
    os.utime(saved, (0, 0))  # make it look ancient

    def refuse(*args, **kwargs):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(cache.requests, "get", refuse)
    assert cache.fetch_json("https://example.com/x", "prices_X", max_age=60) == {"old": True}
    import pytest
    with pytest.raises(requests.ConnectionError):
        cache.fetch_json("https://example.com/y", "prices_Y", max_age=60)


def test_filings_from_before_a_reorganisation_are_joined_on(monkeypatch, tmp_path):
    import json
    from research import config, edgar

    def row(end, val, form):
        return {"start": end[:4] + "-01-01", "end": end, "val": val, "form": form, "filed": end}

    downloads = {
        # The new registration has only this year's quarterly report...
        "facts_2": {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [row("2026-03-31", 30, "10-Q")]}}}}},
        # ...and the history is under the old one.
        "facts_1": {"facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [row("2025-12-31", 100, "10-K")]}},
            "NetIncomeLoss": {"units": {"USD": [row("2025-12-31", 9, "10-K")]}},
        }}},
    }
    listing = tmp_path / "predecessors.json"
    listing.write_text(json.dumps({"2": [1]}))
    monkeypatch.setattr(config, "PREDECESSORS_FILE", listing)
    monkeypatch.setattr(edgar, "fetch_json", lambda url, name, age: downloads[name])

    joined = edgar.get_company_facts(2)["facts"]["us-gaap"]
    assert [r["val"] for r in joined["Revenues"]["units"]["USD"]] == [100, 30]
    assert joined["NetIncomeLoss"]["units"]["USD"][0]["val"] == 9
    # The saved download itself is left as it was, and unlisted companies are untouched.
    assert len(downloads["facts_2"]["facts"]["us-gaap"]["Revenues"]["units"]["USD"]) == 1
    assert edgar.get_company_facts(1) is downloads["facts_1"]
