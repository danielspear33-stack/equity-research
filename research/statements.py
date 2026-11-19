"""Turns the SEC's raw "company facts" into one clean table of annual figures.

Companies label each number in their filings with a standard tag, but different
companies (and the same company in different years) use different tags for the
same idea. For each line we care about, we list the tags to try, in order.
"""

from datetime import date

import pandas as pd

# Figures measured over a full year (income statement and cash flow statement).
FLOW_TAGS = {
    "revenue": [
        # Tags in brackets are alternatives for the same line where one can be
        # a part of another, so the largest is the total. Pfizer, for example,
        # tags its product sales and its total revenue, and only the second
        # includes income from partnerships.
        ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"),
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        # Banks and brokers report revenue after the interest they pay out.
        "RevenuesNetOfInterestExpense",
    ],
    "cost_of_revenue": [("CostOfGoodsAndServicesSold", "CostOfRevenue")],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "income_tax": ["IncomeTaxExpenseBenefit"],
    "net_income": ["NetIncomeLoss"],
    "d_and_a": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAmortizationAndOther",
    ],
    # Used only when a company reports the two halves of D&A separately.
    "depreciation": ["Depreciation"],
    "amortization": ["AmortizationOfIntangibleAssets"],
    "cash_from_operations": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "interest_expense": [
        "InterestExpense",
        "InterestExpenseNonoperating",
        "InterestAndDebtExpense",
        "InterestExpenseDebt",
    ],
    "diluted_shares": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ],
    "eps_diluted": ["EarningsPerShareDiluted"],
    # Cash handed back to shareholders, and pay given to staff in shares.
    "dividends_paid": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    "dividends_per_share": [
        "CommonStockDividendsPerShareDeclared",
        "CommonStockDividendsPerShareCashPaid",
    ],
    "stock_comp": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
}

# Figures measured on a single day (balance sheet).
BALANCE_TAGS = {
    "total_assets": ["Assets"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "equity": ["StockholdersEquity"],
    # Used only when the company doesn't tag its own shareholders' equity:
    # the total including outside owners of subsidiaries, and their part of it.
    "equity_with_minorities": ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "minority_interest": ["MinorityInterest"],
    # The total from the debt note in the accounts. Not used as the debt figure
    # (it can cover only some of the borrowings), only to settle an ambiguity below.
    "debt_per_note": ["DebtInstrumentCarryingAmount"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
    # Cash-like holdings sit on up to two separate balance sheet lines.
    "short_term_investments": ["ShortTermInvestments", "OtherShortTermInvestments"],
    "marketable_securities": ["MarketableSecuritiesCurrent", "MarketableSecurities"],
    # A breakdown of the lines above, used only when neither of them is tagged.
    "securities_for_sale": ["AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "debt_noncurrent": [("LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations")],
    "debt_current": [
        # Some companies tag both, with one of them left at zero.
        ("LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"),
        "DebtCurrent",
    ],
    "short_term_borrowings": ["CommercialPaper", "ShortTermBorrowings", "NotesAndLoansPayable"],
    "debt_combined": ["LongTermDebt", "DebtLongtermAndShorttermCombinedAmount"],
    # Assets you can't touch: the premium paid for past acquisitions, brands, patents.
    "goodwill": ["Goodwill"],
    "intangibles": ["IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"],
    # Preferred shares rank ahead of ordinary shareholders, so they are taken
    # out of equity when working out book value per ordinary share.
    "preferred_equity": ["PreferredStockValue", "PreferredStockValueOutstanding"],
}

ANNUAL_FORMS = {"10-K", "10-K/A"}


def _annual_values(facts: dict, tag: str, full_year: bool) -> dict:
    """Return {period end date: value} for one tag, from annual reports only.

    A 10-K repeats prior years for comparison, so the same period can appear
    several times. We keep the most recently filed value, which picks up any
    restatement.
    """
    entry = facts.get("facts", {}).get("us-gaap", {}).get(tag)
    if not entry:
        return {}

    latest = {}  # end date -> (filed date, value)
    for rows in entry["units"].values():
        for row in rows:
            if row.get("form") not in ANNUAL_FORMS:
                continue
            if full_year:
                if "start" not in row:
                    continue
                days = (date.fromisoformat(row["end"]) - date.fromisoformat(row["start"])).days
                if not 340 <= days <= 380:  # skip the quarterly figures inside a 10-K
                    continue
            elif "start" in row:
                continue
            end = row["end"]
            if end not in latest or row["filed"] > latest[end][0]:
                latest[end] = (row["filed"], row["val"])
    return {end: value for end, (_, value) in latest.items()}


def merge_tags(tags: list, values_for) -> dict:
    """Combine candidate tags into one {period: value}, period by period.

    Earlier entries in the list are preferred. An entry that is a bracketed
    group of tags takes the largest of them (see the note on revenue above).
    `values_for` is a function giving one tag's {period: value}.
    """
    merged = {}
    for entry in tags:
        group = entry if isinstance(entry, tuple) else (entry,)
        largest = {}
        for tag in group:
            for period, value in values_for(tag).items():
                if period not in largest or value > largest[period]:
                    largest[period] = value
        for period, value in largest.items():
            merged.setdefault(period, value)
    return merged


def _first_available(facts: dict, tags: list, full_year: bool) -> dict:
    """One line's annual figures, from whichever of its candidate tags the company uses."""
    return merge_tags(tags, lambda tag: _annual_values(facts, tag, full_year))


def build_annual_statements(facts: dict, years: int = 10) -> pd.DataFrame:
    """One row per fiscal year (indexed by year-end date), one column per line."""
    columns = {name: _first_available(facts, tags, True) for name, tags in FLOW_TAGS.items()}
    columns.update(
        {name: _first_available(facts, tags, False) for name, tags in BALANCE_TAGS.items()}
    )

    # The fiscal years are the periods we have revenue or net income for.
    year_ends = sorted(set(columns["revenue"]) | set(columns["net_income"]))
    table = pd.DataFrame(columns, index=year_ends, dtype="float64")
    table = table.reindex(year_ends).tail(years)
    table.index = pd.to_datetime(table.index)
    table.index.name = "fiscal_year_end"
    return adjust_for_splits(add_derived_lines(table))


def adjust_for_splits(table: pd.DataFrame) -> pd.DataFrame:
    """Put share counts from before a stock split on today's basis.

    In a 20-for-1 split every share becomes twenty, so the count jumps
    twentyfold overnight without anything real changing. Companies restate the
    last couple of years in their next report but not older ones, which leaves
    a false jump in the history. A share count that roughly doubles or more
    (or halves or less) in one year is treated as a split, and every earlier
    year is rescaled by the nearest whole ratio.
    """
    shares = table["diluted_shares"]
    factor = pd.Series(1.0, index=table.index)
    known = shares.dropna()
    for earlier, later in zip(known.index[:-1], known.index[1:]):
        ratio = known[later] / known[earlier]
        if ratio >= 1.8:
            split = round(ratio * 2) / 2          # 2, 3, 4 ... and 2.5 for a 5-for-2
        elif ratio <= 0.55:
            split = 1 / round(1 / ratio)          # a reverse split, e.g. 1-for-10
        else:
            continue
        factor[table.index <= earlier] *= split
    table["diluted_shares"] = shares * factor
    for per_share in ("eps_diluted", "dividends_per_share"):
        table[per_share] = table[per_share] / factor
    return table


def add_derived_lines(table: pd.DataFrame) -> pd.DataFrame:
    """Fill in the lines that are worked out from others rather than reported.

    Shared by the annual table and the trailing-twelve-month row, so both are
    built the same way.
    """
    # Gross profit isn't always tagged; it is revenue minus the cost of making the product.
    # A worked-out margin above 80% is not believed: it means the "cost" tag
    # covers only part of the costs (a health insurer's medical bills, say, are
    # tagged elsewhere), and a blank is better than a wrong number.
    worked_out = table["revenue"] - table["cost_of_revenue"]
    table["gross_profit"] = table["gross_profit"].fillna(
        worked_out.where(worked_out <= 0.80 * table["revenue"])
    )

    # Shareholders' equity: when only the total including outside owners of
    # subsidiaries is tagged, take their part off.
    table["equity"] = table["equity"].fillna(
        table["equity_with_minorities"] - table["minority_interest"].fillna(0)
    )

    # Some companies (Exxon, for one) never report operating income. Rebuild an
    # approximation by adding interest cost back to profit before tax.
    table["operating_income"] = table["operating_income"].fillna(
        table["pretax_income"] + table["interest_expense"].fillna(0)
    )

    # Same idea for depreciation and amortization.
    table["d_and_a"] = table["d_and_a"].fillna(
        table[["depreciation", "amortization"]].sum(axis=1, min_count=1)
    )

    # Total debt: add up the pieces if the company reports them separately,
    # otherwise fall back to a single combined figure. This is an approximation:
    # companies tag debt inconsistently, and lease obligations are mostly left out.
    pieces = table[["debt_noncurrent", "debt_current", "short_term_borrowings"]]
    summed = pieces.sum(axis=1, min_count=1)
    # The combined tag is meant to include the part due within a year, but some
    # companies (Tesla, for one) use it for the long-term part only and tag the
    # rest separately. Where the debt note gives a total, use whichever reading
    # lands closer to it.
    combined = table["debt_combined"]
    with_current = combined + table["debt_current"]
    note = table["debt_per_note"]
    closer_with_current = (with_current - note).abs() < (combined - note).abs()
    single_figure = with_current.where(closer_with_current, combined)
    table["total_debt"] = summed.where(table["debt_noncurrent"].notna(), single_figure)
    table["total_debt"] = table["total_debt"].fillna(summed)

    investments = table[["short_term_investments", "marketable_securities"]].sum(axis=1, min_count=1)
    investments = investments.fillna(table["securities_for_sale"])
    table["cash_and_investments"] = pd.concat([table["cash"], investments], axis=1).sum(
        axis=1, min_count=1
    )

    # Operating working capital: money tied up in day-to-day trading (stock,
    # unpaid customer bills) net of what the company owes suppliers. Cash and
    # debt are taken out because they are financing, not operations.
    short_term_debt = table[["debt_current", "short_term_borrowings"]].sum(axis=1).fillna(0)
    table["working_capital"] = (
        table["current_assets"] - table["cash_and_investments"].fillna(0)
    ) - (table["current_liabilities"] - short_term_debt)
    return table


def latest_shares_outstanding(facts: dict, reference: float):
    """The share count from the cover of the newest report, or None if unusable.

    Market value should use the shares that exist today. The cover page of
    each report states that number, and it is more current than the average
    over the period. It is ignored when it is far from the period average,
    which happens for companies with several share classes (the cover figure
    covers only one class) and just after a stock split.
    """
    entry = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding")
    if not entry or reference is None or pd.isna(reference) or reference <= 0:
        return None
    rows = [row for unit in entry["units"].values() for row in unit]
    if not rows:
        return None
    newest = max(rows, key=lambda row: (row["end"], row.get("filed", "")))
    count = float(newest["val"])
    return count if 0.7 <= count / reference <= 1.3 else None
