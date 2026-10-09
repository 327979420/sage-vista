# e3-graded-exposure-v1

Plain-language report written by the research lab on 2026-10-09. Every number comes from `result.json` in this folder.

## The question

Can the core step its stock (and bond and gold) exposure down gradually when markets turn bad, cutting the worst falls without lowering Sharpe? Published rules only: Faber's 10-month average, the share of 1/3/12-month returns above cash (Hurst, Ooi and Pedersen), and volatility targeting (Moreira and Muir).

## The short answer

- **PERM-ALL-TSMOM** (Core, stocks, long bonds and gold each stepped by 1/3/12-month trend) passed every check written down before the run.
- Carried to the next step: **PERM-ALL-TSMOM** (Core, stocks, long bonds and gold each stepped by 1/3/12-month trend), picked by the rule fixed before the run (A variant replaces the fixed core only if its Calmar is higher, its Sharpe is not lower and its worst fall stays within 25%; among those, the highest Calmar.).
- Goal 1 (match SPY's Sharpe 0.64 and Calmar 0.19 with a worst fall of at most 25%): met by PERM, PERM-SMA, PERM-TSMOM, PERM-VOL, PERM-TSMOM-VOL, PERM-ALL-TSMOM.

## The benchmark

Holding SPY from 1993-01-04 to 2026-01-16 turned $100,000 into $2,874,348: 10.7% a year, worst fall 55.2%, Sharpe 0.64, Calmar 0.19.

## Account results

| Rule | $100k became | Growth a year | Worst fall | Sharpe | Calmar | Money invested | Checks passed |
|---|---|---|---|---|---|---|---|
| SPY: US stocks only (benchmark) | $2,874,348 | 10.7% | 55.2% | 0.64 | 0.19 | 100% | 2 of 5 |
| PERM: Permanent Portfolio, fixed 25% each (current core) | $1,080,058 | 7.5% | 18.4% | 1.10 | 0.41 | 100% | 5 of 5 |
| PERM-SMA: Core, stock slice on/off by Faber's 10-month average | $931,013 | 7.0% | 18.6% | 1.08 | 0.38 | 100% | 5 of 5 |
| PERM-TSMOM: Core, stock slice stepped by 1/3/12-month trend (0, 1/3, 2/3 or all) | $844,436 | 6.7% | 18.4% | 1.06 | 0.36 | 100% | 5 of 5 |
| PERM-VOL: Core, stock slice scaled to 15% volatility (never above full) | $906,810 | 6.9% | 17.8% | 1.08 | 0.39 | 100% | 5 of 5 |
| PERM-TSMOM-VOL: Core, stock slice stepped by trend and scaled by volatility | $787,932 | 6.4% | 17.6% | 1.03 | 0.37 | 100% | 5 of 5 |
| PERM-ALL-TSMOM (carried forward): Core, stocks, long bonds and gold each stepped by 1/3/12-month trend | $636,669 | 5.8% | 11.5% | 1.16 | 0.50 | 100% | 5 of 5 |

## Checks for PERM-ALL-TSMOM

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
| PERM | 1.02 | 0.63 | 18.4% | 14.6% | 100% |
| PERM-SMA | 1.06 | 0.43 | 18.6% | 8.0% | 100% |
| PERM-TSMOM | 1.07 | 0.35 | 18.4% | 3.8% | 100% |
| PERM-VOL | 1.05 | 0.53 | 17.8% | 11.7% | 100% |
| PERM-TSMOM-VOL | 1.03 | 0.34 | 17.6% | 2.8% | 100% |
| PERM-ALL-TSMOM | 1.11 | 0.31 | 11.5% | 2.7% | 100% |

Improvement over PERM: **yes, PERM-ALL-TSMOM**.

## Next step (planned before the run)

If a variant improves the core, it joins the forward paper accounts next to the fixed core; neither replaces the other until the forward record agrees. If none improves it, the fixed core stays and SV's market reading is not used to time the core.

## Words used

- **Sharpe**: return per unit of day-to-day swing; higher is smoother growth.
- **Calmar**: growth per year divided by the worst fall.
- **Worst fall**: the biggest drop from a previous high, in percent of the account.
- **Luck check**: the same rule re-run 200 times with same-day signals in shuffled order.
- **Money invested**: the average share of the account in stocks; the rest is cash.
