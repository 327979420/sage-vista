# b1-core-satellite-v1

Plain-language report written by the research lab on 2026-10-09. Every number comes from `result.json` in this folder.

## The question

Step B: do SV's stock picks improve a proven portfolio? SV takes 0, 20, 35 or 50% of the account (5% per stock, up to 0, 4, 7 or 10 stocks), the rest sits in the core (the Permanent Portfolio, with All Weather as a check) and 5% is always kept in cash.

## The short answer

- No rule passed every check written down before the run, so the current rule stays.
- Carried to the next step: **CPERM-M0** (Core PERM, no SV stocks), picked by the rule fixed before the run (SV is added only if a satellite beats the Permanent core without SV on both Sharpe and Calmar with a worst fall within 25%; within 0.01 Sharpe the smaller satellite wins; the same share is reported on All Weather.).
- Goal 1 (match SPY's Sharpe 0.61 and Calmar 0.19 with a worst fall of at most 25%): met by CPERM-M0, CPERM-M4, CPERM-M7, CAW-M0, CAW-M4, CAW-M7.

## The benchmark

Holding SPY from 2007-01-03 to 2026-01-16 turned $100,000 into $691,596: 10.7% a year, worst fall 55.2%, Sharpe 0.61, Calmar 0.19.

## Account results

| Rule | $100k became | Growth a year | Worst fall | Sharpe | Calmar | Money invested | Checks passed |
|---|---|---|---|---|---|---|---|
| SV: SV picks alone, step 1 setting (5% per stock, up to 10), rest in cash | $247,082 | 4.9% | 26.9% | 0.60 | 0.18 | 36% | 2 of 10 |
| CPERM-M0 (carried forward): Core PERM, no SV stocks | $366,675 | 7.1% | 17.7% | 1.01 | 0.40 | 0% | 6 of 10 |
| CPERM-M4: Core PERM, up to 4 stocks | $420,956 | 7.8% | 21.3% | 0.95 | 0.37 | 17% | 7 of 10 |
| CAW-M0: Core AW, no SV stocks | $329,902 | 6.5% | 22.2% | 0.85 | 0.29 | 0% | 6 of 10 |
| CPERM-M10: Core PERM, up to 10 stocks | $505,458 | 8.9% | 27.0% | 0.84 | 0.33 | 36% | 5 of 10 |
| CPERM-M7: Core PERM, up to 7 stocks | $404,814 | 7.6% | 23.8% | 0.82 | 0.32 | 27% | 6 of 10 |

Showing 6 of 9 rules: the references, the one carried forward and the five best luck-check results. All are in `result.json` and the scoreboard.

## Checks for CPERM-M0

- ✗ Enough trades to judge
- ✓ Worst fall within the limit
- ✗ Better Sharpe than the current rule
- ✗ Better growth per worst fall (Calmar) than the current rule
- ✓ Better Sharpe than holding SPY
- ✓ Better growth per worst fall than holding SPY
- ✗ Still beats the current rule when same-day signal order is shuffled
- ✓ Even the unluckiest 5% of shuffled runs still grow
- ✓ Account grew in every five-year period
- ✓ Not explained by having tried many rules

## Next step (planned before the run)

If SV is added: sector limits on the satellite (step 2), then the forward test and practice account. If not: the core alone goes forward, and SV research returns to what it buys (entries and signal quality) before trying again.

## Words used

- **Sharpe**: return per unit of day-to-day swing; higher is smoother growth.
- **Calmar**: growth per year divided by the worst fall.
- **Worst fall**: the biggest drop from a previous high, in percent of the account.
- **Luck check**: the same rule re-run 200 times with same-day signals in shuffled order.
- **Money invested**: the average share of the account in stocks; the rest is cash.
