"""Frozen 2x2 and matched-control study for Connors RSI and Choppiness.

This module reuses Factor Strategy Lab V2 annual point-in-time checkpoints.
It does not alter the production registry, score, event gate, or execution.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime

from research.backtest.factor_strategy_lab_v2 import (
    BASELINE_COVARIATES,
    HORIZONS,
    PRIMARY_HORIZON,
    _eligible,
    _finite,
    _legacy_value,
    _load_rows,
    _quarter,
)
from research.backtest.reused_event_study_v2 import (
    bh_adjust,
    deduplicate,
    metrics,
    normal_mean_pvalue,
)


EXPERIMENT_ID = "connors-choppiness-paired-ab-v1.0.0-2026-08-29"
A_ID = "momentum.connors_rsi_3_2_100"
B_ID = "regime.choppiness_14"
A_THRESHOLD = 67.719304
B_THRESHOLD = 58.814226
PERIODS = {
    "development_2001_2024": ("2001-01-01", "2024-12-31"),
    "seen_2025": ("2025-01-01", "2025-12-31"),
    "seen_2026": ("2026-01-01", "9999-12-31"),
}
CONTRASTS = (
    ("a_only_vs_none", "a_only", "none"),
    ("b_only_vs_none", "b_only", "none"),
    ("both_vs_none", "both", "none"),
    ("both_vs_a_only", "both", "a_only"),
    ("both_vs_b_only", "both", "b_only"),
)
DELTA_KEYS = ("win_rate_pct", "median_pct", "trimmed_mean_pct", "profit_factor", "expectancy_pct")


def factor_group(row: dict) -> str | None:
    features = row.get("candidate_features", {})
    a_value, b_value = features.get(A_ID), features.get(B_ID)
    if not _finite(a_value) or not _finite(b_value):
        return None
    a_hit = a_value <= A_THRESHOLD
    b_hit = b_value >= B_THRESHOLD
    if a_hit and b_hit:
        return "both"
    if a_hit:
        return "a_only"
    if b_hit:
        return "b_only"
    return "none"


def _period_rows(rows: list[dict]) -> dict[str, list[dict]]:
    return {
        name: [row for row in rows if start <= row["date"] <= end and factor_group(row) is not None]
        for name, (start, end) in PERIODS.items()
    }


def _metric_delta(treatment: list[dict], control: list[dict], horizon: int) -> dict:
    treated, baseline = metrics(treatment, horizon), metrics(control, horizon)
    first = [row["returns"][str(horizon)] for row in treatment if _finite(row.get("returns", {}).get(str(horizon)))]
    second = [row["returns"][str(horizon)] for row in control if _finite(row.get("returns", {}).get(str(horizon)))]
    return {
        "treatment": treated,
        "control": baseline,
        "delta": {key: round((treated.get(key) or 0) - (baseline.get(key) or 0), 5) for key in DELTA_KEYS},
        "mean_difference_p": round(normal_mean_pvalue(first, second), 7),
    }


def _scales(rows: list[dict]) -> dict[str, float]:
    output = {}
    for key in BASELINE_COVARIATES:
        values = [_legacy_value(row, key) for row in rows if _finite(_legacy_value(row, key))]
        output[key] = statistics.pstdev(values) if len(values) > 1 else 1.0
        if not output[key]:
            output[key] = 1.0
    return output


def match_treatment_control(treatment: list[dict], control: list[dict]) -> list[dict]:
    usable_treatment = [row for row in treatment if all(_finite(_legacy_value(row, key)) for key in BASELINE_COVARIATES)]
    usable_control = [row for row in control if all(_finite(_legacy_value(row, key)) for key in BASELINE_COVARIATES)]
    scales = _scales(usable_treatment + usable_control)
    by_year: dict[int, list[dict]] = defaultdict(list)
    for row in usable_control:
        by_year[int(row["date"][:4])].append(row)
    reuse = Counter()
    pairs = []
    for treated in sorted(usable_treatment, key=lambda row: (row["date"], row["symbol"])):
        year = int(treated["date"][:4])
        year_controls = by_year.get(year, [])
        same_quarter = [row for row in year_controls if _quarter(row["date"]) == _quarter(treated["date"])]
        pool = same_quarter or year_controls
        if not pool:
            continue
        treated_day = date.fromisoformat(treated["date"]).toordinal()

        def distance(candidate):
            covariates = sum(
                ((_legacy_value(treated, key) - _legacy_value(candidate, key)) / scales[key]) ** 2
                for key in BASELINE_COVARIATES
            )
            calendar = abs(treated_day - date.fromisoformat(candidate["date"]).toordinal()) / 60
            return covariates + calendar ** 2 + reuse[(candidate["symbol"], candidate["date"])] * 0.25

        matched = min(pool, key=distance)
        matched_distance = distance(matched)
        reuse[(matched["symbol"], matched["date"])] += 1
        pairs.append({
            "treatment": {"symbol": treated["symbol"], "date": treated["date"], "return_20d": treated["returns"]["20"]},
            "control": {"symbol": matched["symbol"], "date": matched["date"], "return_20d": matched["returns"]["20"]},
            "distance": round(matched_distance, 6),
            "return_difference": treated["returns"]["20"] - matched["returns"]["20"],
        })
    return pairs


def _trimmed_mean(values: list[float], proportion: float = 0.01) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    trim = int(len(ordered) * proportion)
    retained = ordered[trim:len(ordered) - trim] if trim and len(ordered) > 2 * trim else ordered
    return statistics.fmean(retained)


def matched_metrics(pairs: list[dict]) -> dict:
    differences = [pair["return_difference"] for pair in pairs]
    treatment = [pair["treatment"]["return_20d"] for pair in pairs]
    control = [pair["control"]["return_20d"] for pair in pairs]
    return {
        "pairs": len(pairs),
        "treatment_win_rate_pct": round(100 * sum(value > 0 for value in treatment) / len(treatment), 3) if pairs else None,
        "control_win_rate_pct": round(100 * sum(value > 0 for value in control) / len(control), 3) if pairs else None,
        "win_rate_delta_pct": round(100 * (sum(value > 0 for value in treatment) - sum(value > 0 for value in control)) / len(pairs), 3) if pairs else None,
        "median_return_difference_pct": round(100 * statistics.median(differences), 4) if pairs else None,
        "trimmed_mean_return_difference_pct": round(100 * _trimmed_mean(differences), 4) if pairs else None,
        "mean_return_difference_p": round(normal_mean_pvalue(differences, [0.0] * len(differences)), 7) if pairs else None,
    }


def analyze_rows(rows: list[dict]) -> dict:
    primary = _eligible(deduplicate(rows, 120))
    periods = _period_rows(primary)
    group_results = {}
    contrast_results = {}
    pair_details = {}
    for period_name, period in periods.items():
        groups = {name: [row for row in period if factor_group(row) == name] for name in ("none", "a_only", "b_only", "both")}
        group_results[period_name] = {
            group: {str(horizon): metrics(group_rows, horizon) for horizon in HORIZONS}
            for group, group_rows in groups.items()
        }
        period_contrasts = []
        for contrast_id, treatment_name, control_name in CONTRASTS:
            treatment, control = groups[treatment_name], groups[control_name]
            pairs = match_treatment_control(treatment, control)
            pair_details[f"{period_name}:{contrast_id}"] = pairs
            period_contrasts.append({
                "contrast_id": contrast_id,
                "treatment_group": treatment_name,
                "control_group": control_name,
                "horizons": {str(horizon): _metric_delta(treatment, control, horizon) for horizon in HORIZONS},
                "matched_20d": matched_metrics(pairs),
            })
        qvalues = bh_adjust([item["matched_20d"]["mean_return_difference_p"] for item in period_contrasts])
        for item, qvalue in zip(period_contrasts, qvalues):
            item["matched_20d"]["bh_q"] = qvalue
        contrast_results[period_name] = {item["contrast_id"]: item for item in period_contrasts}

    decisions = {}
    for contrast_id, _, _ in CONTRASTS:
        evidence = [contrast_results[period][contrast_id] for period in PERIODS]
        enough = all(
            item["horizons"]["20"]["treatment"]["samples"] >= 100 and
            item["horizons"]["20"]["control"]["samples"] >= 100 and
            item["matched_20d"]["pairs"] >= 100
            for item in evidence
        )
        unadjusted_aligned = all(
            item["horizons"]["20"]["delta"]["trimmed_mean_pct"] > 0 and
            item["horizons"]["20"]["delta"]["profit_factor"] > 0
            for item in evidence
        )
        matched_aligned = all((item["matched_20d"]["trimmed_mean_return_difference_pct"] or 0) > 0 for item in evidence)
        multiplicity_pass = all((item["matched_20d"]["bh_q"] or 1) <= 0.10 for item in evidence)
        decisions[contrast_id] = {
            "enough_samples": enough,
            "unadjusted_aligned": unadjusted_aligned,
            "matched_aligned": matched_aligned,
            "multiplicity_pass": multiplicity_pass,
            "verdict": (
                "sample_insufficient" if not enough else
                "continue_unseen_forward" if unadjusted_aligned and matched_aligned and multiplicity_pass else
                "directional_only" if unadjusted_aligned and matched_aligned else
                "reject"
            ),
        }
    combination_pass = all(
        decisions[contrast]["verdict"] == "continue_unseen_forward"
        for contrast in ("both_vs_none", "both_vs_a_only", "both_vs_b_only")
    )
    report = {
        "schema_version": "connors-choppiness-paired-ab-v1.0.0",
        "experiment_id": EXPERIMENT_ID,
        "generated_at": datetime.now().astimezone().isoformat(),
        "production_scoring_changed": False,
        "event_gate": "exact completed daily MACD bullish cross plus archived long-trend qualification",
        "frozen_conditions": {
            "A": {"candidate_id": A_ID, "operator": "<=", "threshold": A_THRESHOLD},
            "B": {"candidate_id": B_ID, "operator": ">=", "threshold": B_THRESHOLD},
        },
        "coverage": {
            "start": min(row["date"] for row in primary),
            "end": max(row["date"] for row in primary),
            "primary_events": len(primary),
            "period_events": {name: len(period) for name, period in periods.items()},
        },
        "method": {
            "groups": ["none", "a_only", "b_only", "both"],
            "contrasts": [contrast_id for contrast_id, _, _ in CONTRASTS],
            "matching_covariates": list(BASELINE_COVARIATES),
            "matching_excludes": "A/B values, group outcome and all future path fields",
            "primary_horizon_sessions": 20,
            "sensitivity_horizons": [5, 10, 40, 60],
            "multiple_testing": "Benjamini-Hochberg across five matched contrasts within each period",
            "true_unseen_forward_starts_after": "2026-08-29",
        },
        "group_results": group_results,
        "contrast_results": contrast_results,
        "decisions": decisions,
        "combination_pass": combination_pass,
        "production_action": "none",
        "limitations": [
            "A/B thresholds were selected after reviewing historical and seen-period data",
            "2025 and 2026 are seen-period mechanism checks, not independent validation",
            "matching reduces measured baseline imbalance but does not prove causality",
            "2019 onward universe coverage expands materially",
            "event-level results are not a capital-constrained portfolio",
        ],
    }
    return report, pair_details


def run(input_dir, out, detail_out=None) -> dict:
    report, pair_details = analyze_rows(_load_rows(input_dir))
    target = pathlib.Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if detail_out:
        detail = pathlib.Path(detail_out)
        detail.parent.mkdir(parents=True, exist_ok=True)
        detail.write_text(json.dumps({"experiment_id": EXPERIMENT_ID, "pairs": pair_details}, ensure_ascii=False))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--detail-out")
    args = parser.parse_args()
    report = run(args.input_dir, args.out, args.detail_out)
    print(json.dumps({"coverage": report["coverage"], "decisions": report["decisions"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
