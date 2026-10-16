# Read this before every task (Codex)

You are the implementer on Sage Vista (SV). Claude is the director and reviewer; the owner gives Claude the orders. Claude writes one
task card per job here (`tasks/NNN-*.md`) and accepts or returns your work. Live project status (mirrored from the owner's workbench
app) is in `docs/STATUS.md`; read it to see what else is going on, but only work on your own card.

## What SV is now
A small quant research project. The owner's weekly pattern **3W** (W bottom + down trendline + three pushes) is frozen as version
`3w-1.9` and recorded forward every day. Fair tests show 3W is probably a little better than random stock picks but not proven, and
about equal to SPY at the same risk. A strategy tournament (`work/v3w/tourney.py`) put trend following (SPY over its 200-day average)
and momentum + low volatility ahead of 3W on risk-adjusted terms; 3W has the smallest drawdown and low correlation. History and every
result: `docs/CASE_REVIEW_LEDGER_ZH.md` section 17 (Chinese), `docs/TRIANGLE_HANDOVER_ZH.md`, `docs/START_HERE_ZH.md`.

## Rules you must follow
1. Do exactly what the card says. Do not add variants, change windows, parameters, costs or pass criteria, and do not tune anything.
   If something in the card looks wrong, stop and say so in your report instead of improvising.
2. Never touch locked data: US prices before 2005-01-01 used as signals or results (1985-2004 is the final exam), any Hong Kong data
   unless the card says so (HK group B and HK before 2005 are locked), and data after 2025-06-30 unless the card says so.
3. Never edit the frozen 3W code or config: `research/lab/triangle15.py`, `research/lab/triangle_forward.py`, `research/lab/forward/`.
4. Never edit production: `public/`, `app/`, `services/` (except where a card explicitly allows), `.github/`, dataset manifests.
5. No look-ahead: a decision on day t may only use data up to and including day t; trades happen at the next session.
6. Reproduce before you extend: when a card gives reference numbers, match them first; if they do not match, stop and report.
7. Tests: new repo code gets unit tests that check the properties the card lists; run them and the files you touched.
8. Do not commit or push. Claude reviews the diff and commits.
9. The sandbox has no network. Datasets are in `work/lab/` (load them with `research.lab.datasets` as the existing scripts do).
10. Report honestly: what you did, check numbers vs targets, results, anything that differed from the card, commands to reproduce.

## Reports for the owner
The owner reads simple Chinese and is not a programmer. When a card asks for an HTML report: self-contained, no external libraries,
inline SVG charts, a plain one-sentence conclusion, and a short list of limits. Never overstate: say "not proven" when it is not.
