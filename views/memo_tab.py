"""AI memo tab: have Claude write up the numbers and the annual report."""

import streamlit as st

from research import config, edgar, filings, memo, store


def _build_context(data, dcf_output, comps_result, include_report: bool, bank_output=None,
                   insider_summary=None) -> str:
    sections = None
    if include_report:
        try:
            with st.spinner("Downloading the annual report…"):
                # Ask for the latest 10-K specifically: it is often older than
                # the handful of recent filings shown on the overview tab.
                annual = edgar.get_recent_filings(data["cik"], forms=("10-K",), limit=1)
                sections, _ = filings.get_annual_report_sections(annual)
        except Exception as error:  # noqa: BLE001
            st.warning(f"Carrying on without the annual report. {error}")
    result, assumptions, wacc_parts, user_set = dcf_output or (None, None, None, False)
    extras = memo.build_extras(data, bank_output, insider_summary)
    return memo.build_context(data, result, assumptions, wacc_parts, user_set, comps_result,
                              sections, extras)


def render(data: dict, dcf_output, comps_result, bank_output=None, insider_summary=None) -> None:
    ticker = data["ticker"]
    st.caption(
        "Gives Claude everything on these tabs, plus the Business, Risk Factors and MD&A sections "
        "of the latest annual report, and asks for a one-page memo. It explains and questions "
        "the numbers; it does not make a buy or sell call."
    )
    include_report = st.checkbox("Include the annual report text", value=True, key=f"{ticker}_10k")

    # Route 1: Claude Code on this computer (uses your subscription, no extra charge).
    if memo.claude_code_available():
        if st.button("Write memo with Claude Code", type="primary", key=f"{ticker}_memo_cli",
                     help="Uses the Claude Code tool installed on this computer, which counts "
                          "against your Claude subscription's usage rather than charging per call."):
            context = _build_context(data, dcf_output, comps_result, include_report, bank_output,
                                     insider_summary)
            try:
                with st.spinner("Claude is writing the memo. This can take a minute or two…"):
                    store.save_memo(ticker, memo.write_with_claude_code(context))
            except memo.MemoError as error:
                st.error(str(error))
    else:
        st.info("Install Claude Code and sign in with your Claude account to write memos here "
                "with one click on your subscription. Until then, use the claude.ai option below.")

    # Route 2: do it by hand in claude.ai (also on your subscription).
    with st.expander("Or write it in claude.ai yourself"):
        st.write("1. Prepare and download the prompt file. 2. Attach it to a new chat at "
                 "claude.ai and send it. 3. Paste the memo back here to keep it with the company.")
        if st.button("Prepare prompt file", key=f"{ticker}_prepare"):
            context = _build_context(data, dcf_output, comps_result, include_report, bank_output,
                                     insider_summary)
            st.session_state[f"{ticker}_prompt"] = memo.prompt_for_chat(context)
        if f"{ticker}_prompt" in st.session_state:
            st.download_button("Download prompt file", st.session_state[f"{ticker}_prompt"],
                               file_name=f"{ticker}_memo_prompt.txt", key=f"{ticker}_download")
        pasted = st.text_area("Paste the memo here", key=f"{ticker}_pasted", height=150)
        if st.button("Save pasted memo", key=f"{ticker}_save_pasted") and pasted.strip():
            store.save_memo(ticker, pasted.strip())

    # Route 3: the paid API, offered only if you have deliberately set a key.
    if memo.api_key_configured():
        with st.expander("Or use the paid Claude API"):
            st.caption(f"Uses your API key and the model {config.MEMO_MODEL}. "
                       "This is billed per call, separately from a Claude subscription.")
            if st.button("Write memo with the API", key=f"{ticker}_memo_api"):
                context = _build_context(data, dcf_output, comps_result, include_report, bank_output,
                                     insider_summary)
                try:
                    store.save_memo(ticker, st.write_stream(memo.stream_memo(context)))
                    st.rerun()
                except memo.MemoError as error:
                    st.error(str(error))

    saved = store.get_memo(ticker)
    if saved:
        st.divider()
        st.markdown(saved)
        st.caption("Saved memo. The numbers may have moved since it was written.")
