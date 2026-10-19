# Task 039 — Blind training bank from another market (Hong Kong group A)

Read `tasks/README.md`, then `tasks/035-mixed-timeframe-trainer.md` (this card copies it) and `tasks/010-hk-exam.md` (HK local
conditions). Owner asked 2026-10-19: keep practising, with charts from other markets. This trains and measures the OWNER's eye; it
never changes the frozen 3w-1.9 or any rule (ADR-16). Results feed Task 038 part A as their own bank (`hk1`).

## Fixed (do not change)
- Data: `hk-a-1995-v1` only (local in `work/lab/`). HK group B stays LOCKED: never load, list or
  name its file. Tracker Fund 2800 is the market proxy and never a question. Japan is NOT used here (its exam, Task 037, comes first;
  a Japan group-A bank may follow as a new card after that exam).
- Candidates: Task 034/035 templates and gates exactly (timeframe-scaled shape, 8-bar order, 26-bar holding, daily OHLC
  execution), with the HK local conditions from Task 010: pool unadjusted close >= HK$1 and >= HK$78M traded, 2800 replaces SPY
  in the market filter, cost 0.2% per side. Signal dates 2005-01-01..2024-06-30; account marked to 2025-06-30.
  Training-eligible only if filled AND completed. Never sample on win/loss.
- Bank `hk1`, target 60 questions: 20 daily / 20 weekly / 20 monthly, shuffled with seed 20261028; one stock per question.
  If a timeframe has fewer eligible cases, report the shortfall; no substitutions, no relaxation.
- Blind view as in 035: hide ticker, dates, timeframe AND market during answering; price axis shows relative % from the signal
  close (not HK$ levels). Reveal ticker, market, timeframe and dates only after each completed ten.
- Same page features as the current mixed trainer (`work/site-v2/mixed-trainer-2.html` build): first-answer lock with cloud
  get-before-set, cumulative $100k account first (frozen account rules .02/.20/10/.10, but cost 0.2% per side for HK), batch
  reflections, "我的眼光（按周期）", original chart / later-move toggle. Reuse the 035 build module; do not fork a second copy of
  the page code. New page `work/site-v2/hk-trainer-1.html`, private scripts in `work/v3w/hk039/`.
- Never touch `daily1` or `mixed1` banks, keys or cloud answers.

## Acceptance (Claude checks each line; report each with evidence)
1. Counts: candidates found / eligible / sampled per timeframe, every exclusion with its reason and count.
2. No group-B symbol and no 2800 anywhere in the bank (show the check).
3. Blind check: the answer view contains no ticker, date, currency, market or timeframe text (automated scan of the built HTML
   before reveal, plus a 390px and a 1440px screenshot).
4. Five sampled questions recomputed independently from raw prices (entry, stop, target, exit, net R) and matching the key.
5. JS account equals the frozen Python account on the bank inputs (mock answers only, no real answers).
6. Python and Node tests pass; list the commands.

## Deliverables
Ledger §17 entry before building (copy "Fixed" verbatim); page + private bank/scripts/tests; `docs/STATUS.md` and a
`docs/REVIEW_QUEUE.md` row (待核查). Branch `codex/hk-trainer`; never merge main; never `git add -f work/`. Publishing the page
and the live save test are Claude's job. Report with Concerns (HK has fewer liquid stocks; monthly cases may be scarce).
