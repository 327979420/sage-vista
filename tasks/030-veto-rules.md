# Task 030: "don't-trade" (veto) rules from the owner's habits - one registered test + a losers gallery

Read `tasks/README.md` first. Owner (2026-10-19): instead of picking winners, filter out the bad ones. The owner avoids setups with
heavy overhead resistance (lots of past turnover / many prior highs between entry and target) and likes room above (even an unfilled
gap / FVG). Blind v2 hint: losers' signal-week volume ratio median 0.84 vs 1.00 for 3R winners (88 trades, description).

## Sample
The 500 completed US events of research standard v1 (task 024, frozen 3w-1.9, US cost 0.1%), already used = development data.
Point-in-time only: every feature uses data up to the signal week close.
Owner-approved coverage convention (2026-10-19): retain all 500 trades; for DBX, HOOD, HOUS, PSUN and SWFT use the available 93–98 prior weeks without padding, label coverage in JSON/gallery, and resolve similar small coverage questions conservatively with disclosure unless the verdict definition would change.

## Features (fixed now)
F1 overhead supply: weekly volume-at-price over the 104 weeks before the signal; share of that volume traded at prices between the
   limit price and the 3R target (bin by weekly typical price = (H+L+C)/3).
F2 overhead highs: number of swing highs (frozen `pivots` highs) in the 104 weeks before the signal whose high lies between the limit
   price and the 3R target, excluding the three pushes.
F3 signal-week volume ratio: signal-week volume / mean volume of the 10 prior weeks.
Also describe (no test): an unfilled weekly gap (FVG) above the limit price within the target range (yes/no); stop distance in ATR.
Owner-confirmed FVG convention (2026-10-19): use three-bar weekly FVGs within the 104 weeks up to the signal week, show only the remaining unfilled portions overlapping the limit-to-3R range, include both directions labelled bullish or bearish in the gallery, and keep this description outside the registered test.

## The registered test (ledger section 17 BEFORE computing anything)
Veto rules (thresholds fixed now, terciles computed on the full 500 once):
V1 F1 in the top tercile; V2 F2 >= 3; V3 F3 < 0.8. Combined veto = any of V1-V3.
Primary: kept mean R minus all-500 mean R, week-block bootstrap (10,000, seed 20261022). USEFUL only if the improvement is
>= +0.10R, one-sided p <= 0.05, and >= 60% of trades are kept. Each single rule reported as description. If not useful: stop, no
re-tuning of thresholds.

## Losers gallery (for the owner to browse)
The 20 fastest stop-outs (shortest days from fill to stop) among the 500, plus the 8 worst-R trades of blind v2: one card each with
the weekly chart from 60 weeks before the signal to the exit (signal week marked), EMA20, the push line, limit/stop/target lines, a
horizontal volume-at-price histogram on the right edge (104 weeks to the signal), prior highs in the target range marked, FVGs shaded,
and F1-F3 values. Symbol and dates shown (these are reviews, not blind tests). Self-contained HTML in Sage Vista style.

## Deliverables
`work/v3w/veto_v1.py` + log, `work/reports/veto-v1.{json,html}` (result, simple Chinese), `work/reports/losers-gallery-v1.html`.
If writes via work/ are refused use `task030-staging/`. Stop and ask on ambiguity. No network, no commits.
