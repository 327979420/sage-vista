# Sage Vista - the baton (read first, update last)

The owner switches between Claude and Codex. **Whoever works on Sage Vista reads this file first and updates it before stopping.**
Keep it short and current; history belongs in `docs/COLLAB-LOG.md` and ledger section 17. Owner's live board (Claude updates it):
https://claude.ai/artifact/BdbVybVXiShDN5MtaqtVUQ - Codex cannot open it, so this file is the shared truth.

Last updated: 2026-10-19 by Claude.

## Mode
Run-and-record (ADR-16, 2026-10-19). 3W rule 3w-1.9 is frozen and runs mechanically. No new rule mining on old data unless the owner
explicitly asks. Paper account = sector trend core 50% + 3W satellite 50% (in the owner's cockpit). Evidence comes from the forward record.

## In progress (owner / agent / next step)
| Item | Who | Next step |
|---|---|---|
| Weekly routine (SV-52) | Claude, scheduled every Saturday 10:00 Melbourne | first run 2026-10-24: signals, cockpit, review queue, weekly report |
| Month-end rebalance | Claude (in the weekly routine) | decided at the 2026-10-30 close; at current prices XLB and XLP switch from SHY back to ETFs |
| Forward record (3w-1.9) | GitHub, daily | 0 signals so far; next weekly check after the Friday 2026-10-23 close |

## Waiting for review (see docs/REVIEW_QUEUE.md)
(none)

## Open owner decisions
- Delete the public copies of the datasets (SV-21) - needs the owner's explicit OK.
- Portfolio label: drop "候选" for the sector basket? (owner deferred)
- HK group B stays locked; Korea data not downloaded (deferred).

## Recently finished (one line each; details in ledger section 17)
- 2026-10-19 factor scan v1: 0 candidates. Veto rules v1: not useful. Blind test v2 (88): FAIL (d -0.37R). Edge decomposition: 3W's
  +0.23R/trade is mostly market tailwind + rules. Exchange calendars + weekly report generator (task 032).
- 2026-10-18 site: 信号凭证, 前向记录, 形态速览 live; research standard v1 registered.

## Session checklist (both agents)
Start: read this file, `git status`, open PRs (`gh pr list`), `docs/REVIEW_QUEUE.md`.
End: update this file (In progress / Waiting / Decisions / Recently finished), add a review-queue row for finished work, commit on a
branch, never leave uncommitted changes without saying so here.
