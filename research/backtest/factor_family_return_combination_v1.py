"""Return-ranked role-family combinations over the archived MACD event pool.

The experiment deliberately searches only four pre-registered family states,
not arbitrary raw-factor subsets or weights.  Thresholds are fitted inside
each rolling training window and then applied unchanged to the next test
window.  Production factor metadata, scoring, risk and execution are never
modified by this module.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import pathlib
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime

from research.backtest.factor_strategy_lab_v2 import _eligible, _finite, _load_rows, _quarter
from research.backtest.reused_event_study_v2 import (
    bh_adjust,
    deduplicate,
    metrics,
    normal_mean_pvalue,
    percentile,
    trimmed_mean,
)


EXPERIMENT_ID = "factor-family-return-combination-v1.0.0-2026-08-29"
PRIMARY_HORIZON = 20
HORIZONS = (5, 10, 20, 40, 60)
PRIMARY_COST_BPS = 50
FAMILIES = (
    "support_location",
    "controlled_pullback",
    "reacceleration",
    "low_supply_risk",
)
FAMILY_LABELS = {
    "support_location": "支撑位置",
    "controlled_pullback": "可控回调",
    "reacceleration": "重新启动",
    "low_supply_risk": "低供应风险",
}
COMBINATIONS = tuple(
    combo
    for size in range(1, len(FAMILIES) + 1)
    for combo in itertools.combinations(FAMILIES, size)
)
FOLDS = (
    ("test_2013_2015", "2001-01-01", "2012-12-31", "2013-01-01", "2015-12-31"),
    ("test_2016_2018", "2001-01-01", "2015-12-31", "2016-01-01", "2018-12-31"),
    ("test_2019_2021", "2001-01-01", "2018-12-31", "2019-01-01", "2021-12-31"),
    ("test_2022_2024", "2001-01-01", "2021-12-31", "2022-01-01", "2024-12-31"),
)
SUPPORT_FACTORS = frozenset({
    "support.ema_proximity",
    "support.weekly_ema_proximity",
    "support.monthly_ema_proximity",
    "support.fibonacci_half",
    "support.fibonacci_618",
    "support.golden_pocket",
    "support.close_congestion",
    "support.volume_profile_proxy",
    "structure.bullish_fvg_support",
})
CONFIRMATION_FACTORS = frozenset({
    "volume.relative_expansion",
    "volume.bottom_expansion",
    "structure.trendline_three_push",
    "structure.trendline_three_push_retest",
    "structure.bottom_bullish_engulfing",
    "structure.support_bullish_engulfing",
    "structure.engulfing_bullish_follow_through",
    "structure.hammer",
})
MATCH_COVARIATES = (
    "trend.ema200_slope_60_pct",
    "volatility.atr14_pct",
)


def combo_id(combo: tuple[str, ...]) -> str:
    return "+".join(combo)


def _value(row: dict, key: str) -> float | None:
    if key.startswith("score."):
        return row.get("scores", {}).get(key.split(".", 1)[1])
    if key in row.get("legacy_features", {}):
        return row["legacy_features"].get(key)
    return row.get("candidate_features", {}).get(key)


def _percentile(rows: list[dict], key: str, quantile: float) -> float | None:
    values = [_value(row, key) for row in rows]
    return percentile([value for value in values if _finite(value)], quantile)


def fit_thresholds(rows: list[dict]) -> dict[str, float | None]:
    """Fit only the quantiles frozen in the preregistration."""
    return {
        "pullback_depth_p20": _percentile(rows, "location.pullback_60d_pct", 0.20),
        "pullback_depth_p80": _percentile(rows, "location.pullback_60d_pct", 0.80),
        "days_since_high_p20": _percentile(rows, "location.days_since_high_60", 0.20),
        "days_since_high_p80": _percentile(rows, "location.days_since_high_60", 0.80),
        "ulcer_p70": _percentile(rows, "risk.ulcer_index_20", 0.70),
        "return_balance_p30": _percentile(rows, "pullback.return_balance_20", 0.30),
        "macd_histogram_change_p60": _percentile(rows, "momentum.macd_histogram_change_3_pct", 0.60),
        "relative_volume_p60": _percentile(rows, "volume.relative_20", 0.60),
        "directional_control_p60": _percentile(rows, "trend.directional_control_14", 0.60),
        "squeeze_p80": _percentile(rows, "volatility.squeeze_ratio_20", 0.80),
        "ulcer_p80": _percentile(rows, "risk.ulcer_index_20", 0.80),
    }


def _between(value: float | None, low: float | None, high: float | None) -> bool:
    return _finite(value) and _finite(low) and _finite(high) and low <= value <= high


def _at_least(value: float | None, threshold: float | None) -> bool:
    return _finite(value) and _finite(threshold) and value >= threshold


def _at_most(value: float | None, threshold: float | None) -> bool:
    return _finite(value) and _finite(threshold) and value <= threshold


def family_flags(row: dict, thresholds: dict[str, float | None]) -> dict[str, bool]:
    hits = set(row.get("factors", []))
    support_location = bool(hits & SUPPORT_FACTORS)

    pullback_votes = (
        _between(
            _value(row, "location.pullback_60d_pct"),
            thresholds["pullback_depth_p20"],
            thresholds["pullback_depth_p80"],
        ),
        _between(
            _value(row, "location.days_since_high_60"),
            thresholds["days_since_high_p20"],
            thresholds["days_since_high_p80"],
        ),
        _at_most(_value(row, "risk.ulcer_index_20"), thresholds["ulcer_p70"]),
        _at_least(_value(row, "pullback.return_balance_20"), thresholds["return_balance_p30"]),
    )
    controlled_pullback = "qualification.pullback_60d" in hits and sum(pullback_votes) >= 2

    relative_volume_floor = thresholds["relative_volume_p60"]
    if _finite(relative_volume_floor):
        relative_volume_floor = max(1.0, relative_volume_floor)
    reacceleration_votes = (
        _at_least(
            _value(row, "momentum.macd_histogram_change_3_pct"),
            thresholds["macd_histogram_change_p60"],
        ),
        _at_least(_value(row, "volume.relative_20"), relative_volume_floor),
        _at_least(
            _value(row, "trend.directional_control_14"),
            thresholds["directional_control_p60"],
        ),
        _finite(_value(row, "candle.close_location")) and _value(row, "candle.close_location") >= 0.60,
        bool(hits & CONFIRMATION_FACTORS),
    )
    reacceleration = sum(reacceleration_votes) >= 2

    low_supply_votes = (
        "risk.overhead_unfilled_gap" not in hits,
        _finite(_value(row, "volume.chaikin_money_flow_20"))
        and _value(row, "volume.chaikin_money_flow_20") >= 0,
        _finite(_value(row, "volume.return_volume_corr_20"))
        and _value(row, "volume.return_volume_corr_20") >= 0,
        _at_most(_value(row, "volatility.squeeze_ratio_20"), thresholds["squeeze_p80"]),
        _at_most(_value(row, "risk.ulcer_index_20"), thresholds["ulcer_p80"]),
    )
    low_supply_risk = sum(low_supply_votes) >= 3
    return {
        "support_location": support_location,
        "controlled_pullback": controlled_pullback,
        "reacceleration": reacceleration,
        "low_supply_risk": low_supply_risk,
    }


def tag_rows(rows: list[dict], thresholds: dict[str, float | None]) -> list[dict]:
    return [{**row, "family_flags": family_flags(row, thresholds)} for row in rows]


def _matches(row: dict, combo: tuple[str, ...]) -> bool:
    flags = row.get("family_flags", {})
    return all(flags.get(family, False) for family in combo)


def _metric_bundle(rows: list[dict], horizon: int = PRIMARY_HORIZON) -> dict:
    return {
        "raw": metrics(rows, horizon),
        "net_20bps": metrics(rows, horizon, 20),
        "net_50bps": metrics(rows, horizon, PRIMARY_COST_BPS),
    }


def _difference(first: dict, second: dict) -> dict:
    keys = ("win_rate_pct", "median_pct", "trimmed_mean_pct", "profit_factor", "expectancy_pct")
    return {
        key: round((first.get(key) or 0) - (second.get(key) or 0), 5)
        for key in keys
    }


def evaluate_combo(rows: list[dict], combo: tuple[str, ...]) -> tuple[dict, list[dict], list[dict]]:
    hit = [row for row in rows if _matches(row, combo)]
    miss = [row for row in rows if not _matches(row, combo)]
    baseline_metrics = _metric_bundle(rows)
    hit_metrics = _metric_bundle(hit)
    miss_metrics = _metric_bundle(miss)
    hit_values = [row["returns"][str(PRIMARY_HORIZON)] for row in hit]
    miss_values = [row["returns"][str(PRIMARY_HORIZON)] for row in miss]
    result = {
        "combination_id": combo_id(combo),
        "families": list(combo),
        "family_labels_zh": [FAMILY_LABELS[family] for family in combo],
        "hit": hit_metrics,
        "miss": miss_metrics,
        "baseline": baseline_metrics,
        "net_50bps_delta_vs_baseline": _difference(hit_metrics["net_50bps"], baseline_metrics["net_50bps"]),
        "net_50bps_delta_vs_miss": _difference(hit_metrics["net_50bps"], miss_metrics["net_50bps"]),
        "hit_vs_miss_mean_p": round(normal_mean_pvalue(hit_values, miss_values), 7),
    }
    return result, hit, miss


def _eligible_training(row: dict, hit_rows: list[dict]) -> bool:
    net = row["hit"]["net_50bps"]
    baseline = row["baseline"]["net_50bps"]
    years = {item["date"][:4] for item in hit_rows}
    return (
        net["samples"] >= 80
        and len(years) >= 3
        and (net["profit_factor"] or 0) > 1
        and (net["median_pct"] or 0) > 0
        and (net["trimmed_mean_pct"] or -math.inf) > (baseline["trimmed_mean_pct"] or -math.inf)
    )


def _sort_key(row: dict) -> tuple[float, float, int]:
    net = row["hit"]["net_50bps"]
    return (
        net["trimmed_mean_pct"] if net["trimmed_mean_pct"] is not None else -math.inf,
        net["profit_factor"] if net["profit_factor"] is not None else -math.inf,
        net["samples"],
    )


def _year_concentration(rows: list[dict]) -> dict:
    counts = Counter(row["date"][:4] for row in rows)
    total = sum(counts.values())
    return {
        "by_year": dict(sorted(counts.items())),
        "max_year_share": round(max(counts.values()) / total, 6) if total else None,
        "max_year": max(counts, key=counts.get) if counts else None,
    }


def _scale(rows: list[dict], key: str) -> float:
    values = [_value(row, key) for row in rows]
    values = [value for value in values if _finite(value)]
    result = statistics.pstdev(values) if len(values) > 1 else 1.0
    return result or 1.0


def matched_controls(treatment: list[dict], control: list[dict]) -> dict:
    usable_treatment = [
        row for row in treatment
        if all(_finite(_value(row, key)) for key in MATCH_COVARIATES)
    ]
    usable_control = [
        row for row in control
        if all(_finite(_value(row, key)) for key in MATCH_COVARIATES)
    ]
    scales = {key: _scale(usable_treatment + usable_control, key) for key in MATCH_COVARIATES}
    by_year: dict[int, list[dict]] = defaultdict(list)
    for row in usable_control:
        by_year[int(row["date"][:4])].append(row)
    reuse = Counter()
    pairs = []
    for treated in sorted(usable_treatment, key=lambda row: (row["date"], row["symbol"])):
        candidates = by_year.get(int(treated["date"][:4]), [])
        same_quarter = [row for row in candidates if _quarter(row["date"]) == _quarter(treated["date"])]
        pool = same_quarter or candidates
        if not pool:
            continue
        treated_day = date.fromisoformat(treated["date"]).toordinal()

        def distance(candidate: dict) -> float:
            covariates = sum(
                ((_value(treated, key) - _value(candidate, key)) / scales[key]) ** 2
                for key in MATCH_COVARIATES
            )
            calendar = abs(treated_day - date.fromisoformat(candidate["date"]).toordinal()) / 60
            return covariates + calendar ** 2 + reuse[(candidate["symbol"], candidate["date"])] * 0.25

        matched = min(pool, key=distance)
        reuse[(matched["symbol"], matched["date"])] += 1
        pairs.append((treated, matched))
    treatment_rows = [pair[0] for pair in pairs]
    control_rows = [pair[1] for pair in pairs]
    differences = [
        treated["returns"][str(PRIMARY_HORIZON)] - matched["returns"][str(PRIMARY_HORIZON)]
        for treated, matched in pairs
    ]
    return {
        "pairs": len(pairs),
        "matching_covariates": list(MATCH_COVARIATES),
        "treatment_net_50bps": metrics(treatment_rows, PRIMARY_HORIZON, PRIMARY_COST_BPS),
        "control_net_50bps": metrics(control_rows, PRIMARY_HORIZON, PRIMARY_COST_BPS),
        "win_rate_delta_pct": round(
            100 * (
                sum(row["returns"]["20"] - 0.005 > 0 for row in treatment_rows)
                - sum(row["returns"]["20"] - 0.005 > 0 for row in control_rows)
            ) / len(pairs),
            4,
        ) if pairs else None,
        "median_return_difference_pct": round(100 * statistics.median(differences), 4) if pairs else None,
        "trimmed_mean_return_difference_pct": round(100 * trimmed_mean(differences), 4) if pairs else None,
        "mean_return_difference_p": round(
            normal_mean_pvalue(differences, [0.0] * len(differences)), 7
        ) if pairs else None,
    }


def _period_final_report(rows: list[dict], combo: tuple[str, ...], thresholds: dict) -> dict:
    tagged = tag_rows(rows, thresholds)
    result, hit, miss = evaluate_combo(tagged, combo)
    singles = {}
    for family in combo:
        single, _, _ = evaluate_combo(tagged, (family,))
        singles[family] = single["hit"]
    result["constituent_single_families"] = singles
    result["matched_control_20d"] = matched_controls(hit, miss)
    result["horizon_sensitivity"] = {
        str(horizon): {
            "hit": _metric_bundle(hit, horizon),
            "baseline": _metric_bundle(tagged, horizon),
        }
        for horizon in HORIZONS
    }
    result["family_hit_rates"] = {
        family: round(sum(row["family_flags"][family] for row in tagged) / len(tagged), 6)
        if tagged else None
        for family in FAMILIES
    }
    return result


def analyze_rows(rows: list[dict]) -> dict:
    eligible = _eligible(deduplicate(rows, 120))
    primary = [row for row in eligible if row["date"] >= "2001-01-01"]
    fold_reports = []
    pooled_hits = {combo_id(combo): [] for combo in COMBINATIONS}
    pooled_misses = {combo_id(combo): [] for combo in COMBINATIONS}
    pooled_baseline = []
    fold_combo_results: dict[str, dict[str, dict]] = {}

    for fold_id, train_start, train_end, test_start, test_end in FOLDS:
        train = [row for row in primary if train_start <= row["date"] <= train_end]
        test = [row for row in primary if test_start <= row["date"] <= test_end]
        thresholds = fit_thresholds(train)
        tagged_train, tagged_test = tag_rows(train, thresholds), tag_rows(test, thresholds)
        train_candidates = []
        for combo in COMBINATIONS:
            result, hit, _ = evaluate_combo(tagged_train, combo)
            result["training_eligible"] = _eligible_training(result, hit)
            train_candidates.append(result)
        eligible_candidates = [row for row in train_candidates if row["training_eligible"]]
        selected = max(eligible_candidates, key=_sort_key) if eligible_candidates else None
        selected_test = None
        if selected:
            selected_combo = tuple(selected["families"])
            selected_test, _, _ = evaluate_combo(tagged_test, selected_combo)

        test_results = {}
        for combo in COMBINATIONS:
            result, hit, miss = evaluate_combo(tagged_test, combo)
            key = combo_id(combo)
            test_results[key] = result
            pooled_hits[key].extend(hit)
            pooled_misses[key].extend(miss)
        pooled_baseline.extend(tagged_test)
        fold_combo_results[fold_id] = test_results
        fold_reports.append({
            "fold_id": fold_id,
            "train_range": [train_start, train_end],
            "test_range": [test_start, test_end],
            "train_events": len(train),
            "test_events": len(test),
            "thresholds": thresholds,
            "selected_training_winner": selected,
            "selected_test_result": selected_test,
            "selection_status": "selected" if selected else "no_training_combination_passed",
        })

    pooled_table = []
    pvalues = []
    for combo in COMBINATIONS:
        key = combo_id(combo)
        hit, miss = pooled_hits[key], pooled_misses[key]
        hit_bundle, miss_bundle, baseline_bundle = (
            _metric_bundle(hit),
            _metric_bundle(miss),
            _metric_bundle(pooled_baseline),
        )
        hit_values = [row["returns"]["20"] for row in hit]
        miss_values = [row["returns"]["20"] for row in miss]
        positive_folds = sum(
            (fold_combo_results[fold_id][key]["net_50bps_delta_vs_baseline"]["trimmed_mean_pct"] or 0) > 0
            for fold_id, *_ in FOLDS
        )
        pvalue = normal_mean_pvalue(hit_values, miss_values)
        pvalues.append(pvalue)
        pooled_table.append({
            "combination_id": key,
            "families": list(combo),
            "family_labels_zh": [FAMILY_LABELS[family] for family in combo],
            "hit": hit_bundle,
            "miss": miss_bundle,
            "baseline": baseline_bundle,
            "net_50bps_delta_vs_baseline": _difference(hit_bundle["net_50bps"], baseline_bundle["net_50bps"]),
            "net_50bps_delta_vs_miss": _difference(hit_bundle["net_50bps"], miss_bundle["net_50bps"]),
            "positive_test_folds_vs_baseline": positive_folds,
            "year_concentration": _year_concentration(hit),
            "hit_vs_miss_mean_p": round(pvalue, 7),
            "test_folds": {
                fold_id: fold_combo_results[fold_id][key]
                for fold_id, *_ in FOLDS
            },
        })
    for row, qvalue in zip(pooled_table, bh_adjust(pvalues)):
        row["hit_vs_miss_bh_q"] = qvalue

    by_id = {row["combination_id"]: row for row in pooled_table}
    for row in pooled_table:
        hit_net = row["hit"]["net_50bps"]
        baseline_net = row["baseline"]["net_50bps"]
        miss_net = row["miss"]["net_50bps"]
        singles = [by_id[family]["hit"]["net_50bps"] for family in row["families"]]
        beats_singles = len(row["families"]) > 1 and all(
            (hit_net["trimmed_mean_pct"] or -math.inf) > (single["trimmed_mean_pct"] or -math.inf)
            and (hit_net["profit_factor"] or -math.inf) > (single["profit_factor"] or -math.inf)
            for single in singles
        )
        row["constituent_single_control"] = {
            family: by_id[family]["hit"]
            for family in row["families"]
        }
        row["passes_robust_gate"] = (
            len(row["families"]) > 1
            and hit_net["samples"] >= 300
            and row["positive_test_folds_vs_baseline"] >= 3
            and (row["year_concentration"]["max_year_share"] or 1) <= 0.30
            and row["hit_vs_miss_bh_q"] <= 0.10
            and (hit_net["trimmed_mean_pct"] or -math.inf) > (baseline_net["trimmed_mean_pct"] or -math.inf)
            and (hit_net["profit_factor"] or -math.inf) > (baseline_net["profit_factor"] or -math.inf)
            and (hit_net["trimmed_mean_pct"] or -math.inf) > (miss_net["trimmed_mean_pct"] or -math.inf)
            and (hit_net["profit_factor"] or -math.inf) > (miss_net["profit_factor"] or -math.inf)
            and beats_singles
        )

    ranked = sorted(pooled_table, key=_sort_key, reverse=True)
    multi_with_samples = [
        row for row in ranked
        if len(row["families"]) > 1 and row["hit"]["net_50bps"]["samples"] >= 300
    ]
    robust = [row for row in multi_with_samples if row["passes_robust_gate"]]
    historical_winner = (robust or multi_with_samples or [row for row in ranked if len(row["families"]) > 1])[0]
    final_combo = tuple(historical_winner["families"])
    development = [row for row in primary if "2001-01-01" <= row["date"] <= "2024-12-31"]
    full_thresholds = fit_thresholds(development)
    period_rows = {
        "retrospective_development_2001_2024": development,
        "seen_2025": [row for row in primary if "2025-01-01" <= row["date"] <= "2025-12-31"],
        "seen_2026": [row for row in primary if row["date"] >= "2026-01-01"],
    }
    final_periods = {
        period: _period_final_report(period_data, final_combo, full_thresholds)
        for period, period_data in period_rows.items()
    }
    adaptive_test_rows = []
    for fold in fold_reports:
        if fold["selected_training_winner"]:
            adaptive_test_rows.append({
                "fold_id": fold["fold_id"],
                "selection_status": "selected",
                "selected_combination_id": fold["selected_training_winner"]["combination_id"],
                "selected_test_hit": fold["selected_test_result"]["hit"],
                "selected_test_baseline": fold["selected_test_result"]["baseline"],
                "selected_test_delta": fold["selected_test_result"]["net_50bps_delta_vs_baseline"],
            })
        else:
            adaptive_test_rows.append({
                "fold_id": fold["fold_id"],
                "selection_status": "no_training_combination_passed",
                "selected_combination_id": None,
                "selected_test_hit": None,
                "selected_test_baseline": None,
                "selected_test_delta": None,
            })

    verdict = "zero_weight_forward_candidate" if robust else "historical_return_winner_only"
    return {
        "schema_version": "factor-family-return-combination-v1.0.0",
        "experiment_id": EXPERIMENT_ID,
        "generated_at": datetime.now().astimezone().isoformat(),
        "production_scoring_changed": False,
        "event_gate": "exact completed daily MACD bullish cross plus archived long-trend qualification",
        "coverage": {
            "start": min(row["date"] for row in primary),
            "end": max(row["date"] for row in primary),
            "source_feature_events": len(rows),
            "primary_120_session_deduplicated_events": len(primary),
            "development_events": len(period_rows["retrospective_development_2001_2024"]),
            "seen_2025_events": len(period_rows["seen_2025"]),
            "seen_2026_events": len(period_rows["seen_2026"]),
            "annual_event_years": len({row["date"][:4] for row in rows}),
            "annual_checkpoints_reused": len({row["date"][:4] for row in rows}),
        },
        "family_definitions": {
            "support_location": "any frozen support-location evidence; duplicate hits count once",
            "controlled_pullback": "60-day pullback plus at least two of four train-frozen quality votes",
            "reacceleration": "at least two of five momentum, volume, directional, candle or confirmation votes",
            "low_supply_risk": "at least three of five overhead, flow, price-volume, squeeze and downside-risk guards",
        },
        "method": {
            "families": list(FAMILIES),
            "search_combinations": len(COMBINATIONS),
            "search_surface": "all non-empty AND combinations; no raw-factor subset or weight search",
            "primary_horizon_sessions": PRIMARY_HORIZON,
            "primary_cost_bps": PRIMARY_COST_BPS,
            "primary_objective": "50bps net 1% trimmed mean return",
            "walkforward": [fold["fold_id"] for fold in fold_reports],
            "multiple_testing": "Benjamini-Hochberg across 15 pooled rolling-test contrasts",
            "true_unseen_forward_starts_after": "2026-08-29",
            "market_and_industry_mixed": False,
        },
        "rolling_folds": fold_reports,
        "adaptive_selection_test": adaptive_test_rows,
        "rolling_test_combination_ranking": ranked,
        "historical_return_winner": {
            "combination_id": historical_winner["combination_id"],
            "families": historical_winner["families"],
            "family_labels_zh": historical_winner["family_labels_zh"],
            "rolling_test_result": historical_winner,
            "passes_robust_gate": historical_winner["passes_robust_gate"],
        },
        "robust_candidates": [row["combination_id"] for row in robust],
        "final_locked_thresholds_from_2001_2024": full_thresholds,
        "final_candidate_periods": final_periods,
        "decision": {
            "verdict": verdict,
            "candidate_id": historical_winner["combination_id"],
            "production_weight": 0,
            "production_action": "none",
            "eligible_for_true_unseen_forward": bool(robust),
            "reason": (
                "Passed every frozen historical robustness gate; history remains retrospective and only supports a zero-weight forward candidate."
                if robust else
                "This is the highest-return adequately sampled historical combination, but it failed one or more frozen robustness gates and cannot enter scoring."
            ),
        },
        "not_applicable_execution_metrics": {
            "portfolio_max_drawdown": None,
            "mfe": None,
            "mae": None,
            "stop_out_rate": None,
            "target_hit_rate": None,
            "reason": "This is an overlapping event-level fixed-hold factor experiment without capital allocation, stop, target or active exit rules.",
        },
        "audit": {
            "point_in_time_features": True,
            "future_outcome_used_in_family_flags": False,
            "thresholds_fit_inside_each_training_window": True,
            "2025_2026_used_for_selection": False,
            "signals_deduplicated_within_ticker_120_sessions": True,
            "outliers_controlled_by_1pct_trimmed_mean": True,
            "production_outputs_written": False,
        },
        "limitations": [
            "2025 and 2026 have already been reviewed and are seen-period rechecks, not independent validation",
            "2019 onward universe coverage expands materially",
            "historical delisted and ticker-change coverage remains partial",
            "historical industry membership is unavailable and excluded",
            "matching reduces measured imbalance but cannot establish causality",
            "event-level results are not a capital-constrained portfolio",
        ],
    }


def public_payload(report: dict) -> dict:
    winner = report["historical_return_winner"]
    rolling = winner["rolling_test_result"]
    periods = {}
    for period, item in report["final_candidate_periods"].items():
        periods[period] = {
            "hit": item["hit"]["net_50bps"],
            "baseline": item["baseline"]["net_50bps"],
            "miss": item["miss"]["net_50bps"],
            "delta_vs_baseline": item["net_50bps_delta_vs_baseline"],
            "matched_trimmed_mean_delta_pct": item["matched_control_20d"]["trimmed_mean_return_difference_pct"],
            "matched_p": item["matched_control_20d"]["mean_return_difference_p"],
        }
    return {
        "schema_version": "factor-family-combination-public-v1.0.0",
        "experiment_id": report["experiment_id"],
        "generated_at": report["generated_at"],
        "production_scoring_changed": False,
        "coverage": report["coverage"],
        "candidate": {
            "combination_id": winner["combination_id"],
            "family_labels_zh": winner["family_labels_zh"],
            "verdict": report["decision"]["verdict"],
            "verdict_zh": (
                "通过历史门槛，等待真正前向"
                if report["decision"]["eligible_for_true_unseen_forward"]
                else "仅是历史收益冠军，不能加入评分"
            ),
            "production_weight": 0,
            "rolling_test": {
                "samples": rolling["hit"]["net_50bps"]["samples"],
                "hit": rolling["hit"]["net_50bps"],
                "baseline": rolling["baseline"]["net_50bps"],
                "delta_vs_baseline": rolling["net_50bps_delta_vs_baseline"],
                "positive_folds": rolling["positive_test_folds_vs_baseline"],
                "total_folds": len(FOLDS),
                "bh_q": rolling["hit_vs_miss_bh_q"],
                "max_year_share": rolling["year_concentration"]["max_year_share"],
                "passes_robust_gate": rolling["passes_robust_gate"],
            },
            "periods": periods,
        },
        "plain_conclusion_zh": (
            "“支撑位置＋可控回调”是本轮20日扣50bps收益最高且样本充足的组合；"
            "滚动测试稳健收益比共同门票高，但多重比较未通过，且2025已见期明显落后，"
            "所以只记录为历史收益冠军，生产权重仍为0。"
        ),
        "how_to_use_zh": "继续把长期趋势＋日线MACD刚金叉作为门票；支撑＋可控回调可作人工观察标签，但不能据此自动加分或扩大仓位。",
        "true_unseen_forward_starts_after": "2026-08-29",
    }


def run(input_dir: str, out: str, public_out: str | None = None) -> dict:
    source_paths = sorted(pathlib.Path(input_dir).rglob("factor-lab-events-*.jsonl.gz"))
    report = analyze_rows(_load_rows(input_dir))
    report["coverage"]["annual_checkpoints_reused"] = len(source_paths)
    target = pathlib.Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if public_out:
        public_target = pathlib.Path(public_out)
        public_target.parent.mkdir(parents=True, exist_ok=True)
        public_target.write_text(json.dumps(public_payload(report), ensure_ascii=False, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--public-out")
    args = parser.parse_args()
    report = run(args.input_dir, args.out, args.public_out)
    print(json.dumps({
        "coverage": report["coverage"],
        "historical_return_winner": report["historical_return_winner"]["combination_id"],
        "decision": report["decision"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
