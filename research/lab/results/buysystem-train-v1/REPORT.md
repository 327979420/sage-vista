# buysystem-train-v1

Plain-language report written by the research lab on 2026-10-13. Every number comes from `result.json` in this folder.

## The question

Does the buy system 0.2.0 (monthly and weekly opportunities, every layer must pass; docs/BUY_SYSTEM_ZH.md) pick better trades than random stocks bought the same day with the same stop distance, target multiple and exits? Train on 2005-2016: compare the baseline with seven one-change variants and adopt a change only if it clearly helps; then run the chosen rule once on 2017 to mid-2025.

## Training window (2005-01-01 to 2016-12-31)

| Rule | Changes | Signals | Trades | Sharpe | CAGR | Max DD | Beats random accounts | Excess vs random (t) | Win rate | Payoff | Adopted |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | — | 500 | 171 | 0.26 | 2.0% | 22.7% | 0.0% | -2.28% (-2.57) | 47.1% | 3.03 | — |
| V1_week_pullback_8pct | kinds.week.a.min_pullback=0.08 | 501 | 172 | 0.25 | 1.9% | 22.9% | 0.0% | -2.31% (-2.59) | 47.0% | 3.03 | no |
| V2_daily_wait_5 | daily.window=5 | 469 | 162 | 0.34 | 2.7% | 22.6% | 0.5% | -1.96% (-2.44) | 48.0% | 3.02 | no |
| V3_chase_3atr | veto.chase_atr=3.0 | 539 | 171 | 0.38 | 3.1% | 21.9% | 3.5% | -1.49% (-2.23) | 49.0% | 2.96 | no |
| V4_no_place_macd_veto | veto.place_macd=False | 531 | 169 | 0.25 | 1.9% | 22.5% | 0.0% | -2.06% (-2.48) | 47.5% | 3.04 | no |
| V5_no_t4 | place.t4=False | 500 | 168 | 0.26 | 2.0% | 22.7% | 0.0% | -2.32% (-2.59) | 47.1% | 3.03 | no |
| V6_rs_rank | account.rank=rs_6m | 500 | 177 | 0.27 | 2.1% | 22.7% | 0.5% | -2.28% (-2.57) | 47.1% | 3.03 | no |
| V7_market_filter | account.market_filter=True | 384 | 140 | 0.34 | 2.5% | 20.2% | 1.5% | -2.21% (-2.10) | 45.3% | 2.74 | no |

Adopted: none, so the baseline goes to the test.

## Test window (2017-01-01 to 2025-06-30), run once

- Signals 582 {'month': 97, 'week': 485}; trades taken 125; Sharpe 0.56, CAGR 5.9%, max drawdown 20.8%, average exposure 42.7%.
- Beats 26.0% of 200 random accounts (random Sharpe median 0.68); trade excess vs same-day random 0.93% (t 0.64, median -5.12%).
- SPY: Sharpe 0.81, CAGR 14.5%; SPY at the account's exposure: Sharpe 0.85, CAGR 5.8%.
- Win rate 40.6%, payoff 2.42, expectancy 0.32R; random: 41.8%, 2.34, 0.34R.
- Exits: {'stop': 271, 'stop_gap': 58, 'trend_exit': 211}.

| Check | Passed |
|---|---|
| beats_random_accounts | no |
| trades_beat_random_same_day | no |
| enough_signals | yes |

**Passed: no.**

## Next step

If the test passes: reverse blind review (10 random signals of the chosen rule; the user must approve at least 8), then forward paper trading next to E6 before any account use. If it fails: the buy system does not go into the account; the failure is kept, the user's disagreement cases and the trade list are reviewed for a definition error, and any new version is registered as a new experiment with a fresh test period (2025-07 onward, forward).
