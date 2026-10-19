# data-kr-universe-v1

Plain-language report written by the research lab on 2026-10-19. Every number comes from `result.json` in this folder.

## The question

Korea KO + KQ common-stock universe engineering screen; company dedupe before liquidity. No signals or returns.

## What the lab found

- Provider lists (all types; exclusions below): 3915 listed, 776 delisted, 0 tickers in both (left out).
- KO + KQ candidates after metadata exclusions: 2864; US reference symbols are not excluded.
- Downloaded 2789, failed 75 (2.6%): no history at the provider 75, errors 0 (0.0%).
- Price floor on the unadjusted close.
- Kept (at least 60 sessions with close >= KRW 1000 and >= KRW 13000M traded, 2005-01-01 to 2025-06-30): **1531**, in 1 shards.

| Shard | Stocks |
|---|---|
| `research/lab/universes/kr-2005-2025-v1-a.txt` | 1531 |

**Passed: yes** (download errors at most 2% after a retry, at least 300 stocks kept).

## Korea exclusion counts

Counts can overlap; name_matches counts unique listings per substring.
- listed: 3915
- delisted: 776
- reused: 0
- non_common_type: 1361
- 非普通股代码: 209
- 代码格式异常: 67
- excluded_name: 1357
- market_proxy: 1
- name_matches: {'ETF': 902, 'ETN': 80, 'REIT': 39, 'FUND': 20, 'INDEX': 42, 'SPAC': 79, 'ACQUISITION': 167, 'KODEX': 240, 'TIGER': 241, '스팩': 0, '리츠': 0}
- excluded_metadata_union: 1827
- company_duplicates: 8
- unresolved_company: 4
- below_liquidity: 1246

## Review flags only — Claude must review before freezing at STOP 2

PREF, 우, HOLDINGS, 지주 are flags, not exclusions.

| Code | Provider name |
|---|---|
| 000210.KO | DL Holdings CO. LTD. |
| 000230.KO | Ildong Holdings Co Ltd |
| 000700.KO | Eusu Holdings |
| 003380.KQ | Harim Holdings Co. Ltd |
| 005490.KO | POSCO Holdings |
| 007700.KO | F&F Holdings Co. Ltd |
| 012630.KO | HDC Holdings Co Ltd |
| 015860.KO | Iljin Holdings |
| 028080.KQ | Humax Holdings Co. Ltd |
| 030530.KQ | Wonik Holdings Co. Ltd |
| 031980.KQ | PSK HOLDINGS Inc |
| 034730.KO | SK Holdings Co Ltd |
| 035810.KQ | EASY HOLDINGS Co. Ltd |
| 036830.KQ | Soulbrain Holdings Co. Ltd |
| 038870.KQ | EcoBio Holdings Co. Ltd |
| 039020.KQ | Eagon Holdings Co.Ltd |
| 042420.KQ | NEOWIZ HOLDINGS Corporation |
| 051780.KQ | Curo Holdings Co. Ltd |
| 054620.KQ | APS Holdings Corporation |
| 060560.KQ | Home Center Holdings Co.Ltd |
| 060980.KO | Halla Holdings Corp |
| 071050.KO | Korea Investment Holdings Co |
| 078930.KO | GS Holdings |
| 081660.KO | Fila Holdings Corp |
| 084690.KO | Daesang Holdings Co Ltd |
| 117670.KQ | Alpha Holdings Inc |
| 267250.KO | Hyundai Heavy Industries Holdings Co Ltd |
| 900140.KO | LVMC Holdings |
