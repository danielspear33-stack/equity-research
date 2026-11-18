"""Merger model page: pick a buyer and a target, and see what the deal does to earnings per share."""

import pandas as pd
import streamlit as st

from research import edgar, market, merger

from . import style
from .formatting import dollars, money, multiple, percent


def _company(data: dict) -> merger.Company:
    latest, v = data["latest"], data["valuation"]
    if v is None:
        raise ValueError(f"No share price is available for {data['ticker']}.")
    ebitda = latest["metrics"]["ebitda"]
    return merger.Company(
        ticker=data["ticker"], name=data["profile"]["name"], price=float(v["price"]),
        # The share count behind the market value shown elsewhere in the app.
        shares=float(v["market_cap"] / v["price"]),
        net_income=float(latest["statements"]["net_income"]),
        net_debt=float(latest["metrics"]["net_debt"]),
        ebitda=0.0 if pd.isna(ebitda) else float(ebitda),
    )


def _picker(label: str, key: str, companies: list, preset: str):
    """A search box over every listed company. Returns the chosen ticker or None."""
    if key not in st.session_state and preset:
        match = next((i for i, row in enumerate(companies) if row[0] == preset), None)
        st.session_state[key] = match
    picked = st.selectbox(
        label, range(len(companies)), index=None, key=key,
        format_func=lambda i: f"{companies[i][0]} · {companies[i][2]}",
        placeholder="Type a name, e.g. Microsoft", filter_mode="contains",
    )
    return companies[picked][0] if picked is not None else None


def render(load, presets: dict) -> None:
    st.header("Merger model")
    style.own_analysis(
        "Pick a buyer and a target. The model works out what the deal would do to the buyer's "
        "earnings per share, and how much in savings it would need to pay for itself."
    )
    companies = edgar.company_list()
    left, right = st.columns(2)
    with left:
        buyer_ticker = _picker("Buyer", "merger_buyer", companies, presets.get("buyer"))
    with right:
        target_ticker = _picker("Target", "merger_target", companies, presets.get("target"))
    if not buyer_ticker or not target_ticker:
        st.info("Choose both companies to run the model. Try a real announced deal, or any pairing "
                "you're curious about.")
        return
    if buyer_ticker == target_ticker:
        st.info("Choose two different companies.")
        return

    try:
        with st.spinner("Pulling both companies' filings and prices…"):
            buyer_data, target_data = load(buyer_ticker), load(target_ticker)
            buyer, target = _company(buyer_data), _company(target_data)
    except Exception as error:  # noqa: BLE001
        st.error(f"Couldn't load the two companies: {error}")
        return

    risk_free = market.get_risk_free_rate()[0]
    cols = st.columns(5)
    premium = cols[0].number_input("Bid premium (%)", 0.0, 150.0, 30.0, step=5.0,
                                   help="How far above the target's share price the buyer bids.") / 100
    stock_share = cols[1].slider("Paid in new shares (%)", 0, 100, 50, step=5,
                                 help="The rest is paid in cash, which the model assumes is borrowed.") / 100
    debt_rate = cols[2].number_input("Interest on the cash part (%)", 0.0, 20.0,
                                     round((risk_free + 0.02) * 100, 2), step=0.25) / 100
    synergies = cols[3].number_input("Yearly synergies ($ millions)", 0.0, 100000.0, 0.0, step=50.0,
                                     help="Cost savings or extra profit from combining, before tax. "
                                          "Start at zero: they are easy to promise and hard to deliver.") * 1e6
    tax_rate = cols[4].number_input("Tax rate (%)", 0.0, 40.0, 21.0, step=1.0) / 100

    deal = merger.Deal(premium, stock_share, debt_rate, synergies, tax_rate)
    try:
        result = merger.run(buyer, target, deal)
    except ValueError as error:
        st.error(str(error))
        return

    change = result["accretion"]
    word = "accretive" if change > 0 else "dilutive"
    either_financial = buyer_data["profile"]["is_financial"] or target_data["profile"]["is_financial"]
    needed = result["breakeven_synergies"]
    cards = [
        {"label": f"{buyer.ticker} earnings per share", "own": True,
         "value": f"{change:+.1%}", "tone": style.tone(change),
         "note": f"{word}: {dollars(result['acquirer_eps'])} becomes {dollars(result['combined_eps'])}"},
        {"label": f"Bid per {target.ticker} share", "value": dollars(result["offer_price"]),
         "note": f"{money(result['equity_value'])} for all the shares"},
        {"label": "Synergies needed to break even", "own": True,
         "value": money(needed) if needed > 0 else "None",
         "note": "a year, before tax" if needed > 0 else "already accretive without any"},
        {"label": f"{target.ticker} holders would own", "value": percent(result["target_ownership"]),
         "note": f"of the combined company, through {result['new_shares'] / 1e6:,.0f}M new shares"},
    ]
    if not either_financial and result["combined_leverage"] is not None:
        cards.append({"label": "Combined net debt / EBITDA", "value": multiple(result["combined_leverage"]),
                      "note": f"after borrowing {money(result['cash_paid'])}",
                      "tone": "down" if result["combined_leverage"] > 4 else None})
    style.cards(cards)

    # Why it comes out that way, in one sentence.
    paid = result["target_pe_paid"]
    if paid is None:
        reason = (f"{target.ticker} is loss-making, so it adds no profit while the deal adds "
                  "shares and interest: only synergies can make it pay.")
    else:
        reason = (
            f"The bid values {target.ticker} at {paid:.1f} times its earnings, a yield of "
            f"{result['target_earnings_yield']:.1%}. Paying in {buyer.ticker} shares costs "
            f"{result['cost_of_shares']:.1%} (its own earnings yield, at {result['acquirer_pe']:.1f} times "
            f"earnings) and borrowing costs {result['cost_of_debt']:.1%} after tax. "
            "The deal adds to earnings per share when what it buys yields more than the blend "
            "of what it pays with."
        )
    style.verdict(reason)

    left, right = st.columns([2, 3])
    with left:
        st.subheader("How earnings per share change")
        st.dataframe(
            pd.DataFrame({
                "": [f"{buyer.ticker} net income", f"{target.ticker} net income", "Synergies after tax",
                     "Interest on new debt after tax", "Combined net income",
                     f"{buyer.ticker} shares today", "New shares issued", "Combined shares",
                     "Earnings per share before", "Earnings per share after"],
                "Amount": [money(buyer.net_income), money(target.net_income),
                           money(result["synergies_after_tax"]), money(-result["interest_after_tax"]),
                           money(result["combined_income"]),
                           f"{buyer.shares / 1e6:,.0f}M", f"{result['new_shares'] / 1e6:,.0f}M",
                           f"{result['combined_shares'] / 1e6:,.0f}M",
                           dollars(result["acquirer_eps"]), dollars(result["combined_eps"])],
            }),
            hide_index=True, width="stretch",
        )
    with right:
        st.subheader("Sensitivity: change in earnings per share")
        grid = merger.sensitivity(buyer, target, deal)

        def shade(value):
            if pd.isna(value):
                return ""
            strength = min(0.15 + abs(value) * 3, 0.55)
            colour = "78,203,158" if value >= 0 else "226,104,122"
            return f"background-color: rgba({colour},{strength:.2f})"

        table = grid.copy()
        table.index = [f"Bid {p:.0%} above the price" for p in grid.index]
        table.columns = ["All cash" if mix == 0 else "All shares" if mix == 1 else f"{mix:.0%} shares"
                         for mix in grid.columns]
        st.dataframe(table.style.map(shade).format("{:+.1%}"), width="stretch")
        st.caption("Rows are bid premiums, columns are how the price is paid.")

    st.caption(
        "Uses each company's earnings for the last twelve months, not forecasts. Left out for "
        "simplicity: deal fees, interest lost on cash the buyer already holds, and the "
        "accounting charge for acquired intangible assets, each of which would lower the result "
        "a little. A deal can add to earnings per share and still destroy value if the price is too high."
    )
