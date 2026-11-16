"""The "at a glance" strip above the tabs: the handful of numbers that matter most."""

import pandas as pd

from research import checks, comps

from . import style
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
    sentences = []

    if dcf_output:
        result = dcf_output[0]
        if result["value_per_share"] <= 0:
            # A negative answer means the forecast never earns enough to cover the
            # debt. "X% below the price" would be meaningless, so say it plainly.
            items.append({"label": "DCF value per share", "value": "None",
                          "note": "no value on these assumptions", "tone": "down", "own": True})
            sentences.append("the base-case DCF finds no value in the shares on the current "
                             "assumptions (usually because recent margins are negative)")
        else:
            note, tone = _against_price(result["value_per_share"], price)
            items.append({"label": "DCF value per share", "value": dollars(result["value_per_share"]),
                          "note": note, "tone": tone, "own": True})
            sentences.append(f"the base-case DCF values the shares at "
                             f"{dollars(result['value_per_share'])}, {note}")
        if result["implied_growth"] is not None:
            items.append({"label": "Price implies growth of", "value": percent(result["implied_growth"]),
                          "note": "sales growth needed next year", "own": True})
    elif bank_output:
        result = bank_output["result"]
        note, tone = _against_price(result["value_by_book"], price)
        items.append({"label": "Value on book and returns", "value": dollars(result["value_by_book"]),
                      "note": note, "tone": tone, "own": True})
        sentences.append(f"its book value and return on equity support {dollars(result['value_by_book'])} "
                         f"a share, {note}")

    peers = peer_value(data, comps_result)
    if peers:
        value, name = peers
        note, tone = _against_price(value, price)
        items.append({"label": "Peers imply", "value": dollars(value),
                      "note": note, "tone": tone, "own": True})
        sentences.append(f"peer {name} multiples imply {dollars(value)}, {note}")

    results = checks.run(data)
    good = sum(r["status"] == checks.GOOD for r in results)
    weak = sum(r["status"] == checks.WEAK for r in results)
    items.append({"label": "Health check", "value": f"{good} of {len(results)} good",
                  "note": f"{weak} weak" if weak else "no weak spots",
                  "tone": "down" if weak else "up", "own": True})

    style.cards(items)
    if sentences:
        style.verdict(f"At {dollars(price)}: " + "; ".join(sentences) + ". "
                      "These come from the assumptions and peers set in the gold tabs, "
                      "so change those to test the conclusion.")
