# Equity Research Tool

A valuation workbench for US-listed companies. Type a ticker and it pulls the
company's own SEC filings and its share price, then builds the analysis an equity
analyst would start from: a discounted cash flow model, a peer comparison, a
bank-specific valuation where a DCF doesn't apply, and a plain-English health check.

**[Try the live demo](https://equity-workbench.streamlit.app/?ticker=AAPL)** (it may take a moment to wake up if nobody has used it recently).

![Apple's overview page: price, DCF value, peer value and health check at a glance](docs/overview.png)

## What it does

- **Live data, no paid feeds.** Financial statements come straight from SEC EDGAR
  (the XBRL figures companies file), prices from Yahoo Finance. Results are rebuilt
  for the latest twelve months from quarterly reports, so the numbers are not a
  year old.
- **A DCF you can argue with.** Every assumption is editable, with a WACC build-up,
  bear, base and bull cases, a sensitivity table, and a reverse DCF that shows the
  growth today's price already assumes.
- **The right model for the company.** Banks, insurers and brokers get a
  price-to-book and dividend discount valuation in place of the DCF.
- **Every method on one chart.** A "football field" sets the DCF, peer multiples
  and the trading range against today's price.
- **AI that is checked, not trusted.** Claude writes a one-page briefing from the
  numbers and the annual report, then every figure in it is checked against the
  source data and anything that can't be traced is flagged.
- **What changed in the filings.** The last two annual reports are compared paragraph
  by paragraph; Claude reads only the paragraphs that differ and says which risks
  were added or dropped and how management's description of the business moved.
- **A backtest of its own signal.** The DCF is re-run on what was known in each past
  year to see whether shares it called cheap went on to beat the ones it called
  expensive. On its mechanical defaults, across about 100 large companies from 2019
  to 2025, they did not, and the page says so.
- **Checked by hand.** The calculations are covered by tests that compare them with
  numbers worked out by hand on small made-up companies.

| | |
| --- | --- |
| ![The DCF tab: value per share, bear, base and bull cases, and a sensitivity table](docs/dcf.png) | ![The valuation summary: every method as a bar against today's price](docs/summary.png) |
| **DCF** with scenarios and sensitivity | **Valuation summary** across every method |

![JPMorgan's bank valuation: book value, return on equity and three valuation methods](docs/bank.png)

## The tabs

- **Overview**: today's valuation, results for the latest twelve months, a health
  check (rule-of-thumb questions answered from the numbers), how the share price has
  behaved against the S&P 500, and ten years of financial statements.
- **Quarterly**: the last eight quarters, growth against a year earlier, and the
  latest twelve months against the last annual report.
- **DCF**: a discounted cash flow model with editable assumptions, a WACC build-up,
  a sensitivity table, bear/base/bull cases and a reverse DCF (the growth today's
  price implies).
- **Bank valuation** (shown instead of the DCF for banks, insurers and brokers): book
  value, return on equity, a justified price-to-book value and a dividend discount model.
- **Comps**: peer multiples and the share value they imply, with editable peers.
- **Valuation summary**: every method on one "football field" chart against the price.
- **Payouts & insiders**: dividends, buybacks, the share count, pay in shares, and
  what directors and executives have been buying and selling.
- **Filing changes**: what is new, removed or reworded in the latest annual report
  compared with the one before, with an AI summary and every changed paragraph listed.
- **AI memo**: Claude reads the numbers and the annual report and writes a one-page
  briefing. It explains and questions; it does not make a buy or sell call. It starts
  writing in the background as soon as you open a company, and a fact-check line shows
  how many of its figures match the data. It runs on your Claude subscription, with
  no per-use charge.
- **Watchlist**: follow companies and get a snapshot of each one every weekday.
- **Backtest** (in the sidebar): how the model's cheap and expensive calls would have
  done in past years, with its limitations spelled out.

Every company page opens with an at-a-glance strip: price, market value, the DCF
value, what peers imply, the growth the price implies and the health-check score,
with one sentence putting them together.

The tabs are in two colour-coded groups. Blue tabs (Overview, Quarterly, Payouts &
insiders) are market data of the kind any finance site shows. Gold tabs (DCF or
Bank valuation, Comps, Valuation summary, AI memo) are this tool's own analysis.
The colours and the rest of the look are set in `.streamlit/config.toml` and
`views/style.py`.

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
| `SEC_USER_AGENT` | Set to your name and contact email, or put the same text in a file called `sec_contact.txt` in this folder. The SEC asks automated tools to identify themselves and may refuse some downloads (such as the text of annual reports) to those that don't. |
| `ANTHROPIC_API_KEY` | Not needed. Only if you set it does the app offer a third, pay-per-call way to write the memo. |

### Writing the AI memo without paying per use

The memo tab offers two routes that use a Claude subscription:

1. **Claude Code** (one click): install the Claude Code command-line tool, then sign
   in once by running `claude auth login` in a terminal. The app then asks it to
   write the memo, which counts against your subscription's usage limits.
2. **claude.ai** (by hand): download the prepared prompt file, attach it to a chat
   at claude.ai, and paste the memo back into the app.

## Hosting a public copy

The app runs as it is on [Streamlit Community Cloud](https://streamlit.io/cloud):
point it at this repository and `app.py`, and add `SEC_USER_AGENT` (your name and
contact email) under the app's Secrets.

A hosted copy switches itself into public-demo mode (`PUBLIC_DEMO` in
`research/config.py`). Each visitor's watchlist, assumptions and memos are kept in
their own browser session and never written to disk, so strangers don't see each
other's work, and the memo routes that would spend the owner's Claude usage are off.

## The daily refresh

`python -m research.refresh` re-runs every company on your watchlist and adds one
row per company to `userdata/snapshots.csv`. It also updates the list of US-listed
companies in `data/companies.json`.

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
| `research/edgar.py` | The list of every US-listed company; turns a ticker into the SEC's company ID; downloads filing data and the list of recent filings |
| `research/statements.py` | Picks the annual figures out of the raw filing data into one table |
| `research/quarterly.py` | Single quarters and the trailing twelve months, from quarterly reports |
| `research/metrics.py` | Margins, growth, returns, leverage and valuation multiples |
| `research/checks.py` | The health check |
| `research/pricestats.py` | Returns, 52-week range, moving averages, volatility |
| `research/prices.py` | Five years of daily share prices |
| `research/market.py` | Risk-free rate and beta, for the discount rate |
| `research/dcf.py` | The DCF: forecast, WACC, terminal value, sensitivity, scenarios, reverse DCF |
| `research/financials.py` | Valuation for banks, insurers and brokers |
| `research/payouts.py` | Dividends, buybacks, share count and stock-based pay |
| `research/insiders.py` | Insider trades from SEC Form 4 filings |
| `research/comps.py` | Peer suggestions, peer multiples and implied values |
| `research/filings.py` | Downloads the annual report and extracts the key sections |
| `research/memo.py` | Builds the prompt and calls Claude for the memo |
| `research/factcheck.py` | Checks each figure in an AI memo against the data the AI was given |
| `research/changes.py` | Compares the last two annual reports and has Claude summarise the differences |
| `research/backtest.py` | Re-runs the DCF on past data and measures what happened next |
| `research/background.py` | Runs the slow AI jobs without freezing the screen |
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

## How the AI is kept honest

- The model is given only what this tool computed plus the company's own filing text,
  and is told to say when something is missing rather than fill it in from memory.
- After a memo is written, every dollar amount, percentage and multiple in it is looked
  up in that data, allowing for rounding and units. The memo shows how many matched and
  lists the rest with the sentence each came from. A match proves the figure was in
  the source, not that it is attached to the right label; figures the model worked
  out itself (a difference, a total) show up as unmatched for you to check.
- For filing changes, a mechanical comparison finds the changed paragraphs first. The
  model sees only those, and all of them are shown under its summary.

## Known limitations

- **AI results are reused** until the company files new results (memo) or a new annual
  report (filing changes), so they don't cost usage each time you open a company. Turn
  off "Run AI analysis automatically" in the sidebar to stop them starting on their own.
- **The fact-check can be fooled by coincidence.** A small round figure such as "5%" is
  likely to match something in the data whether or not it is the right thing.
- **The filing comparison works on paragraphs.** A paragraph that was moved and heavily
  rewritten shows as one removed and one new.
- **The backtest covers a short, unusual period and only today's large companies.** Its
  page lists what that means for the result.

- **US-listed companies only.** Any of the roughly 10,000 tickers on the SEC's list
  can be searched by ticker or name (`data/companies.json`, updated by the daily
  refresh). Companies listed only outside the US are not covered, and foreign
  companies that file a 20-F or 40-F instead of a 10-K annual report (many ADRs and
  Canadian companies) are found but can't be analysed.
- **Banks and insurers** get a simpler valuation (price-to-book and dividends) in
  place of the DCF. It ignores things specialists look at, such as capital ratios
  and loan losses.
- **Trailing twelve months are pieced together** from quarterly reports by
  subtraction. If a company's quarters can't be matched up, the latest fiscal year
  is used instead and the page says so.
- **No analyst estimates or earnings dates.** There is no free, reliable source for
  them, so everything here is reported history plus your own assumptions.
- **Insider trades cover the latest 40 filings**, which for a large company is a few
  months. Routine awards and tax withholding are listed separately from open-market
  trades.
- **Bear and bull cases use fixed rule-of-thumb shifts**, not a view on the company.
- **Total debt is approximate.** Companies label debt inconsistently, and lease
  obligations are mostly excluded.
- **Operating income and D&A are rebuilt** from other lines when a company doesn't
  report them directly, so EBITDA can be approximate.
- **Market cap uses the average diluted share count from the latest quarter or
  year reported**, so it drifts slightly after buybacks and is wrong after a stock
  split until the next report. Older share counts are rescaled for splits by rule
  of thumb (a count that doubles or more in a year is treated as a split).
- **Stock-based compensation is not deducted** from free cash flow, which flatters
  companies that pay staff heavily in shares.
- **Peer suggestions are a hand-picked list** covering the built-in tickers. For any
  other company you choose the peers yourself.
- **Prices come from an unofficial Yahoo Finance feed** that can stop working.
- **Figures are not cross-checked** against a second data source.
