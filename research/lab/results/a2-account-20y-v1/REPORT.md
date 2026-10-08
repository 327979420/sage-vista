# a2-account-20y-v1

Plain-language report written by the research lab on 2026-10-08. Every number comes from `result.json` in this folder.

## The question

Which selling rule grows the approved $100k account best after risk over twenty years, and does it beat the current rule and simply holding SPY? The current rule is also taken apart (2R target, 40-day limit) to see which part costs most.

## The short answer

- No rule passed every check written down before the run, so the current rule stays.
- Goal 1 (match SPY's Sharpe 0.63 and Calmar 0.20 with a worst fall of at most 25%): not met yet. Closest Sharpe: D1 at 0.52.

## The benchmark

Holding SPY from 2005-09-12 to 2026-01-16 turned $100,000 into $812,848: 10.8% a year, worst fall 55.2%, Sharpe 0.63, Calmar 0.20.

## Account results

| Rule | $100k became | Growth a year | Worst fall | Sharpe | Calmar | Money invested | Checks passed |
|---|---|---|---|---|---|---|---|
| A0: Current rule: support -5% (max 10%), sell all at 2R, 40 days | $216,416 | 3.9% | 31.9% | 0.44 | 0.12 | 43% | 2 of 10 |
| D1: Current stop, no 2R target, 40 days | $315,462 | 5.8% | 43.1% | 0.52 | 0.13 | 52% | 6 of 10 |
| D2: Current stop and 2R target, 60 days | $200,233 | 3.5% | 34.3% | 0.38 | 0.10 | 49% | 3 of 10 |
| D3: Current stop, no target, 60 days | $255,246 | 4.7% | 44.8% | 0.43 | 0.11 | 56% | 3 of 10 |
| P20-40: Emergency stop -20%, time exit 40 days | $269,757 | 5.0% | 53.4% | 0.40 | 0.09 | 60% | 3 of 10 |
| P20-60: Emergency stop -20%, time exit 60 days | $266,802 | 4.9% | 46.2% | 0.41 | 0.11 | 60% | 3 of 10 |
| P20-90: Emergency stop -20%, time exit 90 days | $288,970 | 5.4% | 56.8% | 0.39 | 0.09 | 73% | 3 of 10 |
| N2.5-60: Stop 2.5xATR(20), time exit 60 days | $280,443 | 5.2% | 60.4% | 0.41 | 0.09 | 61% | 3 of 10 |
| C60: Disaster stop -50% only, sell after 60 days | $352,787 | 6.4% | 44.3% | 0.49 | 0.14 | 56% | 6 of 10 |

## Checks for D1

- ✓ Enough trades to judge
- ✗ Worst fall within the limit
- ✓ Better Sharpe than the current rule
- ✓ Better growth per worst fall (Calmar) than the current rule
- ✗ Better Sharpe than holding SPY
- ✗ Better growth per worst fall than holding SPY
- ✓ Still beats the current rule when same-day signal order is shuffled
- ✓ Even the unluckiest 5% of shuffled runs still grow
- ✗ Account grew in every five-year period
- ✓ Not explained by having tried many rules

## Words used

- **Sharpe**: return per unit of day-to-day swing; higher is smoother growth.
- **Calmar**: growth per year divided by the worst fall.
- **Worst fall**: the biggest drop from a previous high, in percent of the account.
- **Luck check**: the same rule re-run 200 times with same-day signals in shuffled order.
- **Money invested**: the average share of the account in stocks; the rest is cash.
