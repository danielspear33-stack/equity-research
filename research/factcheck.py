"""Checks the figures in an AI-written memo against the data the AI was given.

Language models sometimes state a number that was never in their source
material. This finds every figure in the memo (dollar amounts, percentages,
multiples) and looks for it in the data, allowing for rounding and for the
same amount written differently ("$5.1T" for 5,123.4 in a table of billions,
"33%" for 0.33).

What it proves: the figure exists in what the AI was shown. What it can't
prove: that the AI attached it to the right label, or that a figure the AI
worked out itself (a difference, a sum) is right. Those are listed for you to
check by eye.
"""

import bisect
import re

# A figure is a number with a unit: "$351.92", "33.0%", "38.7x", "$5.1T", "$136.1B".
FIGURE = re.compile(
    r"(?<![\w.,])(?P<dollar>\$)?\s?(?P<number>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<unit>%|trillion\b|billion\b|million\b|bn\b|[TBM]\b|x\b)?",
    re.IGNORECASE,
)
NUMBER = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?(?:e[+-]?\d+)?", re.IGNORECASE)
REPORT_MARKER = "<annual_report_section"


def _pool(text: str) -> list:
    """Every number in a block of text, sorted, ignoring signs."""
    values = []
    for match in NUMBER.finditer(text):
        try:
            values.append(abs(float(match.group().replace(",", ""))))
        except ValueError:
            pass
    return sorted(values)


def _within(pool: list, value: float, tolerance: float) -> bool:
    """True if the pool holds a number within `tolerance` of `value`."""
    tolerance = tolerance + abs(value) * 0.001   # a little slack for double rounding
    at = bisect.bisect_left(pool, value - tolerance)
    return at < len(pool) and pool[at] <= value + tolerance


def _readings(number: str, unit: str) -> list:
    """The ways a memo figure could appear in the data, as (value, rounding tolerance)."""
    value = float(number.replace(",", ""))
    decimals = len(number.split(".")[1]) if "." in number else 0
    tolerance = 0.5 * 10 ** -decimals
    unit = unit.lower()
    if unit == "%":
        scales = [1, 0.01]                # 33.0% may be stored as 33.0 or 0.33
    elif unit in ("t", "trillion"):
        scales = [1000, 1e12, 1, 1e6]     # this tool's tables are in billions; filings often in millions
    elif unit in ("b", "bn", "billion"):
        scales = [1, 1e9, 1000]           # "$20.2 billion" may be 20,165 in a table of millions
    elif unit in ("m", "million"):
        scales = [1, 0.001, 1e6]
    else:
        scales = [1]
    return [(value * scale, tolerance * scale) for scale in scales]


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence a figure sits in, for showing where it came from."""
    left = max(text.rfind(". ", 0, start), text.rfind("\n", 0, start)) + 1
    stops = [i for i in (text.find(". ", end), text.find("\n", end)) if i != -1]
    right = min(stops) + 1 if stops else len(text)
    return " ".join(text[left:right].split()).strip("*-# ")


def check(memo: str, context: str) -> dict:
    """Compare every figure in `memo` with the data in `context`.

    Returns:
      checked      how many distinct figures the memo states
      in_data      how many match a number in the tool's own figures
      in_report    how many match only a number in the annual report text
      unverified   [{"figure", "sentence"}] for the rest
    """
    data_text, _, report_text = context.partition(REPORT_MARKER)
    data_pool, report_pool = _pool(data_text), _pool(report_text)

    seen, in_data, in_report, unverified = set(), 0, 0, []
    for match in FIGURE.finditer(memo):
        unit = match.group("unit") or ""
        if not match.group("dollar") and not unit:
            continue                       # a bare number: a year, a count, a list item
        figure = " ".join(match.group().split())
        if figure in seen:
            continue
        seen.add(figure)
        readings = _readings(match.group("number"), unit)
        if any(_within(data_pool, value, tolerance) for value, tolerance in readings):
            in_data += 1
        elif any(_within(report_pool, value, tolerance) for value, tolerance in readings):
            in_report += 1
        else:
            unverified.append({"figure": figure,
                               "sentence": _sentence_around(memo, match.start(), match.end())})
    return {"checked": len(seen), "in_data": in_data, "in_report": in_report,
            "unverified": unverified}
