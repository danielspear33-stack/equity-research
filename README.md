# Equity Research Tool

Type a US-listed company's ticker and get a full valuation workup built from the
company's own SEC filings and its share price:

- **Overview**: ten years of financial statements, margins, returns, leverage and
  today's valuation multiples.
- **DCF**: a discounted cash flow model with editable assumptions, a WACC build-up,
  a sensitivity table and a reverse DCF (the growth today's price implies).
- **Comps**: peer multiples and the share value they imply, with editable peers.
- **Valuation summary**: every method on one "football field" chart against the price.
- **AI memo**: Claude reads the numbers and the annual report and writes a one-page
  briefing. It explains and questions; it does not make a buy or sell call. It runs
  on your Claude subscription, with no per-use charge.
- **Watchlist**: follow companies and get a snapshot of each one every weekday.

Built with AI assistance (Claude Code).

## Run it

Double-click the launcher for your system:

- **Mac:** `Start Equity Research.command`
- **Windows:** `Start Equity Research.bat`

The first run sets up a private Python environment in this folder and installs the
libraries, which takes a few minutes. After that it starts the app and opens it in
your browser. Keep the launcher's window open while you use the app.

For a Desktop icon, make a shortcut (Windows) or alias (Mac) to the launcher and
move that to the Desktop. The launcher itself has to stay in this folder.

To run it by hand instead: `pip install -r requirements.txt`, then
`streamlit run app.py`.

### Optional settings

Environment variables you set before starting the app.

| Variable | What it unlocks |
| --- | --- |
| `SEC_USER_AGENT` | Set to your name and contact email, or put the same text in a file called `sec_contact.txt` in this folder. The SEC only serves its full ticker list and the text of annual reports to tools that identify themselves. Without it, about 125 built-in tickers work and the AI memo runs without the annual report. |
| `ANTHROPIC_API_KEY` | Not needed. Only if you set it does the app offer a third, pay-per-call way to write the memo. |

### Writing the AI memo without paying per use

The memo tab offers two routes that use a Claude subscription:

1. **Claude Code** (one click): install Claude Code and sign in with your Claude
   account. The app then asks it to write the memo, which counts against your
   subscription's usage limits.
2. **claude.ai** (by hand): download the prepared prompt file, attach it to a chat
   at claude.ai, and paste the memo back into the app.

## The daily refresh

`python -m research.refresh` re-runs every company on your watchlist and adds one
row per company to `userdata/snapshots.csv`.

`.github/workflows/daily-refresh.yml` runs that command on GitHub every weekday at
22:30 UTC (after the US market closes) and commits the new snapshot. To turn it on:
push this project to GitHub, and add `SEC_USER_AGENT` under
Settings > Secrets and variables > Actions. Pull the repository to see the new data
in the app.

Prices change daily but financial statements change only when a new report is
filed, so most days the refresh moves the price, the multiples and the gap between
the DCF value and the price. It also records each company's latest filing, and the
watchlist marks filings from the last week as new.

## How it works

| File | Job |
| --- | --- |
| `research/edgar.py` | Turns a ticker into the SEC's company ID; downloads filing data and the list of recent filings |
| `research/statements.py` | Picks the annual figures out of the raw filing data into one table |
| `research/metrics.py` | Margins, growth, returns, leverage and valuation multiples |
| `research/prices.py` | Five years of daily share prices |
| `research/market.py` | Risk-free rate and beta, for the discount rate |
| `research/dcf.py` | The DCF: forecast, WACC, terminal value, sensitivity, reverse DCF |
| `research/comps.py` | Peer suggestions, peer multiples and implied values |
| `research/filings.py` | Downloads the annual report and extracts the key sections |
| `research/memo.py` | Builds the prompt and calls Claude for the memo |
| `research/store.py` | Saves your watchlist, assumptions, peers, snapshots and memos in `userdata/` |
| `research/refresh.py` | The daily refresh |
| `research/report.py` | Ties the pieces together for one ticker |
| `app.py`, `views/` | The screens |
| `tests/` | Checks the calculations against numbers worked out by hand |

Run the tests with `python -m pytest`.

## Assumptions baked in

These are judgement calls, set in `research/config.py`:

- Equity risk premium of 5%.
- Terminal growth of 2.5%.
- A 10-year forecast with growth fading in a straight line to the terminal rate.
- Default DCF inputs are three-year averages of the company's own history. They are
  a baseline to challenge, not a forecast. For most large, highly valued companies
  they produce a DCF value well below the share price; the reverse DCF shows what
  growth the price needs instead.

## Known limitations

- **US filers only.** Companies that don't file annual 10-K reports (most foreign
  and Canada-only listings) are not supported.
- **Banks and insurers** are flagged: no DCF is run and most metrics don't apply.
- **Annual figures only.** Multiples use the latest full fiscal year, not the
  trailing twelve months, so they lag for fast-changing companies.
- **Total debt is approximate.** Companies label debt inconsistently, and lease
  obligations are mostly excluded.
- **Operating income and D&A are rebuilt** from other lines when a company doesn't
  report them directly, so EBITDA can be approximate.
- **Market cap uses the latest fiscal year's average diluted share count**, so it
  drifts after buybacks and is wrong after a stock split until the next annual report.
- **Stock-based compensation is not deducted** from free cash flow, which flatters
  companies that pay staff heavily in shares.
- **Peer suggestions are a hand-picked list** covering the built-in tickers. For any
  other company you choose the peers yourself.
- **Prices come from an unofficial Yahoo Finance feed** that can stop working.
- **Figures are not cross-checked** against a second data source.
