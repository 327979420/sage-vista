"""Find the stocks for a wider, unseen universe (engineering check; no returns are computed).

Every US common stock the provider lists on a primary exchange, listed today or delisted, is downloaded once and kept if it met the
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


def candidates(listed, delisted, exclude):
    """Primary-exchange common stocks, without reused tickers or already-known symbols, in a fixed order."""
    common = lambda rows: {x["Code"] for x in rows if x.get("Type") == "Common Stock" and x.get("Exchange") in PRIMARY and x.get("Code")}
    live, gone = common(listed), common(delisted)
    reused = live & gone
    return sorted((live | gone) - reused - set(exclude)), {"listed": len(live), "delisted": len(gone), "reused": len(reused)}


def qualifies(rows, window, pool):
    """Sessions inside the window that meet the pool floor, and whether the stock had enough of them."""
    start, end = window
    good = sum(1 for r in rows if start <= r["date"] <= end and r["close"] >= pool["min_close"] and r["close"] * r["volume"] >= pool["min_dollar_volume"])
    return good


def screen(symbols, fetch, window, pool, min_sessions, workers=6):
    """Download each symbol once (in parallel), keep the ones with at least `min_sessions` pool sessions; failures are counted."""
    def one(symbol):
        try:
            rows = adjusted_rows(fetch(symbol))
        except Exception:
            return symbol, None
        if not rows:
            return symbol, None
        return symbol, {"good_sessions": qualifies(rows, window, pool), "first": rows[0]["date"], "last": rows[-1]["date"], "bars": len(rows)}
    stats, failed = {}, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for symbol, info in ex.map(one, symbols):
            if info is None:
                failed.append(symbol)
            else:
                stats[symbol] = info
    kept = sorted(s for s, info in stats.items() if info["good_sessions"] >= min_sessions)
    return kept, stats, sorted(failed)


def shards(symbols, size):
    return [symbols[i:i + size] for i in range(0, len(symbols), size)]


def run(spec, data, dataset_entry, root, listed=None, delisted=None, fetch=None):
    if fetch is None:
        from services.scanner.eodhd import get, symbols
        listed, delisted = symbols(False), symbols(True)
        fetch = lambda s: get(f"eod/{s}.US", **{"from": spec["fetch_start"], "period": "d", "_attempts": 3})
    names, counts = candidates(listed, delisted, data["prices"].keys())
    kept, stats, failed = screen(names, fetch, spec["window"], spec["pool"], spec["min_sessions"], spec.get("workers", 4))
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
    return {"kind": "screen", "spec_id": spec["id"], "experiment_id": spec["experiment_id"], "group": spec["group"], "question": spec["question"],
            "dataset": {k: dataset_entry[k] for k in ("dataset_id", "asset", "sha256", "symbols")}, "window": spec["window"], "pool": spec["pool"],
            "min_sessions": spec["min_sessions"], "provider_counts": counts, "candidates": len(names), "downloaded": len(stats), "failed": len(failed),
            "failed_share": round(fail_share, 4), "kept": len(kept), "shards": files, "first_bar_year_of_kept": dict(sorted(by_year.items())),
            "criteria": crit, "passed": fail_share <= crit["max_failed_share"] and len(kept) >= crit["min_kept"], "champion": None}, stats, failed


def render(result):
    lines = [f"# {result['spec_id']}", "", f"Plain-language report written by the research lab on {(result.get('completed_at') or '—')[:10]}. "
             "Every number comes from `result.json` in this folder.", "", "## The question", "", result["question"], "", "## What the lab found", "",
             f"- Provider lists (primary-exchange common stocks): {result['provider_counts']['listed']} listed, {result['provider_counts']['delisted']} delisted, "
             f"{result['provider_counts']['reused']} tickers in both (left out).",
             f"- Candidates after leaving out the {result['dataset']['symbols']} stocks already in {result['dataset']['dataset_id']}: {result['candidates']}.",
             f"- Downloaded {result['downloaded']}, failed {result['failed']} ({result['failed_share'] * 100:.1f}%).",
             f"- Kept (at least {result['min_sessions']} sessions with close >= ${result['pool']['min_close']:.0f} and >= ${result['pool']['min_dollar_volume'] / 1e6:.0f}M traded, "
             f"{result['window'][0]} to {result['window'][1]}): **{result['kept']}**, in {len(result['shards'])} shards.",
             "", "| Shard | Stocks |", "|---|---|", *[f"| `{x['file']}` | {x['symbols']} |" for x in result["shards"]],
             "", f"**Passed: {'yes' if result['passed'] else 'no'}** (failed downloads at most {result['criteria']['max_failed_share'] * 100:.0f}%, "
             f"at least {result['criteria']['min_kept']} stocks kept)."]
    return "\n".join(lines) + "\n"
