# Task 031: factor scan on 3W trades - find in 2005-2014, check in 2015-2024 (registered; overfitting-guarded)

Read `tasks/README.md` first. Owner (2026-10-19): use our own factor library, treat each trade as a normal stock, find what winners
and losers have in common, and consider adding it to the rules - while guarding against overfitting.

## Sample and factors
The 500 completed US events of research standard v1 (task 024; frozen 3w-1.9; cost 0.1%). Factors: the point-in-time registry factors
available in `research/lab/factor_tags.py` (task 012: 34 of 39), evaluated at the signal date (entry tags) - plus the three task-030
features (overhead supply, prior highs in range, signal-week volume ratio) so they can be ranked alongside. Binary tags as they are;
continuous features split at their discovery-half median (fixed from the discovery half only).

## Procedure (fixed now)
1. Discovery half = signals 2005-01..2014-12. For every factor: mean R with the tag minus mean R without; week-block bootstrap
   (10,000, seed 20261023). Rank by the bootstrap z. Take at most the top 3 with |difference| >= 0.15R and at least 30 trades on each
   side. Direction is fixed by discovery.
   Owner clarification: rank descending by |z| = |mean-R difference| / bootstrap standard error; either sign can be promoted, and that sign is fixed for validation (avoid and prefer count equally).
2. Validation half = signals 2015-01..2024-06. For each of the (<=3) promoted factors, the same difference in the SAME direction,
   one-sided week-block bootstrap (10,000, seed 20261024); Holm correction over the promoted factors at 0.05.
3. A factor is a "candidate" only if it passes validation. Candidates are NOT added to the rules here; they go to a later registered
   test on unseen data (forward record / HK group B / Korea).
Report every factor's discovery numbers (description), the promoted list, the validation results, and how the task-030 features rank.

## Deliverables
`work/v3w/factor_scan.py` + log, `work/reports/factor-scan-v1.{json,html}` (simple Chinese). If work/ is not writable use
`task031-staging/`. Stop and ask on ambiguity. No network, no commits.
