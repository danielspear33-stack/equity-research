"""Filing changes tab: what is different in this year's annual report from last year's."""

from datetime import datetime

import streamlit as st

from research import background, changes, memo, store

from . import memo_tab, style, waiting

SHOWN_PER_LIST = 40


def _start(data: dict) -> None:
    """Compare the two reports, then have Claude summarise the differences, in the background."""
    ticker, cik, name = data["ticker"], data["cik"], data["profile"]["name"]
    with_ai = memo_tab.can_write_here()

    def work():
        comparison = changes.compare_reports(cik)
        comparison["compared"] = datetime.now().isoformat(timespec="minutes")
        store.save_filing_changes(ticker, comparison)      # keep the comparison even if the AI step fails
        if with_ai:
            try:
                comparison["summary"] = changes.summarise(name, comparison)
            except memo.MemoError as error:
                comparison["summary_error"] = str(error)
            store.save_filing_changes(ticker, comparison)

    background.start(f"changes:{ticker}", work)


def _out_of_date(data: dict, saved: dict) -> bool:
    """True if nothing is saved, or a newer annual report has been filed since."""
    if not saved:
        return True
    newest = next((f for f in data["filings"] if f["form"] == "10-K"), None)
    return bool(newest and newest["accession"] != saved["newest"]["accession"])


def _show_paragraphs(title: str, diff: dict) -> None:
    with st.expander(f"{title}: the paragraphs that changed"):
        for label, items in (("New this year", diff["added"]),
                             ("Removed since last year", diff["removed"])):
            if items:
                st.markdown(f"**{label} ({len(items)})**")
                for paragraph in items[:SHOWN_PER_LIST]:
                    st.caption(paragraph)
                if len(items) > SHOWN_PER_LIST:
                    st.caption(f"…and {len(items) - SHOWN_PER_LIST} more.")
        if diff["reworded"]:
            st.markdown(f"**Reworded ({len(diff['reworded'])})**")
            for old, new in diff["reworded"][:SHOWN_PER_LIST]:
                before, after = st.columns(2)
                before.caption("Last year: " + old)
                after.caption("This year: " + new)
            if len(diff["reworded"]) > SHOWN_PER_LIST:
                st.caption(f"…and {len(diff['reworded']) - SHOWN_PER_LIST} more.")


def render(data: dict) -> None:
    ticker, job_name = data["ticker"], f"changes:{data['ticker']}"
    style.own_analysis("What management added, dropped or reworded since last year's annual report.")
    st.caption(
        "Most of an annual report is repeated word for word each year, so the part that changes "
        "is where the news is. The two reports are compared paragraph by paragraph, then Claude "
        "reads only the paragraphs that differ and says what they amount to."
    )

    saved = store.get_filing_changes(ticker)
    job = background.status(job_name)
    if job is None and memo_tab.automatic() and _out_of_date(data, saved):
        _start(data)
        job = background.status(job_name)
    if job and job["state"] == "done":
        background.clear(job_name)
        job = None
    running = bool(job and job["state"] == "running")

    if running:
        waiting.show(job_name, "comparing the last two annual reports")
    elif job and job["state"] == "failed":
        st.warning(job["error"])
    if not running:
        label = "Compare again" if saved else "Compare the last two annual reports"
        if st.button(label, key=f"{ticker}_compare", type="secondary" if saved else "primary"):
            background.clear(job_name)
            _start(data)
            st.rerun()

    if not saved:
        return
    newest, previous = saved["newest"], saved["previous"]
    st.markdown(f"Annual report [filed {newest['filed']}]({newest['url']}) against the one "
                f"[filed {previous['filed']}]({previous['url']}).")
    style.cards([
        {"label": title,
         "value": f"{len(diff['added'])} new",
         "note": f"{len(diff['reworded'])} reworded · {len(diff['removed'])} removed · "
                 f"{diff['unchanged']} of {diff['total']} unchanged",
         "own": True}
        for title, diff in saved["sections"].items()
    ])

    if saved.get("summary"):
        st.markdown(saved["summary"])
        st.caption("Claude was shown only the changed paragraphs listed below, so its summary "
                   "can be checked against them.")
    elif saved.get("summary_error"):
        st.warning(saved["summary_error"])
    elif not memo_tab.can_write_here():
        st.info("The AI summary of these changes runs on the owner's Claude account, so it is "
                "not available here. The paragraph-by-paragraph comparison below needs no AI.")

    for title, diff in saved["sections"].items():
        _show_paragraphs(title, diff)
