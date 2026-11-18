"""Leveraged buyout (LBO) model.

A private equity firm buys a company mostly with borrowed money, uses the
company's own cash flow to pay that debt down for a few years, then sells.
Its return comes from three places:

  1. the business growing its profit,
  2. selling at a higher multiple of profit than it paid, and
  3. the debt being paid off, so more of the sale price belongs to the owner.

For a share investor the model answers a different question: what could a
financial buyer afford to pay for this company? That is a floor of sorts
under the share price, and one more check on the DCF and the peer comparison.
"""

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass
class Base:
    """The company as it stands today."""
    revenue: float     # last twelve months
    ebitda: float      # last twelve months
    net_debt: float    # existing debt minus cash, repaid as part of the deal
    shares: float
    price: float


@dataclass
class Assumptions:
    premium: float        # how far above today's share price the buyer bids
    leverage: float       # new debt, as a multiple of EBITDA
    interest_rate: float  # on that debt
    fees_pct: float       # bankers, lawyers and lenders, as a share of the deal value
    years: int            # how long the buyer holds the company
    growth_start: float   # revenue growth in year 1
    growth_end: float     # revenue growth in the final year
    ebitda_margin: float
    tax_rate: float
    da_pct: float         # depreciation & amortisation, share of revenue
    capex_pct: float
    nwc_pct: float        # working capital needed per extra dollar of revenue
    exit_multiple: float  # EV / EBITDA the company is sold at

    def to_dict(self) -> dict:
        return asdict(self)


def entry(base: Base, a: Assumptions) -> dict:
    """What the buyer pays and how the purchase is funded."""
    offer_price = base.price * (1 + a.premium)
    equity_price = offer_price * base.shares
    # The buyer also takes on the company's existing debt (net of its cash)
    # and refinances it, so the full cost is the enterprise value.
    enterprise_value = equity_price + base.net_debt
    fees = enterprise_value * a.fees_pct
    debt = a.leverage * base.ebitda
    sponsor_equity = enterprise_value + fees - debt
    return {
        "offer_price": offer_price,
        "equity_price": equity_price,
        "enterprise_value": enterprise_value,
        "entry_multiple": enterprise_value / base.ebitda,
        "fees": fees,
        "debt": debt,
        "sponsor_equity": sponsor_equity,
        "debt_share": debt / (enterprise_value + fees),
    }


def project(base: Base, a: Assumptions, opening_debt: float) -> pd.DataFrame:
    """Year by year: profit, interest, the cash left over and the debt it repays."""
    rows = []
    revenue, debt, cash = base.revenue, opening_debt, 0.0
    for year in range(1, a.years + 1):
        progress = (year - 1) / (a.years - 1) if a.years > 1 else 1.0
        growth = a.growth_start + (a.growth_end - a.growth_start) * progress
        previous, revenue = revenue, revenue * (1 + growth)

        ebitda = revenue * a.ebitda_margin
        d_and_a = revenue * a.da_pct
        ebit = ebitda - d_and_a
        # Interest is charged on the debt owed at the start of the year.
        interest = debt * a.interest_rate
        pretax = ebit - interest
        tax = max(pretax, 0.0) * a.tax_rate
        net_income = pretax - tax

        capex = revenue * a.capex_pct
        working_capital = (revenue - previous) * a.nwc_pct
        free_cash_flow = net_income + d_and_a - capex - working_capital

        # Every spare dollar repays debt. A shortfall is borrowed, and once
        # the debt is gone the cash simply builds up.
        opening = debt
        repaid = min(free_cash_flow, debt)
        debt -= repaid
        cash += free_cash_flow - repaid

        rows.append({
            "year": year, "growth": growth, "revenue": revenue, "ebitda": ebitda,
            "d_and_a": d_and_a, "ebit": ebit, "interest": interest, "tax": tax,
            "net_income": net_income, "capex": capex, "working_capital_change": working_capital,
            "free_cash_flow": free_cash_flow, "debt_start": opening, "debt_repaid": repaid,
            "debt_end": debt, "cash_end": cash,
            "leverage": debt / ebitda if ebitda > 0 else float("nan"),
            "interest_cover": ebitda / interest if interest > 0 else float("nan"),
        })
    return pd.DataFrame(rows).set_index("year")


def run(base: Base, a: Assumptions) -> dict:
    """The whole buyout: entry, the holding period, the sale and the return."""
    if base.ebitda <= 0:
        raise ValueError("A buyout borrows against EBITDA, and this company's is not positive.")
    deal = entry(base, a)
    if deal["sponsor_equity"] <= 0:
        raise ValueError("The debt is larger than the purchase price. Lower the leverage.")

    schedule = project(base, a, deal["debt"])
    final = schedule.iloc[-1]

    exit_value = a.exit_multiple * final["ebitda"]
    exit_equity = exit_value - final["debt_end"] + final["cash_end"]

    # Money multiple: what the buyer gets back per dollar put in.
    # IRR: the yearly return that turns the money in into the money out.
    multiple = max(exit_equity, 0.0) / deal["sponsor_equity"]
    irr = multiple ** (1 / a.years) - 1 if multiple > 0 else -1.0

    # Where the gain came from. The three parts and the fees add up exactly
    # to the gain.
    from_growth = (final["ebitda"] - base.ebitda) * deal["entry_multiple"]
    from_multiple = (a.exit_multiple - deal["entry_multiple"]) * final["ebitda"]
    from_debt = deal["debt"] - final["debt_end"] + final["cash_end"]
    return {
        **deal,
        "schedule": schedule,
        "exit_ebitda": final["ebitda"],
        "exit_value": exit_value,
        "exit_debt": final["debt_end"],
        "exit_cash": final["cash_end"],
        "exit_equity": exit_equity,
        "money_multiple": multiple,
        "irr": irr,
        "gain": exit_equity - deal["sponsor_equity"],
        "gain_from_growth": from_growth,
        "gain_from_multiple": from_multiple,
        "gain_from_debt": from_debt,
        "gain_lost_to_fees": -deal["fees"],
        "min_interest_cover": schedule["interest_cover"].min(),
    }


def affordable_price(base: Base, a: Assumptions, target_irr: float) -> float:
    """The highest share price a buyer could pay and still earn `target_irr`.

    The debt and the eventual sale price don't depend on what the buyer pays,
    so this works backwards: the sale proceeds, discounted at the target
    return, are the most equity the buyer can put in. Add the debt, take off
    fees and the company's existing net debt, and divide by the share count.
    """
    schedule = project(base, a, a.leverage * base.ebitda)
    final = schedule.iloc[-1]
    exit_equity = a.exit_multiple * final["ebitda"] - final["debt_end"] + final["cash_end"]
    most_equity = max(exit_equity, 0.0) / (1 + target_irr) ** a.years
    enterprise_value = (most_equity + a.leverage * base.ebitda) / (1 + a.fees_pct)
    return (enterprise_value - base.net_debt) / base.shares


def sensitivity(base: Base, a: Assumptions) -> pd.DataFrame:
    """Yearly return for a grid of bid premiums (rows) and exit multiples (columns)."""
    premiums = [round(max(a.premium + step, 0.0), 4) for step in (-0.20, -0.10, 0.0, 0.10, 0.20)]
    premiums = list(dict.fromkeys(premiums))
    multiples = [a.exit_multiple * scale for scale in (0.8, 0.9, 1.0, 1.1, 1.2)]
    grid = {}
    for multiple in multiples:
        column = []
        for premium in premiums:
            trial = Assumptions(**{**a.to_dict(), "premium": premium, "exit_multiple": multiple})
            try:
                column.append(run(base, trial)["irr"])
            except ValueError:
                column.append(float("nan"))
        grid[multiple] = column
    table = pd.DataFrame(grid, index=premiums)
    table.index.name, table.columns.name = "premium", "exit_multiple"
    return table


def default_assumptions(base: Base, dcf_assumptions, risk_free: float) -> Assumptions:
    """A conventional starting structure, using the DCF's operating assumptions.

    Five times EBITDA of debt is a typical buyout, but never more than 60% of
    the price, and the company is assumed to be sold at the multiple it was
    bought at, so the return isn't flattered by a rising multiple.
    """
    premium = 0.30
    entry_multiple = (base.price * (1 + premium) * base.shares + base.net_debt) / base.ebitda
    growth_start = dcf_assumptions.growth_start
    return Assumptions(
        premium=premium,
        leverage=round(min(5.0, 0.6 * entry_multiple), 1),
        interest_rate=risk_free + 0.04,
        fees_pct=0.02,
        years=5,
        growth_start=growth_start,
        # The DCF fades growth over ten years; five years in, it is halfway there.
        growth_end=(growth_start + dcf_assumptions.growth_end) / 2,
        ebitda_margin=dcf_assumptions.ebit_margin + dcf_assumptions.da_pct,
        tax_rate=dcf_assumptions.tax_rate,
        da_pct=dcf_assumptions.da_pct,
        capex_pct=dcf_assumptions.capex_pct,
        nwc_pct=dcf_assumptions.nwc_pct,
        exit_multiple=round(entry_multiple, 1),
    )
