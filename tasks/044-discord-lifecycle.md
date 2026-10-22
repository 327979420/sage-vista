# Task 044 — Discord: alert IDs, suggested shares, and follow-up messages

Read `tasks/README.md`, `services/scanner/triangle_discord.py`, `tests/test_triangle_discord.py`, the `triangle_discord` job in
`.github/workflows/research-lab.yml`, `.github/workflows/triangle-discord.yml`, `research/lab/forward_judge.py` and
`research/lab/trade_review.py`. Owner asked 2026-10-22 (ADR-17: execute mechanically, the machine tracks everything).
This card ALLOWS edits to `services/scanner/triangle_discord.py`, its tests, `research/lab/app_data.py` only if needed for
outcome fields, and the two workflows above. Frozen 3W code and rules stay untouched; no rule, price or timing changes.

## 1. Alert ID
- Every opportunity gets a short, stable ID derived from the existing signal id: `A-` + first 6 characters of `signal['id']`
  (collision check against all ids in the snapshot and in `automation/triangle-discord-state.json`; on collision use 8).
- Shown on every message about that signal. This is the `alert_id` the owner logs in the cockpit (Task 042 matches on it).

## 2. Suggested shares (frozen account rules, per trade)
- shares = floor(min(equity × 2% / (entry − stop), equity × 20% / entry)). Show the risk in $ and which limit bound it.
- Two lines: the paper account (equity from the frozen forward paper account if the job can read it; else "$100,000 模拟")
  and the real account from an optional GitHub secret `SV_ACCOUNT_EQUITY_USD`. If the secret is absent, show "每 $10,000：N 股".
  The owner sets the secret; never print it in logs or artifacts other than the Discord message itself.
- One reminder line, no computation: "开仓前确认：总风险 ≤ 10%、持仓 ≤ 10 只".

## 3. Follow-up messages (one per event, durable dedupe key `{version}:{signal_id}:{event}`)
Events for a signal that was alerted: `filled` (limit filled, date + fill price), `stopped` (exit date, price, net R),
`target` (exit date, price, net R), `time` (26-week exit, net R), `expired` (no fill within 40 sessions), `cancelled`
(stop or target touched before the fill — frozen rule). Source the event, dates and prices from the same daily-OHLC replay the
forward record already uses (forward_judge recompute details or app-data ticket outcomes — pick ONE source, the one already
produced in the scheduled job, and say which). Net R uses 0.1% per side, as in 036.
- Never send a follow-up for a signal that never got an opportunity alert (no key in the state file).
- Send at most one message per event; if two events land in one run (e.g. filled and stopped the same day), send them in order.

## 4. Message format (plain Chinese, vertical, same style as the approved card)
Opportunity: title line with symbol + ID; limit / stop / target (3R); suggested shares lines; reminder; valid-until line.
Follow-ups: one emoji + event word + symbol + ID on line 1; date and price; net R where it exists. Examples in your report.

## Safety (keep all existing checks)
Same snapshot freshness, ticket identity, frozen 3R and expiry checks; reserve-before-send; webhook never logged; EOD
window respected. Simulation mode: one synthetic message per event type, marked "🧪 模拟", deduplicated, never touching
production state; preview mode needs no secret.

## Tests
ID stability and collision; share math (risk-bound vs cap-bound, tiny equity, missing secret); every event type incl. same-day
fill+stop; no follow-up without an opportunity key; dedupe across runs; reservation retained on send failure; all existing tests.

## Deliverables
Code + tests; preview JSON of every template; ledger §17 note (notification change, no rule change); `docs/STATUS.md`,
`docs/REVIEW_QUEUE.md` (待核查). Branch `codex/discord-lifecycle`; do not commit; no network. Claude runs the card preview
on Actions for the owner before merge.
