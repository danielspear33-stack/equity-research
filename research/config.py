"""Settings shared by the rest of the project."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / ".cache"
COMPANY_LIST_FILE = PROJECT_ROOT / "data" / "companies.json"
SEED_SIC_FILE = PROJECT_ROOT / "data" / "seed_sic.json"
PEER_GROUPS_FILE = PROJECT_ROOT / "data" / "peer_groups.json"
# Your own saved data: watchlist, DCF assumptions, peers, daily snapshots, memos.
USER_DATA_DIR = PROJECT_ROOT / "userdata"

# The SEC asks automated tools to identify themselves. Its full ticker list is
# only served to clients that include contact details, so set your own, e.g.
#   export SEC_USER_AGENT="Your Name your.email@example.com"
# Alternatively, put the same text on one line in a file called sec_contact.txt
# in the project folder (it is kept out of GitHub).
_CONTACT_FILE = PROJECT_ROOT / "sec_contact.txt"
_SAVED_CONTACT = _CONTACT_FILE.read_text().strip() if _CONTACT_FILE.exists() else ""
USER_AGENT = (
    os.environ.get("SEC_USER_AGENT")
    or _SAVED_CONTACT
    or "equity-research-tool/0.1 (student project)"
)

# The public demo is the copy hosted online for anyone to try. There, nothing a
# visitor saves is written to disk (see store.py) and the memo routes that
# would spend the owner's Claude usage are switched off. It is on when
# PUBLIC_DEMO is set, or when running on Streamlit Community Cloud, which
# keeps apps under /mount/src.
PUBLIC_DEMO = bool(os.environ.get("PUBLIC_DEMO")) or str(PROJECT_ROOT).startswith("/mount/src/")

# How long downloaded data is reused before being fetched again, in seconds.
FILINGS_MAX_AGE = 24 * 60 * 60   # financial statements change four times a year
PRICES_MAX_AGE = 60 * 60         # prices change all day
TICKER_LIST_MAX_AGE = 7 * 24 * 60 * 60

REQUEST_TIMEOUT = 60

# The daily refresh sets this to True so it always downloads fresh data.
FORCE_REFRESH = False

# Valuation assumptions that are judgement calls rather than data.
EQUITY_RISK_PREMIUM = 0.05      # extra return investors demand for owning shares
DEFAULT_TERMINAL_GROWTH = 0.025  # long-run growth, roughly inflation plus a little
FALLBACK_RISK_FREE_RATE = 0.043  # used only if the Treasury yield can't be fetched
DEFAULT_FORECAST_YEARS = 10

# Model used to write the research memo.
MEMO_MODEL = "claude-opus-5-5"
