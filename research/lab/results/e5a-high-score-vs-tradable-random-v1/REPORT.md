# e5a-high-score-vs-tradable-random-v1

Plain-language report written by the research lab on 2026-10-09. Every number comes from `result.json` in this folder.

## The question

Do SV's higher-scored signals pick better stocks than chance? Only signals in the fixed score groups of 45 and above (519 of 3,115) are traded, against random picks from the stocks SV could actually have picked that day.

## The short answer

- SV's account Sharpe 0.09 beat 10% of 200 random accounts (needed 95%).
- Trade by trade, SV's picks returned -1.02% more than random stocks bought the same day (t -1.38, needed 2.00).
- Selection skill shown: **no**.

## Account, 2005-09-12 to 2026-01-16

| Account | Sharpe | Growth a year | Worst fall |
|---|---|---|---|
| SV picks | 0.09 | 0.3% | 16.1% |
| Random picks, middle result | 0.27 | 1.0% | 17.5% |
| Random picks, best 5% | 0.50 | 2.0% | 13.2% |
| Random picks, worst 5% | 0.04 | 0.1% | 21.6% |

## Trade by trade

513 SV signals. Average trade: SV 0.26%, random 1.05%. Winning trades: SV 37.2%, random 43.7%. Statistic: winsorized at 1%/99%; median difference -2.96%; raw average difference -0.79%.

Random picks use SV's tradability floor on the signal day (min_history 420, min_close 5.0, min_dollar_volume 10000000.0). Excluded from both sides for provider price errors: ALT, APLD, CAPR, CATX, CHRD, CLSK, COGT, CYTK, LDOS, MDXG, MEL, PSKY, QNRX, QRVO, SYRE, VNDA, WFRD, WT.

## Style check

Same share of the account in each fund on the same days: SPY Sharpe 0.29, QQQ Sharpe 0.40, IWM Sharpe 0.25, RSP Sharpe 0.26.
After removing market, Nasdaq-100 and small-cap tilts, SV's extra return is -0.42% a year (t -0.54).

## Next step (planned before the run)

If the high-score signals pass: E2 with only those signals filling the core's 25% stock slice. If not: SV's stock picks are not used for the account; SV stays a market-information and watch-list tool while research looks for a different edge.
