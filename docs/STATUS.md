# Sage Vista status (mirror of the owner's workbench)

Maintained by Claude; the owner's interactive workbench is https://claude.ai/artifact/BdbVybVXiShDN5MtaqtVUQ (Codex cannot open it, so
this file mirrors it). Updated 2026-10-17. Owner's priority order: factor attribution, then the portfolio decision layer.

## In progress
| Task | Owner | Status | Next |
|---|---|---|---|
| Private datasets (SV-21, ADR-10) | owner | assets in `sage-vista-data` (verified); code merged (#104), switches only once the secret exists | token set and verified 2026-10-17; public copies removed only with owner OK |
| Nightly backtest fix (SV-22, PR #101) | Claude | stuck since 10-12 on the 2025-09-01 holiday; fixed | owner approves the merge (touches the site data pipeline) |
| Weekly forward record (3w-1.9, frozen) | GitHub (daily) | running, 0 signals so far | first signals after Monday 2026-10-19 data; weekly blind page |

## Queued
| Task | Owner | Waits for |
|---|---|---|
| App phase 1 (014 data layer, then pages) | Codex | task 013 accepted |

## Paused
Website redesign and Discord digest (ADR-5, ADR-1). The multi-factor ranking stays on the site for now.

## Done recently
- 2026-10-17 locked-data exam (013, US 1994-2004, once): 3W FAIL (p 0.59, 23 trades; second independent non-confirmation after HK);
  sector trend basket useful (Sharpe 0.50 vs 0.26, DD 18% vs 37%); core+satellite useful (Sharpe 0.60, DD 12%). 1985-2004 is no longer unseen.
- 2026-10-17 overnight: requirements audit (62 groups, none forgotten); sector baskets (3W in basket slots: not useful); sector trend
  basket (Faber 2007): useful (Sharpe 0.78, DD 17%); core+satellite 50/50 with 3W: tie on Sharpe, lower drawdown (14.5%); moomoo AU
  costs (US$0.99/order, FX 0.55%); HK exam group A: FAIL (p 0.089, 14 trades). Codex's review caught 3 bugs in Claude's basket code.
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
