# e8-factor-slice-v1

Plain-language report written by the research lab on 2026-10-10. Every number comes from `result.json` in this folder.

## The question

Can a published factor fund (low volatility, quality, momentum, dividend growers, equal weight) replace SPY as the core's 25% stock slice and raise its risk-adjusted result without picking single stocks?

## The short answer

- No portfolio passed every check written down before the run.
- Carried to the next step: **PERM** (Permanent core with SPY (current core)), picked by the rule fixed before the run (A factor slice replaces SPY in the core only if the core's Sharpe rises with a worst fall within 25%; among those, the highest Sharpe.).
- Goal 1 (match SPY's Sharpe 0.82 and Calmar 0.41 with a worst fall of at most 25%): not met yet. Closest Sharpe: PERM at 1.00.

## The benchmark

Holding SPY from 2014-08-01 to 2026-01-16 turned $100,000 into $436,538: 13.7% a year, worst fall 33.7%, Sharpe 0.82, Calmar 0.41.

## Account results

| Rule | $100k became | Growth a year | Worst fall | Sharpe | Calmar | Money invested | Checks passed |
|---|---|---|---|---|---|---|---|
| SPY: S&P 500 (benchmark) | $436,538 | 13.7% | 33.7% | 0.82 | 0.41 | 100% | 2 of 5 |
| USMV: US minimum volatility (USMV) | $318,911 | 10.6% | 33.1% | 0.78 | 0.32 | 100% | 2 of 5 |
| QUAL: US quality (QUAL) | $420,785 | 13.4% | 34.1% | 0.80 | 0.39 | 100% | 2 of 5 |
| MTUM: US momentum (MTUM) | $472,705 | 14.5% | 34.1% | 0.78 | 0.43 | 100% | 3 of 5 |
| SPLV: S&P 500 low volatility (SPLV) | $274,480 | 9.2% | 36.3% | 0.66 | 0.25 | 100% | 1 of 5 |
| VIG: Dividend growers (VIG) | $375,768 | 12.2% | 31.7% | 0.81 | 0.39 | 100% | 2 of 5 |
| RSP: S&P 500 equal weight (RSP) | $322,807 | 10.8% | 39.0% | 0.66 | 0.28 | 100% | 1 of 5 |
| PERM (carried forward): Permanent core with SPY (current core) | $220,802 | 7.2% | 18.4% | 1.00 | 0.39 | 100% | 4 of 5 |
| PERM-USMV: Core with minimum volatility as the stock slice | $202,665 | 6.4% | 16.9% | 0.91 | 0.38 | 100% | 4 of 5 |
| PERM-QUAL: Core with quality as the stock slice | $219,159 | 7.1% | 19.6% | 0.99 | 0.36 | 100% | 4 of 5 |
| PERM-MTUM: Core with momentum as the stock slice | $224,924 | 7.3% | 20.0% | 0.96 | 0.37 | 100% | 4 of 5 |
| PERM-SPLV: Core with S&P 500 low volatility as the stock slice | $195,901 | 6.0% | 16.4% | 0.85 | 0.37 | 100% | 4 of 5 |
| PERM-VIG: Core with dividend growers as the stock slice | $211,206 | 6.7% | 17.4% | 0.97 | 0.39 | 100% | 4 of 5 |
| PERM-RSP: Core with equal weight as the stock slice | $203,923 | 6.4% | 17.7% | 0.90 | 0.36 | 100% | 4 of 5 |
| PERM-MULTI: Core with a third each of minimum volatility, quality and momentum | $215,613 | 6.9% | 18.7% | 0.97 | 0.37 | 100% | 4 of 5 |

## Checks for PERM

- ✓ Enough trades to judge
- ✓ Worst fall within the limit
- ✓ Better Sharpe than holding SPY
- ✗ Better growth per worst fall than holding SPY
- ✓ Not explained by having tried many rules

## Questions fixed before the run

- ✗ USMV beats SPY on Sharpe on its own (USMV 0.78 vs SPY 0.82)
- ✗ QUAL beats SPY on Sharpe on its own (QUAL 0.80 vs SPY 0.82)
- ✗ MTUM beats SPY on Sharpe on its own (MTUM 0.78 vs SPY 0.82)
- ✗ SPLV beats SPY on Sharpe on its own (SPLV 0.66 vs SPY 0.82)
- ✗ VIG beats SPY on Sharpe on its own (VIG 0.81 vs SPY 0.82)
- ✗ RSP beats SPY on Sharpe on its own (RSP 0.66 vs SPY 0.82)

Improvement over PERM: **no, the baseline stays**.

## Next step (planned before the run)

If a factor slice improves the core, it joins the forward paper accounts next to the fixed core. Factor funds are diversified and need no stock picking, so they avoid the selection problem SV's picks showed.

## Words used

- **Sharpe**: return per unit of day-to-day swing; higher is smoother growth.
- **Calmar**: growth per year divided by the worst fall.
- **Worst fall**: the biggest drop from a previous high, in percent of the account.
- **Luck check**: the same rule re-run 200 times with same-day signals in shuffled order.
- **Money invested**: the average share of the account in stocks; the rest is cash.
