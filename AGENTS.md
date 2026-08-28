# Sage Vista repository instructions

Before changing any strategy, score, factor, detector, ranking, market/industry adjustment, holding rule, backtest, experiment, production explanation, or related UI:

1. Read the concise project purpose and module map in `docs/SAGE_VISTA_RULEBOOK_ZH.md` completely.
2. Use `docs/rules/README.md` to identify the affected module.
3. Read only that module rule and the files named by its linkage conditions. Do not load every module for a single-module change.

Examples: scoring-only changes start with `docs/rules/04_SCORING.md`; factor-definition changes start with `03_FACTOR_MODEL.md`; experiments start with `08_BACKTEST_AND_EXPERIMENTS.md`.

For any semantic change:

1. Update and version the affected module rule first. Update the overall rulebook only when project purpose, module boundaries, or cross-system flow changes.
2. Append the approved decision to `docs/DECISION_LOG_ZH.md`.
3. Pre-register an experiment before changing selection, scoring, holding, stop, or target behavior.
4. Then change code, add leakage/contract tests, run the experiment, archive all results, update UI, deploy, and verify production.

Always distinguish current production behavior from approved target behavior and unimplemented ideas. Never silently rewrite historical scores or delete failed, negative, incomplete, or insufficient-sample experiments.

Validated strategies belong in `docs/rules/11_VALIDATED_PLAYBOOK.md`. Evidence-backed prohibitions belong in `docs/rules/12_HARD_RULES.md`; a high score never overrides an active hard rule.
