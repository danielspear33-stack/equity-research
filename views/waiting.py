"""Shows that a background job is still running, and refreshes the page when it finishes."""

import time

import streamlit as st

from research import background


@st.fragment(run_every=3)
def show(job_name: str, doing: str) -> None:
    """A status line that updates itself every few seconds.

    `doing` finishes the sentence "Claude is ...", e.g. "writing the memo".
    """
    job = background.status(job_name)
    if job and job["state"] == "running":
        seconds = int(time.time() - job["started"])
        st.info(f"Claude is {doing} in the background ({seconds}s so far, usually one to two "
                "minutes). Carry on with the other tabs: it will appear here when it's ready.")
    else:
        st.rerun()
