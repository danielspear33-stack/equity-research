"""The "at a glance" panel above the tabs: a scorecard shape, the price against what the
share might be worth, and the health check as a row of dots."""

import pandas as pd

import streamlit as st

from research import checks, comps, scorecard

from . import style, visuals
from .formatting import dollars, money, multiple, percent


def _against_price(value, price) -> tuple:
    """Describe a value per share against today's price, as (note, tone)."""
    gap = value / price - 1
    if abs(gap) < 0.005:
        return "in line with the price", None
    return f"{abs(gap):.0%} {'above' if gap > 0 else 'below'} the price", style.tone(gap)


def peer_value(data: dict, comps_result):
    """The value per share peers imply, as (value, which multiple), or None.

    Uses EV/EBITDA when available, as it ignores differences in debt, and
    P/E for banks and insurers or when EBITDA is negative.
    """
    if comps_result is None or comps_result["implied"].empty:
        return None
    implied = comps_result["implied"]
    order = ["price_to_earnings"] if data["profile"]["is_financial"] else ["ev_to_ebitda", "price_to_earnings", "ev_to_sales"]
    for name in order:
        if name in implied.index and pd.notna(implied.loc[name, "median"]):
            return float(implied.loc[name, "median"]), comps.MULTIPLES[name]
    return None


HEALTH_LABELS = {checks.GOOD: "Good", checks.WATCH: "Watch", checks.WEAK: "Weak",
                 checks.UNKNOWN: "No data"}


def render(data: dict, dcf_output, comps_result, bank_output) -> None:
    v = data["valuation"]
    if v is None:
        return
    price, history = v["price"], data["price_history"]

    day_change = history.iloc[-1] / history.iloc[-2] - 1 if history is not None and len(history) > 1 else None
    items = [
        {"label": "Share price", "value": dollars(price),
         "note": f"{day_change:+.1%} on the day" if day_change is not None else None,
         "tone": style.tone(day_change)},
        {"label": "Market value", "value": money(v["market_cap"]),
         "note": f"P/E {multiple(v['price_to_earnings'])}"},
    ]
    sentences, marks, band = [], [], None
    dcf_value = bank_value = None

    if dcf_output:
        result = dcf_output[0]
        dcf_value = result["value_per_share"]
        if dcf_value <= 0:
            # A negative answer means the forecast never earns enough to cover the
            # debt. "X% below the price" would be meaningless, so say it plainly.
            items.append({"label": "DCF value per share", "value": "None",
                          "note": "no value on these assumptions", "tone": "down", "own": True})
            sentences.append("the base-case DCF finds no value in the shares on the current "
                             "assumptions (usually because recent margins are negative)")
        else:
            note, tone = _against_price(dcf_value, price)
            items.append({"label": "DCF value per share", "value": dollars(dcf_value),
                          "note": note, "tone": tone, "own": True})
            sentences.append(f"the base-case DCF values the shares at {dollars(dcf_value)}, {note}")
            marks.append({"label": "DCF", "value": dcf_value})
            cases = result["scenarios"]["value_per_share"].dropna()
            if len(cases) == 3 and cases["Bear"] > 0:
                band = (float(cases["Bear"]), float(cases["Bull"]))
        if result["implied_growth"] is not None:
            items.append({"label": "Price implies growth of", "value": percent(result["implied_growth"]),
                          "note": "sales growth needed next year", "own": True})
    elif bank_output:
        result = bank_output["result"]
        bank_value = result["value_by_book"]
        note, tone = _against_price(bank_value, price)
        items.append({"label": "Value on book and returns", "value": dollars(bank_value),
                      "note": note, "tone": tone, "own": True})
        sentences.append(f"its book value and return on equity support {dollars(bank_value)} "
                         f"a share, {note}")
        marks.append({"label": "Book and returns", "value": bank_value})
        marks.append({"label": "Dividends and buybacks", "value": result["value_by_total_payout"]})

    peers = peer_value(data, comps_result)
    if peers:
        value, name = peers
        note, tone = _against_price(value, price)
        items.append({"label": "Peers imply", "value": dollars(value),
                      "note": note, "tone": tone, "own": True})
        sentences.append(f"peer {name} multiples imply {dollars(value)}, {note}")
        marks.append({"label": "Peers", "value": value})

    scores = scorecard.scores(data, dcf_value=dcf_value, peer_value=peers[0] if peers else None,
                              bank_value=bank_value)
    results = checks.run(data)

    shape, numbers = st.columns([1, 2.4], vertical_alignment="center")
    with shape:
        visuals.scorecard(scores, scorecard.overall(scores))
    with numbers:
        style.cards(items)
        visuals.value_bar(price, marks, band)
        visuals.health_dots(results, HEALTH_LABELS)

    with st.expander("What the scores and the bar are saying"):
        if sentences:
            st.write(f"At {dollars(price)}: " + "; ".join(sentences) + ". These come from the "
                     "assumptions and peers set in the gold tabs, so change those to test the conclusion.")
        if band:
            st.caption("The shaded stretch of the bar runs from the DCF's bear case to its bull case.")
        st.markdown("\n".join(
            f"- **{s['name']} {'n/a' if s['score'] is None else format(s['score'], '.1f')}** · {s['why']}"
            for s in scores))
        st.caption("Each score runs from 0 to 5 on a fixed scale (for example, sales growth of "
                   "20% or more scores 5 for Growth, none scores 0). They are for skimming, "
                   "not verdicts.")
