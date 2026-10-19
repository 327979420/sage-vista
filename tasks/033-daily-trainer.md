# Task 033: daily-chart trainer with a summary every 10 trades (owner's self-training; not an exam)

Read `tasks/README.md`, `docs/STATUS.md` and `docs/REVIEW_QUEUE.md` first. Owner (2026-10-19): "like 新数据盲测 batches 3/4, but on
DAILY charts; mainly so I learn my own judgement - a summary after every 10 trades; useful data can also feed SV later." Dates
shuffled; no market filter.

This is TRAINING, not a registered test: outcomes may be embedded in the page (hidden until answered), and nothing here becomes a
rule. Do not change frozen code (`triangle.py`, `triangle15.py`, `buysystem.py`, `account.py`, forward config), never load HK group B,
and do not derive new rules from old data. Every parameter below was fixed by Claude on 2026-10-19 from the existing code and the
owner's stated rules - NOT by trying returns. Do not tune anything by looking at outcomes; if something is impossible as written, stop
and ask.

## 1. Daily shape (all parameters fixed)
Build daily rows `{date, open, high, low, close, volume}` per stock. Reuse the frozen helpers by CALLING them; set module parameters
only at runtime inside the generator process (never edit the files).

| Item | Weekly frozen 3w-1.9 | Daily trainer (use exactly) |
|---|---|---|
| Swing highs (push candidates) | `v3weekly.pivots(highs, "high")`, left = right = 2 bars | `pivots(..., left=5, right=5)` (one trading week each side) |
| Push candidates window | `t - span_max <= p <= t - 2` | `t - 180 <= p <= t - 5` (right-side confirmation must exist by day t) |
| Pattern span (first push to signal) | 10..90 weeks | 20..180 trading days (set `T.P["span"] = (20, 180)` at runtime) |
| Each push lower | `push_drop` 0.995 | same 0.995 |
| Middle (2nd) push vs the line | within +/-8% of the line (`push_fit` 0.08) | **owner's rule (SV-49): the 2nd push high must reach the line**: `line(b) * 0.995 <= high(b) <= line(b) * 1.08` (touch or pierce; never below) - apply as a post-filter on `push_lines` output |
| Line not broken before signal | no close above line*1.01 between push 1 and t | same, on daily closes |
| Bottoms | `bottoms_of` (lows_tol 1%, >= 2 bottoms) | same function, daily rows |
| Converging | `converging`, converge 0.5 | same |
| Pullback from push 1 to lowest bottom | 10%..60% | same |
| Flat bottoms | last bottom <= lowest bottom * 1.10 | same |
| Not a new long-term low | lowest bottom >= 0.9 * min low of 156 weeks before push 1 | 0.9 * min low of 756 trading days before push 1 |
| ATR | weekly ATR14 (`_atr`) | daily ATR14 (same function on daily rows) |
| Signal bar | bullish week (close > open) | bullish day (close > open) |
| Near the last bottom | signal low <= last bottom + 1.5 * ATR | same with daily ATR |
| MACD | weekly 12/26/9 (`buysystem` EMA, DIF = EMA12 - EMA26, DEA = EMA9 of DIF, hist = DIF - DEA) | daily 12/26/9, same formulas |
| Golden cross | hist > 0 on signal week, hist < 0 on each of the 4 prior weeks | hist > 0 on signal day, hist < 0 on each of the 4 prior days |
| "Under zero" | DIF < 0 at signal close | DIF < 0 at signal-day close |
| Room above (t1) | nearest swing high inside the triangle >= 7% over the signal close, x0.97 | same rule on daily swing highs |
| Planned R:R check | (t1 - limit) / (limit - stop) >= 1.5 | same |
| Cooldown per stock | 13 weeks after a signal | 65 trading days |
| Monthly MACD veto | yes | **not used** (training) |
| Market filter (SPY / breadth) | yes | **not used** (owner) |
| Liquidity pool | `triangle15.POOL`: >= 420 days history, raw close >= $5, close*volume >= $10M on the signal day | same |

## 2. Data range and sampling
- Universe: the five frozen US datasets (`universe-1985-v1`, `fresh-a..d-1995-v1`), US only. Never HK.
- Historical: signal days **2005-01-01..2024-06-30** (yes, include 2005-2014: this is training, and the earlier exclusion only applied
  to registered tests). Pre-2005 bars only as indicator warm-up.
- New: signal days **2025-07-01..2026-08-31** (after the frozen development period).
- Draw **30 new + 70 historical = 100**. If fewer than 30 eligible new cases exist, take all of them and fill the rest from historical;
  if the total eligible is < 100, use all and report the count (do not loosen any rule).
- **One case per stock** across the whole bank (pick the stock's case at random among its eligible cases, same seed).
- Exclude every symbol + ISO week the owner already judged (`research/lab/cases/3w-user-decisions-2026-10.json`,
  `triangle-user-judgements-2026-10.json`, blind v2 keys `work/v3w/blind-v2-keys.json`, via the local keys; match on the ISO week of
  the signal day).
- Eligible = the order filled AND the trade finished (stop, target or time) before the dataset's last bar. Never choose by outcome.
- Randomness: sort candidates by (dataset, symbol, signal_date), `random.Random(20261025)`; sample the two groups, then shuffle the
  100 together with the same generator. Hide symbols and dates; rebase prices so the signal close = 100.

## 3. Fills and exits (mirror the frozen `triangle15.trade` logic, daily)
- Limit = signal close * 0.99. Stop = last bottom * 0.99, but at least 0.5 * daily ATR below the limit: `stop = min(bottom*0.99,
  limit - 0.5*ATR)`. Target = limit + 3 * (limit - stop) (planned prices).
- Order valid on the 10 trading days after the signal day (day+1..day+10). Each day in that order: if open <= stop -> cancelled
  ("stop before fill"); else if low <= limit -> filled at **min(open, limit)** (a gap down fills at the open); else if high >= target
  -> cancelled ("target before fill"). Not filled in 10 days -> cancelled. Cancelled cases are not eligible.
- After the fill, holding days are counted with the fill day as day 1, up to **60 trading days**. On each day k:
  1) if k > fill day and open <= stop -> exit at the open (gap through the stop);
  2) else if low <= stop -> exit at the stop (on the fill day too: the worse reading);
  3) else if high >= target -> exit at max(open, target) (on the fill day: at the target).
  Stop is checked before the target, so a day touching both is a loss.
- Not exited after 60 days -> exit at the close of day 60 ("time").
- R = (exit - entry) / (entry - stop) with the ACTUAL entry; net R with 0.1% per side via `standard_v1.net_r(..., 0.001)`.
- A trade that has not finished by the dataset's last bar is not eligible (log the count).

## 4. Page and summaries
- Look and flow of `work/site-v2/blind-v2.html` (auto-advance to the next unanswered case, answer bar under the chart, case grid, D/N
  keys, "三推/线画错了" toggle, confidence 1-3, note). Chart: the ~120 trading days up to the signal day (extend left to keep push 1),
  candles, EMA20, volume pane, MACD pane, push line extended to the signal day, bottoms, limit/stop/target as % from the signal close.
- After each 10 answers: a summary card for those 10 and cumulative - each case's result (net R, days held, exit type, symbol and
  date now revealed), the owner's choice and whether it was right (做 right if R > 0; 不做 right if R <= 0), mean R of 做 vs 不做, mean R
  of all 10 (= "do everything"), confidence 1/2/3 results, the "画错了" cases. A running table of all batches at the bottom.
- Answers via the artifact db: `const db = await window.claude.use("db")`, collection `daily1`, doc id = case id, fields
  {choice: "do"|"no", shape_wrong: bool, confidence: 1|2|3|null, note, answered_at}; first answer final; if db is null keep answers in
  memory and warn.

## 5. Deliverables and authorisation
- `work/v3w/daily_trainer.py` (generator) + `work/v3w/daily_trainer.log`, `work/v3w/daily1-keys.json` (answer key with symbol, dates,
  trade details, net R), `work/v3w/daily1.md` (selection description: counts per group, eligible totals, exclusions, cancellations,
  unfinished), page `work/site-v2/daily-trainer-1.html` (self-contained, no external scripts). If writes via work/ are refused use
  `task033-staging/` with the same names.
- Tests for: the fill/exit rules on synthetic bars (gap fill, stop before fill, same-day stop+target, time exit), the 2nd-push touch
  rule, one-case-per-stock, exclusions.
- Generate from LOCAL data only. Network is allowed only for git push.
- When done: add a row to `docs/REVIEW_QUEUE.md` (status 待核查), update `docs/STATUS.md`, **commit and push branch
  `codex/daily-trainer`** (do not merge to main; `work/` is gitignored - list those files in the review row). Claude publishes the page
  online and verifies that answers save.
