# Task 046 — The core + 3W paper account runs itself (feeds alarm 2 and "proof")

Read `tasks/README.md`, `tasks/036-forward-judging-plan.md`, `research/lab/forward.py` (existing forward paper accounts,
registered 2026-10-10 — do NOT edit its config or folder), `research/lab/forward_judge.py` (`--paper` input),
`research/lab/account.py`, `research/lab/allocation.py` and the research-lab workflow. Owner asked 2026-10-24 (ADR-17: machine
first). Today Claude updates this account by hand in the cockpit and it is stale since 2026-10-16. No 3W rule changes.

## Pre-register first (ledger §17, dated 2026-10-24, before any value is computed)
- Account `paper-core-sat-v1`, $100,000, start = first regular NYSE session after this card merges (state the date in the
  ledger when merging; never backdate). Cost 0.1% per side, whole shares, cash never negative, previous-close values.
- Core 50%: SPY, XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY, 5% each of the account at each rebalance. Signal at the last
  regular session close of each month: a sleeve holds its ETF if that close is above its own 200-day simple moving average of
  closes, else holds SHY. Trades at the next session's open. Initial positions use the latest month-end signal before start.
- Satellite 50%: the frozen 3w-1.9 forward record. Every rule-1.9 order (plan go and market ok) the forward record emits from
  the start date is taken with the frozen account rules on the satellite sleeve's own equity (2% risk, 20% cap, 10% heat,
  ≤ 10 positions, previous-close equity, same-day exits before entries as in `account.py`). Fills, stops, targets and 26-week
  exits come from the same daily-OHLC replay the forward record uses (no second implementation of trade logic). Idle
  satellite cash earns 0%.
- No rebalancing between core and satellite; each sleeve keeps its own equity.

## Output
- New folder `research/lab/paper/` (not `research/lab/forward/`): `config.json` (the registration), append-only
  `history.jsonl` (one line per run: date, core, satellite, total, SPY buy-and-hold on $100k from the same start, positions,
  cash) and `latest.json`. Daily values from start to the latest common session.
- The exact daily series format `forward_judge --paper` expects (`{date, core, satellite, total, spy}` list) written where
  the scorecard step reads it; wire `--paper` into the research-lab scoring step so alarm 2 and "proof" are computed.
- Public site: unchanged for now (the /forward page keeps "需模拟账户，不在公开页").

## Tests
Month-end signal on synthetic prices (above/below SMA, exactly equal → not above), rebalance timing (next open), SHY switch,
satellite sizing incl. heat and 10-position caps, a stop and a target exit, no backdating (start after registration),
missing price → stop the run with an error, never guess. Existing tests stay green.

## Delivery
Workflow change allowed: one step after the forward record, before scoring. Branch `codex/paper-account`; do not commit; no
network. Ledger §17, STATUS, REVIEW_QUEUE (待核查). Claude updates the cockpit from `latest.json` in the Saturday routine.
