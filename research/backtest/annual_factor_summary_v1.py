"""Create a compact permanent annual summary from weekly Unified V2 checkpoints."""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics

from services.scanner.macd_factor_backtest import adjusted_rows
from services.scanner.support_risk import executable_stop, simulate_execution
from research.backtest.trailing_stop_v1 import simulate as simulate_trailing

HORIZONS = (5, 20, 40, 100)


def _metric(values):
    values = [value for value in values if value is not None]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    return {
        "samples": len(values),
        "win_rate_pct": round(100 * len(wins) / len(values), 2) if values else None,
        "mean_return_pct": round(100 * statistics.mean(values), 3) if values else None,
        "median_return_pct": round(100 * statistics.median(values), 3) if values else None,
        "profit_factor": round(sum(wins) / abs(sum(losses)), 3) if losses else None,
        "mean_net_20bps_pct": round(100 * statistics.mean(values) - .20, 3) if values else None,
        "mean_net_50bps_pct": round(100 * statistics.mean(values) - .50, 3) if values else None,
    }


def _load_prices(cache_dir):
    cache = {}
    def load(symbol):
        if symbol not in cache:
            path = pathlib.Path(cache_dir) / f"{symbol}.json"
            cache[symbol] = adjusted_rows(json.loads(path.read_text())) if path.exists() else []
        return cache[symbol]
    return load


def _outcomes(load, symbol, signal_date):
    rows = load(symbol)
    index = next((i for i, row in enumerate(rows) if row.get("date") == signal_date), None)
    if index is None or index + 1 >= len(rows):
        return None, [], {str(h): None for h in HORIZONS}
    path = rows[index + 1:]
    entry = float(path[0]["open"])
    returns = {str(h): float(path[h - 1]["close"]) / entry - 1 if len(path) >= h else None for h in HORIZONS}
    return entry, path, returns


def _exit_metric(rows):
    return _metric([row.get("return") for row in rows]) | {
        "mean_r": round(statistics.mean(row["r_multiple"] for row in rows), 4) if rows else None,
        "stop_rate_pct": round(100 * sum(str(row.get("exit_reason", row.get("reason", ""))).startswith("stop") for row in rows) / len(rows), 2) if rows else None,
        "target_rate_pct": round(100 * sum(row.get("exit_reason", row.get("reason")) == "target" for row in rows) / len(rows), 2) if rows else None,
    }


def run(parts_dir, cache_dir, year, out):
    year = int(str(year)[:4])
    paths = sorted(pathlib.Path(parts_dir).glob("*.json"))
    reports = [json.loads(path.read_text()) for path in paths]
    days = sorted((day for report in reports for day in report.get("days", [])), key=lambda x: x["date"])
    if not days:
        raise RuntimeError(f"No completed sessions for {year}")
    load = _load_prices(cache_dir)
    events, ranking_events = [], []
    for day in days:
        for candidate in day.get("candidate_pool", []):
            entry, price_path, returns = _outcomes(load, candidate["symbol"], day["date"])
            if entry is not None:
                events.append({"symbol":candidate["symbol"],"date":day["date"],"factors":candidate.get("hit_factor_ids",[]),"returns":returns})
        for candidate in day.get("ranking", []):
            entry, price_path, returns = _outcomes(load, candidate["symbol"], day["date"])
            if entry is not None:
                ranking_events.append((day["date"], candidate, entry, price_path))

    baseline = {str(h): _metric([event["returns"][str(h)] for event in events]) for h in HORIZONS}
    factor_ids = sorted({factor for event in events for factor in event["factors"]})
    factors = []
    for factor in factor_ids:
        hit = [event for event in events if factor in event["factors"]]
        miss = [event for event in events if factor not in event["factors"]]
        horizons = {}
        for horizon in HORIZONS:
            hm = _metric([event["returns"][str(horizon)] for event in hit])
            mm = _metric([event["returns"][str(horizon)] for event in miss])
            horizons[str(horizon)] = {"hit":hm,"non_hit":mm,"delta_win_rate_pct":round(hm["win_rate_pct"]-mm["win_rate_pct"],3) if hm["win_rate_pct"] is not None and mm["win_rate_pct"] is not None else None,"delta_mean_return_pct":round(hm["mean_return_pct"]-mm["mean_return_pct"],3) if hm["mean_return_pct"] is not None and mm["mean_return_pct"] is not None else None}
        factors.append({"factor_id":factor,"horizons":horizons})

    exits = {"fixed":[],"close_trail_8pct_after_1r":[]}
    for signal_date, candidate, entry, price_path in ranking_events:
        plan = executable_stop(entry, candidate.get("support_plan") or {})
        if not plan.get("executable") or len(price_path) < 40:
            continue
        fixed = simulate_execution(entry, candidate.get("support_plan") or {}, price_path)
        if fixed.get("status") == "resolved":
            exits["fixed"].append(fixed)
        trail = simulate_trailing(entry, float(plan["stop"]), float(plan["target"]), price_path, "close_trail_8pct_after_1r")
        if trail:
            exits["close_trail_8pct_after_1r"].append(trail)

    report = {
        "schema_version":"annual-factor-summary-v1.0.0",
        "year":int(year),
        "future_data_used_for_selection":False,
        "market_and_industry_mixed_into_technical_factor_test":False,
        "event_gate":"exact completed daily MACD bullish cross",
        "coverage":{"start":days[0]["date"],"end":days[-1]["date"],"sessions":len(days),"weekly_checkpoints":len(paths),"all_candidates":len(events),"ranked_execution_events":len(ranking_events)},
        "baseline":baseline,
        "factors":factors,
        "exit_comparison":{key:_exit_metric(value) for key,value in exits.items()},
        "limitations":["overlapping signals are not independent","historical listing and delisting coverage remains partial","daily OHLCV uses conservative stop-first ordering","annual results are evidence inputs, not production weight changes"],
    }
    target = pathlib.Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--parts-dir", required=True)
    parser.add_argument("--cache-dir", default="work/eodhd-cache")
    parser.add_argument("--year", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = run(args.parts_dir, args.cache_dir, args.year, args.out)
    print(json.dumps(result["coverage"], ensure_ascii=False))
