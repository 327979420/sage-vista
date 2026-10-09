# e0-core-long-history-v1

Plain-language report written by the research lab on 2026-10-09. Every number comes from `result.json` in this folder.

## The question

Is the Permanent Portfolio core robust beyond 2007-2026? Same portfolios on the longest history the data allows (older funds or spot prices before today's funds existed), with every rolling 5-year window checked, including the 1994 bond crash, 2000-02 and 2022.

## The short answer

- **PERM** (Permanent Portfolio: stocks, long bonds, gold, cash 25% each) passed every check written down before the run.
- Carried to the next step: **PERM** (Permanent Portfolio: stocks, long bonds, gold, cash 25% each), picked by the rule fixed before the run (Sharpe among portfolios with a worst fall within 25%).
- Goal 1 (match SPY's Sharpe 0.64 and Calmar 0.19 with a worst fall of at most 25%): met by PERM.

## The benchmark

Holding SPY from 1993-01-04 to 2026-01-16 turned $100,000 into $2,874,348: 10.7% a year, worst fall 55.2%, Sharpe 0.64, Calmar 0.19.

## Account results

| Rule | $100k became | Growth a year | Worst fall | Sharpe | Calmar | Money invested | Checks passed |
|---|---|---|---|---|---|---|---|
| SPY: US stocks only (benchmark) | $2,874,348 | 10.7% | 55.2% | 0.64 | 0.19 | 100% | 2 of 5 |
| 6040: 60/40: 60% US stocks, 40% US bonds | $1,510,021 | 8.6% | 33.8% | 0.81 | 0.25 | 100% | 4 of 5 |
| PERM (carried forward): Permanent Portfolio: stocks, long bonds, gold, cash 25% each | $1,080,058 | 7.5% | 18.4% | 1.10 | 0.41 | 100% | 5 of 5 |
| SPYT: Faber timing on US stocks: above the 10-month average, else short bonds | $2,308,204 | 10.0% | 28.1% | 0.81 | 0.35 | 100% | 4 of 5 |

## Checks for PERM

- ✓ Enough trades to judge
- ✓ Worst fall within the limit
- ✓ Better Sharpe than holding SPY
- ✓ Better growth per worst fall than holding SPY
- ✓ Not explained by having tried many rules

## Rolling 5-year windows

337 windows, starting monthly from 1993-01-04 to 2021-01-08.

| Portfolio | Median Sharpe | Worst 5% Sharpe | Worst fall in any window | Lowest window return | Windows with a gain |
|---|---|---|---|---|---|
| SPY | 0.74 | 0.01 | 55.2% | -34.5% | 85% |
| 6040 | 0.81 | 0.21 | 33.8% | -12.4% | 99% |
| PERM | 1.02 | 0.63 | 18.4% | 14.6% | 100% |
| SPYT | 0.79 | 0.26 | 28.1% | 1.8% | 100% |

Core checks (core): ✓ worst fall within limit, ✓ every window positive, ✓ sharpe beats benchmark often
Core Sharpe at least the benchmark's in 76% of windows. Core confirmed: **yes**.

Not tested on this window: AW (history too short: COMM).

## Next step (planned before the run)

If the core is confirmed, it stays the foundation and E2 (SV filling the 25% stock slice) uses it. If not, compare cores again on the long window (All Weather, 60/40, risk-based weights) before any SV integration.

## Words used

- **Sharpe**: return per unit of day-to-day swing; higher is smoother growth.
- **Calmar**: growth per year divided by the worst fall.
- **Worst fall**: the biggest drop from a previous high, in percent of the account.
- **Luck check**: the same rule re-run 200 times with same-day signals in shuffled order.
- **Money invested**: the average share of the account in stocks; the rest is cash.
