from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from research import config, dcf, memo, store


@pytest.fixture(autouse=True)
def temporary_user_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)


def test_watchlist_add_and_remove():
    store.add_to_watchlist("MSFT")
    store.add_to_watchlist("AAPL")
    store.add_to_watchlist("AAPL")
    assert store.get_watchlist() == ["AAPL", "MSFT"]
    store.remove_from_watchlist("AAPL")
    assert store.get_watchlist() == ["MSFT"]


def test_assumptions_and_peers_round_trip():
    store.save_assumptions("AAPL", {"wacc": 0.09})
    store.save_peers("AAPL", ["MSFT"])
    assert store.get_assumptions("AAPL") == {"wacc": 0.09}
    assert store.get_peers("AAPL") == ["MSFT"]
    store.clear_assumptions("AAPL")
    assert store.get_assumptions("AAPL") is None


def test_snapshot_replaces_same_day_and_keeps_history():
    store.save_snapshot({"ticker": "AAPL", "price": 100.0}, today=date(2026, 1, 5))
    store.save_snapshot({"ticker": "AAPL", "price": 101.0}, today=date(2026, 1, 5))
    store.save_snapshot({"ticker": "AAPL", "price": 105.0}, today=date(2026, 1, 6))
    history = store.get_snapshots()
    assert history["price"].tolist() == [101.0, 105.0]


def _fake_report():
    index = pd.to_datetime(["2023-12-31", "2024-12-31"])
    statements = pd.DataFrame(
        {c: [1.0e9, 2.0e9] for c in ["revenue", "gross_profit", "operating_income", "net_income",
                                     "cash_from_operations", "capex", "total_debt",
                                     "cash_and_investments", "equity"]}, index=index)
    metrics = pd.DataFrame(
        {c: [0.1, 0.2] for c in ["free_cash_flow", "ebitda", "revenue_growth", "gross_margin",
                                 "operating_margin", "net_margin", "fcf_margin", "return_on_equity",
                                 "return_on_invested_capital", "net_debt_to_ebitda"]}, index=index)
    return {
        "ticker": "TEST", "profile": {"name": "Test Co", "industry": "Widgets", "is_financial": False},
        "statements": statements, "metrics": metrics,
        "valuation": {"price": 10.0, "market_cap": 1e10, "enterprise_value": 1.1e10,
                      "price_to_earnings": 5.0, "ev_to_ebitda": 4.0, "ev_to_sales": 2.0,
                      "fcf_yield": 0.05},
    }


def test_memo_context_includes_numbers_and_wraps_report_text():
    context = memo.build_context(_fake_report(), None, None, None, False, None,
                                 {"1A": "Item 1A. Widget demand may fall."})
    assert "Test Co (TEST)" in context and "share price $10.00" in context
    assert '<annual_report_section item="1A" title="Risk Factors">' in context
    without = memo.build_context(_fake_report(), None, None, None, False, None, None)
    assert "annual report text was not available" in without


class _FakeStream:
    def __init__(self, stop_reason):
        self.text_stream = iter(["Hello ", "memo"])
        self._final = SimpleNamespace(stop_reason=stop_reason)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_final_message(self):
        return self._final


def _fake_client(stop_reason, seen):
    def stream(**kwargs):
        seen.update(kwargs)
        return _FakeStream(stop_reason)
    return SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)))


def test_memo_stream_passes_expected_request(monkeypatch):
    seen = {}
    monkeypatch.setattr(memo.anthropic, "Anthropic", lambda: _fake_client("end_turn", seen))
    assert "".join(memo.stream_memo("numbers")) == "Hello memo"
    assert seen["model"] == config.MEMO_MODEL
    assert seen["fallbacks"] == "default"
    assert seen["messages"] == [{"role": "user", "content": "numbers"}]


def test_memo_refusal_is_reported(monkeypatch):
    monkeypatch.setattr(memo.anthropic, "Anthropic", lambda: _fake_client("refusal", {}))
    with pytest.raises(memo.MemoError):
        list(memo.stream_memo("numbers"))


def test_claude_code_route_sends_data_on_stdin_and_hides_api_key(monkeypatch):
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="  The memo.  ", stderr="")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "would-be-billed")
    monkeypatch.setattr(memo.subprocess, "run", fake_run)
    assert memo.write_with_claude_code("numbers") == "The memo."
    assert seen["command"][0].endswith("claude") and seen["command"][1] == "-p"
    assert seen["input"] == "numbers"
    assert "ANTHROPIC_API_KEY" not in seen["env"]


def test_claude_code_failure_is_reported(monkeypatch):
    monkeypatch.setattr(memo.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="not signed in"))
    with pytest.raises(memo.MemoError, match="not signed in"):
        memo.write_with_claude_code("numbers")


def test_chat_prompt_contains_instructions_and_data():
    text = memo.prompt_for_chat("the numbers")
    assert "do not give a buy, sell or hold" in text and "the numbers" in text


def test_public_demo_keeps_each_visitors_data_off_the_disk(tmp_path, monkeypatch):
    # Two visitors to the hosted demo: neither sees the other's saves, and
    # nothing is written to the shared folder.
    first, second = {}, {}
    monkeypatch.setattr(store, "_visitor_data", lambda: first)
    store.add_to_watchlist("AAPL")
    store.save_assumptions("AAPL", {"wacc": 0.09})
    store.save_memo("AAPL", "A memo.")
    assert store.get_watchlist() == ["AAPL"]
    assert store.get_memo("AAPL") == "A memo."

    monkeypatch.setattr(store, "_visitor_data", lambda: second)
    assert store.get_watchlist() == []
    assert store.get_assumptions("AAPL") is None
    assert store.get_memo("AAPL") is None
    assert list(tmp_path.iterdir()) == []
