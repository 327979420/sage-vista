# Task 015: App phase 1 - pages "今日" (Today) and "我的组合" (My portfolio)

Read `tasks/README.md` first. Owner decision (2026-10-17: "3好" = PRD Must items). PRD `work/prd-sv-app.html` US-1 and US-3; clickable
prototype `work/proto-sv-app.html` (views `today` and `pf`) shows the intended content and tone - match its content, follow the site's
existing styles for look. Data: the four files from task 014 (`research/lab/app_data.py`, published to `public/app/`).

## Scope - new routes only, nothing existing changes
- `/app` = 今日, `/app/portfolio` = 我的组合, plus a small shared header with the five phase-1 tabs (今日 · 3W 机会 · 我的组合 · 成绩单 ·
  学习). Tabs for pages not built yet are visible but disabled with "即将上线".
- Do NOT change the homepage, the existing nav, footer, tour, analytics or any existing page. Do not link the new routes from anywhere
  yet - the owner tests them first (UAT) and decides when they replace the homepage.
- Chinese text first. Put every user-facing string in one place so an English version can be added later (follow `app/i18n` if it fits;
  if it does not fit cleanly, a single `strings.ts` for the new pages is fine - say which in the report).
- Each page fetches only its own file from `/app/*.json` (today.json for 今日; portfolio.json and signals.json for 我的组合). No other
  public JSON. If a file is missing or fails, show a calm "数据还没生成" state, never a crash or a blank page.

## 今日 (US-1)
First screen: the traffic light (green / amber / red from `today.json`) with one plain sentence each for SPY vs its 200-day line and
breadth (and the source "universe-1985-v1" in small print); the number of new 3W signals this week; whether a month-end rebalance is due
and which sleeves would switch; "数据日期" (as_of) and a stale warning if any input is stale. `this_week` items as a short list; if empty,
say "本周没有要做的事".

## 我的组合 (US-3)
The 10 sleeves: symbol + Chinese sector name, above / below its 200-day line, distance %, this month's hold (ETF or SHY), and "月底会换"
when `would_switch` is true. Label the portfolio exactly from `portfolio.json` `status` ("candidate" -> "候选组合"). The 3W satellite:
open positions with distance to stop / target (% and R, as given - no extra judgement) and empty slots (max 10); if none, "3W 目前没有持仓".
Each number has a small "来源" line naming the rule (sector trend: Faber 2007, 200-day SMA, monthly; 3W: frozen 3w-1.9).

## Quality
- Works at 390 px and 1440 px; keyboard reachable; colour is never the only signal (the light also has a word: 绿灯 / 黄灯 / 红灯).
- `npm run lint`, `npm run typecheck`, `npm run build` pass; add node tests (`tests/*.test.mjs`, existing pattern) for the state
  mapping and the missing-file state. Existing tests keep passing.
- For local checking, copy `work/app-data/*.json` into `public/app/` but do NOT include those copies in the change set (the GitHub
  step publishes them).

## Stop and ask if
the routing or i18n pattern would force a change to existing pages, a field you need is missing from the task-014 files, or any wording
would claim something the ledger does not support.

## Deliverables
Code + tests on the branch, list of files, screenshots are not required (Claude reviews in a browser), codex report with Concerns.
node_modules is installed. No network, no commits.

## Decision (2026-10-17, Claude, answering Codex before any code)
Approved: extend the task-014 `today.json` projection in `research/lab/app_data.py` (with tests), so 今日 still reads only its own file:
- `new_signals_this_week`: count of 3w-1.9 records whose signal week is the latest COMPLETED week at `as_of` (not the latest week that
  happens to have records - a quiet week must show 0; all records, whether or not an order qualifies; also output that `signal_week`), plus `orders_to_place` = the existing qualifying count. Show both on the page with plain labels.
- `month_end`: `rebalance_due`, `next_session`, and `would_switch` = list of sleeve symbols copied from the same computation as
  `portfolio.json` (one function, no second implementation).
- `stale`: one summary object naming every stale input (market, sectors, signals) with its price date; empty when nothing is stale.
No new trading parameter. Keep each file under 2 MB and the byte-for-byte reproducible build.
