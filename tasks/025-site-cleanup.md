# Task 025: website cleanup (same branch site/evidence; not an "app" - do not call it one)

Read `tasks/README.md` first. Owner feedback (2026-10-18) on the preview: it is a website with new pages, not an app (app work is paused);
the text under the ticket is messy, especially "订单计划"; the forward record is hard to find; "我最喜欢形态" must stay visible as a quick
browse. Keep the live Sage Vista theme and the prototype as the visual standard.

## Changes
1. Navigation (desktop top tabs, same component): 今日 · 3W 信号 · 前向记录 · 形态速览 · 我的组合 · 成绩单 · 更多 (更多 = 学习, 研究档案).
   形态速览 = the existing "我最喜欢形态" page (`/zh/watch/resonance/favorite-pattern`) reachable at a short route `/patterns`
   (redirect or re-export; do not rewrite that page). 前向记录 = `/forward` as its own tab. Remove "App" wording anywhere it appears.
2. Ticket page text cleanup:
   - 订单计划: a compact 2x3 grid of label + number (限价 / 止损 / 目标 3R / 每股风险 / 挂单到期 / 最长持有), no extra sentences. One
     short line under it at most.
   - 后来怎么样: one horizontal timeline (信号 → 成交 → 退出 → 结果 R) with dates; no duplicate sentence.
   - Remove the "TradingView Lightweight Charts" credit line from the body (keep attribution in the footer or an info tooltip, as the
     library licence requires).
   - Banner text: one line.
   - Typography: labels 12px muted, values tabular numbers; no orphan sentences.
3. 前向记录 empty state: show what will appear (a greyed sample of the table and the cumulative-R chart frame labeled 示例) plus
   "下次检查：周五收盘后（10-23）" computed from the data date, instead of a single sentence.
4. 今日: add one small card "前向记录：已记录 N 个信号，最近一次检查 <date>" linking to /forward.

## Quality
lint, typecheck, build, tests; screenshots for /, /signals, /forward, /patterns at 1440 and 390 in the preview workflow. No production
deploy, no network, no commits. Report: files, tests, Concerns.
