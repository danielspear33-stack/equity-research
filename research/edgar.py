"""Talks to SEC EDGAR, the US regulator's free database of company filings.

Every US-listed company has an ID number called a CIK. We turn a ticker into a
CIK, then download two things for it:
  * the company profile (name, industry code, fiscal year end)
  * "company facts": every number the company has tagged in its filings
"""

import json

import requests

from . import config
from .cache import fetch_json

TICKER_LIST_URL = "https://www.sec.gov/files/company_tickers.json"
PROFILE_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"


class TickerNotFound(Exception):
    pass


def lookup_cik(ticker: str) -> int:
    """Turn a ticker like 'AAPL' into the SEC's company ID."""
    ticker = ticker.strip().upper().replace(".", "-")

    seed = json.loads(config.SEED_TICKERS_FILE.read_text())
    if ticker in seed:
        return seed[ticker]

    try:
        listing = fetch_json(TICKER_LIST_URL, "sec_ticker_list", config.TICKER_LIST_MAX_AGE)
    except requests.HTTPError as error:
        raise TickerNotFound(
            f"{ticker} is not in the built-in list, and the SEC refused to send its "
            f"full ticker list ({error.response.status_code}). Set the SEC_USER_AGENT "
            "environment variable to your name and email, as the SEC requires."
        ) from error

    for row in listing.values():
        if row["ticker"].upper() == ticker:
            return int(row["cik_str"])
    raise TickerNotFound(f"No SEC-registered company found for ticker {ticker}.")


def get_profile(cik: int) -> dict:
    """Company name, industry (SIC) code and description."""
    raw = fetch_json(PROFILE_URL.format(cik=cik), f"profile_{cik}", config.FILINGS_MAX_AGE)
    sic = int(raw["sic"]) if raw.get("sic") else None
    return {
        "name": raw["name"],
        "sic": sic,
        "industry": raw.get("sicDescription", ""),
        # SIC codes 6000-6799 are banks, insurers, brokers and real estate.
        # Their statements work differently, so many standard metrics mislead.
        "is_financial": sic is not None and 6000 <= sic <= 6799,
    }


def get_company_facts(cik: int) -> dict:
    """Every tagged number from the company's filings (a large download)."""
    return fetch_json(FACTS_URL.format(cik=cik), f"facts_{cik}", config.FILINGS_MAX_AGE)


def get_recent_filings(cik: int, forms=("10-K", "10-Q", "8-K"), limit: int = 10) -> list:
    """The company's latest filings of the given types, newest first."""
    raw = fetch_json(PROFILE_URL.format(cik=cik), f"profile_{cik}", config.FILINGS_MAX_AGE)
    recent = raw.get("filings", {}).get("recent", {})
    filings = []
    for form, filed, accession, document in zip(
        recent.get("form", []),
        recent.get("filingDate", []),
        recent.get("accessionNumber", []),
        recent.get("primaryDocument", []),
    ):
        if form in forms:
            filings.append(
                {
                    "form": form,
                    "filed": filed,
                    "accession": accession,
                    "url": "https://www.sec.gov/Archives/edgar/data/"
                    f"{cik}/{accession.replace('-', '')}/{document}",
                }
            )
        if len(filings) == limit:
            break
    return filings
