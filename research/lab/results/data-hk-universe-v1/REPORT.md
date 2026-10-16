# data-hk-universe-v1

Plain-language report written by the research lab on 2026-10-16. Every number comes from `result.json` in this folder.

## The question

Hong Kong market for the overseas exam of the frozen 3W (3w-1.9): every common stock EODHD lists for HK, listed today or delisted, downloaded once and kept if it met an HK version of the research pool (unadjusted close >= HK$1, >= HK$78M traded, about US$10M) on enough sessions in 2005-01..2025-06. Engineering check: lists and counts only, no returns.

## What the lab found

- Provider lists (primary-exchange common stocks): 3515 listed, 636 delisted, 0 tickers in both (left out).
- Candidates after leaving out the 1228 stocks already in universe-1985-v1: 4151.
- Downloaded 4148, failed 3 (0.1%): no history at the provider 3, errors 0 (0.0%).
- Price floor on the unadjusted close.
- Kept (at least 60 sessions with close >= $1 and >= $78M traded, 2005-01-01 to 2025-06-30): **881**, in 1 shards.

| Shard | Stocks |
|---|---|
| `research/lab/universes/hk-2005-2025-v1-a.txt` | 881 |

**Passed: yes** (download errors at most 2% after a retry, at least 300 stocks kept).
