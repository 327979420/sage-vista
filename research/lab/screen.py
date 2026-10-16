"""Find the stocks for a wider, unseen universe (engineering check; no returns are computed).

Every common stock the provider lists (US: on a primary exchange; another market with the spec's "exchange", e.g. HK), listed today or delisted, is downloaded once and kept if it met the
research pool's floor (close >= $5, >= $10M traded) on enough sessions inside the window. Tickers that appear in both the listed and
the delisted lists are left out, because a reused ticker can join two companies' prices (the 2026 EODHD audit's warning); stocks
already in the frozen research universe are left out, so the result has never been seen by any rule. The kept stocks are written
as alphabetical shards small enough for one lab dataset each.
"""
from __future__ import annotations

import concurrent.futures
import pathlib

from services.scanner.macd_factor_backtest import adjusted_rows

PRIMARY = {"NASDAQ", "NYSE", "AMEX", "NYSE MKT", "NYSE ARCA"}


def candidates(listed, delisted, exclude, primary=PRIMARY):
    """Primary-exchange common stocks, without reused tickers or already-known symbols, in a fixed order. `primary` None keeps every
    exchange in the provider's list (non-US lists are per exchange already, e.g. HK)."""
    common = lambda rows: {x["Code"] for x in rows if x.get("Type") == "Common Stock" and (primary is None or x.get("Exchange") in primary) and x.get("Code")}
    live, gone = common(listed), common(delisted)
    reused = live & gone
    return sorted((live | gone) - reused - set(exclude)), {"listed": len(live), "delisted": len(gone), "reused": len(reused)}


def qualifies(rows, window, pool, raw=None):
    """Sessions inside the window that meet the pool floor. With `raw` (the provider's rows, version 2) the $5 floor uses the
    unadjusted close, because a split-adjusted close drops the early years of stocks that later split (a look-ahead); the dollar
    volume uses the adjusted close and the provider's split-adjusted volume, as before."""
    start, end = window
    raw_close = {x["date"]: x.get("close") for x in raw} if raw is not None else None
    good = 0
    for r in rows:
        if not start <= r["date"] <= end:
            continue
        price = raw_close.get(r["date"]) if raw_close is not None else r["close"]
        if price is not None and price >= pool["min_close"] and r["close"] * r["volume"] >= pool["min_dollar_volume"]:
            good += 1
    return good


def screen(symbols, fetch, window, pool, min_sessions, workers=6, raw_floor=False, reasons=None):
    """Download each symbol once (in parallel), keep the ones with at least `min_sessions` pool sessions; failures are counted.
    `reasons` (a dict) receives why each failure happened: the provider's error text or "empty" for no history."""
    def one(symbol):
        try:
            raw = fetch(symbol)
            rows = adjusted_rows(raw)
        except Exception as error:
            return symbol, None, str(error)[:80]
        if not rows:
            return symbol, None, "empty"
        good = qualifies(rows, window, pool, raw if raw_floor else None)
        return symbol, {"good_sessions": good, "first": rows[0]["date"], "last": rows[-1]["date"], "bars": len(rows)}, None
    stats, failed = {}, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for symbol, info, why in ex.map(one, symbols):
            if info is None:
                failed.append(symbol)
                if reasons is not None:
                    reasons[symbol] = why
            else:
                stats[symbol] = info
    kept = sorted(s for s, info in stats.items() if info["good_sessions"] >= min_sessions)
    return kept, stats, sorted(failed)


def shards(symbols, size):
    return [symbols[i:i + size] for i in range(0, len(symbols), size)]


def run(spec, data, dataset_entry, root, listed=None, delisted=None, fetch=None):
    exchange = spec.get("exchange", "US")
    primary = PRIMARY if exchange == "US" else (set(spec["primary_exchanges"]) if spec.get("primary_exchanges") else None)
    if fetch is None:
        from services.scanner.eodhd import get, symbols
        listed, delisted = symbols(False, exchange), symbols(True, exchange)
        fetch = lambda s: get(f"eod/{s}.{exchange}", **{"from": spec["fetch_start"], "period": "d", "_attempts": spec.get("attempts", 3)})
    names, counts = candidates(listed, delisted, data["prices"].keys(), primary)
    reasons = {}
    kept, stats, failed = screen(names, fetch, spec["window"], spec["pool"], spec["min_sessions"], spec.get("workers", 4), spec.get("raw_price_floor", False), reasons)
    if spec.get("retry_failed"):
        # a second, slower pass over the failures; what still fails keeps its reason
        retry_reasons = {}
        k2, s2, failed = screen(failed, fetch, spec["window"], spec["pool"], spec["min_sessions"], 1, spec.get("raw_price_floor", False), retry_reasons)
        stats.update(s2)
        kept = sorted(set(kept) | set(k2))
        reasons = retry_reasons
    files = []
    for k, part in enumerate(shards(kept, spec["shard_size"])):
        path = pathlib.Path(root) / spec["shard_dir"] / f"{spec['shard_prefix']}-{chr(97 + k)}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(part) + "\n")
        files.append({"file": str(path.relative_to(root)), "symbols": len(part)})
    by_year = {}
    for s in kept:
        y = stats[s]["first"][:4]
        by_year[y] = by_year.get(y, 0) + 1
    crit = spec["criteria"]
    fail_share = len(failed) / max(len(names), 1)
    empty = sum(1 for s in failed if reasons.get(s) == "empty")
    errors = len(failed) - empty
    error_share = errors / max(len(names), 1)
    passed = (error_share <= crit["max_error_share"] if "max_error_share" in crit else fail_share <= crit["max_failed_share"]) and len(kept) >= crit["min_kept"]
    return {"kind": "screen", "spec_id": spec["id"], "experiment_id": spec["experiment_id"], "group": spec["group"], "question": spec["question"],
            "dataset": {k: dataset_entry[k] for k in ("dataset_id", "asset", "sha256", "symbols")}, "window": spec["window"], "pool": spec["pool"],
            "min_sessions": spec["min_sessions"], "provider_counts": counts, "candidates": len(names), "downloaded": len(stats), "failed": len(failed),
            "failed_share": round(fail_share, 4), "failed_empty": empty, "failed_errors": errors, "error_share": round(error_share, 4),
            "failed_examples": {s: reasons.get(s) for s in failed[:40]}, "raw_price_floor": bool(spec.get("raw_price_floor")),
            "kept": len(kept), "shards": files, "first_bar_year_of_kept": dict(sorted(by_year.items())),
            "criteria": crit, "passed": passed, "champion": None}, stats, failed


def render(result):
    lines = [f"# {result['spec_id']}", "", f"Plain-language report written by the research lab on {(result.get('completed_at') or '—')[:10]}. "
             "Every number comes from `result.json` in this folder.", "", "## The question", "", result["question"], "", "## What the lab found", "",
             f"- Provider lists (primary-exchange common stocks): {result['provider_counts']['listed']} listed, {result['provider_counts']['delisted']} delisted, "
             f"{result['provider_counts']['reused']} tickers in both (left out).",
             f"- Candidates after leaving out the {result['dataset']['symbols']} stocks already in {result['dataset']['dataset_id']}: {result['candidates']}.",
             f"- Downloaded {result['downloaded']}, failed {result['failed']} ({result['failed_share'] * 100:.1f}%)"
             + (f": no history at the provider {result.get('failed_empty')}, errors {result.get('failed_errors')} ({result.get('error_share', 0) * 100:.1f}%)." if "failed_empty" in result else "."),
             f"- Price floor on the {'unadjusted' if result.get('raw_price_floor') else 'split-adjusted'} close.",
             f"- Kept (at least {result['min_sessions']} sessions with close >= ${result['pool']['min_close']:.0f} and >= ${result['pool']['min_dollar_volume'] / 1e6:.0f}M traded, "
             f"{result['window'][0]} to {result['window'][1]}): **{result['kept']}**, in {len(result['shards'])} shards.",
             "", "| Shard | Stocks |", "|---|---|", *[f"| `{x['file']}` | {x['symbols']} |" for x in result["shards"]],
             "", f"**Passed: {'yes' if result['passed'] else 'no'}** ("
             + (f"download errors at most {result['criteria']['max_error_share'] * 100:.0f}% after a retry" if "max_error_share" in result["criteria"] else f"failed downloads at most {result['criteria']['max_failed_share'] * 100:.0f}%")
             + f", at least {result['criteria']['min_kept']} stocks kept)."]
    return "\n".join(lines) + "\n"
