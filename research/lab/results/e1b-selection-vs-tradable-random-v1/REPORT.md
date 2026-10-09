# e1b-selection-vs-tradable-random-v1

Plain-language report written by the research lab on 2026-10-09. Every number comes from `result.json` in this folder.

## The question

Corrected selection-skill test: does SV pick better stocks than random picks drawn from the stocks SV could actually have picked that day (at least 420 sessions of history, close of at least $5, at least $10M traded), with stocks that have provider price errors removed from both sides?

## The short answer

- SV's account Sharpe 0.57 beat 93% of 200 random accounts (needed 95%).
- Trade by trade, SV's picks returned 0.08% more than random stocks bought the same day (t -0.07, needed 2.00).
- Selection skill shown: **no**.

## Account, 2005-09-12 to 2026-01-16

| Account | Sharpe | Growth a year | Worst fall |
|---|---|---|---|
| SV picks | 0.57 | 4.5% | 25.9% |
| Random picks, middle result | 0.42 | 3.0% | 31.4% |
| Random picks, best 5% | 0.61 | 4.6% | 24.3% |
| Random picks, worst 5% | 0.25 | 1.6% | 37.4% |

## Trade by trade

3072 SV signals. Average trade: SV 1.64%, random 1.33%. Winning trades: SV 41.0%, random 44.8%. Statistic: winsorized at 1%/99%; median difference -2.21%; raw average difference 0.31%.

Random picks use SV's tradability floor on the signal day (min_history 420, min_close 5.0, min_dollar_volume 10000000.0). Excluded from both sides for provider price errors: ALT, APLD, CAPR, CATX, CHRD, CLSK, COGT, CYTK, LDOS, MDXG, MEL, PSKY, QNRX, QRVO, SYRE, VNDA, WFRD, WT.

## Style check

Same share of the account in each fund on the same days: SPY Sharpe 0.60, QQQ Sharpe 0.73, IWM Sharpe 0.39, RSP Sharpe 0.51.
After removing market, Nasdaq-100 and small-cap tilts, SV's extra return is 2.34% a year (t 1.62).

## Next step (planned before the run)

If selection skill is shown: E2, SV fills the 25% stock slice of the core with SPY filling the gaps. If not: SV's stock picks are not built on; research continues with the market and sector reading (E3, E4) and with why the picks fall short.
