# Sage Vista status (mirror of the owner's workbench)

Maintained by Claude; the owner's interactive workbench is https://claude.ai/artifact/BdbVybVXiShDN5MtaqtVUQ (Codex cannot open it, so
this file mirrors it). Updated 2026-10-17. Owner's priority order: factor attribution, then the portfolio decision layer.

## In progress
| Task | Owner | Status | Next |
|---|---|---|---|
| 004 Sectors from SEC SIC -> Fama-French 12 (SV-20) | Codex | phase B running | Claude acceptance; feeds task 005 |
| Private datasets (SV-21, ADR-10) | Claude + Codex | private repo `sage-vista-data` created, assets uploading; card 006 queued for Codex | owner creates token + secret `DATA_REPO_TOKEN`; then merge, verify, remove public copies (owner OK) |
| Nightly backtest fix (SV-22, PR #101) | Claude | stuck since 10-12 on the 2025-09-01 holiday; fixed | owner approves the merge (touches the site data pipeline) |
| Weekly forward record (3w-1.9, frozen) | GitHub (daily) | running, 0 signals so far | first signals after Monday 2026-10-19 data; weekly blind page |

## Queued
| Task | Owner | Waits for |
|---|---|---|
| 005 Decision-layer test: sector cap / gaps first / swaps (registered) | Codex | task 004 accepted |
| 006 Private datasets code change | Codex | task 004 finished (one Codex task at a time) |
| HK A/B split + HK exam | Claude / Codex | owner decision ADR-2 |
| Point-in-time bad-data filter (SV-17); report tool + move scripts into repo (SV-8) | Codex | later |

## Paused
Website redesign and Discord digest (ADR-5, ADR-1). The multi-factor ranking stays on the site for now.

## Done recently
- Factor attribution (Claude, 2026-10-17): 3W alpha +4.2%/yr after FF5 + momentum, t 1.88 -> "hint, not significant"; small-cap tilt,
  84% idiosyncratic. Ledger section 17.
- 003 Decision-layer diagnostics: little upside from ordering same-day signals; sector concentration common.
- 002 3W reality check: robust to slot luck, 0.25% costs, $1M capacity; typical drawdown ~26%.
- 001 Portfolio layer: P1/P3 pass, P2 not; not proven.
- Workbench: board ranking, report library, bilingual, live "who is doing what" panel.
- Backup of `work/` (33MB zip) in the owner's Baidu Netdisk; GitHub secret scanning + push protection enabled by the owner.
