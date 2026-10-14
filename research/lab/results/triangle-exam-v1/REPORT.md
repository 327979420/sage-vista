# triangle-exam-v1

Plain-language report written by the research lab on 2026-10-14. Every number comes from `result.json` in this folder.

## The question

Does the user's weekly triangle (research/lab/triangle.py 1.0, frozen 2026-10-14 after matching the user's own buy points: buy C at the bottom on a weekly MACD golden cross, or B on the retest after the breakout; never the breakout itself) pick better trades than random stocks bought the same day with the same stop distance, target multiple and exits? Train on the 1,228 known stocks in 2005-2016 (the frozen rule against seven one-change variants taken from the user's open choices and from published methods), then run the chosen rule once on 5,500 stocks no rule has seen, in four shards, 2005 to mid-2025.

## Training on the known stocks (2005-01-01 to 2016-12-31)

| Rule | Changes | Signals (C/B) | Trades | Sharpe | CAGR | Max DD | Beats random accounts | Excess vs random (t) | Win rate | Payoff | Adopted |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | — | 2215 (795/1420) | 267 | 0.42 | 3.2% | 29.5% | 9.5% | -1.24% (-2.78) | 33.4% | 3.53 | — |
| V1_c_only | options=['C'] | 795 (795/0) | 219 | 0.27 | 1.9% | 28.3% | 2.5% | -2.31% (-3.22) | 38.6% | 2.65 | no |
| V2_b_only | options=['B'] | 1420 (0/1420) | 316 | 0.71 | 5.6% | 30.0% | 77.5% | -0.64% (-1.04) | 30.6% | 4.22 | yes |
| V3_target_1_5r | target_r=1.5 | 2215 (795/1420) | 452 | 0.38 | 2.3% | 24.3% | 9.5% | -0.19% (-1.58) | 50.3% | 1.46 | no |
| V4_volume_1_25x | min_volume_ratio=1.25 | 412 (112/300) | 204 | 0.56 | 3.7% | 19.4% | 22.5% | -2.26% (-2.12) | 32.0% | 3.29 | yes |
| V5_confluence_4 | min_confluence=4 | 591 (241/350) | 261 | 0.39 | 2.1% | 21.4% | 10.5% | -0.98% (-1.73) | 35.1% | 3.18 | no |
| V6_market_filter | market_filter=True | 1811 (620/1191) | 258 | 0.61 | 4.0% | 17.1% | 50.5% | -0.83% (-1.27) | 34.0% | 3.61 | yes |
| V7_time_stop_26w | max_sessions=130 | 2215 (795/1420) | 439 | 0.41 | 3.0% | 29.3% | 13.5% | -0.42% (-1.73) | 38.4% | 2.48 | no |

Adopted: V2_b_only, V4_volume_1_25x, V6_market_filter; final changes {'options': ['B'], 'market_filter': True, 'min_volume_ratio': 1.25}.

## The exam: stocks no rule has seen (2005-01-01 to 2025-06-30), run once

| Shard | Stocks | Signals | Trades | Sharpe | SPY Sharpe | CAGR | SPY CAGR | Max DD | Beats random accounts | Excess vs random (t) | Win rate | Payoff |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fresh-a-1995-v1 | 1500 | 224 | 215 | 0.09 | 0.61 | 0.3% | 10.3% | 18.4% | 23.5% | -0.80% (-0.34) | 20.3% | 3.97 |
| fresh-b-1995-v1 | 1500 | 214 | 205 | 0.18 | 0.61 | 0.6% | 10.3% | 14.3% | 79.5% | 1.22% (0.79) | 19.7% | 4.61 |
| fresh-c-1995-v1 | 1500 | 217 | 210 | 0.01 | 0.61 | -0.0% | 10.3% | 18.9% | 41.0% | 0.13% (-0.57) | 21.2% | 3.48 |
| fresh-d-1995-v1 | 1000 | 148 | 141 | 0.40 | 0.61 | 1.3% | 10.3% | 7.8% | 93.5% | 1.80% (1.19) | 21.4% | 4.55 |

All four shards together: 777 trades; excess over same-day random 0.49% per trade (t 0.86, median -3.81%); win rate 20.6%.

| Check | Passed |
|---|---|
| shards_beating_random_accounts | no |
| trades_beat_random_same_day | no |
| enough_trades | yes |

**Passed: no.** The user's goal (Sharpe at least SPY's) in 0 of 4 shards; full goal 1 (Sharpe and Calmar at least SPY's, drawdown at most 25%) in 0.

## Reported, not judged: the known stocks after training (2017-01-01 to 2025-06-30)

- Signals 392; trades 209; Sharpe 0.30 (SPY 0.81); CAGR 1.6% (SPY 14.5%); beats 20.0% of random accounts; excess vs random -1.37% (t -0.67).

## Next step

If it passes, the triangle goes to forward paper observation beside the E6 accounts (no production change without the user's approval). If it fails, the report shows which part lost (C or B, target, timing) and no rule is changed on the exam shards.
