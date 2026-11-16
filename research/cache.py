"""A tiny disk cache so we don't re-download the same data on every search."""

import json
import time

import requests

from . import config


def fetch_json(url: str, cache_name: str, max_age: float) -> dict:
    """Return the JSON at `url`, reusing a saved copy if it is fresh enough."""
    path = config.CACHE_DIR / f"{cache_name}.json"
    if not config.FORCE_REFRESH and path.exists() and time.time() - path.stat().st_mtime < max_age:
        return json.loads(path.read_text())

    response = requests.get(
        url, headers={"User-Agent": config.USER_AGENT}, timeout=config.REQUEST_TIMEOUT
    )
    response.raise_for_status()
    data = response.json()

    config.CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps(data))
    return data
