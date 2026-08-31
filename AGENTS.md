# Sage Vista repository instructions

Status: confirmed repository governance. Strategy targets and module designs referenced by these instructions keep their own CR status and do not become approved merely by appearing here.

## Framework-first approval gate

When the user proposes any modification to code, data contracts, scanning, strategy, experiments, workflows, website behavior, or Discord behavior, do not implement it in the intake turn.

1. Read `docs/SYSTEM_ARCHITECTURE_ZH.md` and follow `docs/CHANGE_WORKFLOW_ZH.md`.
2. Register one bounded CR, identify the current flow and exact architecture insertion point, and produce the fixed design packet: inputs, outputs, owner module, affected and explicitly unaffected modules, migration, tests, examples, rollback and work packages.
3. Mark the CR `design_review` and wait for explicit user approval of that packet. A new idea, positive reaction, investigation request, or approval of a similar earlier change is not implementation approval.
4. Only after the user says to implement the reviewed design may the CR become `approved` / `implementing` and business code be edited.
5. Keep each implementation work package reviewable and estimated at no more than 20 minutes. If scope expands, stop, return the CR to design review, and ask for renewed approval.
6. Do not bundle unrelated requests or make opportunistic cleanup, scoring, UI, dependency or workflow changes outside the approved packet.

Read-only diagnosis and governance/design documentation are allowed before approval. An emergency production fix still requires a short architecture/impact card and explicit authorization; a protective production pause must be reported and recorded.

## Start every new conversation here

Before proposing work or changing files:

1. Read `docs/NEXT_SESSION_HANDOFF_ZH.md` and `docs/CURRENT_STATUS_ZH.md` completely.
2. Use `docs/CODEBASE_MAP_ZH.md` to locate the smallest code surface; do not scan the whole repository first.
3. Read `docs/SAGE_VISTA_RULEBOOK_ZH.md` completely.
4. Use `docs/rules/README.md` to select the smallest affected business module.
5. Check `git status`, the latest `main` commit, and the machine state files named by `docs/CURRENT_STATUS_ZH.md`. Never trust an old chat summary over repository state.
6. In the first update to the user, state the current production date, historical replay coverage and next checkpoint, then name the exact module being changed.

Before changing any strategy, score, factor, detector, ranking, market/industry adjustment, holding rule, backtest, experiment, production explanation, or related UI:

1. Read the concise project purpose and module map in `docs/SAGE_VISTA_RULEBOOK_ZH.md` completely.
2. Use `docs/rules/README.md` to identify the affected module.
3. Read only that module rule and the files named by its linkage conditions. Do not load every module for a single-module change.

Examples: scoring-only changes start with `docs/rules/04_SCORING.md`; factor-definition changes start with `03_FACTOR_MODEL.md`; experiments start with `08_BACKTEST_AND_EXPERIMENTS.md`.

For any semantic change:

1. Capture the user's intent in `docs/CHANGE_REQUESTS_ZH.md` before editing code. Fragmentary ideas stay `captured` until clarified; do not silently turn them into production behavior.
2. Update and version the affected module rule before code. Update the overall rulebook only when project purpose, module boundaries, or cross-system flow changes.
3. Append the approved decision to `docs/DECISION_LOG_ZH.md`.
4. Pre-register an experiment before changing selection, scoring, holding, stop, or target behavior.
5. Then change code, add leakage/contract tests, run the experiment, archive all results, update UI, deploy, and verify production.
6. Finish the change-request entry with implementation, test, commit and production evidence. A request is not `implemented` merely because code was drafted locally.

For a behavior-preserving bug fix or refactor, capture it in `docs/CHANGE_REQUESTS_ZH.md` first; update a business module only if business meaning changes. User-visible UI behavior still follows `docs/rules/10_UI_AND_OPERATIONS.md`.

Always distinguish current production behavior from approved target behavior and unimplemented ideas. Never silently rewrite historical scores or delete failed, negative, incomplete, or insufficient-sample experiments.

Validated strategies belong in `docs/rules/11_VALIDATED_PLAYBOOK.md`. Evidence-backed prohibitions belong in `docs/rules/12_HARD_RULES.md`; a high score never overrides an active hard rule.
