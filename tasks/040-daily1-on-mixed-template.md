# Task 040 — Move the daily trainer (daily1) onto the mixed-trainer page

Read `tasks/README.md`, `tasks/033-daily-trainer.md`, `tasks/035-mixed-timeframe-trainer.md` and
`work/v3w/mixed035/MAINTAINING.md`. Owner asked 2026-10-19: the daily trainer's UI is much worse than the improved mixed trainer;
make it the same. Starts only after Task 039 is accepted, because 039 makes the build module serve more than one bank.

## Fixed (do not change)
- **Same questions.** The `daily1` bank and keys (`work/v3w/daily1-keys.json`, `work/v3w/daily1-src/`) are read-only: same 100
  questions, same order, same ids, same entry/stop/target/exit/net R. Show SHA-256 of every daily1 input before and after.
  If the module needs another key shape, write an adapter; never rewrite the keys.
- **Same answers.** Cloud collection `daily1`, doc ids `daily1-001`..`daily1-100`, answer fields
  `{answered_at, choice, confidence, note, shape_wrong}` unchanged. The owner's 10 saved answers must load, stay locked
  (first answer wins, get-before-set as now) and show batch 1 as revealed. Never write to the real collection in tests.
- **Same page as mixed1**, built by the one shared module (no forked copy): one case per screen layout, cumulative $100k account
  first (frozen rules .02/.20/10/.10, US cost 0.1% per side, as in 033), batch reflections (new collection
  `daily1_reflections`, separate from answers), "我的眼光（按周期）" (daily only here), original chart / later-move toggle,
  every layout and pop-up fix the mixed page has. Blind rules as in 033 (ticker and dates hidden until the ten is complete).
- mixed1 and hk1 outputs stay byte-identical (hashes before/after).

## Acceptance (Claude checks each line; report each with evidence)
1. daily1 input hashes unchanged; mixed1/hk1 page hashes unchanged.
2. Mock cloud loaded with copies of the 10 real answer docs (export them read-only from the page's existing export, not from the
   cloud yourself): batch 1 shows revealed and locked; its account summary equals `work/v3w/daily1-overall-10.json`
   (balance, net P&L, win rate, max drawdown).
3. Answering question 11 in the mock writes only `daily1-011`; editing a reflection never touches answer docs or timestamps.
4. 390px and 1440px screenshots of: an unanswered case, a revealed batch summary, the later-move view.
5. Python and Node tests pass; list the commands.

## Deliverables
New page `work/site-v2/daily-trainer-2.html`; build changes in the shared module + tests; ledger §17 note (UI move only, no new
research); `docs/STATUS.md` and a `docs/REVIEW_QUEUE.md` row (待核查). Branch `codex/daily1-template` from the accepted 039
branch; never merge main; never `git add -f work/`. Claude publishes to the same URL
(https://claude.ai/artifact/Q3Asb9s4H6itz8axpDK8yu) and verifies the real answers read-only.
