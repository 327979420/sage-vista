# Task 033: daily-chart trainer with a summary every 10 trades (owner's self-training; not an exam)

Read `tasks/README.md` and `docs/STATUS.md` first. Owner (2026-10-19): "like 新数据盲测 batches 3/4, but on DAILY charts; mainly so I learn
my own judgement - a summary after every 10 trades; useful data can also feed SV later." This is TRAINING, not a registered test:
outcomes may be embedded in the page (hidden until answered). Do not change frozen code or any rule.

## Reference
The earlier batches: generator `work/v3w/fwd_blind.py`, pages `work/v3w/fwd-blind-3.html` / `-4.html` (look, chart style, db usage,
answer flow). Keep that look but use the improved flow of `work/site-v2/blind-v2.html` (auto-advance to the next unanswered case,
answer bar under the chart, case grid, D/N keys, "三推/线画错了" toggle, confidence 1-3, note).

## Cases (daily)
- Detect three-push shapes on DAILY bars with the existing detector code applied to daily rows (`research/lab/triangle.py`
  push_lines/bottoms_of, same parameters scaled from weeks to days only where they are spans: span 10..90 weeks -> 20..180 trading
  days; state every scaling in the card). Signal = daily bullish bar + daily MACD golden cross after >= 4 days under, under zero.
- Order (training defaults, shown on the chart): limit 1% under the signal close valid 10 trading days; stop 1% under the last bottom;
  target 3R; max hold 60 trading days. Only cases whose order filled and finished.
- Sources: US stocks, signals 2025-07-01..2026-08-31 (new data the owner has not judged) plus US development data 2015-2024, never
  HK group B. Exclude symbol+week pairs the owner already judged (`research/lab/cases/*.json` + local keys). 100 cases, shuffled
  (seed 20261025), symbols and dates hidden, prices rebased to 100 at the signal close.
- Chart: ~120 trading days to the signal day, EMA20, volume pane, MACD pane, push line + bottoms.

## Summary every 10
After each 10 answers show a summary card for those 10 (and cumulative): for each case the result (R, days held, win/loss, symbol and
date now revealed), the owner's choice and whether it was right (做 right if R > 0; 不做 right if R <= 0), mean R of 做 vs 不做, mean R
of all 10 (= what "do everything" would have earned), how the confidence levels did, and the cases marked "画错了". Plain Chinese.
Keep a running table of all batches at the bottom.

## Data for SV
Answers stored via the artifact db (collection `daily1`, doc id = case id, fields choice, shape_wrong, confidence, note, answered_at).
Keep the answer key locally (`work/v3w/daily1-keys.json`) and a short `work/v3w/daily1.md` describing the case selection. Not used
for any rule unless the owner asks for a registered test later.

Deliverables: generator script + log, the page `work/site-v2/daily-trainer-1.html` (self-contained), keys file. Add a row to
`docs/REVIEW_QUEUE.md` and update `docs/STATUS.md`. If writes via work/ are refused use `task033-staging/`. No network, no commits.
