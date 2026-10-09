# c1-proven-portfolios-v1

Plain-language report written by the research lab on 2026-10-08. Every number comes from `result.json` in this folder.

## The question

Which published, proven portfolio does best on the same 19 years, judged like the SV account (Sharpe, Calmar, worst fall within 25%, every period)? The best becomes the core that SV's stock picks must improve.

## The short answer

- **PERM** (Permanent Portfolio: stocks, long bonds, gold, cash 25% each) passed every check written down before the run.
- Carried to the next step: **PERM** (Permanent Portfolio: stocks, long bonds, gold, cash 25% each), picked by the rule fixed before the run (Sharpe among portfolios with a worst fall within 25%).
- Goal 1 (match SPY's Sharpe 0.61 and Calmar 0.19 with a worst fall of at most 25%): met by PERM, AW.

## The benchmark

Holding SPY from 2007-01-03 to 2026-01-16 turned $100,000 into $690,905: 10.7% a year, worst fall 55.2%, Sharpe 0.61, Calmar 0.19.

## Account results

| Rule | $100k became | Growth a year | Worst fall | Sharpe | Calmar | Money invested | Checks passed |
|---|---|---|---|---|---|---|---|
| SPY: S&P 500 only (benchmark) | $690,905 | 10.7% | 55.2% | 0.61 | 0.19 | 100% | 1 of 6 |
| 6040: 60/40: 60% US stocks, 40% US bonds | $435,536 | 8.0% | 33.8% | 0.73 | 0.24 | 100% | 4 of 6 |
| PERM (carried forward): Permanent Portfolio: stocks, long bonds, gold, cash 25% each | $384,489 | 7.3% | 18.4% | 1.00 | 0.40 | 100% | 6 of 6 |
| AW: All Weather: 30% stocks, 55% bonds, 15% gold and commodities | $343,798 | 6.7% | 23.0% | 0.84 | 0.29 | 100% | 6 of 6 |
| IVY: Ivy Portfolio: 5 asset classes, 20% each, always held | $285,079 | 5.7% | 47.1% | 0.45 | 0.12 | 100% | 1 of 6 |
| GTAA5: Faber timing: the Ivy 5, each held only above its 10-month average | $238,402 | 4.7% | 13.8% | 0.61 | 0.34 | 100% | 4 of 6 |
| SPYT: Faber timing on the S&P 500 alone: SPY above its 10-month average, else cash | $440,509 | 8.1% | 28.1% | 0.67 | 0.29 | 100% | 5 of 6 |
| GEM: Dual Momentum: US or international stocks when beating cash over 12 months, else bonds | $329,087 | 6.5% | 34.8% | 0.48 | 0.19 | 100% | 2 of 6 |

## Checks for PERM

- ✓ Enough trades to judge
- ✓ Worst fall within the limit
- ✓ Better Sharpe than holding SPY
- ✓ Better growth per worst fall than holding SPY
- ✓ Account grew in every five-year period
- ✓ Not explained by having tried many rules

## Next step (planned before the run)

Step B: put SV's stock picks inside the chosen core as a satellite of 0%, 20%, 35% or 50% of the account, with a standing 5% cash reserve and position sizes from step 1. SV stays only if it improves the core's Sharpe and Calmar.

## Words used

- **Sharpe**: return per unit of day-to-day swing; higher is smoother growth.
- **Calmar**: growth per year divided by the worst fall.
- **Worst fall**: the biggest drop from a previous high, in percent of the account.
- **Luck check**: the same rule re-run 200 times with same-day signals in shuffled order.
- **Money invested**: the average share of the account in stocks; the rest is cash.
