"""Merger model: does buying another company raise or lower earnings per share?

When one company buys another it pays with cash (usually borrowed), with its
own new shares, or a mix. Afterwards the two sets of profits are added
together and divided among more shares. If earnings per share go up the deal
is "accretive"; if they go down it is "dilutive".

Accretion is arithmetic, not proof of a good deal: a company with a high P/E
can make almost any purchase look accretive by paying in shares. The model is
useful for seeing what a deal's terms imply and how much in cost savings
("synergies") it needs to work.
"""

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass
class Company:
    ticker: str
    name: str
    price: float
    shares: float
    net_income: float   # last twelve months
    net_debt: float
    ebitda: float

    @property
    def eps(self) -> float:
        return self.net_income / self.shares


@dataclass
class Deal:
    premium: float       # bid above the target's share price
    stock_share: float   # part of the price paid in new shares (0 = all cash, 1 = all shares)
    debt_rate: float     # interest on money borrowed for the cash part
    synergies: float     # yearly cost savings or extra profit, before tax
    tax_rate: float

    def to_dict(self) -> dict:
        return asdict(self)


def run(acquirer: Company, target: Company, deal: Deal) -> dict:
    if acquirer.net_income <= 0:
        raise ValueError(f"{acquirer.ticker} is loss-making, so a change in its earnings per "
                         "share isn't a meaningful test of a deal.")
    if min(acquirer.price, target.price, acquirer.shares, target.shares) <= 0:
        raise ValueError("Both companies need a share price and a share count.")

    offer_price = target.price * (1 + deal.premium)
    equity_value = offer_price * target.shares
    stock_paid = equity_value * deal.stock_share
    cash_paid = equity_value - stock_paid

    # The share part: new shares handed to the target's owners.
    new_shares = stock_paid / acquirer.price
    # The cash part: borrowed, so it costs interest, less the tax that interest saves.
    interest_after_tax = cash_paid * deal.debt_rate * (1 - deal.tax_rate)
    synergies_after_tax = deal.synergies * (1 - deal.tax_rate)

    combined_income = (acquirer.net_income + target.net_income
                       + synergies_after_tax - interest_after_tax)
    combined_shares = acquirer.shares + new_shares
    combined_eps = combined_income / combined_shares

    # The synergies at which earnings per share come out exactly unchanged.
    # Below zero means the deal is accretive with no synergies at all.
    income_needed = acquirer.eps * combined_shares
    breakeven = (income_needed - (acquirer.net_income + target.net_income - interest_after_tax)) \
        / (1 - deal.tax_rate)

    combined_net_debt = acquirer.net_debt + target.net_debt + cash_paid
    combined_ebitda = acquirer.ebitda + target.ebitda + deal.synergies
    return {
        "offer_price": offer_price,
        "equity_value": equity_value,
        "enterprise_value": equity_value + target.net_debt,
        "cash_paid": cash_paid,
        "stock_paid": stock_paid,
        "new_shares": new_shares,
        "interest_after_tax": interest_after_tax,
        "synergies_after_tax": synergies_after_tax,
        "combined_income": combined_income,
        "combined_shares": combined_shares,
        "acquirer_eps": acquirer.eps,
        "combined_eps": combined_eps,
        "accretion": combined_eps / acquirer.eps - 1,
        "breakeven_synergies": breakeven,
        # The rule of thumb behind the answer: in an all-share deal, buying a
        # company on a lower P/E than your own raises earnings per share.
        "acquirer_pe": acquirer.price / acquirer.eps,
        "target_pe_paid": equity_value / target.net_income if target.net_income > 0 else None,
        "target_ownership": new_shares / combined_shares,
        "combined_net_debt": combined_net_debt,
        "combined_leverage": combined_net_debt / combined_ebitda if combined_ebitda > 0 else None,
        # What each way of paying costs, as a yearly rate after tax.
        "cost_of_debt": deal.debt_rate * (1 - deal.tax_rate),
        "cost_of_shares": acquirer.eps / acquirer.price,
        "target_earnings_yield": target.net_income / equity_value,
    }


def sensitivity(acquirer: Company, target: Company, deal: Deal) -> pd.DataFrame:
    """Change in earnings per share for a grid of premiums (rows) and share/cash mixes (columns)."""
    premiums = list(dict.fromkeys(round(max(deal.premium + step, 0.0), 4) for step in (-0.20, -0.10, 0.0, 0.10, 0.20)))
    mixes = [0.0, 0.25, 0.5, 0.75, 1.0]
    grid = {
        mix: [run(acquirer, target, Deal(**{**deal.to_dict(), "premium": premium, "stock_share": mix}))
              ["accretion"] for premium in premiums]
        for mix in mixes
    }
    table = pd.DataFrame(grid, index=premiums)
    table.index.name, table.columns.name = "premium", "stock_share"
    return table
