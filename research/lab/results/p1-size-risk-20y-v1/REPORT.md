# p1-size-risk-20y-v1

Plain-language report written by the research lab on 2026-10-08. Every number comes from `result.json` in this folder.

## The question

Portfolio step 1: with round 2's best selling rule (current stop, no 2R target, 40 days), how big should each position be and how much should each trade and the whole account risk? Settings are taken from the ranges mature programs use, and a rule fixed before the run picks one.

## The short answer

- No rule passed every check written down before the run, so the current rule stays.
- Carried to the next step: **R0.5-P5-M10-H10** (Risk 0.5%, cap 5%, up to 10 stocks, open risk 10%), picked by the rule fixed before the run (luck-check median Sharpe averaged with neighbouring settings; no setting stayed within the drawdown limit).
- Goal 1 (match SPY's Sharpe 0.63 and Calmar 0.20 with a worst fall of at most 25%): not met yet. Closest Sharpe: R0.5-P5-M10-H6 at 0.64.

## The benchmark

Holding SPY from 2005-09-12 to 2026-01-16 turned $100,000 into $812,848: 10.8% a year, worst fall 55.2%, Sharpe 0.63, Calmar 0.20.

## Account results

| Rule | $100k became | Growth a year | Worst fall | Sharpe | Calmar | Money invested | Checks passed |
|---|---|---|---|---|---|---|---|
| A0: Current rule: support -5% (max 10%), sell all at 2R, 40 days | $216,416 | 3.9% | 31.9% | 0.44 | 0.12 | 43% | 2 of 10 |
| D1: Round 2 best: current stop, no 2R target, 40 days (approved $10k positions) | $315,462 | 5.8% | 43.1% | 0.52 | 0.13 | 52% | 6 of 10 |
| R0.5-P5-M10-H10 (carried forward): Risk 0.5%, cap 5%, up to 10 stocks, open risk 10% | $277,395 | 5.1% | 25.7% | 0.64 | 0.20 | 37% | 8 of 10 |
| R0.5-P10-M20-H10: Risk 0.5%, cap 10%, up to 20 stocks, open risk 10% | $477,849 | 8.0% | 36.0% | 0.62 | 0.22 | 62% | 8 of 10 |
| R0.5-P10-M15-H10: Risk 0.5%, cap 10%, up to 15 stocks, open risk 10% | $443,561 | 7.6% | 36.0% | 0.60 | 0.21 | 62% | 8 of 10 |
| R0.5-P5-M10-H6: Risk 0.5%, cap 5%, up to 10 stocks, open risk 6% | $277,395 | 5.1% | 25.7% | 0.64 | 0.20 | 37% | 8 of 10 |
| R1-P5-M10-H6: Risk 1%, cap 5%, up to 10 stocks, open risk 6% | $277,395 | 5.1% | 25.7% | 0.64 | 0.20 | 37% | 8 of 10 |

Showing 7 of 38 rules: the references, the one carried forward and the five best luck-check results. All are in `result.json` and the scoreboard.

## Checks for R0.5-P5-M10-H10

- ✓ Enough trades to judge
- ✗ Worst fall within the limit
- ✓ Better Sharpe than the current rule
- ✓ Better growth per worst fall (Calmar) than the current rule
- ✓ Better Sharpe than holding SPY
- ✓ Better growth per worst fall than holding SPY
- ✓ Still beats the current rule when same-day signal order is shuffled
- ✓ Even the unluckiest 5% of shuffled runs still grow
- ✗ Account grew in every five-year period
- ✓ Not explained by having tried many rules

## Next step (planned before the run)

Step 2: sector limits on top of the setting carried forward here: at most 25% of the account per sector, or each sector within 5 or 10 points of SPY's sector weight, with SV score deciding within a sector and a monthly-trim version. Uses today's sector labels for research only (approved 2026-10-08).

## Words used

- **Sharpe**: return per unit of day-to-day swing; higher is smoother growth.
- **Calmar**: growth per year divided by the worst fall.
- **Worst fall**: the biggest drop from a previous high, in percent of the account.
- **Luck check**: the same rule re-run 200 times with same-day signals in shuffled order.
- **Money invested**: the average share of the account in stocks; the rest is cash.
