"""Frozen 2026 shadow comparison of two trailing-stop rules."""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics

from services.scanner.macd_factor_backtest import adjusted_rows


VARIANTS = ("fixed", "breakeven_1r", "close_trail_8pct_after_1r")


def simulate(entry, stop, target, path, variant):
    risk = entry - stop
    active_stop = stop
    activated = False
    highest_close = None
    window = path[:40]
    for held, bar in enumerate(window, 1):
        op, low, high, close = (float(bar[k]) for k in ("open", "low", "high", "close"))
        if op <= active_stop:
            fill, reason = op, "stop_gap"
        elif low <= active_stop:
            fill, reason = active_stop, "stop"
        elif op >= target or high >= target:
            fill, reason = target, "target"
        else:
            fill = None
        if fill is not None:
            return {"return": fill / entry - 1, "r_multiple": (fill-entry)/risk,
                    "reason": reason, "held": held, "exit_date": bar["date"]}

        # Completed-close information changes tomorrow's stop only.
        if close >= entry + risk:
            activated = True
        if activated:
            highest_close = max(highest_close or close, close)
            if variant == "breakeven_1r":
                active_stop = max(active_stop, entry)
            elif variant == "close_trail_8pct_after_1r":
                active_stop = max(active_stop, highest_close * 0.92)

    if len(path) < 40:
        return None
    fill = float(window[-1]["close"])
    return {"return": fill / entry - 1, "r_multiple": (fill-entry)/risk,
            "reason": "time_40d", "held": 40, "exit_date": window[-1]["date"]}


def metrics(results):
    vals = [x["return"] for x in results]
    wins, losses = [x for x in vals if x > 0], [x for x in vals if x < 0]
    return {
        "samples": len(vals),
        "win_rate_pct": round(100 * len(wins) / len(vals), 2),
        "mean_return_pct": round(100 * statistics.mean(vals), 3),
        "median_return_pct": round(100 * statistics.median(vals), 3),
        "profit_factor": round(sum(wins) / abs(sum(losses)), 3) if losses else None,
        "mean_r": round(statistics.mean(x["r_multiple"] for x in results), 4),
        "stop_rate_pct": round(100 * sum(x["reason"].startswith("stop") for x in results) / len(vals), 2),
        "target_rate_pct": round(100 * sum(x["reason"] == "target" for x in results) / len(vals), 2),
        "mean_holding_sessions": round(statistics.mean(x["held"] for x in results), 2),
    }


def run(ledger_path, cache_dir, out):
    ledger = json.loads(pathlib.Path(ledger_path).read_text())
    cache, grouped = {}, {name: [] for name in VARIANTS}
    missing = immature = 0
    for event in ledger["events"]:
        if not event["signal_date"].startswith("2026-") or "unified_v2" not in event["source_systems"]:
            continue
        test = event.get("evaluation", {}).get("strategy_test") or {}
        if not test.get("executable"):
            continue
        symbol = event["symbol"]
        if symbol not in cache:
            path = pathlib.Path(cache_dir) / f"{symbol}.json"
            cache[symbol] = adjusted_rows(json.loads(path.read_text())) if path.exists() else []
        rows = cache[symbol]
        idx = next((i for i, row in enumerate(rows) if row.get("date") == event["signal_date"]), None)
        if idx is None:
            missing += 1
            continue
        path = rows[idx + 1:]
        if len(path) < 40:
            immature += 1
            continue
        common = {"event_id": event["event_id"], "entry_date": path[0]["date"]}
        for variant in VARIANTS:
            result = simulate(float(test["entry"]), float(test["stop"]), float(test["target"]), path, variant)
            grouped[variant].append({**common, **result})
    report = {
        "experiment_id": "trailing-stop-v0.1.0-2026-08-29",
        "status": "completed_research_only",
        "coverage": {"year": 2026, "missing_price_path": missing, "immature_40d": immature},
        "rules": {"activation": "completed close >= original entry + 1R; new stop effective next session",
                  "fixed": "original support/cap stop",
                  "breakeven_1r": "stop raised to entry",
                  "close_trail_8pct_after_1r": "stop raised to 92% of highest completed close",
                  "common": "original fixed 2R target; 40 sessions; gap-aware; stop-first"},
        "metrics": {name: metrics(rows) for name, rows in grouped.items()},
        "drawdown_note": "Portfolio maximum drawdown is unavailable until a non-overlapping portfolio sizing and capital allocation rule is frozen.",
    }
    base = report["metrics"]["fixed"]
    report["deltas_vs_fixed"] = {name: {k: round(value - base[k], 3) for k, value in vals.items()
        if isinstance(value, (int, float)) and isinstance(base.get(k), (int, float))}
        for name, vals in report["metrics"].items() if name != "fixed"}
    pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--ledger", default="public/opportunity-ledger.json")
    p.add_argument("--cache-dir", default="work/eodhd-cache")
    p.add_argument("--out", default="research/backtest/output/trailing-stop-v1-2026.json")
    a = p.parse_args()
    print(json.dumps(run(a.ledger, a.cache_dir, a.out)["metrics"], indent=2))
