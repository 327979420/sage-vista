# e1c-live-model-vs-tradable-random-v1

Plain-language report written by the research lab on 2026-10-09. Every number comes from `result.json` in this folder.

## The question

Does SV's current live model pick better stocks than chance? Its real signals from the past year (2025-10 to 2026-10, 4,222 signals) against random picks from the stocks it could have picked the same day, with the same rules on both sides.

## The short answer

- SV's account Sharpe 0.04 beat 34% of 200 random accounts (needed 95%).
- Trade by trade, SV's picks returned -0.87% more than random stocks bought the same day (t -2.41, needed 2.00).
- Selection skill shown: **no**.

## Account, 2025-10-06 to 2026-10-06

| Account | Sharpe | Growth a year | Worst fall |
|---|---|---|---|
| SV picks | 0.04 | -0.1% | 7.9% |
| Random picks, middle result | 0.41 | 3.0% | 7.1% |
| Random picks, best 5% | 1.66 | 18.5% | 4.3% |
| Random picks, worst 5% | -0.92 | -7.3% | 11.3% |

## Trade by trade

3714 SV signals. Average trade: SV 1.51%, random 2.22%. Winning trades: SV 38.1%, random 39.8%. Statistic: winsorized at 1%/99%; median difference -4.85%; raw average difference -0.55%.

Random picks use SV's tradability floor on the signal day (min_history 420, min_close 5.0, min_dollar_volume 10000000.0). Excluded from both sides for provider price errors: ABVX, APLD, BACA, BMNR, CAPR, CHRD, CLSK, COGT, DFTX, DMRA, ENLT, GLXY, INDV, JBIO, ONDS, ORKA, PHVS, QUBT, SHAZ, SRRK, SYRE, VERA, VNDA, WFRD.

## Style check

Same share of the account in each fund on the same days: SPY Sharpe 1.11, QQQ Sharpe 1.54, IWM Sharpe 0.68, RSP Sharpe 0.47.
After removing market, Nasdaq-100 and small-cap tilts, SV's extra return is -4.56% a year (t -0.58).

## Next step (planned before the run)

If the live model passes: E2 with live signals filling the core's 25% stock slice, forward only. If not: SV's stock picks are not used for the account under either model; SV's value is as a market-information and watch-list tool, and any new selection idea must first beat this same random test.
