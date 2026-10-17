# Task 020: one master plan - done / doing / to do, and room for new things

Read `tasks/README.md` first. Owner (2026-10-18): "We must see everything - done, in progress, to do - and plan it as one; new things
will be added later, so leave room for them." Owner is a non-technical product manager; write in simple Chinese.

## Inputs (read, do not change)
`work/workbench-export/` (tickets, ADRs, RAID from the owner's workbench), `docs/STATUS.md`, `docs/COLLAB-LOG.md`,
`docs/TRIANGLE_HANDOVER_ZH.md` §0, ledger section 17 headings, `work/reviews/codex-history-requirements.md` (62 requirement groups),
`work/prd-sv-app.html`, `tasks/*.md`. Agreed order (owner, 2026-10-18): Sprint 2 phase A (same theme, nav + 今日 + 我的组合 on a
branch preview) -> Sprint 3 phase B (3W, 成绩单, 学习, 研究档案) -> Sprint 4 phase C (PWA app, replace homepage after UAT, framework
upgrade) -> Sprint 5 phase D (signal alerts, cockpit in the app, English). Research runs in parallel.

## Output: `docs/ROADMAP_ZH.md` (one file, <= ~250 lines)
1. **一页总览**: three tracks (研究 / 产品(App) / 基础设施与安全) x three columns (已完成 / 进行中 / 待做), each item one line with its
   SV ticket or task number. Every workbench ticket appears exactly once; flag tickets that look duplicated or stale.
2. **路线图**: Sprint 2-5 with dates, goal, deliverables, what the owner must do, and dependencies.
3. **以后加新东西的规矩 (extension rules)**: how a new idea enters (intake -> ticket -> ADR if it is a decision -> card -> acceptance);
   where it lives in the app (a new tab vs a card on 今日 vs a page in 研究档案; the nav has a fixed maximum of 5 tabs + 更多); the data
   contract (one small JSON per page, `schema_version`, built by GitHub, < 2 MB); research ideas need ledger pre-registration and can
   only use unused data; the "parking lot" list for ideas not yet scheduled (seed it from the audit's partial/superseded items).
4. **未决定的事**: open owner decisions (e.g. HK group B exam, portfolio label, Discord ADR-1, multi-factor ranking retirement) with
   the default if nobody decides.
5. **风险** (top 5 from RAID, current).
Also produce `work/workbench-export/roadmap-updates.json`: a list of suggested ticket changes (status/sprint/rank fixes) - Claude applies them.

No code, no network, no commits.
