# data-fresh-universe-v2

Plain-language report written by the research lab on 2026-10-13. Every number comes from `result.json` in this folder.

## The question

Same list as data-fresh-universe-v1, with the failed downloads retried and their reasons recorded, and the $5 floor judged on the unadjusted close (v1 judged the split-adjusted close, which drops the early years of stocks that later split). Engineering check: lists and counts only, no returns.

## What the lab found

- Provider lists (primary-exchange common stocks): 6079 listed, 16619 delisted, 0 tickers in both (left out).
- Candidates after leaving out the 1228 stocks already in universe-1985-v1: 21503.
- Downloaded 18151, failed 3352 (15.6%): no history at the provider 3352, errors 0 (0.0%).
- Price floor on the unadjusted close.
- Kept (at least 60 sessions with close >= $5 and >= $10M traded, 2005-01-01 to 2025-06-30): **5500**, in 4 shards.

| Shard | Stocks |
|---|---|
| `research/lab/universes/fresh-2005-2025-v2-a.txt` | 1500 |
| `research/lab/universes/fresh-2005-2025-v2-b.txt` | 1500 |
| `research/lab/universes/fresh-2005-2025-v2-c.txt` | 1500 |
| `research/lab/universes/fresh-2005-2025-v2-d.txt` | 1000 |

**Passed: yes** (download errors at most 2% after a retry, at least 1000 stocks kept).
