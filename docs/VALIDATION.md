# Validation: this tool's figures against an independent source

Last run 19 November 2026 with `python -m tools.validate`.

The app builds its numbers by picking tagged values out of SEC filings. To check that matching, this compares them with the annual figures published by Yahoo Finance, which come from a separate commercial data provider. Two independent routes arriving at the same number is good evidence that both are right.

Compared: 15 companies, their last 3 fiscal years.

## Lines that mean the same thing in both sources

**262 of 280 figures (94%) agree to within 1%.**

| Line | Figures compared | Agree within 1% | Largest gap |
| --- | ---: | ---: | ---: |
| Revenue | 38 | 35 | 3.0% |
| Net income | 41 | 41 | 0.5% |
| Cash from operations | 38 | 38 | 0.0% |
| Cash and short-term investments | 38 | 37 | 83.0% |
| Shareholders' equity | 44 | 44 | 0.0% |
| Diluted shares | 43 | 41 | 8.8% |
| Total debt, leases excluded | 38 | 26 | 30.3% |

### Every disagreement

| Company | Fiscal year end | Line | This tool | Yahoo Finance | Gap |
| --- | --- | --- | ---: | ---: | ---: |
| NVDA | 2026-01-25 | Cash and short-term investments | 10.61B | 62.56B | -83.0% |
| GOOGL | 2024-12-31 | Total debt, leases excluded | 14.18B | 10.88B | +30.3% |
| CAT | 2023-12-31 | Total debt, leases excluded | 29.11B | 37.94B | -23.3% |
| CAT | 2024-12-31 | Total debt, leases excluded | 31.74B | 38.51B | -17.6% |
| XOM | 2025-12-31 | Total debt, leases excluded | 43.53B | 37.22B | +17.0% |
| CAT | 2025-12-31 | Total debt, leases excluded | 36.21B | 43.32B | -16.4% |
| XOM | 2024-12-31 | Total debt, leases excluded | 41.65B | 37.76B | +10.3% |
| XOM | 2023-12-31 | Total debt, leases excluded | 41.57B | 37.73B | +10.2% |
| TSLA | 2024-12-31 | Diluted shares | 3.50B | 3.22B | +8.8% |
| GOOGL | 2023-12-31 | Total debt, leases excluded | 12.87B | 11.87B | +8.4% |
| TSLA | 2025-12-31 | Diluted shares | 3.53B | 3.75B | -5.9% |
| GOOGL | 2025-12-31 | Total debt, leases excluded | 48.54B | 46.55B | +4.3% |
| XOM | 2024-12-31 | Revenue | 349.58B | 339.25B | +3.0% |
| XOM | 2023-12-31 | Revenue | 344.58B | 334.70B | +3.0% |
| XOM | 2025-12-31 | Revenue | 332.24B | 323.90B | +2.6% |
| COST | 2024-09-01 | Total debt, leases excluded | 5.90B | 5.79B | +1.8% |
| PFE | 2023-12-31 | Total debt, leases excluded | 71.76B | 70.84B | +1.3% |
| PFE | 2025-12-31 | Total debt, leases excluded | 64.64B | 63.96B | +1.1% |

### What the remaining disagreements are

- **Nvidia, cash, latest year:** this tool is too low. Nvidia changed how it tags its marketable securities and the new tag isn't one the tool reads, so about $52B of investments is missing from its cash for that year. Not yet fixed.
- **Caterpillar, debt:** this tool is too low. The part of its long-term debt due within a year is filed under a tag the tool doesn't read. Not yet fixed.
- **Alphabet, debt:** this tool is higher because it counts commercial paper and the part of long-term debt due within a year, which Yahoo's figure leaves out.
- **Exxon, revenue and debt:** this tool's revenue is Exxon's "total revenues and other income", about 3% above the sales figure Yahoo uses. Its debt is higher because Exxon's long-term debt tag includes finance leases, which can't be separated out.
- **Tesla, diluted shares:** the two sources disagree in both directions and the cause hasn't been established.
- **Costco and Pfizer, debt:** gaps of 1-2%, from small items one source counts as debt and the other doesn't.

The first run of this check found four errors in how the tool read filings, all since fixed: revenue that left out partnership income (Pfizer), cash that missed a second line of investments (Coca-Cola, Pfizer), a made-up gross profit where costs were only partly tagged (UnitedHealth, Caterpillar), and equity that included outside owners' share (UnitedHealth). It also led to two fixes to how debt is added up (Domino's, Tesla).

## Lines the two sources define differently

Gaps here are expected and are not errors. This tool shows operating income as the company reports it, including one-off charges such as restructuring that Yahoo takes out, and where a company reports no operating income it uses profit before tax plus interest. Yahoo's capital expenditure includes equipment bought to lease to customers. Gross profit is worked out by each source for companies that don't report it.

| Line | Figures compared | Agree within 1% | Largest gap |
| --- | ---: | ---: | ---: |
| Operating income | 38 | 22 | 41.5% |
| Gross profit | 33 | 30 | 6.3% |
| Capital expenditure | 38 | 35 | 48.4% |

### Gaps over 10%

| Company | Fiscal year end | Line | This tool | Yahoo Finance | Gap |
| --- | --- | --- | ---: | ---: | ---: |
| CAT | 2023-12-31 | Capital expenditure | 1.60B | 3.09B | -48.4% |
| PFE | 2025-12-31 | Operating income | 10.19B | 17.41B | -41.5% |
| CAT | 2024-12-31 | Capital expenditure | 1.99B | 3.21B | -38.2% |
| CAT | 2025-12-31 | Capital expenditure | 2.82B | 4.29B | -34.2% |
| DIS | 2024-09-28 | Operating income | 15.60B | 11.91B | +30.9% |
| KO | 2024-12-31 | Operating income | 9.99B | 14.02B | -28.7% |
| DIS | 2025-09-27 | Operating income | 17.55B | 13.83B | +26.9% |
| PFE | 2023-12-31 | Operating income | 3.27B | 4.42B | -26.0% |
| XOM | 2024-12-31 | Operating income | 49.87B | 39.65B | +25.8% |
| PFE | 2024-12-31 | Operating income | 11.11B | 14.94B | -25.6% |
| XOM | 2025-12-31 | Operating income | 41.87B | 33.94B | +23.4% |
| XOM | 2023-12-31 | Operating income | 53.63B | 44.46B | +20.6% |
| HPQ | 2023-10-31 | Operating income | 3.46B | 4.22B | -18.2% |
| KO | 2023-12-31 | Operating income | 11.31B | 13.10B | -13.6% |
| HPQ | 2025-10-31 | Operating income | 3.17B | 3.62B | -12.4% |
| TSLA | 2025-12-31 | Operating income | 4.36B | 4.85B | -10.2% |
