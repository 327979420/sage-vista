# data-fresh-universe-v1

Plain-language report written by the research lab on 2026-10-13. Every number comes from `result.json` in this folder.

## The question

Which US common stocks, listed today or delisted, met the research pool's floor often enough in 2005 to mid-2025 to belong to a wider universe that no rule has seen? (Engineering check: lists and counts only, no returns.)

## What the lab found

- Provider lists (primary-exchange common stocks): 6079 listed, 16615 delisted, 0 tickers in both (left out).
- Candidates after leaving out the 1228 stocks already in universe-1985-v1: 21499.
- Downloaded 18147, failed 3352 (15.6%).
- Kept (at least 60 sessions with close >= $5 and >= $10M traded, 2005-01-01 to 2025-06-30): **5743**, in 4 shards.

| Shard | Stocks |
|---|---|
| `research/lab/universes/fresh-2005-2025-v1-a.txt` | 1500 |
| `research/lab/universes/fresh-2005-2025-v1-b.txt` | 1500 |
| `research/lab/universes/fresh-2005-2025-v1-c.txt` | 1500 |
| `research/lab/universes/fresh-2005-2025-v1-d.txt` | 1243 |

**Passed: no** (failed downloads at most 10%, at least 1000 stocks kept).
