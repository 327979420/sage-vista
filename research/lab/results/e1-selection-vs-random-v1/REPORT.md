# e1-selection-vs-random-v1

Plain-language report written by the research lab on 2026-10-09. Every number comes from `result.json` in this folder.

## The question

Does SV pick better stocks than chance? Every SV signal is copied with a random stock from the same universe that traded that day, bought and sold by the same rules; SV's account is ranked against 200 such random accounts, and its trades against random trades bought the same day.

## The short answer

- SV's account Sharpe 0.64 beat 86% of 200 random accounts (needed 95%).
- Trade by trade, SV's picks returned -187.35% more than random stocks bought the same day (t -1.00, needed 2.00).
- Selection skill shown: **no**.

## Account, 2005-09-12 to 2026-01-16

| Account | Sharpe | Growth a year | Worst fall |
|---|---|---|---|
| SV picks | 0.64 | 5.1% | 25.7% |
| Random picks, middle result | 0.48 | 4.0% | 31.3% |
| Random picks, best 5% | 0.69 | 6.8% | 25.3% |
| Random picks, worst 5% | 0.25 | 2.0% | 36.9% |

## Trade by trade

3110 SV signals. Average trade: SV 1.72%, random 189.38%. Winning trades: SV 40.8%, random 43.1%.

## Style check

Same share of the account in each fund on the same days: SPY Sharpe 0.60, QQQ Sharpe 0.72, IWM Sharpe 0.39, RSP Sharpe 0.51.
After removing market, Nasdaq-100 and small-cap tilts, SV's extra return is 2.91% a year (t 1.95).

## Next step (planned before the run)

If selection skill is shown: E2, SV fills the 25% stock slice of the core with SPY filling the gaps. If not: SV's stock picks are not built on; research turns to SV's market and sector reading (graded exposure, sector-fund rotation) and to finding why the picks fail.
