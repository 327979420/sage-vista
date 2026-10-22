# Task 045 — Upgrade the public /forward page to the pre-registered judging (SV-44)

Read `tasks/README.md`, `tasks/036-forward-judging-plan.md`, `docs/FORWARD_JUDGING_PLAN_ZH.md`, `app/forward/forward.tsx`,
`app/evidence/data.ts`, `research/lab/app_data.py` (`forward_data`), `research/lab/forward_judge.py` and the research-lab
workflow. Owner asked 2026-10-22. sage.freddyliang.com is PUBLIC: this page shows only the frozen 3W forward record. Never
publish own picks, the real account, the eye results or anything from the cockpit.

The page already exists (task 023). Change it so a visitor sees, honestly, how 3W is being judged and where it stands.

## Data (`research/lab/app_data.py` → `public/app/forward.json`)
- Add a `judging` block built from the Task 036 scorecard (`research.lab.forward_judge`, the same job already runs it before
  app data): completed trades, scored / unscorable, next checkpoint and trades to go, every reached checkpoint (k, mean net-R
  difference vs twins, t, verdict), alarm 1 state, verdict text ("继续记录，未证明" etc.), and the pre-registered thresholds as
  data (30/60/100…, t ≤ −2 / t ≥ 2, 25% drawdown). Alarm 2 and "证明有效" need the satellite paper account, which is not public:
  show them as "需模拟账户，不在公开页" — never guess.
- Per-signal rows: use NET R (0.1% per side, as in 036) and label it; keep gross R only as a small secondary value. Add the
  Discord alert ID (`A-xxxxxx`, Task 044) and the lifecycle status/date from the ticket outcome.
- Remove the blind-judging fields from the public payload and page (ADR-17; nobody judges signals now). Keep the code path
  for `judgements.jsonl` untouched in research code.
- Waiting-time context: a short fixed text derived from `work/reports/forward-sample-size-v1` numbers
  (~28 completed candidates a year; at +0.07R proof needs ~2,900 trades) — mark it "粗估，不是保证".
- If the scorecard file is missing in a run, the block says "本次运行未生成计分" and the page still renders.

## Page (`app/forward/`)
- Top: a judging panel — progress to the next checkpoint (e.g. 0 / 30), current verdict, alarm 1, the two hidden items text,
  and one line on what the thresholds mean. Then the existing tiles, cumulative NET R curve and the table (alert ID + lifecycle
  columns; blind columns removed).
- A small "其他市场考试" note: HK (14 trades, p 0.089) and Korea (29 trades, p 0.172), both "样本不足/未证明", linking nowhere.
- Bilingual like the rest of the site (zh + en via the existing i18n). Mobile 390 px and desktop 1440 px.
- Tests: `validForward` for the new shape (incl. missing scorecard), app_data unit tests for the judging block and net R, page
  tests the repo already uses (`npm test`). Keep every existing test green.

## Delivery
Branch `codex/forward-page`; do not commit; no network. Claude runs the site preview (`preview-site.yml`) on the branch and
hands the preview URL to the owner for UAT; the page goes live only after the owner accepts. Update STATUS, a ledger §17 note
(public page change, no rule change) and a REVIEW_QUEUE row (待核查).
