"""Point-in-time Choppiness state and matched-control mechanism study.

The study enriches already archived Factor Strategy Lab V2 events with
three- and five-session Choppiness changes from the audited price cache.  It
does not alter the production factor registry, score, gate, or execution.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import pathlib
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime

from research.backtest.factor_strategy_lab_v2 import (
    BASELINE_COVARIATES,
    HORIZONS,
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
from research.factor_lab.features import CandidateLoader


EXPERIMENT_ID = "choppiness-state-mechanism-v1.0.0-2026-08-29"
CHOPPINESS_ID = "regime.choppiness_14"
HIGH_THRESHOLD = 58.814226
PRIMARY_CHANGE_SESSIONS = 5
PRIMARY_CHANGE_BOUNDARY = 3.0
SENSITIVITY_CHANGE_SESSIONS = 3
SENSITIVITY_CHANGE_BOUNDARY = 2.0
PERIODS = {
    "development_2001_2024": ("2001-01-01", "2024-12-31"),
    "seen_2025": ("2025-01-01", "2025-12-31"),
    "seen_2026": ("2026-01-01", "9999-12-31"),
}
MINIMUMS = {
    "development_2001_2024": 300,
    "seen_2025": 100,
    "seen_2026": 100,
}
CONTRASTS = (
    ("high_rising_vs_low_mid", "high_rising", "low_mid", False),
    ("high_flat_vs_low_mid", "high_flat", "low_mid", False),
    ("high_falling_vs_low_mid", "high_falling", "low_mid", False),
    ("high_falling_vs_high_rising", "high_falling", "high_rising", True),
    ("high_falling_vs_high_nonfalling", "high_falling", "high_nonfalling", True),
)
DELTA_KEYS = ("win_rate_pct", "median_pct", "trimmed_mean_pct", "profit_factor", "expectancy_pct")


def classify_state(
    current: float | None,
    change: float | None,
    boundary: float = PRIMARY_CHANGE_BOUNDARY,
) -> str | None:
    if not _finite(current) or not _finite(change):
        return None
    if current < HIGH_THRESHOLD:
        return "low_mid"
    if change >= boundary:
        return "high_rising"
    if change <= -boundary:
        return "high_falling"
    return "high_flat"


def row_state(row: dict, change_key: str = "change_5") -> str | None:
    state = row.get("choppiness_state", {})
    boundary = PRIMARY_CHANGE_BOUNDARY if change_key == "change_5" else SENSITIVITY_CHANGE_BOUNDARY
    return classify_state(state.get("current"), state.get(change_key), boundary)


def enrich_year(input_dir, cache_dir, year: int, out_dir) -> dict:
    source_rows = [row for row in _load_rows(input_dir) if int(row["date"][:4]) == int(year)]
    loader = CandidateLoader(cache_dir)
    output = []
    missing_price = level_mismatch = missing_change = 0
    for row in source_rows:
        series = loader(row["symbol"])
        if series is None:
            missing_price += 1
            continue
        index = series.index.get(row["date"])
        archived = row.get("candidate_features", {}).get(CHOPPINESS_ID)
        current = series.choppiness_at_index(index) if index is not None else None
        if not _finite(archived) or not _finite(current):
            missing_change += 1
            continue
        if not math.isclose(archived, current, rel_tol=1e-9, abs_tol=1e-8):
            level_mismatch += 1
            continue
        change_3 = series.choppiness_change(row["date"], SENSITIVITY_CHANGE_SESSIONS)
        change_5 = series.choppiness_change(row["date"], PRIMARY_CHANGE_SESSIONS)
        if not _finite(change_3) or not _finite(change_5):
            missing_change += 1
            continue
        output.append({
            **row,
            "choppiness_state": {
                "current": current,
                "change_3": change_3,
                "change_5": change_5,
                "primary_state": classify_state(current, change_5, PRIMARY_CHANGE_BOUNDARY),
                "sensitivity_state": classify_state(current, change_3, SENSITIVITY_CHANGE_BOUNDARY),
            },
        })
    target = pathlib.Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    with gzip.open(target / f"choppiness-state-events-{year}.jsonl.gz", "wt", encoding="utf-8") as handle:
        for row in output:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    summary = {
        "schema_version": "choppiness-state-year-v1.0.0",
        "experiment_id": EXPERIMENT_ID,
        "year": int(year),
        "source_events": len(source_rows),
        "feature_events": len(output),
        "missing_price_events": missing_price,
        "missing_change_events": missing_change,
        "level_mismatch_events": level_mismatch,
        "future_data_used": False,
        "production_scoring_changed": False,
    }
    (target / f"annual-{year}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def _load_state_rows(input_dir) -> list[dict]:
    rows = []
    for path in sorted(pathlib.Path(input_dir).rglob("choppiness-state-events-*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    return rows


def _period_rows(rows: list[dict], change_key: str = "change_5") -> dict[str, list[dict]]:
    return {
        name: [row for row in rows if start <= row["date"] <= end and row_state(row, change_key) is not None]
        for name, (start, end) in PERIODS.items()
    }


def _covariate_value(row: dict, key: str) -> float | None:
    if key == "choppiness.current":
        return row.get("choppiness_state", {}).get("current")
    return _legacy_value(row, key)


def _scales(rows: list[dict], covariates: tuple[str, ...]) -> dict[str, float]:
    output = {}
    for key in covariates:
        values = [_covariate_value(row, key) for row in rows]
        values = [value for value in values if _finite(value)]
        output[key] = statistics.pstdev(values) if len(values) > 1 else 1.0
        if not output[key]:
            output[key] = 1.0
    return output


def match_treatment_control(
    treatment: list[dict],
    control: list[dict],
    *,
    match_current_level: bool,
) -> list[dict]:
    covariates = BASELINE_COVARIATES + (("choppiness.current",) if match_current_level else ())
    usable_treatment = [
        row for row in treatment
        if all(_finite(_covariate_value(row, key)) for key in covariates)
    ]
    usable_control = [
        row for row in control
        if all(_finite(_covariate_value(row, key)) for key in covariates)
    ]
    scales = _scales(usable_treatment + usable_control, covariates)
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
            covariate_distance = sum(
                ((_covariate_value(treated, key) - _covariate_value(candidate, key)) / scales[key]) ** 2
                for key in covariates
            )
            calendar = abs(treated_day - date.fromisoformat(candidate["date"]).toordinal()) / 60
            return covariate_distance + calendar ** 2 + reuse[(candidate["symbol"], candidate["date"])] * 0.25

        matched = min(pool, key=distance)
        reuse[(matched["symbol"], matched["date"])] += 1
        pairs.append({
            "treatment": {
                "symbol": treated["symbol"],
                "date": treated["date"],
                "return_20d": treated["returns"]["20"],
            },
            "control": {
                "symbol": matched["symbol"],
                "date": matched["date"],
                "return_20d": matched["returns"]["20"],
            },
            "distance": round(distance(matched), 6),
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


def _groups(period: list[dict], change_key: str) -> dict[str, list[dict]]:
    groups = {
        name: [row for row in period if row_state(row, change_key) == name]
        for name in ("low_mid", "high_rising", "high_flat", "high_falling")
    }
    groups["high_nonfalling"] = groups["high_rising"] + groups["high_flat"]
    return groups


def _analyze_periods(periods: dict[str, list[dict]], change_key: str, include_pairs: bool) -> tuple[dict, dict, dict]:
    group_results, contrast_results, pair_details = {}, {}, {}
    for period_name, period in periods.items():
        groups = _groups(period, change_key)
        group_results[period_name] = {
            group: {str(horizon): metrics(group_rows, horizon) for horizon in HORIZONS}
            for group, group_rows in groups.items()
        }
        period_contrasts = []
        for contrast_id, treatment_name, control_name, within_high in CONTRASTS:
            treatment, control = groups[treatment_name], groups[control_name]
            item = {
                "contrast_id": contrast_id,
                "treatment_group": treatment_name,
                "control_group": control_name,
                "matching_includes_current_choppiness": within_high,
                "horizons": {str(horizon): _metric_delta(treatment, control, horizon) for horizon in HORIZONS},
            }
            if include_pairs:
                pairs = match_treatment_control(treatment, control, match_current_level=within_high)
                pair_details[f"{period_name}:{contrast_id}"] = pairs
                item["matched_20d"] = matched_metrics(pairs)
            period_contrasts.append(item)
        if include_pairs:
            qvalues = bh_adjust([item["matched_20d"]["mean_return_difference_p"] for item in period_contrasts])
            for item, qvalue in zip(period_contrasts, qvalues):
                item["matched_20d"]["bh_q"] = qvalue
        contrast_results[period_name] = {item["contrast_id"]: item for item in period_contrasts}
    return group_results, contrast_results, pair_details


def analyze_rows(rows: list[dict]) -> tuple[dict, dict]:
    eligible = [row for row in rows if row_state(row, "change_5") is not None]
    primary = _eligible(deduplicate(eligible, 120))
    primary_periods = _period_rows(primary, "change_5")
    group_results, contrast_results, pair_details = _analyze_periods(primary_periods, "change_5", True)
    sensitivity_periods = _period_rows(primary, "change_3")
    sensitivity_groups, sensitivity_contrasts, _ = _analyze_periods(sensitivity_periods, "change_3", False)

    focus = "high_falling_vs_high_nonfalling"
    focus_results = {period: contrast_results[period][focus] for period in PERIODS}
    enough_samples = all(
        item["horizons"]["20"]["treatment"]["samples"] >= MINIMUMS[period]
        and item["matched_20d"]["pairs"] >= MINIMUMS[period]
        for period, item in focus_results.items()
    )
    unadjusted_aligned = all(
        item["horizons"]["20"]["delta"]["trimmed_mean_pct"] > 0
        and item["horizons"]["20"]["delta"]["profit_factor"] > 0
        for item in focus_results.values()
    )
    matched_aligned = all(
        (item["matched_20d"]["trimmed_mean_return_difference_pct"] or 0) > 0
        for item in focus_results.values()
    )
    multiplicity_pass = all(
        item["matched_20d"]["bh_q"] is not None
        and item["matched_20d"]["bh_q"] <= 0.10
        for item in focus_results.values()
    )
    net_positive = all(
        (item["horizons"]["20"]["treatment"].get("cost_sensitivity", {}).get("50", {}).get("expectancy_pct") or 0) > 0
        for item in focus_results.values()
    )
    verdict = (
        "add_zero_weight_research_candidate"
        if enough_samples and unadjusted_aligned and matched_aligned and multiplicity_pass and net_positive
        else "observe_zero_weight"
        if unadjusted_aligned and matched_aligned
        else "reject"
    )
    report = {
        "schema_version": "choppiness-state-mechanism-v1.0.0",
        "experiment_id": EXPERIMENT_ID,
        "generated_at": datetime.now().astimezone().isoformat(),
        "production_scoring_changed": False,
        "event_gate": "exact completed daily MACD bullish cross plus archived long-trend qualification",
        "frozen_definition": {
            "high_threshold": HIGH_THRESHOLD,
            "primary_change_sessions": PRIMARY_CHANGE_SESSIONS,
            "primary_boundary": PRIMARY_CHANGE_BOUNDARY,
            "sensitivity_change_sessions": SENSITIVITY_CHANGE_SESSIONS,
            "sensitivity_boundary": SENSITIVITY_CHANGE_BOUNDARY,
        },
        "coverage": {
            "start": min(row["date"] for row in primary),
            "end": max(row["date"] for row in primary),
            "primary_events": len(primary),
            "period_events": {name: len(period) for name, period in primary_periods.items()},
        },
        "method": {
            "groups": ["low_mid", "high_rising", "high_flat", "high_falling"],
            "contrasts": [contrast_id for contrast_id, *_ in CONTRASTS],
            "matching_covariates": list(BASELINE_COVARIATES),
            "within_high_extra_match": "current Choppiness14 level",
            "primary_horizon_sessions": 20,
            "sensitivity_horizons": [5, 10, 40, 60],
            "multiple_testing": "Benjamini-Hochberg across five matched contrasts within each period",
            "true_unseen_forward_starts_after": "2026-08-29",
        },
        "group_results": group_results,
        "contrast_results": contrast_results,
        "three_session_sensitivity": {
            "group_results": sensitivity_groups,
            "contrast_results": sensitivity_contrasts,
        },
        "candidate_decision": {
            "candidate_id": "regime.choppiness_release_14_5",
            "focus_contrast": focus,
            "enough_samples": enough_samples,
            "unadjusted_aligned": unadjusted_aligned,
            "matched_aligned": matched_aligned,
            "multiplicity_pass": multiplicity_pass,
            "50bps_expectancy_positive": net_positive,
            "verdict": verdict,
            "production_weight": 0,
        },
        "production_action": "none",
        "limitations": [
            "the threshold and mechanism question were selected after reviewing historical and seen-period results",
            "2025 and 2026 are seen-period mechanism checks, not independent validation",
            "matching reduces measured baseline imbalance but does not prove causality",
            "2019 onward universe coverage expands materially",
            "event-level results are not a capital-constrained portfolio",
        ],
    }
    return report, pair_details


def aggregate(input_dir, out, detail_out=None) -> dict:
    report, pair_details = analyze_rows(_load_state_rows(input_dir))
    target = pathlib.Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if detail_out:
        detail = pathlib.Path(detail_out)
        detail.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(detail, "wt", encoding="utf-8") as handle:
            json.dump({"experiment_id": EXPERIMENT_ID, "pairs": pair_details}, handle, ensure_ascii=False)
    return report


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    year_parser = subparsers.add_parser("year")
    year_parser.add_argument("--input-dir", required=True)
    year_parser.add_argument("--cache-dir", required=True)
    year_parser.add_argument("--year", type=int, required=True)
    year_parser.add_argument("--out-dir", required=True)
    aggregate_parser = subparsers.add_parser("aggregate")
    aggregate_parser.add_argument("--input-dir", required=True)
    aggregate_parser.add_argument("--out", required=True)
    aggregate_parser.add_argument("--detail-out")
    args = parser.parse_args()
    if args.command == "year":
        result = enrich_year(args.input_dir, args.cache_dir, args.year, args.out_dir)
    else:
        result = aggregate(args.input_dir, args.out, args.detail_out)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
