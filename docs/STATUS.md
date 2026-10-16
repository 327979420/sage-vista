# Sage Vista status (mirror of the owner's workbench)

Maintained by Claude; the owner's interactive workbench is https://claude.ai/artifact/BdbVybVXiShDN5MtaqtVUQ (Codex cannot open it, so
this file mirrors it). Updated 2026-10-16.

## In progress
| Task | Owner | Status | Next |
|---|---|---|---|
| HK data: list and freeze | Claude | blocked — the lab run finished but no HK list appeared; cause not checked yet | find the cause, fix, rerun; then register A/B split |
| Weekly forward record (3w-1.9, frozen) | GitHub (daily) | running — freeze check passed on CI; 0 signals so far | first signals after Monday 2026-10-19 data; weekly blind page |

## Queued
| Task | Owner | Waits for |
|---|---|---|
| HK exam (frozen 3W, group A once) | Codex | HK data frozen |
| Factor attribution (Fama-French) | Codex | Claude downloads the public factor data |
| One standard report tool; move tournament and fair tests into the repo | Codex | owner's priority call (001 accepted) |

## Paused
- Website redesign (3W home, tutorial, desktop app) — after the tournament / portfolio results decide the site's main feature. The
  multi-factor ranking stays on the site for now (owner's decision).
- Discord daily digest — owner to confirm the new content.

## Waiting for the owner
- Discord digest new content (draft on the workbench).
- HK: split into groups A and B; lock B and HK before 2005.

## Done recently
002 3W reality check accepted 2026-10-16: robust to slot luck, 0.25% costs and $1M capacity; typical drawdown ~26% (24.8% was lucky); 47% of
signals never get a slot -> signal selection is the next 3W optimisation candidate. Owner's direction: optimise US 3W only (ADR-7).
001 Portfolio layer accepted 2026-10-16: P1 (equal) and P3 (inverse vol + 10% vol target) pass the pre-registered test, P2 misses by
0.013 Sharpe in 2005-14; Sharpe ~0.90 vs best single 0.75, drawdown 15-19% vs 28%; not proven (DSR 0.88). Ledger section 17.
Strategy tournament (PR #97); fair tests (PR #94); daily/monthly 3W not adopted (PR #95); 3W frozen as 3w-1.9 and the owner's 207
decisions committed (PR #93).
