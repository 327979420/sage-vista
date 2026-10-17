# Task 021: Site v2 phase A - same Sage Vista theme, new nav + 今日 + 我的组合 (branch site/v2)

Read `tasks/README.md` and `tasks/018-site-v2.md` first. Owner verdict on the phase-1 mocks (2026-10-18): "looks cheap; it must look at
least like the current Sage Vista - same theme, an upgraded version." The static mocks are deleted. Keep the preview workflow work.

## Design rule (hard)
- NO new visual language. Reuse the live site's design tokens and components: `app/globals.css`, `product-v2.css`, `interface.css`,
  `market.css`, the existing header, cards, tables, badges, fonts (Geist), spacing and colours. Read the current homepage
  (`app/page.tsx` and its components) and the market pages first and list the components you reuse in the report.
- New UI only where nothing exists (the traffic light, the sleeve grid); build it from the same tokens so it looks native.
- The result must look like the current homepage's sibling. If a needed pattern does not exist, stop and describe it before inventing.

## Scope
1. Navigation: 今日 · 3W 机会 · 我的组合 · 成绩单 · 学习 + 研究档案 (all current pages stay reachable there; nothing deleted). Desktop:
   the existing header pattern; phone: the same header, compact (the bottom tab bar comes in phase C).
2. 今日 becomes the homepage content on this branch (`/`), using `today.json` (+ the same plain sentences as task 015). 我的组合 at
   `/portfolio` (or the existing route naming pattern). Pages not built yet show the existing site's "coming soon" style.
3. The old `/app` routes redirect to the new pages.
4. Preview workflow: use ONE fixed worker name (`sv-preview`), overwritten on each dispatch, instead of one per run; keep every other
   safety property. The workflow file must also land on main to be dispatchable - put it (+ its script and test) in a separate small
   commit so Claude can PR it to main first.

## Quality
lint, typecheck, build, node tests, existing tests pass; 390/1440 px layouts; keyboard reachable; no horizontal scroll. Claude takes the
screenshots for the owner (you cannot open a browser). No production deploy, no network, no commits.
Report: reused components, new components, files, the separate preview commit's file list, Concerns.
