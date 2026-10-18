# Task 024: research standard v1 (pattern test) - register, then calibrate on used data

Read `tasks/README.md` first. Owner decisions (2026-10-18): for testing the 3W PATTERN in any market (not live trading), use a wider
pool and an event-level test so all signals count. Chosen options: pool "top half by turnover + floor ~US$1M/day"; verdict "each signal
vs random".

## The standard (write it into `docs/rules/` as the research-standard section and into ledger section 17 BEFORE any run)
- Pool, per market and day: stocks passing the frozen history and price rules whose daily turnover ranks in the top 50% of that day's
  eligible stocks AND >= US$1M equivalent (HK: HK$7.8M; reuse task 019's construction exactly).
- Signals and trades: frozen 3w-1.9 unchanged (shape 1.5, order, stop, 3R target, 26 weeks, market filter as in the frozen rule).
- Costs per side: US 0.1%; HK 0.25% (owner's moomoo fee schedule 2026-10-18: commission 0.03%, stamp 0.10%, exchange/levies ~0.013%,
  platform HK$15, plus half the median one-tick spread ~0.08%).
- Event-level test: for each signal i, the same order on 30 random same-day pool stocks (frozen twin sampler, same seeds scheme);
  d_i = R_i - mean(R_twins_i). Statistic: mean d. p = one-sided bootstrap over signals (10,000 resamples, seed 20261018) of mean d <= 0.
  PASS if p <= 0.05 and mean d > 0. Also report (description only): mean R, win rate, share of twins beaten, number of signals, and the
  account-level result under the old rules.
- Signals that never fill count as "no trade" and are excluded from d (report how many).

## This card: calibration only (no verdict)
Run the standard on (a) US development data 2005-2024 and (b) HK group A (both already used). Report the numbers as calibration, plus a
power estimate: with the HK-B expected signal count, how large a mean d would reach p <= 0.05. Do NOT load HK group B, HK before 2005
for signals, or US 1985-2004.

Deliverables: `work/v3w/standard_v1.py` + log, `work/reports/standard-v1-calibration.{json,html}` (simple Chinese), the rules text and
the ledger paragraph (in Chinese) as file changes on this branch, codex report with Concerns. Stop and ask if anything could change a
conclusion. No network, no commits.
