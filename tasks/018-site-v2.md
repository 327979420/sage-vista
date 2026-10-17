# Task 018: Sage Vista v2 - redesign the real site (branch + preview first)

Read `tasks/README.md`, `AGENTS.md` and `docs/rules/01_GOVERNANCE.md` first. Owner (2026-10-18): the separate `/app` pages are "too rough";
the change must be made to sage.freddyliang.com itself, on a branch, with a preview the owner can open before anything ships.
Inputs: PRD `work/prd-sv-app.html` (IA, US-1..US-5, section 7 migration table), prototype `work/proto-sv-app.html`, data files from task
014/015 (`research/lab/app_data.py`, `public/app/*.json`). Branch `site/v2` (this worktree). Owner does UAT; nothing merges without it.

## Phase 1 (this card) - stop after it and report
1. **Preview without touching production.** Find how the site is deployed (`deploy-site.yml`, `daily-eod.yml`, wrangler config) and add
   the safest way to publish a branch preview (e.g. `wrangler versions upload` / a preview alias, or a separate preview worker name),
   triggered only by `workflow_dispatch` on non-main branches. It must never change the production worker, routes, DNS, secrets or
   the EOD job. If any of that is unavoidable, STOP and explain before writing it.
2. **Design direction.** Propose a polished, professional look for v2 (institutional-trader cockpit, calm, dense but readable, phone
   and desktop) that fits the existing brand. Produce 2 static mock pages in `work/site-v2/` (今日 and 我的组合, real sample data)
   so the owner can choose. No new heavy dependencies.
3. **Plan** for phase 2: which existing routes change, which move to 研究档案 (keep every old page reachable; nothing deleted), the
   nav, how `/app` pages are replaced, test plan (lint, typecheck, build, node tests, 390/1440 px screenshots, keyboard).

Do not change production pages in phase 1. No commits, no network (Claude pushes and dispatches). Report: files, the preview method
and its risks, the two mocks' paths, the phase-2 plan, Concerns.
