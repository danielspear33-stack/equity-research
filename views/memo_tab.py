"""AI memo tab: Claude writes up the numbers and the annual report, and the figures are checked."""

from datetime import datetime

import streamlit as st

from research import background, config, factcheck, memo, store

from . import style, waiting


def can_write_here() -> bool:
    """True if this copy of the app can ask Claude Code to write (not on the public demo)."""
    return not config.PUBLIC_DEMO and memo.claude_code_available()


def automatic() -> bool:
    return can_write_here() and store.get_setting("auto_ai", True)


def results_basis(data: dict):
    """The date of the newest quarterly or annual report: a memo is redone when this moves."""
    return next((f["filed"] for f in data["filings"] if f["form"] in ("10-K", "10-Q")), None)


def _save(ticker: str, text: str, context: str, basis, warning=None) -> None:
    store.save_memo(ticker, text, {
        "written": datetime.now().isoformat(timespec="minutes"),
        "basis": basis,
        "warning": warning,
        "check": factcheck.check(text, context),
    })


def _start(data, dcf_output, comps_result, bank_output, insider_summary, include_report=True) -> None:
    """Write the memo in the background, then fact-check and save it."""
    ticker, basis = data["ticker"], results_basis(data)

    def work():
        context, warning = memo.full_context(data, dcf_output, comps_result, bank_output,
                                             insider_summary, include_report)
        _save(ticker, memo.write_with_claude_code(context), context, basis, warning)

    background.start(f"memo:{ticker}", work)


def _out_of_date(data: dict) -> bool:
    """True if there is no memo, or the company has reported results since it was written."""
    ticker = data["ticker"]
    if not store.get_memo(ticker):
        return True
    written_for, now = store.get_memo_details(ticker).get("basis"), results_basis(data)
    return bool(written_for and now and written_for != now)


def _show_fact_check(check: dict) -> None:
    checked, unverified = check["checked"], check["unverified"]
    if not checked:
        return
    matched = checked - len(unverified)
    sources = f"{check['in_data']} in the tool's own numbers"
    if check["in_report"]:
        sources += f", {check['in_report']} in the annual report text"
    line = f"Fact-check: {matched} of {checked} figures in this memo match the data ({sources})."
    if not unverified:
        st.success(line)
        return
    st.warning(line)
    with st.expander(f"{len(unverified)} figure{'s' if len(unverified) != 1 else ''} to check by eye"):
        st.caption("These weren't found in the data Claude was given. Often that is Claude's own "
                   "arithmetic (a difference or a total), which may be right; sometimes it is a "
                   "number it shouldn't have stated.")
        for item in unverified:
            st.markdown(f"**{item['figure']}** · {item['sentence']}")


def render(data: dict, dcf_output, comps_result, bank_output=None, insider_summary=None) -> None:
    ticker, job_name = data["ticker"], f"memo:{data['ticker']}"
    inputs = (data, dcf_output, comps_result, bank_output, insider_summary)
    style.own_analysis("An AI-written briefing that reads the numbers and the annual report together.")
    st.caption(
        "Gives Claude everything on these tabs, plus the Business, Risk Factors and MD&A sections "
        "of the latest annual report, and asks for a one-page memo. It explains and questions "
        "the numbers; it does not make a buy or sell call. Every figure it writes is then "
        "checked against the data."
    )

    # Start writing as soon as the company is opened, unless a memo for its
    # latest results is already saved.
    job = background.status(job_name)
    if job is None and automatic() and _out_of_date(data):
        _start(*inputs)
        job = background.status(job_name)
    if job and job["state"] == "done":
        background.clear(job_name)
        job = None
    running = bool(job and job["state"] == "running")

    if running:
        waiting.show(job_name, "writing the memo")
    elif job and job["state"] == "failed":
        st.error(job["error"])

    # Route 1: Claude Code on this computer (uses your subscription, no extra charge).
    if config.PUBLIC_DEMO:
        st.info("One-click memos are switched off on this public demo, because they run on the "
                "owner's own Claude account. You can still write one yourself with the claude.ai "
                "option below, or run the tool on your own computer.")
    elif not memo.claude_code_available():
        st.info("Install Claude Code and sign in with your Claude account to write memos here "
                "on your subscription. Until then, use the claude.ai option below.")
    elif not running:
        include_report = st.checkbox("Include the annual report text", value=True, key=f"{ticker}_10k")
        label = "Rewrite the memo" if store.get_memo(ticker) else "Write the memo"
        if st.button(label, type="primary", key=f"{ticker}_memo_cli",
                     help="Uses the Claude Code tool installed on this computer, which counts "
                          "against your Claude subscription's usage rather than charging per call."):
            background.clear(job_name)
            _start(*inputs, include_report)
            st.rerun()

    # Route 2: do it by hand in claude.ai (also on your subscription).
    with st.expander("Or write it in claude.ai yourself"):
        st.write("1. Prepare and download the prompt file. 2. Attach it to a new chat at "
                 "claude.ai and send it. 3. Paste the memo back here to keep it with the company.")
        if st.button("Prepare prompt file", key=f"{ticker}_prepare"):
            with st.spinner("Downloading the annual report…"):
                context, warning = memo.full_context(*inputs)
            if warning:
                st.warning(warning)
            st.session_state[f"{ticker}_prompt"] = memo.prompt_for_chat(context)
        if f"{ticker}_prompt" in st.session_state:
            st.download_button("Download prompt file", st.session_state[f"{ticker}_prompt"],
                               file_name=f"{ticker}_memo_prompt.txt", key=f"{ticker}_download")
        pasted = st.text_area("Paste the memo here", key=f"{ticker}_pasted", height=150)
        if st.button("Save pasted memo", key=f"{ticker}_save_pasted") and pasted.strip():
            context, _ = memo.full_context(*inputs, include_report=False)
            _save(ticker, pasted.strip(), context, results_basis(data))

    # Route 3: the paid API, offered only if you have deliberately set a key.
    if memo.api_key_configured() and not config.PUBLIC_DEMO:
        with st.expander("Or use the paid Claude API"):
            st.caption(f"Uses your API key and the model {config.MEMO_MODEL}. "
                       "This is billed per call, separately from a Claude subscription.")
            if st.button("Write memo with the API", key=f"{ticker}_memo_api"):
                context, warning = memo.full_context(*inputs)
                try:
                    text = st.write_stream(memo.stream_memo(context))
                    _save(ticker, text, context, results_basis(data), warning)
                    st.rerun()
                except memo.MemoError as error:
                    st.error(str(error))

    saved = store.get_memo(ticker)
    if not saved:
        return
    details = store.get_memo_details(ticker)
    st.divider()
    # A memo saved before fact-checking existed is checked now, against the numbers alone.
    check = details.get("check") or factcheck.check(
        saved, memo.full_context(*inputs, include_report=False)[0])
    _show_fact_check(check)
    if details.get("warning"):
        st.caption(details["warning"])
    st.markdown(saved)
    written = details.get("written")
    when = f"Written {datetime.fromisoformat(written):%d %b %Y at %H:%M}. " if written else "Saved memo. "
    st.caption(when + "The share price may have moved since. A new memo is written when the "
               "company next reports results.")
