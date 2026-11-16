"""Runs slow jobs (an AI memo takes a minute or two) without freezing the app.

A job is started under a name such as "memo:AAPL" and runs on a spare thread.
The screens ask for its status each time they redraw.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

# Two at a time: enough for a memo and a filing comparison side by side,
# without firing off a pile of AI requests if you click through many companies.
_pool = ThreadPoolExecutor(max_workers=2)
_jobs = {}
_lock = threading.Lock()


def start(name: str, work) -> bool:
    """Start `work()` in the background. Returns False if that job is already running."""
    with _lock:
        if _jobs.get(name, {}).get("state") == "running":
            return False
        _jobs[name] = {"state": "running", "started": time.time(), "error": None}

    def run():
        try:
            work()
            outcome = {"state": "done", "error": None}
        except Exception as error:  # noqa: BLE001 - report any failure on screen
            outcome = {"state": "failed", "error": str(error)}
        with _lock:
            _jobs[name].update(outcome)

    _pool.submit(run)
    return True


def status(name: str):
    """{"state": "running" | "done" | "failed", "started", "error"}, or None if never started."""
    with _lock:
        job = _jobs.get(name)
        return dict(job) if job else None


def clear(name: str) -> None:
    """Forget a finished job, so it can be started again."""
    with _lock:
        if _jobs.get(name, {}).get("state") != "running":
            _jobs.pop(name, None)
