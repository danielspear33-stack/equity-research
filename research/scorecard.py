"""Five scores out of five that sum a company up at a glance.

  Value          how cheap the price looks against the DCF, peers and cash yield
  Growth         how fast sales are growing
  Profitability  how much of each sales dollar, and each dollar invested, it keeps
  Health         how safely it is financed and whether profit turns into cash
  Payouts        how much it hands back, and whether your slice is growing

Every score is a straight line between a "0" level and a "5" level, written
out below, so a score can always be traced back to the number behind it.
These are rules of thumb for skimming, not verdicts.
"""

import pandas as pd

from . import checks, payouts

NAMES = ["Value", "Growth", "Profitability", "Health", "Payouts"]


def _known(value) -> bool:
    return value is not None and not pd.isna(value)


def _scale(value, zero, five):
    """0 at `zero`, 5 at `five`, a straight line between, capped at both ends."""
    if not _known(value):
        return None
    return float(min(max((value - zero) / (five - zero), 0.0), 1.0) * 5)


def _average(parts: list):
    """Average the parts that could be scored. Each part is (score, description)."""
    scored = [(score, text) for score, text in parts if score is not None]
    if not scored:
        return None, "Not enough data."
    return sum(score for score, _ in scored) / len(scored), "; ".join(text for _, text in scored)


def _value(report, dcf_value, peer_value, bank_value):
    v = report["valuation"]
    if v is None:
        return None, "No share price."
    price, parts = v["price"], []
    # A value 50% above the price scores 5; 50% below scores 0.
    for label, value in (("DCF", dcf_value), ("peers", peer_value), ("book value and returns", bank_value)):
        if _known(value):
            gap = value / price - 1
            parts.append((_scale(gap, -0.5, 0.5), f"{label} value {gap:+.0%} against the price"))
    if report["profile"]["is_financial"]:
        earnings_yield = 1 / v["price_to_earnings"] if _known(v["price_to_earnings"]) else None
        if _known(earnings_yield):
            parts.append((_scale(earnings_yield, 0.0, 0.10), f"earnings yield {earnings_yield:.1%}"))
    elif _known(v["fcf_yield"]):
        parts.append((_scale(v["fcf_yield"], 0.0, 0.075), f"free cash flow yield {v['fcf_yield']:.1%}"))
    return _average(parts)


def _growth(report):
    latest = report["latest"]["metrics"]["revenue_growth"]
    history = report["metrics"]["revenue_growth"].dropna().tail(3)
    three_year = history.mean() if len(history) else None
    return _average([
        (_scale(latest, 0.0, 0.20), f"sales growth {latest:+.1%} over the latest year" if _known(latest) else ""),
        (_scale(three_year, 0.0, 0.20), f"{three_year:+.1%} a year over three years" if _known(three_year) else ""),
    ])


def _profitability(report):
    m = report["latest"]["metrics"]
    if report["profile"]["is_financial"]:
        roe, margin = m["return_on_equity"], m["net_margin"]
        return _average([
            (_scale(roe, 0.0, 0.15), f"return on equity {roe:.1%}" if _known(roe) else ""),
            (_scale(margin, 0.0, 0.30), f"net margin {margin:.1%}" if _known(margin) else ""),
        ])
    margin, roic = m["operating_margin"], m["return_on_invested_capital"]
    return _average([
        (_scale(margin, 0.0, 0.25), f"operating margin {margin:.1%}" if _known(margin) else ""),
        (_scale(roic, 0.0, 0.20), f"return on invested capital {roic:.1%}" if _known(roic) else ""),
    ])


def _health(report):
    results = [r for r in checks.run(report) if r["status"] != checks.UNKNOWN]
    if not results:
        return None, "Not enough data."
    points = {checks.GOOD: 1.0, checks.WATCH: 0.5, checks.WEAK: 0.0}
    score = 5 * sum(points[r["status"]] for r in results) / len(results)
    good = sum(r["status"] == checks.GOOD for r in results)
    weak = sum(r["status"] == checks.WEAK for r in results)
    return score, f"{good} of {len(results)} health checks good, {weak} weak"


def _payouts(report):
    v = report["valuation"]
    now = payouts.today(report["latest"]["statements"], v["market_cap"] if v else None)
    shares = report["statements"]["diluted_shares"].dropna().tail(4)
    yearly_change = None
    if len(shares) >= 2 and shares.iloc[0] > 0:
        yearly_change = (shares.iloc[-1] / shares.iloc[0]) ** (1 / (len(shares) - 1)) - 1
    total = now["shareholder_yield"]
    return _average([
        (_scale(total, 0.0, 0.05), f"dividends plus buybacks {total:.1%} of market value" if _known(total) else ""),
        # A share count shrinking 2% a year scores 5; growing 2% a year scores 0.
        (_scale(yearly_change, 0.02, -0.02),
         f"share count {yearly_change:+.1%} a year" if _known(yearly_change) else ""),
    ])


def scores(report: dict, dcf_value=None, peer_value=None, bank_value=None) -> list:
    """[{"name", "score" (0 to 5, or None), "why"}] for the five measures, in NAMES order."""
    results = [
        _value(report, dcf_value, peer_value, bank_value),
        _growth(report),
        _profitability(report),
        _health(report),
        _payouts(report),
    ]
    return [{"name": name, "score": score, "why": why}
            for name, (score, why) in zip(NAMES, results)]


def overall(results: list):
    """The average of the scores that could be worked out, or None."""
    known = [r["score"] for r in results if r["score"] is not None]
    return sum(known) / len(known) if known else None
