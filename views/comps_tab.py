"""Comps tab: pick peers, compare multiples, see what they imply."""

import altair as alt
import pandas as pd
import streamlit as st

from research import comps, store

from . import style
from .formatting import dollars, money, multiple, percent


# What the chart can compare: label, scale for the axis, axis number format,
# and how to write the figure in a sentence.
COMPARED = {
    "ev_to_ebitda": ("EV / EBITDA", 1, ".1f", multiple),
    "ev_to_sales": ("EV / Sales", 1, ".1f", multiple),
    "price_to_earnings": ("P/E", 1, ".1f", multiple),
    "revenue_growth": ("Revenue growth", 1, "+.0%", percent),
    "operating_margin": ("Operating margin", 1, ".0%", percent),
    "return_on_invested_capital": ("Return on invested capital", 1, ".0%", percent),
    "market_cap": ("Market value ($B)", 1e-9, ",.0f", money),
}
# For banks and insurers the enterprise-value multiples and margins don't apply.
FINANCIAL_CHOICES = ["price_to_earnings", "revenue_growth", "market_cap"]
COMPARED_NOTES = {
    "ev_to_ebitda": "A company trading above the line is priced more richly than its peers.",
    "ev_to_sales": "A company trading above the line is priced more richly than its peers.",
    "price_to_earnings": "A company trading above the line is priced more richly than its peers.",
    "revenue_growth": "Faster growth is the usual reason for a higher multiple.",
    "operating_margin": "Higher margins are the other usual reason for a higher multiple.",
    "return_on_invested_capital": "How much profit each dollar put into the business earns.",
    "market_cap": "Size matters when choosing peers: very different sizes are weaker comparisons.",
}


def render(data: dict, load_comps):
    """Draw the tab. Returns the comps result, or None if there are no peers."""
    ticker = data["ticker"]
    group, suggested = comps.suggest_peers(ticker)
    saved = store.get_peers(ticker)
    key = f"{ticker}_peers"
    if key not in st.session_state:
        st.session_state[key] = ", ".join(saved if saved is not None else suggested)

    style.own_analysis("What investors pay for similar companies, and what that implies for this one.")
    st.caption(
        "Peers decide the answer here, so choose them deliberately. "
        + (f"Suggested from the built-in group “{group}”." if suggested
           else "No built-in suggestion for this company: type the tickers of similar businesses.")
    )
    cols = st.columns([5, 1, 1])
    cols[0].text_input("Peer tickers, separated by commas", key=key)
    peers = [p.strip().upper() for p in st.session_state[key].split(",") if p.strip()]
    peers = [p for p in dict.fromkeys(peers) if p != ticker]
    cols[1].write("")
    cols[2].write("")
    if cols[1].button("Save peers", key=f"{ticker}_save_peers"):
        store.save_peers(ticker, peers)
        st.toast("Peers saved.")
    if cols[2].button("Use suggested", key=f"{ticker}_reset_peers"):
        st.session_state[key] = ", ".join(suggested)
        st.rerun()

    if not peers:
        st.info("Add at least two peers to run the comparison.")
        return None

    with st.spinner("Loading peers…"):
        result = load_comps(ticker, tuple(peers))
    for peer, error in result["errors"].items():
        st.warning(f"{peer} was left out: {error}")
    if result["peers"].empty:
        st.info("None of the peers could be loaded.")
        return None

    # The company itself goes on the top row so it can be read against its peers.
    v, m = data["valuation"], data["latest"]["metrics"]
    own = pd.DataFrame(
        {
            "name": data["profile"]["name"],
            "market_cap": v["market_cap"] if v else None,
            "enterprise_value": v["enterprise_value"] if v else None,
            "ev_to_ebitda": v["ev_to_ebitda"] if v else None,
            "ev_to_sales": v["ev_to_sales"] if v else None,
            "price_to_earnings": v["price_to_earnings"] if v else None,
            "revenue_growth": m["revenue_growth"],
            "operating_margin": m["operating_margin"],
            "return_on_invested_capital": m["return_on_invested_capital"],
        },
        index=[f"{ticker} (this company)"],
    )
    table = pd.concat([own, result["peers"]])
    financial = data["profile"]["is_financial"]
    column = "price_to_earnings" if financial else "ev_to_ebitda"
    summary, implied = result["summary"], result["implied"]

    # 1. What the peers imply, as headline cards.
    if summary.empty:
        st.info("At least two peers with usable multiples are needed for a summary.")
    elif implied.empty:
        st.caption("No implied value: the company's own earnings are negative or missing.")
    else:
        wanted = ["price_to_earnings"] if financial else list(implied.index)
        price = v["price"] if v else None
        st.subheader(f"What peer multiples imply for {ticker}")
        style.cards([
            {"label": f"On peers' median {comps.MULTIPLES[name]}", "own": True,
             "value": dollars(implied.loc[name, "median"]),
             "note": (f"{implied.loc[name, 'median'] / price - 1:+.0%} vs price · " if price else "")
                     + f"range {dollars(implied.loc[name, 'low'])} to {dollars(implied.loc[name, 'high'])}",
             "tone": style.tone(implied.loc[name, "median"] / price - 1) if price else None}
            for name in wanted if name in implied.index
        ] + ([{"label": "Share price today", "value": dollars(price)}] if price else []))
        st.caption("Each range runs from the peers' 25th to 75th percentile multiple.")

    # 2. The comparison as a chart: this company in gold, peers in blue.
    #    A selector switches the chart between everything worth comparing.
    choices = {name: COMPARED[name] for name in
               (FINANCIAL_CHOICES if financial else COMPARED) if table[name].notna().any()}
    if choices:
        chosen = st.segmented_control(
            "Compare on", list(choices), default=column if column in choices else next(iter(choices)),
            format_func=lambda name: choices[name][0], key=f"{ticker}_compare_on",
        ) or column
        label, scale, axis_format, show = choices[chosen]
        bars = (table[chosen].dropna() * scale).rename("value").rename_axis("company").reset_index()
        st.subheader(f"{label}: {ticker} against its peers")
        bars["group"] = bars["company"].str.contains("this company").map({True: "This company", False: "Peer"})
        chart = alt.Chart(bars).mark_bar(cornerRadiusEnd=4, height=22).encode(
            x=alt.X("value:Q", title=label, axis=alt.Axis(format=axis_format)),
            y=alt.Y("company:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
            color=alt.Color("group:N", legend=None,
                            scale=alt.Scale(domain=["This company", "Peer"], range=[style.GOLD, style.BLUE])),
            tooltip=[alt.Tooltip("company:N", title="Company"),
                     alt.Tooltip("value:Q", format=axis_format, title=label)],
        )
        layers = chart
        peers_only = result["peers"][chosen].dropna()
        if len(peers_only) >= 2:
            median = alt.Chart(pd.DataFrame({"median": [peers_only.median() * scale]})).mark_rule(
                color="#e8ecf4", strokeDash=[5, 4]).encode(x="median:Q")
            layers = chart + median
        st.altair_chart(layers.properties(height=60 + 34 * len(bars)), width="stretch")
        note = f"The dashed line is the peer median of {show(peers_only.median())}. " if len(peers_only) >= 2 else ""
        st.caption(note + COMPARED_NOTES.get(chosen, ""))

    # 3. The full numbers, one click away.
    shown = pd.DataFrame(
        {
            "Company": table["name"],
            "Market cap": table["market_cap"].map(money),
            "EV / EBITDA": table["ev_to_ebitda"].map(multiple),
            "EV / Sales": table["ev_to_sales"].map(multiple),
            "P/E": table["price_to_earnings"].map(multiple),
            "Revenue growth": table["revenue_growth"].map(percent),
            "Operating margin": table["operating_margin"].map(percent),
            "ROIC": table["return_on_invested_capital"].map(percent),
        }
    )
    with st.expander("Every company's numbers", expanded=summary.empty):
        st.dataframe(shown, width="stretch")
    if not summary.empty:
        with st.expander("Peer multiples: 25th percentile, median and 75th"):
            st.dataframe(
                pd.DataFrame(
                    {
                        "25th percentile": summary["low"].map(multiple),
                        "Median": summary["median"].map(multiple),
                        "75th percentile": summary["high"].map(multiple),
                        "Peers used": summary["peers_used"].astype(int),
                    }
                ).rename(index=comps.MULTIPLES),
                width="stretch",
            )
    if financial:
        st.caption("For a financial company only P/E is meaningful, so only that is used.")
    return result
