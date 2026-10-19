# Review queue: Codex works with the owner, Claude checks later

Since 2026-10-19 the owner also works with Codex directly. This file keeps Codex and Claude in sync. **Codex adds a row for every
finished piece of work; Claude reviews rows when the owner says "核查" (or during the Saturday routine) and fills in the verdict.**
Nothing here replaces the rules in `tasks/README.md` and `docs/rules/01_GOVERNANCE.md`.

## Codex: before you start any research
1. Read `docs/TRIANGLE_HANDOVER_ZH.md` §0 (current state: run-and-record mode, ADR-16 - no new rule mining on development data unless
   the owner explicitly asks; frozen 3w-1.9 is not changed).
2. Pre-register in `docs/CASE_REVIEW_LEDGER_ZH.md` section 17 BEFORE computing: question, data, the single verdict and threshold.
3. Never load locked data (HK group B, HK pre-2005 for signals) and never change frozen code, `research/lab/account.py`, `services/`
   or the website unless the owner asks for that change in this conversation.
4. Work on a branch named `codex/<topic>`; never push to main.

## Codex: when you finish
Add a row below (newest first) and write the result paragraph into ledger section 17. If you cannot commit, leave the files and the row
uncommitted and tell the owner "等 Claude 核查".

| Date | Topic | Branch / files | Ledger heading | What to check | Status |
|---|---|---|---|---|---|
| (example) 2026-10-20 | short name | `codex/topic`, `work/...` | exact heading | numbers to reproduce, tests to run | 待核查 |

## Claude: how to review a row
Reproduce the key numbers (or rerun the tests), check the pre-registration came first, check no locked data or frozen code was touched,
then set Status to `通过` / `退回：原因`, merge the branch if it passes (respecting the 23:30-04:30 UTC window and any running EOD job),
and update the workbench ticket.
