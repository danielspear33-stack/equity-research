"""Talks to SEC EDGAR, the US regulator's free database of company filings.

Every US-listed company has an ID number called a CIK. We turn a ticker into a
CIK, then download two things for it:
  * the company profile (name, industry code, fiscal year end)
  * "company facts": every number the company has tagged in its filings
"""

import functools
import json

import requests

from . import config
from .cache import fetch_json

TICKER_LIST_URL = "https://www.sec.gov/files/company_tickers.json"
PROFILE_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"


class TickerNotFound(Exception):
    pass


@functools.lru_cache(maxsize=1)
def company_list() -> list:
    """Every company with shares listed in the US: [ticker, SEC ID, name], biggest first.

    This is the SEC's own list (about 10,000 tickers), saved in the project so
    looking a company up needs no download. The daily refresh keeps it current.
    """
    return json.loads(config.COMPANY_LIST_FILE.read_text())


def update_company_list() -> int:
    """Download the SEC's current list and save it. Returns how many tickers it holds."""
    listing = fetch_json(TICKER_LIST_URL, "sec_ticker_list", config.TICKER_LIST_MAX_AGE)
    rows = [[row["ticker"].upper(), int(row["cik_str"]), row["title"]] for row in listing.values()]
    if len(rows) < 5000:  # a truncated download must not wipe out the saved list
        raise ValueError(f"The SEC's list came back with only {len(rows)} tickers; keeping the old one.")
    lines = ",\n".join(json.dumps(row) for row in rows)
    config.COMPANY_LIST_FILE.write_text(f"[\n{lines}\n]\n")
    company_list.cache_clear()
    return len(rows)


def lookup_cik(ticker: str) -> int:
    """Turn a ticker like 'AAPL' into the SEC's company ID."""
    ticker = ticker.strip().upper().replace(".", "-")

    for listed, cik, _ in company_list():
        if listed == ticker:
            return cik

    # Not in the saved list: it may have listed since the list was last
    # updated, so ask the SEC directly before giving up.
    try:
        listing = fetch_json(TICKER_LIST_URL, "sec_ticker_list", config.TICKER_LIST_MAX_AGE)
    except requests.RequestException as error:
        raise TickerNotFound(
            f"No US-listed company found for ticker {ticker}. (The SEC's live list could not "
            "be checked for very recent listings.)"
        ) from error
    for row in listing.values():
        if row["ticker"].upper() == ticker:
            return int(row["cik_str"])
    raise TickerNotFound(
        f"No US-listed company found for ticker {ticker}. Companies listed only outside the "
        "US are not covered."
    )


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
    """Every tagged number from the company's filings (a large download).

    When a company reorganises under a new holding company it gets a new SEC
    registration, and its ticker moves to that while its history stays filed
    under the old one (Exxon did this in 2026). For the companies listed in
    data/predecessors.json the earlier filings are joined on, so the history
    is whole.
    """
    facts = fetch_json(FACTS_URL.format(cik=cik), f"facts_{cik}", config.FILINGS_MAX_AGE)
    earlier = json.loads(config.PREDECESSORS_FILE.read_text()).get(str(cik), [])
    if not earlier:
        return facts
    joined = json.loads(json.dumps(facts))   # a copy, so the saved download isn't altered
    for old_cik in earlier:
        old = fetch_json(FACTS_URL.format(cik=old_cik), f"facts_{old_cik}", config.FILINGS_MAX_AGE)
        for group, tags in old.get("facts", {}).items():
            for tag, entry in tags.items():
                target = joined.setdefault("facts", {}).setdefault(group, {}).setdefault(
                    tag, {**entry, "units": {}})
                for unit, rows in entry["units"].items():
                    target["units"].setdefault(unit, [])
                    target["units"][unit] = rows + target["units"][unit]
    return joined


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
