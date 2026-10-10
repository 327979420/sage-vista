# e7b-level-rules-20y-v1

Plain-language report written by the research lab on 2026-10-10. Every number comes from `result.json` in this folder.

## The question

Under the user's own rules (stop 2% below the daily volume profile's value-area low, positions of 5% of the account losing at most 2% of it at the stop, holding by opportunity level, no profit target, the case ledger's hard checks) do SV's opportunities beat random stocks traded the same day under the same rules, and do the exits of mature trading systems help? Secondary: does the SV account beat SPY in at least one five-year period, and how do win rate and reward against risk compare?

## The short answer

- Families that beat random picks under the pre-registered bar: none.
- Extra checks that passed: none.
- Champion (highest SV Sharpe among passing families): none.
- Rule chosen across every passing family and extra check: none .
- SPY bought and held over the same window: Sharpe 0.65, CAGR 11.1%, worst fall 55.2%, Calmar 0.20.

- Hard checks (deep fall, wide box) on vs off, same family: Sharpe 0.42 vs 0.39, Calmar 0.11 vs 0.11; they help: **yes**.

## main: account and trades against random picks

Signals traded: 2366; median stop distance 15.7%; bought after waiting for a reclaim: 0.

| Family | SV Sharpe | SV CAGR | SV worst fall | Beats random accounts | Trade difference (winsorized) | t | Median difference | Goal 1 vs SPY | Some period beats SPY | Passed |
|---|---|---|---|---|---|---|---|---|---|---|
| T0 | 0.42 | 3.2% | 29.0% | 49.5% | 0.07% | 0.41 | -0.63% | no | no | no |
| T1 | 0.38 | 2.8% | 28.2% | 41.0% | 0.07% | 0.35 | -0.78% | no | no | no |
| T2 | 0.38 | 2.7% | 22.1% | 44.0% | -0.09% | -0.04 | -1.55% | no | yes | no |
| T3 | 0.32 | 2.3% | 31.6% | 19.5% | -0.03% | 0.01 | -1.25% | no | no | no |
| T4 | 0.47 | 4.4% | 31.4% | 46.0% | 0.82% | 1.36 | -3.64% | no | no | no |

Win rate and reward against risk (SV trades vs all random trades; returns are per trade, before position size):

| Family | SV win rate | SV avg win | SV avg loss | SV payoff | SV profit factor | SV E[R] | Random win rate | Random payoff | Random profit factor | Random E[R] |
|---|---|---|---|---|---|---|---|---|---|---|
| T0 | 52.8% | 12.8% | -9.9% | 1.29 | 1.45 | 0.12 | 50.6% | 1.39 | 1.43 | 0.12 |
| T1 | 50.2% | 12.3% | -8.7% | 1.41 | 1.42 | 0.10 | 48.4% | 1.48 | 1.39 | 0.10 |
| T2 | 42.9% | 12.3% | -6.8% | 1.81 | 1.36 | 0.08 | 44.5% | 1.69 | 1.35 | 0.09 |
| T3 | 46.6% | 13.4% | -8.4% | 1.59 | 1.39 | 0.10 | 46.2% | 1.62 | 1.39 | 0.11 |
| T4 | 37.9% | 27.2% | -8.4% | 3.23 | 1.97 | 0.36 | 38.1% | 2.90 | 1.78 | 0.26 |

Signals by level and what happened to them:

| Level | no_support | stop_too_wide | traded | veto_deep_drawdown | veto_wide_box |
|---|---|---|---|---|---|
| daily | 1 | 26 | 915 | 285 | 9 |
| monthly | 1 | 17 | 464 | 171 | 8 |
| weekly | 4 | 21 | 987 | 157 | 11 |

## veto_off: account and trades against random picks

Signals traded: 2762; median stop distance 16.9%; bought after waiting for a reclaim: 0.

| Family | SV Sharpe | SV CAGR | SV worst fall | Beats random accounts | Trade difference (winsorized) | t | Median difference | Goal 1 vs SPY | Some period beats SPY | Passed |
|---|---|---|---|---|---|---|---|---|---|---|
| T0 | 0.39 | 3.2% | 28.8% | 25.5% | 0.00% | 0.25 | -0.83% | no | no | no |

Win rate and reward against risk (SV trades vs all random trades; returns are per trade, before position size):

| Family | SV win rate | SV avg win | SV avg loss | SV payoff | SV profit factor | SV E[R] | Random win rate | Random payoff | Random profit factor | Random E[R] |
|---|---|---|---|---|---|---|---|---|---|---|
| T0 | 53.1% | 14.2% | -10.5% | 1.35 | 1.52 | 0.13 | 51.6% | 1.47 | 1.56 | 0.15 |

Signals by level and what happened to them:

| Level | no_support | stop_too_wide | traded |
|---|---|---|---|
| daily | 1 | 132 | 1103 |
| monthly | 2 | 93 | 566 |
| weekly | 4 | 83 | 1093 |

## stop_va60: account and trades against random picks

Signals traded: 2399; median stop distance 10.6%; bought after waiting for a reclaim: 0.

| Family | SV Sharpe | SV CAGR | SV worst fall | Beats random accounts | Trade difference (winsorized) | t | Median difference | Goal 1 vs SPY | Some period beats SPY | Passed |
|---|---|---|---|---|---|---|---|---|---|---|
| T0 | 0.42 | 3.2% | 33.4% | 56.0% | -0.08% | -0.14 | -0.96% | no | yes | no |

Win rate and reward against risk (SV trades vs all random trades; returns are per trade, before position size):

| Family | SV win rate | SV avg win | SV avg loss | SV payoff | SV profit factor | SV E[R] | Random win rate | Random payoff | Random profit factor | Random E[R] |
|---|---|---|---|---|---|---|---|---|---|---|
| T0 | 48.4% | 13.0% | -8.9% | 1.46 | 1.37 | 0.16 | 47.1% | 1.55 | 1.38 | 0.16 |

Signals by level and what happened to them:

| Level | no_support | stop_too_wide | traded | veto_deep_drawdown | veto_wide_box |
|---|---|---|---|---|---|
| daily | 10 | 2 | 930 | 285 | 9 |
| monthly | 4 | 4 | 474 | 171 | 8 |
| weekly | 9 | 8 | 995 | 157 | 11 |

## risk_0.5pct: account and trades against random picks

Signals traded: 1106; median stop distance 10.1%; bought after waiting for a reclaim: 0.

| Family | SV Sharpe | SV CAGR | SV worst fall | Beats random accounts | Trade difference (winsorized) | t | Median difference | Goal 1 vs SPY | Some period beats SPY | Passed |
|---|---|---|---|---|---|---|---|---|---|---|
| T0 | 0.49 | 2.3% | 22.8% | 76.5% | 0.10% | 0.38 | -0.85% | no | no | no |

Win rate and reward against risk (SV trades vs all random trades; returns are per trade, before position size):

| Family | SV win rate | SV avg win | SV avg loss | SV payoff | SV profit factor | SV E[R] | Random win rate | Random payoff | Random profit factor | Random E[R] |
|---|---|---|---|---|---|---|---|---|---|---|
| T0 | 47.7% | 10.7% | -7.5% | 1.42 | 1.30 | 0.12 | 45.7% | 1.51 | 1.27 | 0.12 |

Signals by level and what happened to them:

| Level | no_support | stop_too_wide | traded | veto_deep_drawdown | veto_wide_box |
|---|---|---|---|---|---|
| daily | 1 | 479 | 462 | 285 | 9 |
| monthly | 1 | 317 | 164 | 171 | 8 |
| weekly | 4 | 528 | 480 | 157 | 11 |

## market_filter: account and trades against random picks

Signals traded: 1852; median stop distance 16.0%; bought after waiting for a reclaim: 0.

| Family | SV Sharpe | SV CAGR | SV worst fall | Beats random accounts | Trade difference (winsorized) | t | Median difference | Goal 1 vs SPY | Some period beats SPY | Passed |
|---|---|---|---|---|---|---|---|---|---|---|
| T0 | 0.40 | 2.7% | 18.2% | 11.5% | 0.04% | -0.55 | -0.53% | no | yes | no |

Win rate and reward against risk (SV trades vs all random trades; returns are per trade, before position size):

| Family | SV win rate | SV avg win | SV avg loss | SV payoff | SV profit factor | SV E[R] | Random win rate | Random payoff | Random profit factor | Random E[R] |
|---|---|---|---|---|---|---|---|---|---|---|
| T0 | 55.6% | 12.9% | -9.3% | 1.38 | 1.73 | 0.19 | 54.5% | 1.47 | 1.77 | 0.19 |

Signals by level and what happened to them:

| Level | market_filter | no_support | stop_too_wide | traded | veto_deep_drawdown | veto_wide_box |
|---|---|---|---|---|---|---|
| daily | 239 | 0 | 21 | 716 | 255 | 5 |
| monthly | 103 | 0 | 16 | 375 | 160 | 7 |
| weekly | 269 | 3 | 12 | 761 | 129 | 6 |

## T0: five-year periods against SPY

| Period | SV Sharpe | SPY Sharpe | SV return | SPY return | SV worst fall | SPY worst fall |
|---|---|---|---|---|---|---|
| 2005-2009 | -0.07 | 0.11 | -4.9% | -1.7% | 29.0% | 55.2% |
| 2010-2014 | 0.55 | 0.98 | 21.9% | 104.1% | 9.2% | 18.6% |
| 2015-2019 | 0.67 | 0.88 | 25.6% | 72.8% | 12.0% | 19.3% |
| 2020-2024 | 0.39 | 0.75 | 17.7% | 96.4% | 14.7% | 33.7% |
| 2025-2026 | 1.06 | 1.11 | 14.0% | 35.5% | 13.0% | 18.8% |

## T0: by segment (exploratory)

| Segment | Group | Signals | SV average | Random average | Difference | t |
|---|---|---|---|---|---|---|
| timeframe | daily | 915 | 0.70% | 0.59% | 0.07% | -0.78 |
| timeframe | monthly | 463 | 4.72% | 4.12% | 0.12% | -0.04 |
| timeframe | weekly | 987 | 2.13% | 1.60% | 0.22% | 0.43 |
| market_trend | SPY above 200-day | 1852 | 3.04% | 2.57% | 0.09% | -0.34 |
| market_trend | SPY below 200-day | 513 | -1.38% | -1.44% | -0.03% | 0.66 |
| market_volatility | calm (volatility below 1-year median) | 1322 | 3.22% | 2.54% | 0.27% | 0.17 |
| market_volatility | stormy (volatility above 1-year median) | 1043 | 0.65% | 0.64% | -0.15% | 0.14 |
| sector | Communication Services | 12 | -0.09% | 2.26% | -2.35% | -0.31 |
| sector | Consumer Discretionary | 43 | 2.92% | 1.87% | 1.05% | 0.84 |
| sector | Consumer Staples | 5 | 2.71% | 1.84% | 0.87% | 0.18 |
| sector | Energy | 44 | 2.72% | 0.93% | 1.80% | 0.63 |
| sector | Financials | 16 | 11.93% | 2.68% | 9.25% | 2.38 |
| sector | Health Care | 176 | 1.05% | 1.95% | -1.15% | -1.16 |
| sector | Industrials | 234 | 2.62% | 2.38% | 0.23% | 0.48 |
| sector | Information Technology | 195 | 2.09% | 2.51% | -0.71% | -1.72 |
| sector | Materials | 65 | 4.48% | 1.86% | 2.17% | 0.69 |
| sector | Real Estate | 5 | 4.79% | 4.58% | 0.21% | 0.05 |
| sector | Utilities | 51 | 0.79% | 1.21% | -0.42% | -0.82 |
| sector | unknown | 1519 | 1.92% | 1.47% | 0.13% | 0.06 |
| supply_flag | flagged | 914 | 2.09% | 1.27% | 0.62% | 0.26 |
| supply_flag | not flagged | 1451 | 2.08% | 1.97% | -0.28% | 0.28 |
| run_up_10d | 3-6% | 836 | 1.77% | 1.54% | 0.06% | -0.56 |
| run_up_10d | 6-10% | 538 | 2.69% | 2.15% | 0.23% | 0.90 |
| run_up_10d | <3% | 641 | 1.77% | 2.19% | -0.42% | -1.16 |
| run_up_10d | >=10% | 350 | 2.49% | 0.52% | 1.26% | 1.26 |
| score_group | 30-45 | 1433 | 1.95% | 1.80% | -0.02% | 0.30 |
| score_group | 45-60 | 405 | 2.50% | 1.57% | 0.06% | 0.05 |
| score_group | <30 | 507 | 2.22% | 1.54% | 0.40% | -0.14 |
| score_group | >=60 | 20 | -0.17% | 1.36% | -1.53% | -0.77 |

## T1: five-year periods against SPY

| Period | SV Sharpe | SPY Sharpe | SV return | SPY return | SV worst fall | SPY worst fall |
|---|---|---|---|---|---|---|
| 2005-2009 | -0.18 | 0.11 | -9.1% | -1.7% | 28.2% | 55.2% |
| 2010-2014 | 0.61 | 0.98 | 24.2% | 104.1% | 8.9% | 18.6% |
| 2015-2019 | 0.57 | 0.88 | 21.6% | 72.8% | 13.8% | 19.3% |
| 2020-2024 | 0.37 | 0.75 | 16.2% | 96.4% | 11.2% | 33.7% |
| 2025-2026 | 1.03 | 1.11 | 13.2% | 35.5% | 12.6% | 18.8% |

## T1: by segment (exploratory)

| Segment | Group | Signals | SV average | Random average | Difference | t |
|---|---|---|---|---|---|---|
| timeframe | daily | 915 | 0.70% | 0.59% | 0.07% | -0.78 |
| timeframe | monthly | 463 | 4.72% | 4.12% | 0.12% | -0.04 |
| timeframe | weekly | 987 | 1.48% | 0.94% | 0.23% | 0.21 |
| market_trend | SPY above 200-day | 1852 | 2.68% | 2.22% | 0.08% | -0.54 |
| market_trend | SPY below 200-day | 513 | -1.33% | -1.42% | -0.00% | 0.77 |
| market_volatility | calm (volatility below 1-year median) | 1322 | 2.87% | 2.17% | 0.30% | -0.09 |
| market_volatility | stormy (volatility above 1-year median) | 1043 | 0.47% | 0.49% | -0.19% | 0.10 |
| sector | Communication Services | 12 | -0.39% | 1.75% | -2.14% | -0.28 |
| sector | Consumer Discretionary | 43 | 1.92% | 1.50% | 0.42% | 0.57 |
| sector | Consumer Staples | 5 | 1.34% | 0.93% | 0.42% | 0.09 |
| sector | Energy | 44 | 2.00% | 0.51% | 1.49% | 0.49 |
| sector | Financials | 16 | 9.68% | 1.84% | 7.84% | 1.82 |
| sector | Health Care | 176 | 0.39% | 1.59% | -1.48% | -1.66 |
| sector | Industrials | 234 | 2.46% | 2.14% | 0.31% | 0.44 |
| sector | Information Technology | 195 | 1.85% | 2.23% | -0.64% | -1.62 |
| sector | Materials | 65 | 3.80% | 1.71% | 1.63% | 0.40 |
| sector | Real Estate | 5 | 5.54% | 3.88% | 1.66% | 0.37 |
| sector | Utilities | 51 | 0.37% | 1.03% | -0.65% | -1.25 |
| sector | unknown | 1519 | 1.75% | 1.21% | 0.20% | 0.02 |
| supply_flag | flagged | 914 | 1.57% | 0.98% | 0.41% | 0.16 |
| supply_flag | not flagged | 1451 | 1.96% | 1.72% | -0.15% | 0.34 |
| run_up_10d | 3-6% | 836 | 1.65% | 1.34% | 0.15% | -0.63 |
| run_up_10d | 6-10% | 538 | 1.84% | 1.63% | -0.09% | 0.12 |
| run_up_10d | <3% | 641 | 1.86% | 1.99% | -0.14% | -0.88 |
| run_up_10d | >=10% | 350 | 2.06% | 0.32% | 1.03% | 1.17 |
| score_group | 30-45 | 1433 | 1.73% | 1.52% | 0.05% | 0.27 |
| score_group | 45-60 | 405 | 1.82% | 1.26% | -0.31% | -0.38 |
| score_group | <30 | 507 | 2.12% | 1.35% | 0.53% | 0.40 |
| score_group | >=60 | 20 | -0.19% | 1.01% | -1.20% | -0.36 |

## T2: five-year periods against SPY

| Period | SV Sharpe | SPY Sharpe | SV return | SPY return | SV worst fall | SPY worst fall |
|---|---|---|---|---|---|---|
| 2005-2009 | 0.05 | 0.11 | 0.2% | -1.7% | 22.1% | 55.2% |
| 2010-2014 | 0.73 | 0.98 | 26.9% | 104.1% | 9.9% | 18.6% |
| 2015-2019 | 0.46 | 0.88 | 15.6% | 72.8% | 14.0% | 19.3% |
| 2020-2024 | 0.08 | 0.75 | 1.5% | 96.4% | 13.0% | 33.7% |
| 2025-2026 | 1.36 | 1.11 | 18.6% | 35.5% | 10.4% | 18.8% |

## T2: by segment (exploratory)

| Segment | Group | Signals | SV average | Random average | Difference | t |
|---|---|---|---|---|---|---|
| timeframe | daily | 915 | 0.24% | 0.33% | -0.15% | -0.67 |
| timeframe | monthly | 463 | 4.74% | 4.10% | 0.17% | 0.03 |
| timeframe | weekly | 987 | 0.92% | 0.68% | -0.04% | -0.60 |
| market_trend | SPY above 200-day | 1852 | 2.12% | 1.92% | -0.14% | -1.09 |
| market_trend | SPY below 200-day | 513 | -1.20% | -1.32% | 0.05% | 0.26 |
| market_volatility | calm (volatility below 1-year median) | 1322 | 2.23% | 1.85% | 0.02% | -0.46 |
| market_volatility | stormy (volatility above 1-year median) | 1043 | 0.35% | 0.41% | -0.21% | -0.15 |
| sector | Communication Services | 12 | 1.26% | 1.79% | -0.53% | -0.10 |
| sector | Consumer Discretionary | 43 | 1.04% | 1.10% | -0.06% | 0.27 |
| sector | Consumer Staples | 5 | 4.10% | 1.87% | 2.23% | 0.50 |
| sector | Energy | 44 | -0.90% | 0.43% | -1.33% | -0.50 |
| sector | Financials | 16 | 11.07% | 1.66% | 9.41% | 2.32 |
| sector | Health Care | 176 | 0.85% | 1.45% | -0.87% | -1.13 |
| sector | Industrials | 234 | 1.77% | 1.81% | -0.01% | 0.26 |
| sector | Information Technology | 195 | 0.55% | 1.97% | -1.70% | -3.18 |
| sector | Materials | 65 | 4.02% | 1.33% | 2.25% | 0.92 |
| sector | Real Estate | 5 | 2.51% | 3.67% | -1.16% | -0.23 |
| sector | Utilities | 51 | 0.56% | 1.02% | -0.45% | -0.88 |
| sector | unknown | 1519 | 1.40% | 1.01% | 0.07% | -0.09 |
| supply_flag | flagged | 914 | 1.26% | 0.80% | 0.30% | 0.05 |
| supply_flag | not flagged | 1451 | 1.49% | 1.48% | -0.33% | -0.04 |
| run_up_10d | 3-6% | 836 | 1.39% | 1.09% | 0.16% | -0.63 |
| run_up_10d | 6-10% | 538 | 1.86% | 1.43% | 0.14% | 0.39 |
| run_up_10d | <3% | 641 | 1.23% | 1.75% | -0.55% | -1.22 |
| run_up_10d | >=10% | 350 | 1.04% | 0.20% | 0.16% | 0.46 |
| score_group | 30-45 | 1433 | 1.17% | 1.28% | -0.24% | -0.26 |
| score_group | 45-60 | 405 | 2.12% | 1.23% | 0.04% | 0.22 |
| score_group | <30 | 507 | 1.56% | 1.04% | 0.28% | 0.34 |
| score_group | >=60 | 20 | -0.59% | 0.51% | -1.10% | -0.46 |

## T3: five-year periods against SPY

| Period | SV Sharpe | SPY Sharpe | SV return | SPY return | SV worst fall | SPY worst fall |
|---|---|---|---|---|---|---|
| 2005-2009 | -0.37 | 0.11 | -15.6% | -1.7% | 31.6% | 55.2% |
| 2010-2014 | 0.41 | 0.98 | 14.1% | 104.1% | 9.2% | 18.6% |
| 2015-2019 | 0.77 | 0.88 | 29.8% | 72.8% | 13.5% | 19.3% |
| 2020-2024 | 0.34 | 0.75 | 14.7% | 96.4% | 12.9% | 33.7% |
| 2025-2026 | 1.06 | 1.11 | 13.1% | 35.5% | 11.2% | 18.8% |

## T3: by segment (exploratory)

| Segment | Group | Signals | SV average | Random average | Difference | t |
|---|---|---|---|---|---|---|
| timeframe | daily | 915 | 0.50% | 0.40% | 0.04% | -0.78 |
| timeframe | monthly | 463 | 4.46% | 4.07% | -0.10% | -0.14 |
| timeframe | weekly | 987 | 1.61% | 1.25% | 0.05% | -0.07 |
| market_trend | SPY above 200-day | 1852 | 2.64% | 2.24% | 0.03% | -0.59 |
| market_trend | SPY below 200-day | 513 | -1.52% | -1.30% | -0.29% | 0.09 |
| market_volatility | calm (volatility below 1-year median) | 1322 | 2.85% | 2.21% | 0.27% | 0.08 |
| market_volatility | stormy (volatility above 1-year median) | 1043 | 0.33% | 0.55% | -0.41% | -0.71 |
| sector | Communication Services | 12 | 1.75% | 2.20% | -0.46% | -0.06 |
| sector | Consumer Discretionary | 43 | 2.19% | 1.41% | 0.77% | 0.74 |
| sector | Consumer Staples | 5 | 2.71% | 1.80% | 0.90% | 0.19 |
| sector | Energy | 44 | 1.55% | 0.62% | 0.93% | 0.13 |
| sector | Financials | 16 | 10.38% | 2.18% | 8.20% | 1.97 |
| sector | Health Care | 176 | 0.54% | 1.77% | -1.49% | -1.70 |
| sector | Industrials | 234 | 1.65% | 2.18% | -0.54% | -0.42 |
| sector | Information Technology | 195 | 1.40% | 2.27% | -1.15% | -2.31 |
| sector | Materials | 65 | 4.38% | 1.66% | 2.49% | 1.14 |
| sector | Real Estate | 5 | 1.58% | 3.80% | -2.22% | -0.45 |
| sector | Utilities | 51 | 0.87% | 1.21% | -0.34% | -0.67 |
| sector | unknown | 1519 | 1.75% | 1.24% | 0.19% | -0.33 |
| supply_flag | flagged | 914 | 1.67% | 1.05% | 0.45% | 0.43 |
| supply_flag | not flagged | 1451 | 1.78% | 1.75% | -0.34% | -0.31 |
| run_up_10d | 3-6% | 836 | 1.32% | 1.29% | -0.12% | -1.08 |
| run_up_10d | 6-10% | 538 | 2.48% | 1.82% | 0.37% | 0.86 |
| run_up_10d | <3% | 641 | 1.59% | 2.01% | -0.43% | -0.82 |
| run_up_10d | >=10% | 350 | 1.87% | 0.41% | 0.79% | 0.86 |
| score_group | 30-45 | 1433 | 1.54% | 1.57% | -0.18% | -0.25 |
| score_group | 45-60 | 405 | 1.93% | 1.44% | -0.42% | -0.48 |
| score_group | <30 | 507 | 2.22% | 1.27% | 0.71% | 0.96 |
| score_group | >=60 | 20 | -0.22% | 0.79% | -1.01% | -0.39 |

## T4: five-year periods against SPY

| Period | SV Sharpe | SPY Sharpe | SV return | SPY return | SV worst fall | SPY worst fall |
|---|---|---|---|---|---|---|
| 2005-2009 | 0.10 | 0.11 | 2.3% | -1.7% | 31.4% | 55.2% |
| 2010-2014 | 0.71 | 0.98 | 37.9% | 104.1% | 8.8% | 18.6% |
| 2015-2019 | 0.61 | 0.88 | 26.6% | 72.8% | 13.4% | 19.3% |
| 2020-2024 | 0.32 | 0.75 | 15.9% | 96.4% | 19.3% | 33.7% |
| 2025-2026 | 0.99 | 1.11 | 19.2% | 35.5% | 10.7% | 18.8% |

## T4: by segment (exploratory)

| Segment | Group | Signals | SV average | Random average | Difference | t |
|---|---|---|---|---|---|---|
| timeframe | daily | 915 | 2.28% | 1.38% | 0.64% | 0.78 |
| timeframe | monthly | 462 | 11.09% | 7.83% | 2.34% | 1.49 |
| timeframe | weekly | 987 | 4.81% | 3.27% | 0.26% | -0.43 |
| market_trend | SPY above 200-day | 1851 | 6.09% | 4.48% | 1.12% | 0.68 |
| market_trend | SPY below 200-day | 513 | 1.33% | -0.38% | -0.20% | 0.84 |
| market_volatility | calm (volatility below 1-year median) | 1321 | 7.87% | 4.58% | 2.14% | 1.93 |
| market_volatility | stormy (volatility above 1-year median) | 1043 | 1.51% | 1.97% | -0.70% | -0.27 |
| sector | Communication Services | 12 | -5.18% | 5.67% | -10.85% | -2.01 |
| sector | Consumer Discretionary | 43 | 6.95% | 3.04% | 3.91% | 1.41 |
| sector | Consumer Staples | 5 | 3.03% | 5.22% | -2.19% | -0.45 |
| sector | Energy | 44 | 4.16% | 2.49% | 1.67% | 0.32 |
| sector | Financials | 16 | 37.54% | 5.57% | 31.98% | 1.58 |
| sector | Health Care | 176 | 2.47% | 3.60% | -1.14% | -1.20 |
| sector | Industrials | 234 | 7.96% | 4.35% | 0.68% | 0.42 |
| sector | Information Technology | 195 | 1.16% | 4.16% | -3.63% | -4.24 |
| sector | Materials | 65 | 5.40% | 4.07% | 0.65% | -0.00 |
| sector | Real Estate | 4 | -4.99% | 5.30% | -10.29% | -2.95 |
| sector | Utilities | 51 | 1.93% | 2.07% | -0.14% | -0.44 |
| sector | unknown | 1519 | 5.25% | 3.17% | 1.39% | 1.68 |
| supply_flag | flagged | 913 | 5.17% | 2.67% | 1.43% | 1.54 |
| supply_flag | not flagged | 1451 | 4.99% | 3.90% | 0.46% | 0.84 |
| run_up_10d | 3-6% | 835 | 4.10% | 3.18% | 0.31% | 0.11 |
| run_up_10d | 6-10% | 538 | 5.98% | 4.02% | 1.32% | 0.61 |
| run_up_10d | <3% | 641 | 4.80% | 3.94% | 0.46% | 0.29 |
| run_up_10d | >=10% | 350 | 6.39% | 2.15% | 1.87% | 1.25 |
| score_group | 30-45 | 1432 | 4.65% | 3.46% | 0.23% | 0.63 |
| score_group | 45-60 | 405 | 6.15% | 3.77% | 1.65% | 1.22 |
| score_group | <30 | 507 | 5.58% | 3.11% | 2.08% | 1.95 |
| score_group | >=60 | 20 | -0.86% | 2.30% | -3.16% | -1.17 |

## Next step (planned before the run)

The chosen rule (if any) is confirmed in direction on the live model's one-year ledger (registered before it runs). For the SPY goal it then goes into E2 under these rules: SV fills the stock slice of the core (SPY fills whatever SV leaves), judged against SPY bought and held and against the core alone, then forward paper accounts. Its holding windows are tuned with the 09 rule (the shortest window reaching 90% of the best cost-adjusted expectancy, stable on validation). Leads by level, market state, sector, supply flag or score group are confirmed on unseen data before any use. If nothing passes, SV's opportunities are not traded for the account under these rules, and the next round tests the 4B stop (nearest high-volume node) or the extra check that came closest.
