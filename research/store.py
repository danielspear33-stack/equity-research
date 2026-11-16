"""Saves your own data as plain files in the userdata/ folder.

Plain JSON and CSV (rather than a database) so the daily refresh can commit
the files to GitHub and you can read them yourself.
"""

import json
from datetime import date

import pandas as pd

from . import config


def _read(name: str, default):
    path = config.USER_DATA_DIR / name
    return json.loads(path.read_text()) if path.exists() else default


def _write(name: str, data) -> None:
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

def get_memo(ticker: str):
    path = config.USER_DATA_DIR / "memos" / f"{ticker}.md"
    return path.read_text() if path.exists() else None


def save_memo(ticker: str, text: str) -> None:
    folder = config.USER_DATA_DIR / "memos"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{ticker}.md").write_text(text)
