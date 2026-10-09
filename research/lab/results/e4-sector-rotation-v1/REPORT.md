# e4-sector-rotation-v1

Plain-language report written by the research lab on 2026-10-09. Every number comes from `result.json` in this folder.

## The question

Does holding the strongest US sectors (industry momentum) beat holding the whole market, on its own and as the 25% stock slice of the core? Sector funds have no survivorship problem and full daily history, so this tests SV's 'sector strength' idea cleanly with price momentum as the measure.

## The short answer

- **PERM** (Permanent Portfolio with SPY as the stock slice (current core)) passed every check written down before the run.
- Carried to the next step: **PERM** (Permanent Portfolio with SPY as the stock slice (current core)), picked by the rule fixed before the run (The rotation slice replaces SPY in the core only if the core's Sharpe rises with a worst fall within 25%.).
- Goal 1 (match SPY's Sharpe 0.63 and Calmar 0.20 with a worst fall of at most 25%): met by PERM, PERM-ROT, PERM-EW9.

## The benchmark

Holding SPY from 2005-12-01 to 2026-01-16 turned $100,000 into $798,522: 10.9% a year, worst fall 55.2%, Sharpe 0.63, Calmar 0.20.

## Account results

| Rule | $100k became | Growth a year | Worst fall | Sharpe | Calmar | Money invested | Checks passed |
|---|---|---|---|---|---|---|---|
| SPY: S&P 500 (benchmark) | $798,522 | 10.9% | 55.2% | 0.63 | 0.20 | 100% | 2 of 5 |
| EW9: Nine sector funds, equal weight, rebalanced monthly | $721,176 | 10.3% | 53.5% | 0.62 | 0.19 | 100% | 1 of 5 |
| ROT: Top 3 of 9 sectors by average 3/6/12-month return, rebalanced monthly | $578,924 | 9.1% | 46.8% | 0.57 | 0.20 | 100% | 1 of 5 |
| ROT-ABS: Same, but a pick is held only if it beat short-term Treasuries, else cash | $534,730 | 8.7% | 25.3% | 0.61 | 0.34 | 100% | 2 of 5 |
| PERM (carried forward): Permanent Portfolio with SPY as the stock slice (current core) | $434,341 | 7.6% | 18.4% | 1.03 | 0.41 | 100% | 5 of 5 |
| PERM-ROT: Core with the stock slice as the top 3 sectors (8.33% each) | $383,542 | 6.9% | 15.2% | 0.93 | 0.45 | 100% | 5 of 5 |
| PERM-EW9: Core with the stock slice as nine sectors equal weight | $408,844 | 7.2% | 16.3% | 0.99 | 0.44 | 100% | 5 of 5 |

## Checks for PERM

- ✓ Enough trades to judge
- ✓ Worst fall within the limit
- ✓ Better Sharpe than holding SPY
- ✓ Better growth per worst fall than holding SPY
- ✓ Not explained by having tried many rules

## Questions fixed before the run

- ✗ Sector rotation beats SPY on Sharpe (ROT 0.57 vs SPY 0.63)
- ✗ Sector rotation beats equal-weight sectors on Sharpe (ROT 0.57 vs EW9 0.62)
- ✓ Rotation with the cash test beats SPY on Calmar (ROT-ABS 0.34 vs SPY 0.20)
- ✓ Core with a rotation slice beats the core with SPY on Calmar (PERM-ROT 0.45 vs PERM 0.41)
- ✗ Core with equal-weight sectors beats the core with SPY on Sharpe (PERM-EW9 0.99 vs PERM 1.03)

Improvement over PERM: **no, the baseline stays**.

## Next step (planned before the run)

If rotation helps the core, it joins the forward paper accounts and SV's live sector score can later be tested the same way. If not, the core keeps SPY as its stock slice.

## Words used

- **Sharpe**: return per unit of day-to-day swing; higher is smoother growth.
- **Calmar**: growth per year divided by the worst fall.
- **Worst fall**: the biggest drop from a previous high, in percent of the account.
- **Luck check**: the same rule re-run 200 times with same-day signals in shuffled order.
- **Money invested**: the average share of the account in stocks; the rest is cash.
