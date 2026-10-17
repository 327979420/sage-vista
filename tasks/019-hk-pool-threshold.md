# Task 019: a market-relative liquidity pool for Hong Kong (design only, no exam)

Read `tasks/README.md` first. Owner (2026-10-18): "this standard should change with the market; for HK it should be lower." Task 016
showed HK shapes are not rarer; HK loses at the tradable pool (21% of stock-weeks pass vs 50% in the US) and the market filter.

## Goal
Propose a rule that sets the daily-turnover floor RELATIVE to each market, decided by a principle, not by returns. For example:
the turnover level each day that keeps the same share of the market's stocks as the US floor (US$10M) keeps in the US, or a fixed
percentile of that day's turnover; plus a minimum that still allows a retail order to fill (state it in HK$ and US$). Compare 2-3
principled options.

## Allowed data
HK group A (already used) and US development data only - counts of pool size and of signals that would pass. NO returns, NO
p-values, NO account runs (that would be tuning on used data). HK group B, HK before 2005 and US 1985-2004 must not be loaded.

## Also check
- Costs: is 0.2% per side still realistic for the less liquid HK names admitted (spread estimate from the data you have, or say it
  cannot be estimated)?
- Would the rule change anything for US 3W (it must not - the frozen US version stays as it is)?

## Deliverables
`work/v3w/hk_pool.py` + log, `work/reports/hk-pool-v1.{json,html}` (simple Chinese), a draft pre-registration paragraph (Chinese) for
a future "3W HK version" exam on group B: the rule, the cost, the single verdict (same as task 010: Sharpe p <= 0.05 vs 1,000 random
accounts). Claude and the owner decide whether to register and spend group B. Codex report with Concerns. No network, no commits.
