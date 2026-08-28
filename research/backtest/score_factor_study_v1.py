"""Pre-registered score monotonicity and factor attribution study V1."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import pathlib
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).parents[2]
SOURCE = ROOT / "research/backtest/output/signals.jsonl"
OUT = ROOT / "research/backtest/output/score-factor-study-v1.json"
CHECKPOINTS = ROOT / "research/backtest/output/score-factor-study-v1-weekly.jsonl"
HORIZONS = (5, 20, 40, 100)
PERIODS = (
    ("development", "0000-01-01", "2024-12-31"),
    ("validation_2025", "2025-01-01", "2025-12-31"),
    ("forward_2026", "2026-01-01", "9999-12-31"),
)
FACTOR_MINIMUMS = {"development": 300, "validation_2025": 100}
PAIR_MINIMUMS = {"development": 200, "validation_2025": 75}
FAMILIES = {
    "Fibonacci支撑": "support",
    "EMA支撑": "support",
    "支撑位底部放量": "volume",
    "支撑位看涨吞没": "candle",
    "周线MACD改善": "momentum",
    "三推趋势线突破": "structure",
    "三推突破后回踩确认": "structure",
    "上方未补跳空缺口": "gap_risk",
    "Bullish FVG支撑": "fvg",
}


def period_of(value: str) -> str:
    return next(name for name, lo, hi in PERIODS if lo <= value <= hi)


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    pos = (len(values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return values[lo] if lo == hi else values[lo] + (values[hi] - values[lo]) * (pos - lo)


def trimmed_mean(values, proportion=0.01):
    values = sorted(values)
    if not values:
        return None
    cut = int(len(values) * proportion)
    kept = values[cut:len(values) - cut] if cut and len(values) > 2 * cut else values
    return statistics.fmean(kept)


def metrics(rows, horizon, cost_bps=0):
    values = [row["returns"].get(str(horizon)) for row in rows]
    values = [value - cost_bps / 10_000 for value in values if value is not None]
    if not values:
        return {"samples": 0, "win_rate": None, "median_pct": None, "trimmed_mean_pct": None, "profit_factor": None, "expectancy_pct": None}
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    result = {
        "samples": len(values),
        "win_rate": round(100 * sum(value > 0 for value in values) / len(values), 3),
        "median_pct": round(100 * statistics.median(values), 4),
        "trimmed_mean_pct": round(100 * trimmed_mean(values), 4),
        "profit_factor": round(gains / losses, 4) if losses else None,
        "expectancy_pct": round(100 * statistics.fmean(values), 4),
    }
    if horizon == 40:
        mfe = [row["mfe_40d"] for row in rows if row.get("mfe_40d") is not None]
        mae = [row["mae_40d"] for row in rows if row.get("mae_40d") is not None]
        result["median_mfe_pct"] = round(100 * statistics.median(mfe), 4) if mfe else None
        result["median_mae_pct"] = round(100 * statistics.median(mae), 4) if mae else None
    if cost_bps == 0:
        result["cost_sensitivity"] = {}
        raw = [row["returns"].get(str(horizon)) for row in rows]
        raw = [value for value in raw if value is not None]
        for bps in (20, 50):
            net = [value - bps / 10_000 for value in raw]
            net_gains = sum(value for value in net if value > 0)
            net_losses = -sum(value for value in net if value < 0)
            result["cost_sensitivity"][str(bps)] = {
                "expectancy_pct": round(100 * statistics.fmean(net), 4) if net else None,
                "profit_factor": round(net_gains / net_losses, 4) if net_losses else None,
            }
    return result


def normal_mean_pvalue(a, b):
    if len(a) < 2 or len(b) < 2:
        return 1.0
    variance = statistics.variance(a) / len(a) + statistics.variance(b) / len(b)
    if variance <= 0:
        return 1.0
    z = abs(statistics.fmean(a) - statistics.fmean(b)) / math.sqrt(variance)
    return math.erfc(z / math.sqrt(2))


def bh_adjust(pvalues):
    ordered = sorted(enumerate(pvalues), key=lambda item: item[1])
    result = [1.0] * len(pvalues)
    running = 1.0
    for rank, (index, value) in reversed(list(enumerate(ordered, start=1))):
        running = min(running, value * len(pvalues) / rank)
        result[index] = round(min(1.0, running), 6)
    return result


def load_events(path=SOURCE):
    rows = []
    for line in pathlib.Path(path).read_text().splitlines():
        event = json.loads(line)
        if event.get("status") != "Confirmed" or not event.get("strict_long_trend"):
            continue
        factors = {key: bool(value) for key, value in event.get("factor_states", {}).items() if not key.startswith("layer.")}
        factors.pop("日线MACD近5日金叉", None)
        rows.append({
            "ticker": event["ticker"], "date": event["date"], "period": period_of(event["date"]),
            "score": event.get("multi_factor_total_score", 0), "factors": factors,
            "returns": event.get("forward_returns", {}), "mfe_40d": event.get("mfe_40d"), "mae_40d": event.get("mae_40d"),
        })
    return rows


def deduplicate(rows, calendar_days=56):
    kept, last = [], {}
    for row in sorted(rows, key=lambda value: (value["date"], value["ticker"])):
        current = date.fromisoformat(row["date"])
        if row["ticker"] in last and current < last[row["ticker"]] + timedelta(days=calendar_days):
            continue
        kept.append(row)
        last[row["ticker"]] = current
    return kept


def delta(yes, no, horizon):
    a, b = metrics(yes, horizon), metrics(no, horizon)
    av = [row["returns"].get(str(horizon)) for row in yes if row["returns"].get(str(horizon)) is not None]
    bv = [row["returns"].get(str(horizon)) for row in no if row["returns"].get(str(horizon)) is not None]
    return {
        "with": a, "without": b,
        "delta": {
            "win_rate_pp": round((a["win_rate"] or 0) - (b["win_rate"] or 0), 3),
            "median_pp": round((a["median_pct"] or 0) - (b["median_pct"] or 0), 4),
            "trimmed_mean_pp": round((a["trimmed_mean_pct"] or 0) - (b["trimmed_mean_pct"] or 0), 4),
            "profit_factor": round((a["profit_factor"] or 0) - (b["profit_factor"] or 0), 4),
            "expectancy_pp": round((a["expectancy_pct"] or 0) - (b["expectancy_pct"] or 0), 4),
        },
        "mean_difference_p": round(normal_mean_pvalue(av, bv), 6),
    }


def score_results(rows):
    exact_scores = sorted({row["score"] for row in rows})
    groups = [(f"score_{score}", lambda row, value=score: row["score"] == value) for score in exact_scores]
    groups += [("score_0_2", lambda row: row["score"] <= 2), ("score_3_4", lambda row: 3 <= row["score"] <= 4), ("score_5_plus", lambda row: row["score"] >= 5)]
    result = {}
    for period in [name for name, _, _ in PERIODS]:
        subset = [row for row in rows if row["period"] == period]
        result[period] = {name: {str(h): metrics([row for row in subset if test(row)], h) for h in HORIZONS} for name, test in groups}
    return result


def enrichment(rows, factor, period, horizon):
    subset = [row for row in rows if row["period"] == period and row["returns"].get(str(horizon)) is not None]
    if not subset:
        return {"samples": 0}
    threshold = percentile([row["returns"][str(horizon)] for row in subset], .9)
    groups = {
        "all": subset,
        "winners": [row for row in subset if row["returns"][str(horizon)] > 0],
        "losers": [row for row in subset if row["returns"][str(horizon)] <= 0],
        "top_decile": [row for row in subset if row["returns"][str(horizon)] >= threshold],
        "absolute_10pct": [row for row in subset if row["returns"][str(horizon)] >= .10],
    }
    rates = {name: round(sum(row["factors"].get(factor, False) for row in values) / len(values), 6) if values else None for name, values in groups.items()}
    base = rates["all"]
    return {"samples": len(subset), "top_decile_threshold_pct": round(threshold * 100, 4), "rates": rates,
            "winner_enrichment": round(rates["winners"] / base, 4) if base and rates["winners"] is not None else None,
            "top_decile_enrichment": round(rates["top_decile"] / base, 4) if base and rates["top_decile"] is not None else None}


def factor_results(rows):
    factors = sorted({factor for row in rows for factor in row["factors"]})
    output, pvalues = [], []
    for factor in factors:
        periods = {}
        for period, _, _ in PERIODS:
            subset = [row for row in rows if row["period"] == period]
            yes = [row for row in subset if row["factors"].get(factor, False)]
            no = [row for row in subset if not row["factors"].get(factor, False)]
            periods[period] = {str(h): {**delta(yes, no, h), "enrichment": enrichment(rows, factor, period, h)} for h in HORIZONS}
        pvalues.append(periods["development"]["20"]["mean_difference_p"])
        output.append({"factor": factor, "family": FAMILIES.get(factor, "unclassified"), "periods": periods})
    for row, adjusted in zip(output, bh_adjust(pvalues)):
        row["development_20d_bh_q"] = adjusted
        dev = row["periods"]["development"]["20"]
        val = row["periods"]["validation_2025"]["20"]
        fwd = row["periods"]["forward_2026"]["20"]
        row["development_qualified"] = bool(
            dev["with"]["samples"] >= FACTOR_MINIMUMS["development"] and
            val["with"]["samples"] >= FACTOR_MINIMUMS["validation_2025"] and
            dev["delta"]["trimmed_mean_pp"] > 0 and dev["delta"]["profit_factor"] > 0 and adjusted <= .10
        )
        same_direction = all(item["delta"]["trimmed_mean_pp"] > 0 for item in (dev, val, fwd))
        row["verdict"] = "candidate" if row["development_qualified"] and same_direction else "unstable" if row["development_qualified"] else "not_validated"
    return output


def pair_results(rows, factors):
    qualified = sorted((row for row in factors if row["development_qualified"]), key=lambda row: row["periods"]["development"]["20"]["delta"]["trimmed_mean_pp"], reverse=True)[:6]
    frozen = [row["factor"] for row in qualified]
    pairs = []
    for a, b in itertools.combinations(frozen, 2):
        if FAMILIES.get(a) == FAMILIES.get(b):
            continue
        periods = {}
        for period, _, _ in PERIODS:
            subset = [row for row in rows if row["period"] == period]
            both = [row for row in subset if row["factors"].get(a, False) and row["factors"].get(b, False)]
            neither = [row for row in subset if not (row["factors"].get(a, False) and row["factors"].get(b, False))]
            a_only = [row for row in subset if row["factors"].get(a, False) and not row["factors"].get(b, False)]
            b_only = [row for row in subset if row["factors"].get(b, False) and not row["factors"].get(a, False)]
            periods[period] = {"both_vs_rest": delta(both, neither, 20), "both": metrics(both, 20), "a_only": metrics(a_only, 20), "b_only": metrics(b_only, 20)}
        enough = periods["development"]["both"]["samples"] >= PAIR_MINIMUMS["development"] and periods["validation_2025"]["both"]["samples"] >= PAIR_MINIMUMS["validation_2025"]
        uplift = all(periods[name]["both"]["trimmed_mean_pct"] is not None and periods[name]["a_only"]["trimmed_mean_pct"] is not None and periods[name]["b_only"]["trimmed_mean_pct"] is not None and periods[name]["both"]["trimmed_mean_pct"] > max(periods[name]["a_only"]["trimmed_mean_pct"], periods[name]["b_only"]["trimmed_mean_pct"]) for name, _, _ in PERIODS)
        pairs.append({"factors": [a, b], "periods": periods, "verdict": "candidate" if enough and uplift else "sample_insufficient" if not enough else "not_validated"})
    return {"frozen_development_candidates": frozen, "pairs": pairs}


def weekly_checkpoints(rows, source_path=SOURCE, checkpoint_path=CHECKPOINTS):
    weeks = defaultdict(list)
    for row in rows:
        day = date.fromisoformat(row["date"])
        monday = day - timedelta(days=day.weekday())
        weeks[monday.isoformat()].append(row)
    source_path, checkpoint_path = pathlib.Path(source_path), pathlib.Path(checkpoint_path)
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    records = []
    for monday in sorted(weeks):
        values = weeks[monday]
        records.append({"week_start": monday, "week_end": (date.fromisoformat(monday) + timedelta(days=6)).isoformat(), "status": "success", "events": len(values), "symbols": len({row["ticker"] for row in values}), "source_sha256": source_hash})
    checkpoint_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records))
    return records, source_hash


def run(source=SOURCE, out=OUT):
    source = pathlib.Path(source)
    out = pathlib.Path(out)
    checkpoints_path = out.with_name("score-factor-study-v1-weekly.jsonl")
    all_rows = load_events(source)
    primary = deduplicate(all_rows)
    checkpoints, source_hash = weekly_checkpoints(all_rows, source, checkpoints_path)
    factors = factor_results(primary)
    report = {
        "version": "1.0.0", "experiment_id": "score-monotonicity-factor-attribution-v1.0.0-2026-08-29",
        "generated_at": datetime.now(timezone.utc).isoformat(), "research_only": True,
        "source": {"path": str(source.relative_to(ROOT)) if source.is_relative_to(ROOT) else str(source), "sha256": source_hash, "frozen_events": len(all_rows), "primary_deduplicated_events": len(primary), "date_start": min(row["date"] for row in all_rows), "date_end": max(row["date"] for row in all_rows)},
        "audit": {"daily_macd_gate_preserved": True, "production_outputs_written": False, "market_and_industry_excluded": True, "entry": "next adjusted open", "available_horizons": [5, 20, 40], "missing_horizons": {"100": "Frozen event rows do not contain point-level 100-day outcomes; pending cache restoration."}, "overlap_primary": "first ticker event within 56 calendar days (transparent approximation to 40 trading sessions)", "all_event_sensitivity_included": True},
        "definitions": {"high_score": ">=5", "score_groups": ["exact", "0-2", "3-4", ">=5"], "winner": "raw fixed-horizon return >0", "high_return": "top period/horizon decile", "absolute_high_return_sensitivity": ">=10%", "cost_bps": [0, 20, 50]},
        "weekly_checkpoints": {"path": str(checkpoints_path.relative_to(ROOT)) if checkpoints_path.is_relative_to(ROOT) else str(checkpoints_path), "count": len(checkpoints), "first": checkpoints[0], "last": checkpoints[-1]},
        "primary": {"score_monotonicity": score_results(primary), "factor_attribution": factors, "two_factor_combinations": pair_results(primary, factors)},
        "all_event_sensitivity": {"score_monotonicity": score_results(all_rows)},
        "limitations": ["Frozen input is the earlier Tracker selection surface, not every neutral current-model candidate.", "The 56-calendar-day overlap rule approximates 40 trading sessions because the frozen file lacks a complete exchange-session calendar.", "100-day point-level results remain pending and are not inferred from older aggregate studies.", "Mean-difference p-values use a normal approximation; effect sizes, medians, trimmed means and cross-period direction remain primary."],
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps({"events": result["source"], "checkpoints": result["weekly_checkpoints"], "qualified_factors": result["primary"]["two_factor_combinations"]["frozen_development_candidates"]}, ensure_ascii=False, indent=2))
