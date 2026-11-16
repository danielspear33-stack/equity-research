"""Shared helpers for turning numbers into readable text."""

import pandas as pd


def missing(value) -> bool:
    return value is None or pd.isna(value)


def money(value) -> str:
    """Format dollars as $1.2B / $340M, or a dash when there is no figure."""
    if missing(value):
        return "–"
    sign = "-" if value < 0 else ""
    for size, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(value) >= size:
            return f"{sign}${abs(value) / size:,.1f}{suffix}"
    return f"{sign}${abs(value):,.0f}"


def dollars(value) -> str:
    if missing(value):
        return "–"
    return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"


def percent(value) -> str:
    return "–" if missing(value) else f"{value:.1%}"


def signed_percent(value) -> str:
    return "–" if missing(value) else f"{value:+.0%}"


def multiple(value) -> str:
    return "–" if missing(value) else f"{value:.1f}x"


def by_year(table: pd.DataFrame, rows: dict, formatter) -> pd.DataFrame:
    """Flip a year-indexed table so years run across the top, newest last."""
    out = table[list(rows)].rename(columns=rows).T
    out.columns = [f"FY{d.year}" for d in table.index]
    return out.map(formatter)
