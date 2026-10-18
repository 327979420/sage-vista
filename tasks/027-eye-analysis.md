# Task 027: machine vs the owner's eye on the existing 207 decisions (description + one CV comparison)

Read `tasks/README.md` first. Owner (2026-10-18): first goal is to prove whether the owner's eye has value; meanwhile "with only the
existing ~200 decisions, can the machine become more like me, or is it at its limit?" Task 026: 做 +0.40R vs 不做 -0.18R (d +0.57R,
p 0.12, 73 closed trades). Data: `research/lab/cases/3w-user-decisions-2026-10.json` + local keys (`work/v3w/3w-blind-keys-2026-10.json`),
`research/lab/cases/taste-model-v1.json`, the task-022 ticket builder for per-case gate values.

## Part A - where machine and owner differ (description only)
For all 207 decisions: the owner's 做/不做, the frozen rule's decision (order or not, why), taste-model-v1 score. Tables: agreement
owner vs rule, owner vs taste v1; on disagreements, who was right (closed trades only); per-feature comparison of 做 vs 不做 using the
ticket gate values (pullback %, flat-bottom %, push-line drop ratios and span, distance to bottom in ATR, R:R, MACD depth, breadth,
SPY distance, 3-year-low margin, weekly volume trend if available), with medians and a simple effect size. Plain-Chinese "what the
owner seems to look at" summary - as hypotheses only.

## Part B - can the machine be more like the owner? (one comparison, registered here)
Target: predict the owner's 做/不做 (all 207, outcomes not used). Compare taste v1 (as is) vs a "taste v2" = L2 logistic regression on
the Part-A features (fixed list above, standardised, C=1.0, no tuning). Metric: leave-one-week-out cross-validated accuracy and AUC.
v2 counts as "more like the owner" only if CV AUC improves by >= 0.05 over v1. Report the 73-trade outcome of v2's 做 picks as
description only (in-sample, cannot prove value). Nothing is deployed.

## Deliverables
`work/v3w/eye_analysis.py` + log, `work/reports/eye-analysis-v1.{json,html}` (simple Chinese). If the sandbox refuses writes via work/,
use `task027-staging/`. Stop and ask on ambiguity. No network, no commits.
