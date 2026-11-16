"""Comps tab: pick peers, compare multiples, see what they imply."""

import pandas as pd
import streamlit as st

from research import comps, store

from .formatting import dollars, money, multiple, percent


def render(data: dict, load_comps):
    """Draw the tab. Returns the comps result, or None if there are no peers."""
    ticker = data["ticker"]
    group, suggested = comps.suggest_peers(ticker)
    saved = store.get_peers(ticker)
    key = f"{ticker}_peers"
    if key not in st.session_state:
        st.session_state[key] = ", ".join(saved if saved is not None else suggested)

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
    v, m = data["valuation"], data["metrics"].iloc[-1]
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
    st.dataframe(shown, width="stretch")

    if result["summary"].empty:
        st.info("At least two peers with usable multiples are needed for a summary.")
        return result

    left, right = st.columns(2)
    with left:
        st.subheader("Peer multiples")
        summary = result["summary"]
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
    with right:
        st.subheader(f"Implied value per share of {ticker}")
        if result["implied"].empty:
            st.caption("Not available (the company's own earnings are negative or missing).")
        else:
            implied = result["implied"]
            st.dataframe(
                pd.DataFrame(
                    {
                        "At 25th percentile": implied["low"].map(dollars),
                        "At median": implied["median"].map(dollars),
                        "At 75th percentile": implied["high"].map(dollars),
                    }
                ).rename(index=comps.MULTIPLES),
                width="stretch",
            )
            if v:
                st.caption(f"The share price today is {dollars(v['price'])}.")
    if data["profile"]["is_financial"]:
        st.caption("For a financial company, read only the P/E row.")
    return result
