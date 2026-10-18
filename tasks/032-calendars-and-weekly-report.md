# Task 032: real exchange calendars + a weekly QuantStats report (run-and-record mode)

Read `tasks/README.md` first. Owner (2026-10-19, ADR-16): run-and-record mode; adopt two mature open-source libraries. Do NOT touch
frozen 3W code or change any trading rule.

## Environment (installed by Claude; you work offline)
`work/vectorbt-env/bin/python` has pandas 3.0.5, QuantStats 0.0.81 (from `research/backtest/dependencies/quantstats-requirements.lock`)
and exchange_calendars 4.11.1. Use `get_calendar(code, start='2005-01-03', end='2030-12-31')` and read `.sessions` (and early-close
attributes). Note: `is_session()/next_session()` raise DateOutOfBounds with pandas 3 in this env - do not use them; export the session
list instead.

## A. Calendars without a runtime dependency
- `scripts/build_calendars.py` (runs in that env): export NYSE (XNYS) and HKEX (XHKG) sessions 2005-01-03..2030-12-31 to
  `data/calendars/xnys-2005-2030.json` and `xhkg-2005-2030.json` (sorted ISO dates + early closes if available + header with
  source, library version and sha256).
- `research/lab/calendars.py` (stdlib only): load those files; `is_session(market, day)`, `next_session`, `previous_session`,
  `last_session_of_month`.
- Replace the hand-written holiday logic in `research/lab/app_data.py` (`next_session` / month-end) with the new module. Find other
  hand-written holiday code (e.g. `services/scanner/backtest_progress.py`, the 2025-09-01 bug) and LIST it in the report; change only
  research/app code here, not production services - Claude decides on those.
- Record the dependency like the existing ones: `research/backtest/dependencies/exchange_calendars-4.11.1.evidence.json` (version,
  PyPI URL, licence) + licence text. Tests: 2025-09-01 Labor Day, 2026-11-26 Thanksgiving, HK Lunar New Year 2026, month-end; app_data
  outputs unchanged except where the old logic was wrong (list differences).

## B. Weekly report
`research/lab/weekly_report.py` (runs in the env): inputs = a cockpit export JSON (Claude exports the paper account each Saturday:
accounts, positions, prices, journal - create a fixture from the shape described here: accounts/paper {start_cash, cash},
positions {account, symbol, source, qty, entry, opened, status, closed?, exit?}, prices/{SYM} {close, date}, journal {at, text}) +
`research/lab/forward/triangle/outcomes.json` + SPY/sector prices from the sector dataset. Output `work/reports/weekly/<date>.html`:
one page in simple Chinese - this week's signals, paper account value and P&L by sleeve, month-end rebalance status, forward record
summary, and a QuantStats section (equity vs SPY, drawdown, monthly returns) once there are >= 20 trading days of paper history
(before that, say so). Sage Vista theme (navy header, cards). Tests with fixtures.

No network, no commits. Report: files, test results, old-calendar differences, Concerns.
