"""A tiny disk cache so we don't re-download the same data on every search."""

import json
import time
from urllib.parse import urlparse

import requests

from . import config

GENERIC_CLIENT_NAME = "equity-research-tool/0.1"


def _headers(url: str) -> dict:
    """Identify ourselves. Your name and email go to the SEC, which asks for
    them, and to nobody else."""
    host = urlparse(url).hostname or ""
    is_sec = host == "sec.gov" or host.endswith(".sec.gov")
    return {"User-Agent": config.USER_AGENT if is_sec else GENERIC_CLIENT_NAME}


def fetch_json(url: str, cache_name: str, max_age: float) -> dict:
    """Return the JSON at `url`, reusing a saved copy if it is fresh enough.

    If the download fails and an older copy is on disk, that copy is used
    rather than giving up: slightly stale data beats none, and the price feed
    in particular refuses requests from time to time.
    """
    path = config.CACHE_DIR / f"{cache_name}.json"
    if not config.FORCE_REFRESH and path.exists() and time.time() - path.stat().st_mtime < max_age:
        return json.loads(path.read_text())

    try:
        response = requests.get(url, headers=_headers(url), timeout=config.REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        if path.exists():
            return json.loads(path.read_text())
        raise

    config.CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def fetch_text(url: str, cache_name: str, max_age: float = None) -> str:
    """Return the text at `url`. With no `max_age` the saved copy never expires,
    which suits filed documents: once filed they don't change."""
    path = config.CACHE_DIR / cache_name
    if path.exists():
        if max_age is None:
            return path.read_text()
        if not config.FORCE_REFRESH and time.time() - path.stat().st_mtime < max_age:
            return path.read_text()

    response = requests.get(url, headers=_headers(url), timeout=config.REQUEST_TIMEOUT)
    response.raise_for_status()
    config.CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(response.text)
    return response.text
