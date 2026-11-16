"""Downloads an annual report (10-K) and pulls out the sections worth reading.

A 10-K is split into numbered "Items". The three that matter most here:
  Item 1   Business: what the company does
  Item 1A  Risk Factors: what management thinks could go wrong
  Item 7   Management's Discussion and Analysis: management's own account of the year
"""

import re
from html.parser import HTMLParser

import requests

from .cache import fetch_text

SECTIONS = {"1": "Business", "1A": "Risk Factors", "7": "Management's Discussion and Analysis"}

BLOCK_TAGS = {"p", "div", "br", "tr", "li", "table", "h1", "h2", "h3", "h4", "h5", "h6"}
HEADING = re.compile(r"^\s*item\s+(\d{1,2}[ab]?)\s*[\.:\-–—]", re.IGNORECASE | re.MULTILINE)


class _TextExtractor(HTMLParser):
    """Keeps the words of a web page and drops the markup."""

    def __init__(self):
        super().__init__()
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    text = "".join(parser.parts).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def extract_sections(text: str) -> dict:
    """Return {item number: section text} for the items in SECTIONS.

    Each item heading appears at least twice: once in the table of contents
    and once at the real section. The real one is followed by far more text,
    so for each item we keep the longest stretch up to the next heading.
    """
    headings = [(m.start(), m.group(1).upper()) for m in HEADING.finditer(text)]
    sections = {}
    for index, (start, item) in enumerate(headings):
        if item not in SECTIONS:
            continue
        end = len(text)
        for next_start, next_item in headings[index + 1:]:
            if next_item != item:
                end = next_start
                break
        body = text[start:end].strip()
        if len(body) > len(sections.get(item, "")):
            sections[item] = body
    return sections


def sections_of(filing: dict) -> dict:
    """{item number: text} for one annual report.

    The document is saved after the first download and never fetched again:
    a filing doesn't change once it is filed.
    """
    try:
        html = fetch_text(filing["url"], f"filing_{filing['accession']}.html")
    except requests.HTTPError as error:
        if error.response is not None and error.response.status_code == 403:
            raise PermissionError(
                "The SEC refused to send the annual report. It only serves documents to tools "
                "that identify themselves: set the SEC_USER_AGENT environment variable to your "
                "name and email."
            ) from error
        raise
    sections = extract_sections(html_to_text(html))
    if not sections:
        raise ValueError("Couldn't find the standard sections in the annual report.")
    return sections


def get_annual_report_sections(filings: list) -> tuple:
    """Fetch the latest 10-K and return ({item: text}, the filing used)."""
    annual = next((f for f in filings if f["form"] == "10-K"), None)
    if annual is None:
        raise ValueError("No 10-K found among the company's recent filings.")
    return sections_of(annual), annual
