# Sage Vista status (mirror of the owner's workbench)

Maintained by Claude; the owner's interactive workbench is https://claude.ai/artifact/BdbVybVXiShDN5MtaqtVUQ (Codex cannot open it, so
this file mirrors it). Updated 2026-10-17. Owner's priority order: factor attribution, then the portfolio decision layer.

## In progress
| Task | Owner | Status | Next |
|---|---|---|---|
| Private datasets (SV-21, ADR-10) | owner | assets in `sage-vista-data` (verified); code merged (#104), switches only once the secret exists | owner creates token + secret `DATA_REPO_TOKEN`; Claude verifies; public copies removed only with owner OK |
| Nightly backtest fix (SV-22, PR #101) | Claude | stuck since 10-12 on the 2025-09-01 holiday; fixed | owner approves the merge (touches the site data pipeline) |
| Weekly forward record (3w-1.9, frozen) | GitHub (daily) | running, 0 signals so far | first signals after Monday 2026-10-19 data; weekly blind page |

## Queued
| Task | Owner | Waits for |
|---|---|---|
| HK A/B split + HK exam | Claude / Codex | owner decision ADR-2 |
| Move study scripts into the public repo (SV-8) | owner decision | scripts are backed up in the private repo `sage-vista-data/research-work/` |

## Paused
Website redesign and Discord digest (ADR-5, ADR-1). The multi-factor ranking stays on the site for now.

## Done recently
- 004 sectors (FF12 from SEC SIC, `data/industry/ff12-sic-v1.json`); 006 private-datasets code; 007 point-in-time filter check: small
  effect by the pre-set rule, but describe 3W conservatively (~6.3%/yr, Sharpe ~0.62, typical max drawdown ~29%).
- 005 Decision-layer test (2026-10-17): sector cap, gaps-first and swaps all fail; swaps sell future winners. 3W does not need a
  decision layer at its current size (few holdings). Private datasets uploaded to `sage-vista-data` (14 assets, verified).
- Factor attribution (Claude, 2026-10-17): 3W alpha +4.2%/yr after FF5 + momentum, t 1.88 -> "hint, not significant"; small-cap tilt,
  84% idiosyncratic. Ledger section 17.
- 003 Decision-layer diagnostics: little upside from ordering same-day signals; sector concentration common.
- 002 3W reality check: robust to slot luck, 0.25% costs, $1M capacity; typical drawdown ~26%.
- 001 Portfolio layer: P1/P3 pass, P2 not; not proven.
- Workbench: board ranking, report library, bilingual, live "who is doing what" panel.
- Backup of `work/` (33MB zip) in the owner's Baidu Netdisk; GitHub secret scanning + push protection enabled by the owner.
