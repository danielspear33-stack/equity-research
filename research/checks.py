"""A quick health check: the questions to ask of any company, answered from its numbers.

Each check is a rule of thumb with a stated threshold. None is a verdict on
its own, and none says anything about whether the share price is fair. They
are here so the weak spots stand out before you read the detail.
"""

import pandas as pd

GOOD, WATCH, WEAK, UNKNOWN = "good", "watch", "weak", "unknown"


def _known(*values) -> bool:
    return all(v is not None and not pd.isna(v) for v in values)


def _check(question, status, detail):
    return {"question": question, "status": status, "detail": detail}


def _band(value, good, watch, higher_is_better=True):
    if not _known(value):
        return UNKNOWN
    if higher_is_better:
        return GOOD if value >= good else WATCH if value >= watch else WEAK
    return GOOD if value <= good else WATCH if value <= watch else WEAK


def run(report: dict) -> list:
    """Return the checks as a list of {question, status, detail}."""
    s, m = report["statements"], report["metrics"]
    latest_s, latest_m = report["latest"]["statements"], report["latest"]["metrics"]
    period = report["latest"]["label"]
    financial = report["profile"]["is_financial"]
    checks = []

    # 1. Growth.
    growth = latest_m["revenue_growth"]
    if not _known(growth):
        growth = m["revenue_growth"].iloc[-1]
    checks.append(_check(
        "Are sales growing?", _band(growth, 0.05, 0.0),
        f"Revenue changed {growth:+.1%} over the {period}." if _known(growth)
        else "Revenue growth isn't available from the filings."))

    # 2. Profit.
    income = latest_s["net_income"]
    checks.append(_check(
        "Is it profitable?",
        UNKNOWN if not _known(income) else GOOD if income > 0 else WEAK,
        f"Net income was ${income / 1e9:,.1f}B over the {period}." if _known(income)
        else "Net income isn't available."))

    if financial:
        roe = latest_m["return_on_equity"]
        checks.append(_check(
            "Does it earn a good return on shareholders' money?", _band(roe, 0.12, 0.08),
            f"Return on equity is {roe:.1%}. Around 10% is what investors typically require."
            if _known(roe) else "Return on equity isn't available."))
        dividends = latest_s.get("dividends_paid")
        if _known(dividends, income) and income > 0:
            payout = dividends / income
            checks.append(_check(
                "Is the dividend comfortably covered by profit?",
                _band(payout, 0.5, 0.8, higher_is_better=False),
                f"Dividends took {payout:.0%} of profit."))
    else:
        # 3. Cash.
        cash_flow = latest_m["free_cash_flow"]
        checks.append(_check(
            "Does it generate cash after reinvesting?",
            UNKNOWN if not _known(cash_flow) else GOOD if cash_flow > 0 else WEAK,
            f"Free cash flow was ${cash_flow / 1e9:,.1f}B over the {period}." if _known(cash_flow)
            else "Free cash flow isn't available."))

        # 4. Is reported profit turning into cash? Over three years to smooth out timing.
        recent = s.tail(3)
        profit, cash = recent["net_income"].sum(), recent["cash_from_operations"].sum()
        if _known(profit, cash) and profit > 0:
            conversion = cash / profit
            checks.append(_check(
                "Is profit backed by cash?", _band(conversion, 1.0, 0.8),
                f"Over the last {len(recent)} fiscal years, cash from operations was "
                f"{conversion:.0%} of net income. Well under 100% can mean profit is flattered "
                "by accounting."))

        # 5. Margin direction.
        margins = m["operating_margin"].dropna()
        if len(margins) >= 4 and _known(latest_m["operating_margin"]):
            now, before = latest_m["operating_margin"], margins.iloc[-4:-1].mean()
            change = now - before
            checks.append(_check(
                "Are profit margins holding up?", _band(change, 0.0, -0.02),
                f"Operating margin is {now:.1%}, against an average of {before:.1%} over the "
                "three fiscal years before."))

        # 6. Returns on capital.
        roic = latest_m["return_on_invested_capital"]
        checks.append(_check(
            "Does it earn good returns on the money invested in it?", _band(roic, 0.12, 0.07),
            f"Return on invested capital is {roic:.1%}. Above roughly 10% usually means the "
            "business creates value as it grows." if _known(roic)
            else "Return on invested capital can't be worked out (invested capital is negative "
                 "or missing)."))

        # 7. Debt.
        net_debt, ebitda = latest_m["net_debt"], latest_m["ebitda"]
        if _known(net_debt) and net_debt <= 0:
            checks.append(_check("Is debt manageable?", GOOD,
                                 f"It holds ${-net_debt / 1e9:,.1f}B more cash than debt."))
        elif _known(net_debt, ebitda) and ebitda > 0:
            years = net_debt / ebitda
            checks.append(_check(
                "Is debt manageable?", _band(years, 2.0, 4.0, higher_is_better=False),
                f"Net debt is {years:.1f} times a year's EBITDA. Above about 4 times is heavy."))
        else:
            checks.append(_check("Is debt manageable?", UNKNOWN if not _known(net_debt) else WEAK,
                                 "It has net debt and no positive EBITDA to pay it down with."
                                 if _known(net_debt) else "Debt figures aren't available."))

        # 8. Interest cover.
        interest, operating = latest_s.get("interest_expense"), latest_s["operating_income"]
        if _known(interest, operating) and interest > 0:
            cover = operating / interest
            checks.append(_check(
                "Can it comfortably pay its interest?", _band(cover, 6.0, 2.5),
                f"Operating profit covers the interest bill {cover:.1f} times."))

        # 9. Stock-based pay.
        stock_comp, revenue = latest_s.get("stock_comp"), latest_s["revenue"]
        if _known(stock_comp, revenue) and revenue > 0:
            share = stock_comp / revenue
            checks.append(_check(
                "Is pay in shares kept modest?", _band(share, 0.05, 0.12, higher_is_better=False),
                f"Stock-based pay is {share:.1%} of revenue. It is a real cost that free cash "
                "flow leaves out."))

    # 10. Share count, for everyone.
    shares = s["diluted_shares"].dropna()
    if len(shares) >= 4:
        yearly = (shares.iloc[-1] / shares.iloc[-4]) ** (1 / 3) - 1
        checks.append(_check(
            "Is your slice of the company being protected?",
            _band(yearly, 0.005, 0.03, higher_is_better=False),
            f"The share count has changed {yearly:+.1%} a year over three years. A falling "
            "count (buybacks) grows each share's slice; a rising one shrinks it."))
    return checks
