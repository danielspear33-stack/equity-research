"""The app's look: colours, cards and the markers for this tool's own analysis.

Two colours carry meaning throughout:
  blue  = market data, the kind any finance site shows
  gold  = this tool's own valuation work
"""

from html import escape

import streamlit as st

BLUE, GOLD = "#5b9dff", "#f2b84b"
GREEN, RED, GREY = "#4ecb9e", "#e2687a", "#8b95ab"
CARD, BORDER, MUTED = "#161e2e", "#28324a", "#9aa5bd"

# How many of the company page's tabs are plain market data. They come first;
# every tab after them is this tool's own analysis and is coloured gold.
MARKET_DATA_TABS = 3

CSS = f"""
<style>
.block-container {{ padding-top: 4rem; max-width: 1400px; }}

/* Every headline number sits in its own card. */
[data-testid="stMetric"] {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; padding: 14px 16px;
}}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: 0.82rem; }}
[data-testid="stMetricValue"] {{ font-size: 1.55rem; font-weight: 650; }}

/* Tabs as pills: blue for market data, gold for this tool's own analysis. */
[data-testid="stTabs"] [role="tablist"] {{ gap: 6px; }}
[data-testid="stTab"] {{
    background: {CARD}; border-radius: 9px 9px 0 0; padding: 9px 18px; height: auto;
}}
[data-testid="stTab"] p {{ font-size: 0.95rem; font-weight: 600; color: #c9d3e6; }}
[data-testid="stTab"][aria-selected="true"] {{ background: rgba(91,157,255,0.18); }}
[data-testid="stTab"][aria-selected="true"] p {{ color: {BLUE}; }}
[data-testid="stTab"]:nth-child(n+{MARKET_DATA_TABS + 1}) {{ background: rgba(242,184,75,0.09); }}
[data-testid="stTab"]:nth-child(n+{MARKET_DATA_TABS + 1}) p {{ color: {GOLD}; }}
[data-testid="stTab"]:nth-child(n+{MARKET_DATA_TABS + 1})[aria-selected="true"] {{
    background: rgba(242,184,75,0.24);
}}
[data-testid="stTab"]:nth-child({MARKET_DATA_TABS + 1}) {{ margin-left: 22px; }}

.er-legend {{ display: flex; gap: 22px; color: {MUTED}; font-size: 0.82rem; margin: 2px 0 6px; }}
.er-dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 7px; }}

.er-grid {{ display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }}
.er-card {{
    background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; padding: 14px 16px;
    border-top: 3px solid {BLUE};
}}
.er-card.gold {{ border-top-color: {GOLD}; }}
.er-card .label {{ color: {MUTED}; font-size: 0.8rem; margin-bottom: 4px; }}
.er-card .value {{ font-size: 1.55rem; font-weight: 650; line-height: 1.25; }}
.er-card .note {{ font-size: 0.82rem; margin-top: 4px; color: {MUTED}; }}
.er-card .note.up {{ color: {GREEN}; }}
.er-card .note.down {{ color: {RED}; }}

.er-verdict {{
    background: rgba(242,184,75,0.07); border: 1px solid rgba(242,184,75,0.35);
    border-radius: 12px; padding: 12px 16px; margin-top: 12px; font-size: 0.98rem; line-height: 1.5;
}}
.er-tag {{
    display: inline-block; background: rgba(242,184,75,0.16); color: {GOLD};
    border-radius: 999px; padding: 2px 11px; font-size: 0.72rem; font-weight: 700;
    letter-spacing: 0.06em; text-transform: uppercase; margin-right: 8px;
}}
.er-banner {{ color: {MUTED}; font-size: 0.9rem; margin: 2px 0 12px; }}

.er-checks {{ display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }}
.er-check {{
    background: {CARD}; border: 1px solid {BORDER}; border-left: 4px solid {GREY};
    border-radius: 10px; padding: 10px 14px;
}}
.er-check.good {{ border-left-color: {GREEN}; }}
.er-check.watch {{ border-left-color: {GOLD}; }}
.er-check.weak {{ border-left-color: {RED}; }}
.er-check .q {{ font-weight: 600; font-size: 0.92rem; }}
.er-check .status {{ float: right; font-size: 0.74rem; font-weight: 700; text-transform: uppercase; }}
.er-check.good .status {{ color: {GREEN}; }}
.er-check.watch .status {{ color: {GOLD}; }}
.er-check.weak .status {{ color: {RED}; }}
.er-check .status {{ color: {GREY}; }}
.er-check .d {{ color: {MUTED}; font-size: 0.84rem; margin-top: 3px; }}
</style>
"""


def apply() -> None:
    """Load the styles. Called once at the top of the app."""
    st.html(CSS)


def cards(items: list) -> None:
    """A row of headline cards.

    Each item is a dict with `label` and `value`, and optionally `note` (small
    text underneath), `tone` ("up" or "down" colours the note green or red)
    and `own` (True marks it gold: this tool's own analysis).
    """
    parts = []
    for item in items:
        note = ""
        if item.get("note"):
            note = f'<div class="note {item.get("tone") or ""}">{escape(str(item["note"]))}</div>'
        parts.append(
            f'<div class="er-card {"gold" if item.get("own") else ""}">'
            f'<div class="label">{escape(str(item["label"]))}</div>'
            f'<div class="value">{escape(str(item["value"]))}</div>{note}</div>'
        )
    st.html(f'<div class="er-grid">{"".join(parts)}</div>')


def legend() -> None:
    """Explains the two tab colours."""
    st.html(
        '<div class="er-legend">'
        f'<span><span class="er-dot" style="background:{BLUE}"></span>'
        "Market data: what any finance site shows</span>"
        f'<span><span class="er-dot" style="background:{GOLD}"></span>'
        "Valuation and analysis: built by this tool</span></div>"
    )


def own_analysis(text: str) -> None:
    """The banner at the top of each gold tab."""
    st.html(f'<div class="er-banner"><span class="er-tag">Original analysis</span>{escape(text)}</div>')


def verdict(text: str) -> None:
    """A highlighted plain-English sentence."""
    st.html(f'<div class="er-verdict">{escape(text)}</div>')


def health_checks(results: list, labels: dict) -> None:
    """The health check as a grid of colour-coded cards instead of a table."""
    parts = [
        f'<div class="er-check {escape(r["status"])}">'
        f'<span class="status">{escape(labels[r["status"]])}</span>'
        f'<div class="q">{escape(r["question"])}</div>'
        f'<div class="d">{escape(r["detail"])}</div></div>'
        for r in results
    ]
    st.html(f'<div class="er-checks">{"".join(parts)}</div>')


def tone(value) -> str:
    """ "up" for a positive number, "down" for a negative one, None otherwise."""
    if value is None or value != value:  # the second test catches NaN
        return None
    return "up" if value > 0 else "down" if value < 0 else None
