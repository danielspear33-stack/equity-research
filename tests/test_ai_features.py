import time

import pandas as pd
import pytest

from research import backtest, background, changes, config, factcheck, store


# ---- Fact-check: figures in a memo against the data the AI was given ----

DATA = """ANNUAL FIGURES ($ billions):
revenue 478.82
VALUATION TODAY: share price $351.92; market cap $5123.4B; P/E 38.6712
operating_margin 0.33
DCF value per share $133.16 vs price $351.92 (-62.2%)
<annual_report_section item="1A">
We employ approximately 164,000 people and repurchased $90.7 billion of shares.
</annual_report_section>"""


def test_figures_are_matched_through_rounding_and_units():
    memo = ("Revenue was $478.8B with a 33.0% operating margin. The shares trade at 38.7x "
            "earnings, a market value of $5.1T, and the DCF sits 62% below the price.")
    result = factcheck.check(memo, DATA)
    assert result["checked"] == 5
    assert result["in_data"] == 5 and result["unverified"] == []


def test_invented_figure_is_flagged_with_its_sentence():
    memo = "Revenue was $478.8B. Management expects margins of 41.5% next year."
    result = factcheck.check(memo, DATA)
    assert [item["figure"] for item in result["unverified"]] == ["41.5%"]
    assert "Management expects" in result["unverified"][0]["sentence"]


def test_figure_found_only_in_the_annual_report_is_counted_separately():
    result = factcheck.check("It bought back $90.7 billion of stock.", DATA)
    assert (result["in_data"], result["in_report"], result["unverified"]) == (0, 1, [])


def test_bare_numbers_like_years_are_not_treated_as_figures():
    assert factcheck.check("In 2024 it opened 12 stores across 3 regions.", DATA)["checked"] == 0


# ---- Filing changes: paragraph-by-paragraph comparison ----

def _paragraph(text):
    return text + " " + "This sentence pads the paragraph past the minimum length. " * 3


def test_compare_sorts_paragraphs_into_unchanged_reworded_new_and_removed():
    same = _paragraph("We sell widgets in forty countries through our own stores.")
    figures_old = _paragraph("Revenue was $394 billion in the year.")
    figures_new = _paragraph("Revenue was $416 billion in the year.")
    edited_old = _paragraph("Our suppliers are concentrated in a small number of countries which exposes us to disruption.")
    edited_new = _paragraph("Our suppliers are concentrated in a small number of countries which exposes us to disruption and tariffs.")
    dropped = _paragraph("The pandemic continues to affect demand for our products worldwide.")
    brand_new = _paragraph("Artificial intelligence regulation could raise our compliance costs.")
    old = "\n\n".join([same, figures_old, edited_old, dropped, "Short heading"])
    new = "\n\n".join([same, figures_new, edited_new, brand_new])

    diff = changes.compare(old, new)
    assert diff["total"] == 4 and diff["unchanged"] == 2     # an updated number alone is "unchanged"
    assert diff["added"] == [" ".join(brand_new.split())]
    assert diff["removed"] == [" ".join(dropped.split())]
    assert len(diff["reworded"]) == 1 and "tariffs" in diff["reworded"][0][1]


def test_prompt_says_when_paragraphs_were_left_out(monkeypatch):
    monkeypatch.setitem(changes.PROMPT_BUDGET, "added", 300)
    diff = {"added": ["A" * 200, "B" * 200, "C" * 200], "removed": [], "reworded": [],
            "unchanged": 5, "total": 8}
    comparison = {"newest": {"filed": "2026-10-30"}, "previous": {"filed": "2025-10-31"},
                  "sections": {"Risk Factors": diff}}
    prompt = changes.build_prompt("Example Corp", comparison)
    assert "NEW THIS YEAR (2 more not shown)" in prompt and "B" * 200 not in prompt


# ---- Backtest ----

def _annual(years):
    index = pd.to_datetime([f"{year}-12-31" for year in years])
    n = len(years)
    return pd.DataFrame({
        "revenue": [1000.0 * 1.1 ** i for i in range(n)],
        "gross_profit": [400.0] * n, "operating_income": [200.0 * 1.1 ** i for i in range(n)],
        "pretax_income": [190.0] * n, "income_tax": [40.0] * n, "net_income": [150.0] * n,
        "d_and_a": [50.0] * n, "cash_from_operations": [220.0] * n, "capex": [60.0] * n,
        "equity": [800.0] * n, "total_debt": [300.0] * n, "cash_and_investments": [100.0] * n,
        "working_capital": [100.0] * n, "diluted_shares": [100.0] * n,
    }, index=index)


def test_backtest_uses_only_what_was_known_and_measures_the_following_year():
    days = pd.date_range("2018-01-01", "2024-12-31", freq="D")
    prices = pd.Series(range(len(days)), index=days, dtype="float64") + 100
    market = pd.Series(1000.0, index=days)
    yields = pd.Series(4.0, index=days)

    rows = backtest.observations("TEST", _annual(range(2018, 2024)), prices, market, yields,
                                 today=pd.Timestamp("2024-12-31"))
    # Three years of history are needed, and a full year must have passed
    # since entry: fiscal 2020, 2021 and 2022 qualify; 2023 has not played out.
    assert [row["fiscal_year_end"] for row in rows] == ["2020-12-31", "2021-12-31", "2022-12-31"]
    first = rows[0]
    assert first["entry_date"] == "2021-03-31"                 # 90 days after the year end
    entry_price = prices[pd.Timestamp("2021-03-31")]
    assert first["price"] == entry_price
    assert first["stock_return"] == pytest.approx(365 / entry_price)   # the price rises 1 a day
    assert first["market_return"] == 0 and first["excess_return"] == first["stock_return"]
    # Other measures are taken at the same moment: profit of 150 on 100 shares at that price.
    assert first["earnings_yield"] == pytest.approx(150 / (entry_price * 100))
    assert first["momentum"] == pytest.approx(entry_price / (entry_price - 365) - 1)


def test_backtest_summary_ranks_within_each_year():
    rows = []
    for year in (2020, 2021):
        for i in range(10):
            # Cheaper shares (higher gap) do better, by construction.
            rows.append({"ticker": f"T{i}", "entry_year": year, "dcf_gap": i / 10,
                         "stock_return": 0.10 + i / 100, "market_return": 0.10,
                         "excess_return": i / 100})
    summary = backtest.summarise(pd.DataFrame(rows))
    assert summary["by_group"]["observations"].tolist() == [4, 4, 4, 4, 4]
    assert summary["spread"] == pytest.approx(0.085 - 0.005)
    assert summary["rank_correlation"] == pytest.approx(1.0)
    assert summary["years_high_won"] == 2
    assert backtest.grade(summary) == "Worked"
    assert backtest.verdict(summary).startswith("This one held up")


def test_backtest_grades_a_signal_that_points_the_wrong_way():
    rows = []
    for year in (2020, 2021, 2022):
        for i in range(10):
            rows.append({"ticker": f"T{i}", "entry_year": year, "fcf_yield": i / 100,
                         "stock_return": 0.2 - i / 50, "market_return": 0.1,
                         "excess_return": 0.1 - i / 50})
    summary = backtest.summarise(pd.DataFrame(rows), "fcf_yield")
    assert summary["spread"] < 0 and summary["years_high_won"] == 0
    assert backtest.grade(summary) == "Backwards"


# ---- Background jobs and saved details ----

def _wait(name):
    for _ in range(200):
        if background.status(name)["state"] != "running":
            return background.status(name)
        time.sleep(0.01)
    raise AssertionError("job never finished")


def test_background_job_reports_success_and_failure():
    done = []
    assert background.start("test:ok", lambda: done.append(1))
    assert _wait("test:ok")["state"] == "done" and done == [1]

    def broken():
        raise ValueError("no luck")

    background.start("test:bad", broken)
    assert _wait("test:bad") == {"state": "failed", "error": "no luck",
                                 "started": background.status("test:bad")["started"]}
    background.clear("test:bad")
    assert background.status("test:bad") is None


def test_memo_details_and_settings_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    assert store.get_memo_details("AAPL") == {} and store.get_setting("auto_ai", True) is True
    store.save_memo("AAPL", "A memo.", {"basis": "2026-10-30", "check": {"checked": 3}})
    store.save_setting("auto_ai", False)
    assert store.get_memo("AAPL") == "A memo."
    assert store.get_memo_details("AAPL")["basis"] == "2026-10-30"
    assert store.get_setting("auto_ai", True) is False


def test_billions_are_matched_against_a_source_stated_in_millions():
    release = "Total cash and investments 20,165 (amounts in millions)"
    assert factcheck.check("It holds $20.2 billion of cash.", release)["unverified"] == []
    assert len(factcheck.check("It holds $21.9 billion of cash.", release)["unverified"]) == 1
