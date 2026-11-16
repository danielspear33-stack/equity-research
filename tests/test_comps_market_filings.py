import numpy as np
import pandas as pd
import pytest
import requests

from research import comps, filings, market


def test_beta_recovers_a_known_slope():
    days = pd.bdate_range("2021-01-01", periods=1300)
    rng = np.random.default_rng(0)
    market_returns = pd.Series(rng.normal(0.0004, 0.01, len(days)), index=days)
    market_prices = 100 * (1 + market_returns).cumprod()
    # A share that always moves 1.5x the market in log terms.
    stock_prices = 50 * (market_prices / 100) ** 1.5
    assert market.compute_beta(stock_prices, market_prices) == pytest.approx(1.5, abs=0.05)


def test_suggested_peers_exclude_the_company_itself():
    group, peers = comps.suggest_peers("KO")
    assert group == "Consumer staples"
    assert "KO" not in peers and "PEP" in peers


def test_multiple_summary_and_implied_values_by_hand():
    peers = pd.DataFrame(
        {
            "ev_to_ebitda": [10.0, 12.0, 14.0],
            "ev_to_sales": [2.0, 3.0, 4.0],
            "price_to_earnings": [15.0, None, 25.0],
        },
        index=["A", "B", "C"],
    )
    summary = comps.summarise_multiples(peers)
    assert summary.loc["ev_to_ebitda", "median"] == 12
    assert summary.loc["price_to_earnings", "peers_used"] == 2

    index = pd.to_datetime(["2024-12-31"])
    statements = pd.DataFrame(
        {"revenue": [1000.0], "net_income": [100.0], "diluted_shares": [50.0]}, index=index
    )
    metrics = pd.DataFrame({"ebitda": [200.0], "net_debt": [400.0]}, index=index)
    implied = comps.implied_values(summary, statements, metrics)
    # 12 x 200 EBITDA = 2400 enterprise value, less 400 net debt = 2000, over 50 shares.
    assert implied.loc["ev_to_ebitda", "median"] == pytest.approx(40)
    assert implied.loc["ev_to_sales", "median"] == pytest.approx((3 * 1000 - 400) / 50)
    # P/E values the shares directly, so no net debt adjustment: 20 x 100 / 50.
    assert implied.loc["price_to_earnings", "median"] == pytest.approx(40)


ANNUAL_REPORT = """
<html><style>p {color: red}</style><body>
<p>Table of contents</p>
<p>Item 1. Business 3</p><p>Item 1A. Risk Factors 9</p><p>Item 7. Management's Discussion 30</p>
<p>Item 8. Financial Statements 45</p>
<div>Item 1. Business</div><p>We sell widgets in forty countries.</p>
<div>Item 1A. Risk Factors</div><p>Widget demand may fall.</p><p>Suppliers are concentrated.</p>
<div>Item 1B. Unresolved Staff Comments</div><p>None.</p>
<div>Item 7. Management's Discussion and Analysis</div><p>Revenue rose because prices rose.</p>
<div>Item 7A. Market Risk</div><p>Rates.</p>
</body></html>
"""


def test_sections_come_from_the_body_not_the_table_of_contents():
    text = filings.html_to_text(ANNUAL_REPORT)
    assert "color: red" not in text
    sections = filings.extract_sections(text)
    assert set(sections) == {"1", "1A", "7"}
    assert "forty countries" in sections["1"]
    assert "Suppliers are concentrated" in sections["1A"]
    assert "Unresolved" not in sections["1A"]
    assert "prices rose" in sections["7"] and "Rates" not in sections["7"]


def test_tickers_are_found_in_the_saved_list_without_any_download(monkeypatch):
    from research import edgar

    def no_network(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(edgar, "fetch_json", no_network)
    assert len(edgar.company_list()) > 5000
    assert edgar.lookup_cik("aapl") == 320193
    assert edgar.lookup_cik("BRK.B") == 1067983      # written BRK-B in the SEC's list
    with pytest.raises(edgar.TickerNotFound):
        edgar.lookup_cik("NOTREAL")
