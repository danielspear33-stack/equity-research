"""Insider trades: what directors and executives have done with their own shares.

Insiders must report every trade to the SEC within two business days on a
"Form 4". Most of what they report is routine (share awards, selling to cover
tax). The trades worth noticing are the ones made by choice on the open market:

  * Buying with their own money is the stronger signal, since there is only one
    reason to do it.
  * Selling is weaker: people sell to pay tax, buy a house or diversify. Sales
    under a pre-arranged "10b5-1" plan were scheduled months earlier.
"""

import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import config
from .cache import fetch_json, fetch_text

PROFILE_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# What the SEC's one-letter transaction codes mean.
CODES = {
    "P": "Bought on the open market",
    "S": "Sold on the open market",
    "A": "Share award from the company",
    "M": "Exercised options or vested units",
    "F": "Shares withheld to pay tax",
    "G": "Gift",
    "C": "Conversion",
    "X": "Exercised options",
    "D": "Returned to the company",
    "J": "Other",
}
OPEN_MARKET = {"P": "Buy", "S": "Sell"}


def list_form4s(cik: int, limit: int = 40) -> list:
    """The company's most recent Form 4 filings, newest first."""
    raw = fetch_json(PROFILE_URL.format(cik=cik), f"profile_{cik}", config.FILINGS_MAX_AGE)
    recent = raw.get("filings", {}).get("recent", {})
    found = []
    for form, filed, accession, document in zip(
        recent.get("form", []), recent.get("filingDate", []),
        recent.get("accessionNumber", []), recent.get("primaryDocument", []),
    ):
        if form != "4" or not document.endswith(".xml"):
            continue
        folder = accession.replace("-", "")
        # The listed document is a formatted view; the data file has the same
        # name without the "xsl..." folder in front.
        name = document.split("/")[-1]
        found.append({
            "filed": filed,
            "accession": accession,
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{name}",
            "page": f"https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{document}",
        })
        if len(found) == limit:
            break
    return found


def _text(node, path: str):
    found = node.find(path)
    return found.text.strip() if found is not None and found.text else None


def _number(node, path: str):
    text = _text(node, path)
    try:
        return float(text) if text else None
    except ValueError:
        return None


def parse_form4(xml: str, cik: int = None) -> list:
    """Every ordinary-share transaction in one Form 4, as a list of rows."""
    root = ET.fromstring(xml)
    issuer = _text(root, "issuer/issuerCik")
    if cik is not None and issuer and int(issuer) != cik:
        return []  # a filing about some other company's shares

    owner = root.find("reportingOwner")
    name = _text(owner, "reportingOwnerId/rptOwnerName") if owner is not None else None
    relationship = owner.find("reportingOwnerRelationship") if owner is not None else None
    role = "Insider"
    if relationship is not None:
        def flag(tag):
            return (_text(relationship, tag) or "").lower() in ("1", "true")

        if flag("isOfficer"):
            role = _text(relationship, "officerTitle") or "Officer"
        elif flag("isDirector"):
            role = "Director"
        elif flag("isTenPercentOwner"):
            role = "Owner of more than 10%"
    planned = (_text(root, "aff10b5One") or "").lower() in ("1", "true")

    rows = []
    for trade in root.iterfind("nonDerivativeTable/nonDerivativeTransaction"):
        code = _text(trade, "transactionCoding/transactionCode")
        shares = _number(trade, "transactionAmounts/transactionShares/value")
        price = _number(trade, "transactionAmounts/transactionPricePerShare/value")
        if code is None or shares is None:
            continue
        rows.append({
            "date": _text(trade, "transactionDate/value"),
            "insider": name.title() if name else "Unknown",
            "role": role,
            "code": code,
            "what": CODES.get(code, "Other"),
            "shares": shares,
            "price": price,
            "value": shares * price if price else None,
            "shares_after": _number(
                trade, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"),
            "planned": planned,
        })
    return rows


def get_trades(cik: int, limit: int = 40) -> pd.DataFrame:
    """Transactions from the company's latest Form 4s, newest first."""
    filings = list_form4s(cik, limit)

    def load(filing):
        try:
            text = fetch_text(filing["url"], f"form4_{filing['accession']}.xml")
            return [{**row, "filed": filing["filed"], "page": filing["page"]}
                    for row in parse_form4(text, cik)]
        except Exception:  # noqa: BLE001 - one unreadable filing shouldn't sink the rest
            return []

    # A few at a time, to stay well inside the SEC's request limits.
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = [row for batch in pool.map(load, filings) for row in batch]
    if not rows:
        return pd.DataFrame()
    table = pd.DataFrame(rows)
    table["date"] = pd.to_datetime(table["date"], errors="coerce")
    return table.sort_values("date", ascending=False, ignore_index=True)


def summarise(trades: pd.DataFrame) -> dict:
    """Totals for open-market buying and selling in the trades given."""
    empty = {"buy_value": 0.0, "sell_value": 0.0, "buyers": 0, "sellers": 0,
             "planned_share_of_sales": None, "from": None, "to": None, "open_market": pd.DataFrame()}
    if trades.empty:
        return empty
    chosen = trades[trades["code"].isin(OPEN_MARKET)].copy()
    chosen["side"] = chosen["code"].map(OPEN_MARKET)
    buys, sells = chosen[chosen["side"] == "Buy"], chosen[chosen["side"] == "Sell"]
    sold = sells["value"].sum()
    return {
        "buy_value": float(buys["value"].sum()),
        "sell_value": float(sold),
        "buyers": int(buys["insider"].nunique()),
        "sellers": int(sells["insider"].nunique()),
        "planned_share_of_sales": float(sells.loc[sells["planned"], "value"].sum() / sold)
        if sold > 0 else None,
        "from": trades["date"].min(),
        "to": trades["date"].max(),
        "open_market": chosen,
    }
