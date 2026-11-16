import pandas as pd

from views import glance, style


def test_gap_to_price_is_described_in_words():
    assert glance._against_price(150, 100) == ("50% above the price", "up")
    assert glance._against_price(60, 100) == ("40% below the price", "down")
    assert glance._against_price(100.2, 100) == ("in line with the price", None)


def _comps(rows):
    return {"implied": pd.DataFrame(rows).T}


def test_peer_value_prefers_ev_to_ebitda_but_uses_pe_for_banks():
    implied = {"ev_to_ebitda": {"low": 8, "median": 10, "high": 12},
               "price_to_earnings": {"low": 18, "median": 20, "high": 22}}
    company = {"profile": {"is_financial": False}}
    bank = {"profile": {"is_financial": True}}
    assert glance.peer_value(company, _comps(implied)) == (10.0, "EV / EBITDA")
    assert glance.peer_value(bank, _comps(implied)) == (20.0, "P/E")
    assert glance.peer_value(company, None) is None
    assert glance.peer_value(company, {"implied": pd.DataFrame()}) is None


def test_tone():
    assert style.tone(0.1) == "up" and style.tone(-0.1) == "down"
    assert style.tone(0) is None and style.tone(None) is None and style.tone(float("nan")) is None
