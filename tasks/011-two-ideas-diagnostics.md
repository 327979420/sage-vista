# Task 011: two parked ideas - descriptive diagnostics only (no rule change)

Read `tasks/README.md` first. Owner request (2026-10-17): look at two ideas parked since August/September (CR-2026-08-30-033 and the
head-and-shoulders-top note) WITHOUT changing the frozen 3W. Pre-registered in ledger section 17 ("两个旧想法·诊断"). Nothing here
becomes a rule; it only tells us whether a later, pre-registered 3W 2.0 candidate is worth registering.

## Inputs
`work/v3w/w3_cands.json` (571 frozen 3W signals with entry, stop, fills, closes; 287 taken by the baseline account in task 002 order),
the same price datasets the 3W builder uses (load as `work/v3w/components.py` / `fair19.py` do), weekly bars via
`research.lab.buysystem.periods(series, "week")`, and the existing detector `services/scanner/detectors.py::head_shoulders_bottom`
(read-only; do not edit services/). Same data boundary as task 002 (no signal/trade/statistic before 2005-01-01 or after 2025-06-30).

## A. "Second independent three-push" = a later 3W signal on the same stock after an earlier one
For every symbol, order its 3W signals by date. A signal is a "second" if the same symbol had an earlier 3W signal whose trade had
fully finished (last fill) before this signal's date and within the previous 104 weeks; otherwise "first". Report counts and the
standalone R (task 003 definition: from its own fills, before account fees) for first vs second: count, mean, median, win rate,
by decade; plus the 10 seconds with the largest and smallest R (symbols hidden, dates shown). Descriptive only.

### Answer to Codex (2026-10-17): date convention for A
Use the cached `entry_date` (fill date) as the date of each signal. For trading, what matters is "a new 3W trade was entered after
the previous 3W trade on the same stock had fully closed"; the fill can be up to 8 weeks after the pattern week, small against the
104-week window. Do not rebuild candidates. State this convention in the report.

## B. Head-and-shoulders TOP during a 3W holding (as a sell warning)
Mirror the bottom detector without editing it: build mirrored weekly bars (open/high/low/close -> negatives, high and low swapped)
and call `head_shoulders_bottom` on them; a mirrored "confirmed" (neckline break) is a TOP neckline break. For each of the 571
signals that has fills: walk its holding weeks (entry week .. week before the final fill); at each week use only bars up to that
week (`end` argument). Record the first week a top neckline break appears (if any). Hypothetical exit = next week's open. Report:
how many trades get a warning, how many weeks after entry, and for those trades the actual R vs the hypothetical R (same remaining
fractions, fees ignored on both): mean, median, share where exiting earlier was better, by decade. Also the same for trades that
eventually hit the stop vs those that hit the 3R target. Descriptive only; no account run, no adoption.

## Deliverables
`work/v3w/two_ideas.py` + `.log`, `work/reports/two-ideas-v1.{json,html}` (simple Chinese, inline SVG, no pre-2005 data), codex
report with Concerns (especially: how many cases are too few to judge, and which result would justify a pre-registered 3W 2.0
candidate). No tests in `tests/` importing `work/`. No network, no commits, no changes outside work/.
