# Task 004: industries for every 3W stock from SEC SIC codes (Fama-French 12), phase A = matching

Read `tasks/README.md` first. Owner decision ADR-9 (2026-10-17): use SEC SIC codes mapped to Ken French's 12 industries; ETF
similarity only as a flagged fallback. Pre-registered in ledger section 17 ("行业数据·SEC").

## Inputs (already downloaded by Claude; offline; all in `work/data/sec-2026-10-16/`, checksums in SHA256SUMS)
- `cik-lookup-data.txt`: every EDGAR entity name ever, `NAME:CIK:` per line (1.06M lines, includes former names).
- `company_tickers.json`: current ticker -> CIK.
- `us-names.json`: EODHD US symbol lists `listed` / `delisted` with Code, Name, Exchange, Type, Isin.
- `Siccodes12.txt`: Ken French SIC ranges -> 12 industries (12 = "Other" for anything not listed).
- The 3W stocks: unique symbols in `work/v3w/w3_cands.json` (497). Current sector snapshot: `data/industry/nasdaq-industry-2026-08-25.json`.

## Phase A (now): symbol -> CIK
1. For each of the 497 symbols: if the symbol (without a `_old`-style suffix) is in `company_tickers.json` AND the EODHD name
   matches that CIK's name reasonably, take that CIK ("ticker" match). Otherwise match the EODHD name against `cik-lookup-data.txt`.
2. Name matching: normalise (upper case, drop punctuation and suffixes INC, CORP, CORPORATION, CO, LTD, LLC, PLC, HOLDINGS, GROUP,
   THE, CLASS A/B, /DE/ style state tags). Exact normalised match first; otherwise the best fuzzy match with a similarity score
   (difflib ratio is fine). Keep up to 3 candidate CIKs per symbol with scores.
3. Decide per symbol: `matched` (one CIK, exact normalised or score >= 0.92 and clearly ahead of the 2nd), `ambiguous` (several
   plausible), `unmatched`. Never force a match.
4. Write `work/v3w/sic_phaseA.json` (per symbol: name, method, chosen CIK or null, candidates with scores, status) and
   `work/v3w/sic_ciks.txt` = every CIK Claude must fetch (chosen + candidates of ambiguous ones), one per line, zero-padded to 10.

STOP after phase A and report counts (matched by ticker / by exact name / by fuzzy / ambiguous / unmatched), 15 random matched
examples (symbol, EODHD name, SEC name) for a human sanity check, and your Concerns. Claude then fetches SIC for `sic_ciks.txt`
(network) and gives you phase B.

## Answer to Codex (2026-10-17): match thresholds
- Fuzzy: a candidate is plausible at score >= 0.92. `matched` only if the best CIK is >= 0.92 AND leads the best *different* CIK by
  >= 0.05; otherwise `ambiguous` (keep up to 3 candidates). Below 0.92 everywhere -> `unmatched`.
- Ticker route (ticker reuse risk): accept the `company_tickers.json` CIK only if the normalised EODHD name vs that CIK's SEC
  name(s) in `cik-lookup-data.txt` scores >= 0.80; otherwise ignore the ticker hit and use the name route above.
- Exact normalised name hitting one CIK = `matched`; hitting several CIKs = `ambiguous`.

## Scope extended by the owner (2026-10-17): all US stocks
Match every US symbol in the union of `research/lab/universes/fresh-*.txt` and `observation-2005-2025-v1.txt` (about 6.7k unique),
plus the 497 3W symbols (most are already inside). Do NOT use `hk-*.txt`. Symbols and company names only: never load or read any
price file (the 1985-2004 and HK price data stay locked). Report the 3W 497 and the full set separately; phase B's pass rule
applies to the 497, the full set is reported for coverage only.

## Phase B (after Claude's fetch; for information now)
SIC -> FF12 via `Siccodes12.txt`; validation against the Nasdaq snapshot with this crosswalk fixed in advance:
Health Care->Hlth; Technology->BusEq; Finance->Money; Utilities->Utils; Energy->Enrgy; Telecommunications->Telcm;
Consumer Staples->NoDur; Basic Materials->Chems or Manuf; Industrials->Manuf or Other; Consumer Discretionary->Durbl, Shops or
Other; Real Estate->Money or Other; Miscellaneous->not compared. Pass if >= 85% of the 497 symbols get an FF12 industry from SIC and
agreement on comparable known symbols is >= 75%.

## Forbidden
No network, no commits, no changes outside `work/` and `tasks/`. Do not touch prices, frozen code or locked data.
