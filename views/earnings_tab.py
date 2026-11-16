"""Latest results: Claude reads the company's newest results press release."""

from datetime import datetime

import streamlit as st

from research import background, earnings, store

from . import memo_tab, style, waiting


def _start(data: dict, announcement: dict) -> None:
    ticker, name = data["ticker"], data["profile"]["name"]

    def work():
        result = earnings.digest(name, announcement)
        result["written"] = datetime.now().isoformat(timespec="minutes")
        store.save_earnings_digest(ticker, result)

    background.start(f"earnings:{ticker}", work)


def render(data: dict) -> None:
    ticker, job_name = data["ticker"], f"earnings:{data['ticker']}"
    style.own_analysis("What management said when it last reported: results, outlook and tone.")
    st.caption(
        "The numbers elsewhere in this tool look backwards. The results press release is where "
        "management talks about what comes next. Claude reads the newest one and its figures "
        "are then checked against the release."
    )
    announcement = earnings.latest_announcement(data.get("announcements"))
    if announcement is None:
        st.info("No results announcement was found among this company's recent filings.")
        return

    saved = store.get_earnings_digest(ticker)
    out_of_date = not saved or saved.get("filed") != announcement["filed"]
    job = background.status(job_name)
    if job is None and memo_tab.automatic() and out_of_date:
        _start(data, announcement)
        job = background.status(job_name)
    if job and job["state"] == "done":
        background.clear(job_name)
        job = None
    running = bool(job and job["state"] == "running")

    if running:
        waiting.show(job_name, "reading the latest results announcement")
    elif job and job["state"] == "failed":
        st.warning(job["error"])
    if not running and memo_tab.can_write_here():
        label = "Read it again" if saved else "Read the latest results announcement"
        if st.button(label, key=f"{ticker}_earnings", type="secondary" if saved else "primary"):
            background.clear(job_name)
            _start(data, announcement)
            st.rerun()
    elif not memo_tab.can_write_here():
        st.info("This runs on the owner's Claude account, so it is not available here. "
                f"The announcement itself is [on SEC.gov]({announcement['url']}).")

    if not saved:
        return
    st.markdown(f"Results announced {saved['filed']} · [read the press release]({saved['release_url']})")
    if out_of_date:
        st.caption("A newer announcement has been filed since this was written.")
    check = saved.get("check") or {}
    if check.get("checked"):
        missing = len(check["unverified"])
        line = (f"Fact-check: {check['checked'] - missing} of {check['checked']} figures match "
                "the press release.")
        if missing:
            st.warning(line)
            with st.expander(f"{missing} figure{'s' if missing != 1 else ''} to check by eye"):
                for item in check["unverified"]:
                    st.markdown(f"**{item['figure']}** · {item['sentence']}")
        else:
            st.success(line)
    st.markdown(saved["digest"])
