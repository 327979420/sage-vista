# Task 009: sector-basket US portfolio with 3W stocks replacing ETF slices

Read `tasks/README.md` first. Owner request (2026-10-17). Pre-registered in ledger section 17 ("行业篮子").

## Idea
3W alone keeps ~50% cash. A sector basket keeps the money invested by sector and lets 3W signals pick stocks inside each sector.

## Data
Sector ETFs from dataset `sector-etf-1998-to-2026-10-v1` (XLB XLE XLF XLI XLK XLP XLU XLV XLY SPY). 3W candidates:
`work/v3w/w3_cands.json` (same 571, entry/exit fills as today). Industries: `data/industry/ff12-sic-v1.json` (status assigned).
Map FF12 -> sleeve: NoDur XLP, Durbl XLY, Shops XLY, Manuf XLI, Enrgy XLE, Chems XLB, BusEq XLK, Telcm XLK, Utils XLU, Hlth XLV,
Money XLF, Other SPY, UNKNOWN SPY. Period 2005-01-03 .. 2025-06-30. Start $100,000. Cost 0.1% per side on every ETF and stock trade.

## Portfolios (fixed; do not tune)
- SPY: buy and hold.
- EQ-SECT: 10 sleeves (9 sector ETFs + SPY) at 10% each, ETFs only, rebalanced to 10% each at month end (trade next session).
- 3W: the task 002 baseline account (unchanged).
- BASKET: EQ-SECT, plus 3W stocks. A 3W candidate enters on its fill date if its sleeve holds fewer than 2 stocks: position =
  3W sizing (2% of total equity at risk to the stop, max 20% of total) but never more than the sleeve's ETF value; the stock is
  bought with money from selling that sleeve's ETF. When the trade exits (its own fills), proceeds buy that sleeve's ETF back.
  If the sleeve already holds 2 stocks the signal is skipped. Never sell a stock to make room. Month-end rebalancing only moves ETF
  money between sleeves (stocks are never trimmed); a sleeve whose stocks exceed 10% simply holds no ETF.
- BASKET-SIZE: as BASKET, but the 2 slots are typed: 1 "large" slot (stock's ADV20 percentile >= 70 in the previous session's
  eligible pool, as computed in task 003) and 1 "other" slot (any size). A large stock may use either free slot; others only "other".
All decisions use data up to the previous close; trades at the fill prices in the cache (stocks) or next-session close (ETFs).

## Evaluation (pre-registered)
BASKET and BASKET-SIZE under the same 200 random orderings as task 002 (orderings only matter for same-day competition).
Report P10/P50/P90 of CAGR, Sharpe, max drawdown, decade CAGRs, average invested share, average stocks held, skips by reason; and
SPY / EQ-SECT / 3W single values. Verdict: a basket version is "useful" if its median Sharpe >= EQ-SECT Sharpe + 0.05, its median
CAGR in both decades >= EQ-SECT's, and its median max drawdown <= EQ-SECT's + 2 pp.

## Deliverables / forbidden
Engine in a new module `research/lab/basket.py` with unit tests in `tests/test_basket.py` (synthetic data only; check: ETF money is
conserved, sleeve cap respected, no stock sold to make room, costs charged once per trade, no look-ahead). Script
`work/v3w/sector_basket.py` + `.log`, report `work/reports/sector-basket-v1.{json,html}` (simple Chinese, inline SVG, no pre-2005
data shown) and codex report with Concerns. Same data boundary as task 002. No tuning or extra variants, no commits, no network.
