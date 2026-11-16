"""Runs the whole pipeline for one ticker and bundles the results."""

import pandas as pd

from . import comps, dcf, edgar, market, metrics, prices, quarterly, statements, store


def run(ticker: str) -> dict:
    """Filings, statements, metrics, prices and valuation multiples for one company."""
    ticker = ticker.strip().upper()
    cik = edgar.lookup_cik(ticker)
    profile = edgar.get_profile(cik)
    facts = edgar.get_company_facts(cik)
    annual = statements.build_annual_statements(facts)
    if annual.empty:
        raise ValueError(
            f"{profile['name']} has no annual reports (10-K) in SEC data. "
            "Foreign companies that file other forms are not supported yet."
        )
    annual_metrics = metrics.compute_annual_metrics(annual)

    # The most recent twelve months, which is newer than the last annual report
    # for most of the year. Valuation and the DCF start from these.
    latest = quarterly.build_latest(facts, annual)
    latest["metrics"] = metrics.compute_latest_metrics(latest["statements"], annual)
    if latest["is_ttm"]:
        latest["metrics"]["revenue_growth"] = (
            latest["revenue_growth"] if latest["revenue_growth"] is not None else float("nan")
        )
        latest["label"] = f"12 months to {latest['as_of']:%d %b %Y}"
    else:
        latest["label"] = f"fiscal year to {latest['as_of']:%d %b %Y}"

    # Prices come from an unofficial source, so a failure there shouldn't
    # stop us showing everything that comes from the filings.
    try:
        price_history = prices.get_price_history(ticker)
        valuation = metrics.compute_valuation(
            annual, annual_metrics, float(price_history.iloc[-1]),
            latest["statements"], latest["metrics"],
            statements.latest_shares_outstanding(facts, latest["statements"]["diluted_shares"]),
        )
        price_error = None
    except Exception as error:  # noqa: BLE001 - any failure means "no prices today"
        price_history, valuation, price_error = None, None, str(error)

    return {
        "ticker": ticker,
        "cik": cik,
        "profile": profile,
        "statements": annual,
        "metrics": annual_metrics,
        "latest": latest,
        "quarters": quarterly.build_quarters(facts),
        "price_history": price_history,
        "valuation": valuation,
        "price_error": price_error,
        "filings": edgar.get_recent_filings(cik),
        "announcements": edgar.get_announcements(cik),
    }


def dcf_blocker(report: dict):
    """Why a DCF can't sensibly be run for this company, or None if it can."""
    latest = report["latest"]["statements"]
    if report["profile"]["is_financial"]:
        return (
            "A standard DCF doesn't work for banks, insurers and similar companies: debt is "
            "part of their product, so free cash flow and enterprise value aren't meaningful."
        )
    if report["valuation"] is None:
        return "No share price available, so the discount rate and upside can't be worked out."
    if pd.isna(latest["revenue"]) or pd.isna(latest["diluted_shares"]):
        return "The filings are missing revenue or the share count."
    if pd.isna(report["valuation"]["market_cap"]):
        return "Market value couldn't be worked out."
    return None


def dcf_defaults(report: dict) -> tuple:
    """Mechanical starting assumptions and the WACC build-up behind them."""
    risk_free, risk_free_source = market.get_risk_free_rate()
    beta, beta_source = market.get_beta(report["price_history"])
    assumptions, wacc_parts = dcf.default_assumptions(
        report["statements"], report["metrics"], report["valuation"], beta, risk_free
    )
    wacc_parts["risk_free_source"] = risk_free_source
    wacc_parts["beta_source"] = beta_source
    return assumptions, wacc_parts


def dcf_inputs(report: dict) -> tuple:
    """Where the DCF starts from: latest twelve months' revenue, net debt and share count."""
    latest = report["latest"]
    return (latest["statements"]["revenue"], latest["metrics"]["net_debt"],
            latest["statements"]["diluted_shares"])


def run_dcf(report: dict, assumptions: dcf.Assumptions) -> dict:
    """Value the company and add the sensitivity table and upside to today's price."""
    base_revenue, net_debt, shares = dcf_inputs(report)

    result = dcf.value(base_revenue, net_debt, shares, assumptions)
    result["sensitivity"] = dcf.sensitivity(base_revenue, net_debt, shares, assumptions)
    result["scenarios"] = dcf.scenarios(base_revenue, net_debt, shares, assumptions)
    price = report["valuation"]["price"]
    result["upside"] = result["value_per_share"] / price - 1
    result["implied_growth"] = dcf.implied_growth(base_revenue, net_debt, shares, assumptions, price)
    return result


def saved_or_default_assumptions(report: dict) -> dcf.Assumptions:
    saved = store.get_assumptions(report["ticker"])
    if saved:
        return dcf.Assumptions(**saved)
    return dcf_defaults(report)[0]


def run_comps(report: dict, peer_tickers: list) -> dict:
    """Peer multiples and what they imply for this company's share value."""
    table, errors = comps.build_peer_table(peer_tickers, run)
    summary = comps.summarise_multiples(table) if not table.empty else pd.DataFrame()
    implied = (
        comps.implied_values(summary, report["latest"]["statements"].to_frame().T,
                             report["latest"]["metrics"].to_frame().T)
        if not summary.empty
        else pd.DataFrame()
    )
    return {"peers": table, "errors": errors, "summary": summary, "implied": implied}
