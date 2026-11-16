"""Saves your own data as plain files in the userdata/ folder.

Plain JSON and CSV (rather than a database) so the daily refresh can commit
the files to GitHub and you can read them yourself.
"""

import json
from datetime import date

import pandas as pd

from . import config


def _visitor_data():
    """On the public demo, a private scratch space for the current visitor.

    Strangers share one hosted copy, so what one saves must not show up for
    the next. Their watchlist, assumptions and memos live in their own browser
    session and vanish when they leave. Returns None everywhere else.
    """
    if not config.PUBLIC_DEMO:
        return None
    import streamlit as st

    return st.session_state.setdefault("_visitor_data", {})


def _read(name: str, default):
    visitor = _visitor_data()
    if visitor is not None:
        return json.loads(visitor[name]) if name in visitor else default
    path = config.USER_DATA_DIR / name
    return json.loads(path.read_text()) if path.exists() else default


def _write(name: str, data) -> None:
    visitor = _visitor_data()
    if visitor is not None:
        visitor[name] = json.dumps(data)
        return
    config.USER_DATA_DIR.mkdir(exist_ok=True)
    (config.USER_DATA_DIR / name).write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")


# ---- Watchlist: the companies you follow ----

def get_watchlist() -> list:
    return _read("watchlist.json", [])


def add_to_watchlist(ticker: str) -> None:
    tickers = get_watchlist()
    if ticker not in tickers:
        _write("watchlist.json", sorted(tickers + [ticker]))


def remove_from_watchlist(ticker: str) -> None:
    _write("watchlist.json", [t for t in get_watchlist() if t != ticker])


# ---- Your DCF assumptions and peer choices, per company ----

def get_assumptions(ticker: str):
    return _read("assumptions.json", {}).get(ticker)


def save_assumptions(ticker: str, assumptions: dict) -> None:
    everything = _read("assumptions.json", {})
    everything[ticker] = assumptions
    _write("assumptions.json", everything)


def clear_assumptions(ticker: str) -> None:
    everything = _read("assumptions.json", {})
    everything.pop(ticker, None)
    _write("assumptions.json", everything)


def get_peers(ticker: str):
    return _read("peers.json", {}).get(ticker)


def save_peers(ticker: str, peers: list) -> None:
    everything = _read("peers.json", {})
    everything[ticker] = peers
    _write("peers.json", everything)


# ---- Daily snapshots: one row per company per day ----

SNAPSHOT_FILE = "snapshots.csv"


def get_snapshots() -> pd.DataFrame:
    path = config.USER_DATA_DIR / SNAPSHOT_FILE
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=["date"])


def save_snapshot(row: dict, today: date = None) -> None:
    """Add today's row for a ticker, replacing any earlier row from the same day."""
    row = {"date": pd.Timestamp(today or date.today()), **row}
    history = get_snapshots()
    if not history.empty:
        same = (history["ticker"] == row["ticker"]) & (history["date"] == row["date"])
        history = history[~same]
    history = pd.concat([history, pd.DataFrame([row])], ignore_index=True)
    config.USER_DATA_DIR.mkdir(exist_ok=True)
    history.sort_values(["date", "ticker"]).to_csv(
        config.USER_DATA_DIR / SNAPSHOT_FILE, index=False, date_format="%Y-%m-%d"
    )


# ---- AI memos ----

def _read_text(name: str):
    visitor = _visitor_data()
    if visitor is not None:
        return visitor.get(name)
    path = config.USER_DATA_DIR / name
    return path.read_text() if path.exists() else None


def _write_text(name: str, text: str) -> None:
    visitor = _visitor_data()
    if visitor is not None:
        visitor[name] = text
        return
    path = config.USER_DATA_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def get_memo(ticker: str):
    return _read_text(f"memos/{ticker}.md")


def get_memo_details(ticker: str) -> dict:
    """When the memo was written, which results it was based on, and its fact-check."""
    return _read(f"memos/{ticker}.json", {})


def save_memo(ticker: str, text: str, details: dict = None) -> None:
    _write_text(f"memos/{ticker}.md", text)
    _write_text(f"memos/{ticker}.json", json.dumps(details or {}, indent=1) + "\n")


# ---- What changed between annual reports ----

def get_filing_changes(ticker: str) -> dict:
    """The saved comparison of the last two annual reports, or {}."""
    return _read(f"changes/{ticker}.json", {})


def save_filing_changes(ticker: str, comparison: dict) -> None:
    _write_text(f"changes/{ticker}.json", json.dumps(comparison, indent=1) + "\n")


# ---- Latest results announcement, read by AI ----

def get_earnings_digest(ticker: str) -> dict:
    return _read(f"earnings/{ticker}.json", {})


def save_earnings_digest(ticker: str, digest: dict) -> None:
    _write_text(f"earnings/{ticker}.json", json.dumps(digest, indent=1) + "\n")


# ---- Settings ----

def get_setting(name: str, default):
    return _read("settings.json", {}).get(name, default)


def save_setting(name: str, value) -> None:
    settings = _read("settings.json", {})
    settings[name] = value
    _write("settings.json", settings)
