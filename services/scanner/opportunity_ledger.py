"""Build one compact ledger for historical replay and production forward tests.

Selection-time fields and later outcomes are deliberately separated.  A row is
never removed because it lost its score, left a ranking, or later lost money.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import statistics
from datetime import datetime, timezone

from .macd_factor_backtest import adjusted_rows


SCHEMA_VERSION = "opportunity-ledger-v1.0.0"
HORIZONS = (1, 5, 10, 20, 40, 60, 100)
DEFAULT_UNIFIED = pathlib.Path("public/unified-v2-rankings.json")
DEFAULT_FORWARD = pathlib.Path("public/signal-history.json")
DEFAULT_OUT = pathlib.Path("public/opportunity-ledger.json")
DEFAULT_CACHE = pathlib.Path("work/eodhd-cache")


def _cached_loader(cache_dir):
    cache = {}

    def load(symbol):
        if symbol not in cache:
            path = pathlib.Path(cache_dir) / f"{symbol}.json"
            cache[symbol] = adjusted_rows(json.loads(path.read_text())) if path.exists() else []
        return cache[symbol]

    return load


def _evaluation(symbol, signal_date, loader):
    try:
        rows = [row for row in loader(symbol) if row.get("date") and row["date"] >= signal_date]
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        rows = []
    signal_index = next((i for i, row in enumerate(rows) if row["date"] == signal_date), None)
    empty = {"entry_date": None, "entry_price": None, "elapsed_sessions": 0, "returns": {str(h): None for h in HORIZONS}, "mfe": None, "mae": None, "status": "data_unavailable"}
    if signal_index is None:
        return empty
    elapsed = rows[signal_index + 1 :]
    if not elapsed:
        return {**empty, "status": "pending"}
    entry = float(elapsed[0]["open"])
    returns = {str(h): round(float(elapsed[h - 1]["close"]) / entry - 1, 8) if len(elapsed) >= h else None for h in HORIZONS}
    window = elapsed[: max(HORIZONS)]
    return {
        "entry_date": elapsed[0]["date"],
        "entry_price": round(entry, 6),
        "elapsed_sessions": len(elapsed),
        "returns": returns,
        "mfe": round(max(float(row["high"]) for row in window) / entry - 1, 8),
        "mae": round(min(float(row["low"]) for row in window) / entry - 1, 8),
        "status": "matured" if len(elapsed) >= max(HORIZONS) else "observing",
    }


def _v2_event(day, row, loader, model_version):
    ledger = row.get("factor_ledger", [])
    rare_symbols = {x["symbol"] for x in day.get("rare_opportunities", [])} or {x["symbol"] for x in day.get("ranking", [])[:5] if x.get("final_priority", 0) >= 9}
    return {
        "event_id": f"V2-{row['symbol']}-{day['date']}",
        "symbol": row["symbol"],
        "signal_date": day["date"],
        "origins": ["historical_replay"],
        "source_systems": ["unified_v2"],
        "selection": {
            "model_version": model_version,
            "rank": row.get("rank"),
            "signal_price": row.get("price"),
            "technical_score": row.get("technical_score"),
            "industry_adjustment": row.get("industry_adjustment"),
            "market_adjustment": row.get("market_adjustment"),
            "final_priority": row.get("final_priority"),
            "rare_selected": row["symbol"] in rare_symbols,
            "score_equation": row.get("score_equation"),
            "reasons": row.get("reasons", []),
            "scored_factor_ids": [x["factor_id"] for x in ledger if x.get("points", 0) > 0],
            "risk_factor_ids": [x["factor_id"] for x in ledger if x.get("points", 0) < 0],
            "observed_factor_ids": [x["factor_id"] for x in ledger if x.get("hit") and x.get("points", 0) == 0],
            "market": day.get("market"),
            "industry_states": row.get("industry_states", []),
        },
        "production_forward": None,
        "evaluation": _evaluation(row["symbol"], day["date"], loader),
    }


def _legacy_event(case):
    technical = case.get("signal_time_snapshot", {}).get("technical", {})
    multifactor = case.get("signal_time_snapshot", {}).get("multi_factor", {})
    forward = case.get("forward", {})
    returns = {str(h): forward.get("returns", {}).get(str(h)) for h in HORIZONS}
    def factor_ids(items):
        result = []
        for item in items or []:
            factor_id = item.get("factor_id") if isinstance(item, dict) else str(item)
            if factor_id and (isinstance(item, dict) or "." in factor_id):
                result.append(factor_id)
        return result

    market = case.get("signal_time_snapshot", {}).get("market", {}) or {}
    temperature = market.get("market_temperature", {}) or {}
    compact_market = {"state": temperature.get("state"), "score": temperature.get("score"), "as_of": market.get("as_of")}

    return {
        "event_id": case["signal_id"],
        "symbol": case["symbol"],
        "signal_date": case["first_seen_date"],
        "origins": ["production_forward"],
        "source_systems": case.get("source_systems", []),
        "selection": {
            "model_version": case.get("product_version"),
            "rank": technical.get("tracker_rank"),
            "signal_price": None,
            "technical_score": technical.get("technical_score"),
            "industry_adjustment": None,
            "market_adjustment": None,
            "final_priority": multifactor.get("experimental_observational_score"),
            "rare_selected": False,
            "score_equation": None,
            "reasons": [],
            "scored_factor_ids": factor_ids(multifactor.get("score_contributions", [])),
            "risk_factor_ids": factor_ids(multifactor.get("risks", [])),
            "observed_factor_ids": factor_ids(multifactor.get("non_scoring_evidence", [])),
            "market": compact_market,
            "industry_states": [x.get("state") for x in case.get("signal_time_snapshot", {}).get("industry", {}).get("themes", []) if x.get("state")],
        },
        "production_forward": {
            "lifecycle": case.get("lifecycle"),
            "current_status": case.get("latest_current_status"),
            "last_seen_date": case.get("last_seen_date"),
        },
        "evaluation": {
            "entry_date": case.get("entry", {}).get("date"),
            "entry_price": case.get("entry", {}).get("price"),
            "elapsed_sessions": forward.get("elapsed_sessions", 0),
            "returns": returns,
            "mfe": forward.get("mfe"),
            "mae": forward.get("mae"),
            "status": forward.get("status", "pending"),
        },
    }


def _merge_event(v2, production):
    result = {**v2}
    result["origins"] = sorted(set(v2["origins"] + production["origins"]))
    result["source_systems"] = sorted(set(v2["source_systems"] + production["source_systems"]))
    result["production_forward"] = production["production_forward"]
    if production["evaluation"].get("entry_date"):
        result["evaluation"] = production["evaluation"]
    return result


def _horizon_metrics(events, horizon):
    values = [x["evaluation"]["returns"].get(str(horizon)) for x in events]
    values = [x for x in values if x is not None]
    return {
        "samples": len(values),
        "win_rate_pct": round(sum(x > 0 for x in values) / len(values) * 100, 2) if values else None,
        "mean_return_pct": round(statistics.mean(values) * 100, 3) if values else None,
        "median_return_pct": round(statistics.median(values) * 100, 3) if values else None,
    }


def build(unified, forward, loader):
    by_key = {}
    for day in unified.get("days", []):
        for row in day.get("ranking", []):
            event = _v2_event(day, row, loader, unified.get("version"))
            by_key[(event["symbol"], event["signal_date"])] = event
    for case in forward.get("cases", []):
        event = _legacy_event(case)
        key = (event["symbol"], event["signal_date"])
        by_key[key] = _merge_event(by_key[key], event) if key in by_key else event
    events = sorted(by_key.values(), key=lambda x: (x["signal_date"], x["symbol"], x["event_id"]))
    dates = [x["signal_date"] for x in events]
    as_of = max([unified.get("coverage", {}).get("end") or "", forward.get("as_of") or ""])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of,
        "selection_future_data_used": False,
        "entry_convention": "signal at completed close; evaluate from next adjusted open",
        "ranking_policy": "selection-time scores only; later outcomes never change historical rank",
        "retention_policy": "append all published V2 rankings and production alerts; never delete losers, dropped names, or expired factors",
        "coverage": {"first": min(dates) if dates else None, "last": max(dates) if dates else None, "events": len(events)},
        "summary": {
            "unified_v2_events": sum("unified_v2" in x["source_systems"] for x in events),
            "production_forward_events": sum("production_forward" in x["origins"] for x in events),
            "pending_or_observing": sum(x["evaluation"]["status"] in {"pending", "observing", "data_unavailable"} for x in events),
            "by_horizon": {str(h): _horizon_metrics(events, h) for h in HORIZONS},
        },
        "limitations": [
            "Consecutive daily rankings can contain overlapping signals and are not independent trades.",
            "These are next-open forward returns; stop-loss, take-profit, costs and capital constraints are evaluated in separate strategy experiments.",
            "Historical stock-universe and delisting coverage remain incomplete and must be reported before promotion to production weights.",
        ],
        "events": events,
    }
    payload["content_hash"] = hashlib.sha256(json.dumps({k: v for k, v in payload.items() if k not in {"generated_at", "content_hash"}}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    validate(payload)
    return payload


def validate(payload):
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("selection_future_data_used") is not False:
        raise ValueError("Opportunity ledger schema or look-ahead audit failed")
    events = payload.get("events", [])
    ids = [x["event_id"] for x in events]
    keys = [(x["symbol"], x["signal_date"]) for x in events]
    if len(ids) != len(set(ids)) or len(keys) != len(set(keys)):
        raise ValueError("Duplicate opportunity event")
    if any(x["signal_date"] > payload["as_of"] for x in events):
        raise ValueError("Future signal in opportunity ledger")
    return True


def run(unified_path=DEFAULT_UNIFIED, forward_path=DEFAULT_FORWARD, out=DEFAULT_OUT, cache_dir=DEFAULT_CACHE):
    unified = json.loads(pathlib.Path(unified_path).read_text())
    forward = json.loads(pathlib.Path(forward_path).read_text())
    payload = build(unified, forward, _cached_loader(cache_dir))
    pathlib.Path(out).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--unified", default=str(DEFAULT_UNIFIED))
    parser.add_argument("--forward", default=str(DEFAULT_FORWARD))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    args = parser.parse_args()
    report = run(args.unified, args.forward, args.out, args.cache_dir)
    print(json.dumps({"as_of": report["as_of"], "coverage": report["coverage"], "summary": report["summary"]}, ensure_ascii=False))
