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


# An 8-K is the form a company files when something happens that investors
# should know about. Each one lists numbered "items" saying what kind of news it is.
ANNOUNCEMENT_TYPES = {
    "2.02": "Results announced",
    "1.01": "Major agreement signed",
    "1.02": "Major agreement ended",
    "1.03": "Bankruptcy",
    "1.05": "Cybersecurity incident",
    "2.01": "Acquisition or sale completed",
    "2.03": "New debt taken on",
    "2.05": "Restructuring or job cuts",
    "2.06": "Asset write-down",
    "3.01": "Stock exchange listing warning",
    "4.01": "Auditor changed",
    "4.02": "Earlier financial statements withdrawn",
    "5.02": "Director or executive change",
    "5.03": "Bylaws changed",
    "5.07": "Shareholder vote results",
    "7.01": "Investor update",
    "8.01": "Other news",
}
EARNINGS_ITEM = "2.02"


def get_announcements(cik: int, limit: int = 15) -> list:
    """The company's latest announcements (8-K filings), newest first.

    Each has the date, a plain description of what it was, whether it was a
    results announcement, and a link to the document.
    """
    raw = fetch_json(PROFILE_URL.format(cik=cik), f"profile_{cik}", config.FILINGS_MAX_AGE)
    recent = raw.get("filings", {}).get("recent", {})
    announcements = []
    for form, filed, accession, document, items in zip(
        recent.get("form", []),
        recent.get("filingDate", []),
        recent.get("accessionNumber", []),
        recent.get("primaryDocument", []),
        recent.get("items", []),
    ):
        if form != "8-K":
            continue
        codes = [code.strip() for code in (items or "").split(",")]
        kinds = [ANNOUNCEMENT_TYPES[code] for code in codes if code in ANNOUNCEMENT_TYPES]
        announcements.append(
            {
                "filed": filed,
                "what": ", ".join(dict.fromkeys(kinds)) or "Other news",
                "is_earnings": EARNINGS_ITEM in codes,
                "url": "https://www.sec.gov/Archives/edgar/data/"
                f"{cik}/{accession.replace('-', '')}/{document}",
            }
        )
        if len(announcements) == limit:
            break
    return announcements
