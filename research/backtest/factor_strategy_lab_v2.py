"""Reusable external-factor and matched-control research for Sage Vista.

The module never edits the production factor registry or score.  It enriches
the already-audited exact daily-MACD event pool from point-in-time OHLCV,
archives annual checkpoints, and compares both new continuous candidates and
existing factor hits.  Extreme winners are case studies; evidence comes from
full-sample and matched-control comparisons.
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

from research.backtest.reused_event_study_v2 import (
    _load_enriched,
    bh_adjust,
    deduplicate,
    metrics,
    normal_mean_pvalue,
    percentile,
)
from research.factor_lab.features import (
    CANDIDATES,
    CandidateLoader,
    CandidateSeries,
    finite,
    load_catalog,
)
from services.scanner.factor_registry import FACTORS_BY_ID


EXPERIMENT_ID = "factor-strategy-lab-v2.0.0-2026-08-29"
PRIMARY_HORIZON = 20
HORIZONS = (5, 10, 20, 40, 60)
SPLITS = (
    ("discovery_2001_2012", "2001-01-01", "2012-12-31"),
    ("walkforward_2013_2015", "2013-01-01", "2015-12-31"),
    ("walkforward_2016_2018", "2016-01-01", "2018-12-31"),
    ("walkforward_2019_2021", "2019-01-01", "2021-12-31"),
    ("walkforward_2022_2024", "2022-01-01", "2024-12-31"),
    ("seen_2025", "2025-01-01", "2025-12-31"),
    ("seen_2026", "2026-01-01", "9999-12-31"),
)
TRAIN_END_BY_SPLIT = {
    "discovery_2001_2012": "2012-12-31",
    "walkforward_2013_2015": "2012-12-31",
    "walkforward_2016_2018": "2015-12-31",
    "walkforward_2019_2021": "2018-12-31",
    "walkforward_2022_2024": "2021-12-31",
    "seen_2025": "2024-12-31",
    "seen_2026": "2024-12-31",
}
WALKFORWARD_SPLITS = tuple(name for name, _, _ in SPLITS if name.startswith("walkforward_"))
BASELINE_COVARIATES = (
    "score.current",
    "momentum.return_20_pct",
    "location.pullback_60d_pct",
    "volatility.atr14_pct",
)


_finite = finite


def split_of(value: str) -> str | None:
    return next((name for name, start, end in SPLITS if start <= value <= end), None)


def enrich_year(input_dir, cache_dir, year: int, out_dir) -> dict:
    source_rows = [row for row in _load_enriched(input_dir) if int(row["date"][:4]) == int(year)]
    loader = CandidateLoader(cache_dir)
    spy, qqq = loader("SPY"), loader("QQQ")
    output, missing = [], 0
    for row in source_rows:
        series = loader(row["symbol"])
        if series is None:
            missing += 1
            continue
        candidates, legacy, auxiliary = series.technical(row["date"])
        if not any(_finite(value) for value in candidates.values()):
            missing += 1
            continue
        stock_return20 = series.trailing_return(row["date"], 20)
        context = {
            "stock_minus_spy_return_20": stock_return20 - spy.trailing_return(row["date"], 20)
            if spy and _finite(stock_return20) and _finite(spy.trailing_return(row["date"], 20)) else None,
            "stock_minus_qqq_return_20": stock_return20 - qqq.trailing_return(row["date"], 20)
            if qqq and _finite(stock_return20) and _finite(qqq.trailing_return(row["date"], 20)) else None,
        }
        output.append({
            **row,
            "factor_lab_split": split_of(row["date"]),
            "candidate_features": candidates,
            "legacy_features": legacy,
            "auxiliary_features": auxiliary,
            "separate_market_context": context,
        })
    target = pathlib.Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    with gzip.open(target / f"factor-lab-events-{year}.jsonl.gz", "wt", encoding="utf-8") as handle:
        for row in output:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    summary = {
        "schema_version": "factor-strategy-lab-year-v2.0.0",
        "experiment_id": EXPERIMENT_ID,
        "year": int(year),
        "source_events": len(source_rows),
        "feature_events": len(output),
        "missing_feature_events": missing,
        "candidate_count": len(CANDIDATES),
        "future_data_used": False,
        "production_scoring_changed": False,
        "industry_point_in_time_available": False,
    }
    (target / f"annual-{year}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def _load_rows(input_dir) -> list[dict]:
    rows = []
    for path in sorted(pathlib.Path(input_dir).rglob("factor-lab-events-*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    return rows


def _eligible(rows: list[dict]) -> list[dict]:
    return [
        row for row in rows
        if split_of(row["date"]) and _finite(row.get("returns", {}).get(str(PRIMARY_HORIZON)))
    ]


def _split_rows(rows: list[dict]) -> dict[str, list[dict]]:
    return {name: [row for row in rows if name == split_of(row["date"])] for name, _, _ in SPLITS}


def _legacy_value(row: dict, key: str) -> float | None:
    if key == "score.current":
        return row.get("scores", {}).get("current")
    return row.get("legacy_features", {}).get(key)


def _quarter(value: str) -> tuple[int, int]:
    parsed = date.fromisoformat(value)
    return parsed.year, (parsed.month - 1) // 3 + 1


def matched_pairs(rows: list[dict]) -> list[dict]:
    pairs = []
    reuse = Counter()
    by_year: dict[int, list[dict]] = defaultdict(list)
    for row in _eligible(rows):
        if row["date"] <= "2024-12-31":
            by_year[int(row["date"][:4])].append(row)
    for year, year_rows in sorted(by_year.items()):
        outcomes = [row["returns"][str(PRIMARY_HORIZON)] for row in year_rows]
        cutoff = percentile(outcomes, 0.90)
        winners = [row for row in year_rows if cutoff is not None and row["returns"][str(PRIMARY_HORIZON)] >= cutoff]
        losers = [row for row in year_rows if row["returns"][str(PRIMARY_HORIZON)] <= 0]
        usable = [row for row in year_rows if all(_finite(_legacy_value(row, key)) for key in BASELINE_COVARIATES)]
        scales = {}
        for key in BASELINE_COVARIATES:
            values = [_legacy_value(row, key) for row in usable]
            scales[key] = statistics.pstdev(values) if len(values) > 1 else 1.0
            if not scales[key]:
                scales[key] = 1.0
        for winner in sorted(winners, key=lambda row: row["returns"][str(PRIMARY_HORIZON)], reverse=True):
            if not all(_finite(_legacy_value(winner, key)) for key in BASELINE_COVARIATES):
                continue
            same_quarter = [row for row in losers if _quarter(row["date"]) == _quarter(winner["date"])]
            pool = same_quarter or losers
            pool = [row for row in pool if all(_finite(_legacy_value(row, key)) for key in BASELINE_COVARIATES)]
            if not pool:
                continue
            winner_day = date.fromisoformat(winner["date"]).toordinal()

            def distance(loser):
                covariate_distance = sum(
                    ((_legacy_value(winner, key) - _legacy_value(loser, key)) / scales[key]) ** 2
                    for key in BASELINE_COVARIATES
                )
                calendar_distance = abs(winner_day - date.fromisoformat(loser["date"]).toordinal()) / 60
                return covariate_distance + calendar_distance ** 2 + reuse[(loser["symbol"], loser["date"])] * 0.25

            loser = min(pool, key=distance)
            matched_distance = distance(loser)
            reuse[(loser["symbol"], loser["date"])] += 1
            pairs.append({
                "year": year,
                "winner": {"symbol": winner["symbol"], "date": winner["date"], "return_20d": winner["returns"]["20"]},
                "loser": {"symbol": loser["symbol"], "date": loser["date"], "return_20d": loser["returns"]["20"]},
                "distance": round(matched_distance, 6),
                "winner_only_existing_factors": sorted(set(winner.get("factors", [])) - set(loser.get("factors", []))),
                "loser_only_existing_factors": sorted(set(loser.get("factors", [])) - set(winner.get("factors", []))),
                "candidate_values": {
                    candidate_id: {
                        "winner": winner["candidate_features"].get(candidate_id),
                        "loser": loser["candidate_features"].get(candidate_id),
                        "difference": winner["candidate_features"].get(candidate_id) - loser["candidate_features"].get(candidate_id)
                        if _finite(winner["candidate_features"].get(candidate_id)) and _finite(loser["candidate_features"].get(candidate_id)) else None,
                    }
                    for candidate_id in CANDIDATES
                },
            })
    return pairs


def matched_summary(pairs: list[dict]) -> dict:
    candidates = []
    for candidate_id, meta in CANDIDATES.items():
        values = [pair["candidate_values"][candidate_id] for pair in pairs]
        values = [value for value in values if _finite(value["difference"])]
        candidates.append({
            "candidate_id": candidate_id,
            "name_zh": meta["name_zh"],
            "family": meta["family"],
            "redundancy_group": meta["redundancy_group"],
            "pairs": len(values),
            "winner_median": round(statistics.median(value["winner"] for value in values), 6) if values else None,
            "loser_median": round(statistics.median(value["loser"] for value in values), 6) if values else None,
            "median_winner_minus_loser": round(statistics.median(value["difference"] for value in values), 6) if values else None,
            "winner_higher_rate": round(sum(value["difference"] > 0 for value in values) / len(values), 6) if values else None,
        })
    factors = sorted({factor for pair in pairs for factor in pair["winner_only_existing_factors"] + pair["loser_only_existing_factors"]})
    existing = []
    for factor in factors:
        winner_hits = sum(factor in pair["winner_only_existing_factors"] for pair in pairs)
        loser_hits = sum(factor in pair["loser_only_existing_factors"] for pair in pairs)
        registered = FACTORS_BY_ID.get(factor)
        existing.append({
            "factor_id": factor,
            "name_zh": registered.name_zh if registered else factor,
            "family": registered.evidence_family if registered else "unclassified",
            "pairs": len(pairs),
            "winner_only_rate": round(winner_hits / len(pairs), 6) if pairs else None,
            "loser_only_rate": round(loser_hits / len(pairs), 6) if pairs else None,
            "net_pair_rate_gap": round((winner_hits - loser_hits) / len(pairs), 6) if pairs else None,
        })
    return {
        "pair_count": len(pairs),
        "matching_covariates": list(BASELINE_COVARIATES),
        "new_candidates": candidates,
        "existing_factors": sorted(existing, key=lambda item: abs(item["net_pair_rate_gap"] or 0), reverse=True),
    }


def _delta(rows: list[dict], condition) -> dict:
    hit = [row for row in rows if condition(row)]
    miss = [row for row in rows if not condition(row)]
    with_factor, without_factor = metrics(hit, PRIMARY_HORIZON), metrics(miss, PRIMARY_HORIZON)
    first = [row["returns"][str(PRIMARY_HORIZON)] for row in hit if _finite(row["returns"].get(str(PRIMARY_HORIZON)))]
    second = [row["returns"][str(PRIMARY_HORIZON)] for row in miss if _finite(row["returns"].get(str(PRIMARY_HORIZON)))]
    sensitivity = {}
    for horizon in HORIZONS:
        if horizon == PRIMARY_HORIZON:
            continue
        hit_metrics, miss_metrics = metrics(hit, horizon), metrics(miss, horizon)
        sensitivity[str(horizon)] = {
            "with": hit_metrics,
            "without": miss_metrics,
            "delta": {
                key: round((hit_metrics.get(key) or 0) - (miss_metrics.get(key) or 0), 5)
                for key in ("win_rate_pct", "median_pct", "trimmed_mean_pct", "profit_factor", "expectancy_pct")
            },
        }
    eligible = [row for row in rows if _finite(row.get("returns", {}).get(str(PRIMARY_HORIZON)))]
    outcomes = [row["returns"][str(PRIMARY_HORIZON)] for row in eligible]
    top_cutoff = percentile(outcomes, 0.90)
    cohorts = {
        "all": eligible,
        "winners": [row for row in eligible if row["returns"][str(PRIMARY_HORIZON)] > 0],
        "top_decile": [row for row in eligible if top_cutoff is not None and row["returns"][str(PRIMARY_HORIZON)] >= top_cutoff],
        "losers": [row for row in eligible if row["returns"][str(PRIMARY_HORIZON)] <= 0],
    }
    return {
        "with": with_factor,
        "without": without_factor,
        "delta": {
            key: round((with_factor.get(key) or 0) - (without_factor.get(key) or 0), 5)
            for key in ("win_rate_pct", "median_pct", "trimmed_mean_pct", "profit_factor", "expectancy_pct")
        },
        "mean_difference_p": round(normal_mean_pvalue(first, second), 7),
        "factor_base_rates": {
            name: round(sum(condition(row) for row in cohort) / len(cohort), 6) if cohort else None
            for name, cohort in cohorts.items()
        },
        "horizon_sensitivity": sensitivity,
    }


def _quintile_metrics(rows: list[dict], candidate_id: str) -> dict:
    eligible = [row for row in rows if _finite(row["candidate_features"].get(candidate_id))]
    ordered = sorted(eligible, key=lambda row: row["candidate_features"][candidate_id])
    groups = {index: [] for index in range(1, 6)}
    for index, row in enumerate(ordered):
        group = min(5, int(5 * index / len(ordered)) + 1) if ordered else 1
        groups[group].append(row)
    return {
        str(group): {
            "value_min": min((row["candidate_features"][candidate_id] for row in group_rows), default=None),
            "value_max": max((row["candidate_features"][candidate_id] for row in group_rows), default=None),
            "metrics_20d": metrics(group_rows, PRIMARY_HORIZON),
        }
        for group, group_rows in groups.items()
    }


def _candidate_direction(discovery: list[dict], candidate_id: str) -> tuple[str, float | None, float | None]:
    values = [row["candidate_features"].get(candidate_id) for row in discovery]
    values = [value for value in values if _finite(value)]
    low, high = percentile(values, 0.20), percentile(values, 0.80)
    if low is None or high is None:
        return "unknown", low, high
    low_metrics = metrics([row for row in discovery if _finite(row["candidate_features"].get(candidate_id)) and row["candidate_features"][candidate_id] <= low], PRIMARY_HORIZON)
    high_metrics = metrics([row for row in discovery if _finite(row["candidate_features"].get(candidate_id)) and row["candidate_features"][candidate_id] >= high], PRIMARY_HORIZON)
    return ("high" if (high_metrics["trimmed_mean_pct"] or -math.inf) >= (low_metrics["trimmed_mean_pct"] or -math.inf) else "low"), low, high


def _threshold(rows: list[dict], candidate_id: str, direction: str) -> float | None:
    values = [row["candidate_features"].get(candidate_id) for row in rows]
    values = [value for value in values if _finite(value)]
    return percentile(values, 0.80 if direction == "high" else 0.20)


def candidate_study(rows: list[dict], pair_summary: dict) -> list[dict]:
    split_rows = _split_rows(rows)
    discovery = split_rows["discovery_2001_2012"]
    pair_by_id = {item["candidate_id"]: item for item in pair_summary["new_candidates"]}
    reports, pvalues = [], []
    for candidate_id, meta in CANDIDATES.items():
        direction, discovery_low, discovery_high = _candidate_direction(discovery, candidate_id)
        periods = {}
        for split_name, _, _ in SPLITS:
            train_end = TRAIN_END_BY_SPLIT[split_name]
            train = [row for row in rows if "2001-01-01" <= row["date"] <= train_end]
            threshold = _threshold(train, candidate_id, direction) if direction != "unknown" else None
            condition = lambda row, candidate_id=candidate_id, direction=direction, threshold=threshold: (
                _finite(row["candidate_features"].get(candidate_id)) and threshold is not None and
                (row["candidate_features"][candidate_id] >= threshold if direction == "high" else row["candidate_features"][candidate_id] <= threshold)
            )
            test_rows = [row for row in split_rows[split_name] if _finite(row["candidate_features"].get(candidate_id))]
            periods[split_name] = {
                "training_end": train_end,
                "threshold": threshold,
                "continuous_quintiles": _quintile_metrics(test_rows, candidate_id),
                **_delta(test_rows, condition),
            }
        pvalues.append(periods["discovery_2001_2012"]["mean_difference_p"])
        reports.append({
            "candidate_id": candidate_id,
            "name_zh": meta["name_zh"],
            "family": meta["family"],
            "source_project": meta["source_project"],
            "direction_from_discovery": direction,
            "discovery_percentiles": {"p20": discovery_low, "p80": discovery_high},
            "matched_control": pair_by_id.get(candidate_id),
            "periods": periods,
        })
    for report, qvalue in zip(reports, bh_adjust(pvalues)):
        report["discovery_bh_q"] = qvalue
        walkforward = [report["periods"][name] for name in WALKFORWARD_SPLITS]
        positive_windows = sum(
            item["delta"]["trimmed_mean_pct"] > 0 and item["delta"]["profit_factor"] > 0
            for item in walkforward
        )
        enough = all(item["with"]["samples"] >= 50 for item in walkforward)
        matched = report.get("matched_control") or {}
        matched_rate = matched.get("winner_higher_rate")
        matched_aligned = _finite(matched_rate) and (
            matched_rate >= 0.55 if report["direction_from_discovery"] == "high" else matched_rate <= 0.45
        )
        cost_positive = sum(
            (item["with"].get("cost_sensitivity", {}).get("50", {}).get("expectancy_pct") or 0) > 0
            for item in walkforward
        ) >= 3
        if not enough:
            verdict = "sample_insufficient"
        elif positive_windows >= 3 and matched_aligned and cost_positive and qvalue <= 0.10:
            verdict = "retain_for_shadow"
        elif positive_windows >= 3 and matched_aligned and qvalue <= 0.25:
            verdict = "observe"
        else:
            verdict = "reject"
        report["walkforward_positive_windows"] = positive_windows
        report["verdict"] = verdict
        report["provisional_condition_weight"] = 1 if verdict == "retain_for_shadow" else 0
    by_family = defaultdict(list)
    for report in reports:
        if report["verdict"] == "retain_for_shadow":
            by_family[report["redundancy_group"]].append(report)
    for family_reports in by_family.values():
        ordered = sorted(
            family_reports,
            key=lambda item: (
                -item["walkforward_positive_windows"],
                item["discovery_bh_q"],
                -abs((item.get("matched_control") or {}).get("median_winner_minus_loser") or 0),
            ),
        )
        ordered[0]["family_selected"] = True
        for duplicate in ordered[1:]:
            duplicate["family_selected"] = False
            duplicate["verdict"] = "observe"
            duplicate["provisional_condition_weight"] = 0
            duplicate["verdict_note"] = "same-family candidate lost the frozen one-per-family comparison"
    return reports


def existing_factor_study(rows: list[dict], pair_summary: dict) -> list[dict]:
    common = {"macd.daily_bull_cross", "qualification.long_trend"}
    factors = sorted({factor for row in rows for factor in row.get("factors", []) if factor not in common})
    split_rows = _split_rows(rows)
    pair_by_id = {item["factor_id"]: item for item in pair_summary["existing_factors"]}
    output, pvalues = [], []
    for factor in factors:
        periods = {
            split_name: _delta(split_rows[split_name], lambda row, factor=factor: factor in row.get("factors", []))
            for split_name, _, _ in SPLITS
        }
        pvalues.append(periods["discovery_2001_2012"]["mean_difference_p"])
        registered = FACTORS_BY_ID.get(factor)
        discovery_delta = periods["discovery_2001_2012"]["delta"]["trimmed_mean_pct"]
        output.append({
            "factor_id": factor,
            "name_zh": registered.name_zh if registered else factor,
            "family": registered.evidence_family if registered else "unclassified",
            "matched_control": pair_by_id.get(factor),
            "direction_from_discovery": "positive" if discovery_delta >= 0 else "negative",
            "periods": periods,
        })
    for report, qvalue in zip(output, bh_adjust(pvalues)):
        report["discovery_bh_q"] = qvalue
        walkforward = [report["periods"][name] for name in WALKFORWARD_SPLITS]
        sign = 1 if report["direction_from_discovery"] == "positive" else -1
        positive = sum(
            item["delta"]["trimmed_mean_pct"] * sign > 0 and item["delta"]["profit_factor"] * sign > 0
            for item in walkforward
        )
        samples = [item["with"]["samples"] for item in walkforward]
        pair_gap = (report.get("matched_control") or {}).get("net_pair_rate_gap")
        matched_aligned = _finite(pair_gap) and abs(pair_gap) >= 0.03 and pair_gap * sign > 0
        if any(sample < 50 for sample in samples):
            verdict = "sample_insufficient"
        elif positive >= 3 and matched_aligned and qvalue <= 0.10:
            verdict = "retain_for_shadow"
        elif positive >= 3 and matched_aligned and qvalue <= 0.25:
            verdict = "observe"
        else:
            verdict = "reject"
        report["walkforward_positive_windows"] = positive
        report["verdict"] = verdict
        report["provisional_weight"] = sign if verdict == "retain_for_shadow" else 0
    by_family = defaultdict(list)
    for report in output:
        if report["verdict"] == "retain_for_shadow":
            by_family[report["family"]].append(report)
    for family_reports in by_family.values():
        ordered = sorted(
            family_reports,
            key=lambda item: (-item["walkforward_positive_windows"], item["discovery_bh_q"]),
        )
        ordered[0]["family_selected"] = True
        for duplicate in ordered[1:]:
            duplicate["family_selected"] = False
            duplicate["verdict"] = "observe"
            duplicate["provisional_weight"] = 0
            duplicate["verdict_note"] = "same-family factor lost the frozen one-per-family comparison"
    return output


def unseen_forward_hypotheses(rows: list[dict]) -> dict:
    """Generate bounded post-hoc hypotheses without relabeling them validation.

    Both development-fitted tails are enumerated for every continuous candidate.
    A tail is retained only when trimmed-mean and Profit-Factor deltas keep the
    same sign in development, seen-2025 and seen-2026, with at least 100 hits in
    every period.  The output is a future test queue, never a production action.
    """
    development = [row for row in rows if row["date"] <= "2024-12-31"]
    seen_2025 = [row for row in rows if row["date"].startswith("2025-")]
    seen_2026 = [row for row in rows if row["date"] >= "2026-01-01"]
    period_rows = {
        "development_2001_2024": development,
        "seen_2025": seen_2025,
        "seen_2026": seen_2026,
    }
    hypotheses = []
    for candidate_id, meta in CANDIDATES.items():
        values = [row["candidate_features"].get(candidate_id) for row in development]
        values = [value for value in values if _finite(value)]
        for tail, quantile in (("low", 0.20), ("high", 0.80)):
            threshold = percentile(values, quantile)
            if threshold is None:
                continue
            condition = lambda row, candidate_id=candidate_id, tail=tail, threshold=threshold: (
                _finite(row["candidate_features"].get(candidate_id)) and
                (row["candidate_features"][candidate_id] <= threshold if tail == "low"
                 else row["candidate_features"][candidate_id] >= threshold)
            )
            periods = {name: _delta(period, condition) for name, period in period_rows.items()}
            enough = all(item["with"]["samples"] >= 100 for item in periods.values())
            trimmed = [item["delta"]["trimmed_mean_pct"] for item in periods.values()]
            profit_factor = [item["delta"]["profit_factor"] for item in periods.values()]
            direction = (
                "positive" if enough and all(value > 0 for value in trimmed + profit_factor)
                else "negative" if enough and all(value < 0 for value in trimmed + profit_factor)
                else None
            )
            if direction is None:
                continue
            hypotheses.append({
                "candidate_id": candidate_id,
                "name_zh": meta["name_zh"],
                "tail": tail,
                "development_fitted_threshold": round(threshold, 6),
                "direction": direction,
                "periods": periods,
                "production_weight": 0,
                "shadow_weight": -1 if direction == "negative" else 0,
                "status": "freeze_for_unseen_forward",
                "why_not_production": "selected after reviewing development and already-seen 2025/2026; requires events after 2026-08-29",
            })
    return {
        "role": "hypothesis_generation_only",
        "selection_rule": "enumerate both development-fitted 20% tails; require same-sign trimmed-mean and PF deltas in development, seen-2025 and seen-2026; minimum 100 hits per period",
        "selection_used_seen_periods": True,
        "true_unseen_forward_starts_after": "2026-08-29",
        "production_action": "none",
        "items": hypotheses,
    }


def _percent_rank(values: list[float], current: float) -> float | None:
    clean = [value for value in values if _finite(value)]
    return round(100 * sum(value <= current for value in clean) / len(clean), 2) if clean else None


def case_cards(rows: list[dict], pairs: list[dict], count: int = 20) -> dict:
    development = [row for row in _eligible(rows) if row["date"] <= "2024-12-31"]
    ordered = sorted(development, key=lambda row: row["returns"][str(PRIMARY_HORIZON)])
    factor_universe = sorted({factor for row in development for factor in row.get("factors", [])})
    pair_by_winner = {(pair["winner"]["symbol"], pair["winner"]["date"]): pair for pair in pairs}
    by_year = defaultdict(list)
    for row in development:
        by_year[row["date"][:4]].append(row)

    def card(row):
        year_rows = by_year[row["date"][:4]]
        matched = pair_by_winner.get((row["symbol"], row["date"]))
        return {
            "symbol": row["symbol"],
            "date": row["date"],
            "return_20d_pct": round(100 * row["returns"]["20"], 4),
            "existing_factors": row.get("factors", []),
            "missing_existing_factors": sorted(set(factor_universe) - set(row.get("factors", []))),
            "matched_failure": {
                "symbol": matched["loser"]["symbol"],
                "date": matched["loser"]["date"],
                "return_20d_pct": round(100 * matched["loser"]["return_20d"], 4),
                "winner_only_existing_factors": matched["winner_only_existing_factors"],
                "failure_only_existing_factors": matched["loser_only_existing_factors"],
            } if matched else None,
            "new_candidates": {
                candidate_id: {
                    "value": row["candidate_features"].get(candidate_id),
                    "same_year_percentile": _percent_rank(
                        [item["candidate_features"].get(candidate_id) for item in year_rows],
                        row["candidate_features"].get(candidate_id),
                    ) if _finite(row["candidate_features"].get(candidate_id)) else None,
                }
                for candidate_id in CANDIDATES
            },
            "audit_note": "case study only; never selects a threshold or production weight",
        }
    return {
        "top_winners": [card(row) for row in reversed(ordered[-count:])],
        "top_losers": [card(row) for row in ordered[:count]],
    }


def aggregate(input_dir, out, detail_out=None) -> dict:
    all_rows = _load_rows(input_dir)
    if not all_rows:
        raise RuntimeError("No factor-lab annual checkpoints found")
    primary = _eligible(deduplicate(all_rows, 120))
    pairs = matched_pairs(primary)
    pair_report = matched_summary(pairs)
    candidates = candidate_study(primary, pair_report)
    existing = existing_factor_study(primary, pair_report)
    annual = [json.loads(path.read_text()) for path in sorted(pathlib.Path(input_dir).rglob("annual-*.json"))]
    forward_hypotheses = unseen_forward_hypotheses(primary)
    report = {
        "schema_version": "factor-strategy-lab-v2.0.1",
        "experiment_id": EXPERIMENT_ID,
        "generated_at": datetime.now().astimezone().isoformat(),
        "event_gate": "exact completed daily MACD bullish cross plus archived long-trend qualification",
        "production_scoring_changed": False,
        "candidate_catalog": "research/factor-candidates-v2.json",
        "coverage": {
            "start": min(row["date"] for row in all_rows),
            "end": max(row["date"] for row in all_rows),
            "feature_events": len(all_rows),
            "primary_120_session_deduplicated_mature_events": len(primary),
            "matched_winner_loser_pairs": len(pairs),
            "candidate_factors": len(CANDIDATES),
            "existing_factors": len(existing),
            "split_events": {name: len(rows) for name, rows in _split_rows(primary).items()},
        },
        "method": {
            "primary_horizon_sessions": PRIMARY_HORIZON,
            "matched_winner": "top 10% 20-session return inside each calendar year",
            "matched_loser": "20-session return <= 0, same quarter when available",
            "matching_covariates": list(BASELINE_COVARIATES),
            "matching_excludes": "new candidate values and all future path fields",
            "walkforward": list(WALKFORWARD_SPLITS),
            "seen_periods": ["seen_2025", "seen_2026"],
            "true_unseen_forward_starts_after": "2026-08-29",
            "multiple_testing": "Benjamini-Hochberg within new-candidate and existing-factor families",
        },
        "matched_control_summary": pair_report,
        "new_candidate_results": candidates,
        "existing_factor_results": existing,
        "unseen_forward_hypotheses": forward_hypotheses,
        "case_cards": case_cards(primary, pairs),
        "actions": {
            "new_candidates": {
                verdict: [item["candidate_id"] for item in candidates if item["verdict"] == verdict]
                for verdict in ("retain_for_shadow", "observe", "reject", "sample_insufficient")
            },
            "existing_factors": {
                verdict: [item["factor_id"] for item in existing if item["verdict"] == verdict]
                for verdict in ("retain_for_shadow", "observe", "reject", "sample_insufficient")
            },
            "unseen_forward_hypotheses": {
                "positive_observation": [
                    item["candidate_id"] for item in forward_hypotheses["items"]
                    if item["direction"] == "positive"
                ],
                "risk_penalty_shadow": [
                    item["candidate_id"] for item in forward_hypotheses["items"]
                    if item["shadow_weight"] < 0
                ],
            },
            "production_action": "none; any shadow challenger requires separate approval and model version",
        },
        "annual_coverage": annual,
        "limitations": [
            "candidate definitions were proposed after prior 2025/2026 results were viewed, so historical walk-forward is retrospective evidence",
            "2025 and 2026 are seen-period rechecks, not fresh independent validation",
            "historical point-in-time stock-industry membership is unavailable and is not imputed",
            "historical delisted, ticker-change and corporate-action coverage remains partial",
            "matched controls reduce measured confounding but do not prove causality",
            "event-level results are not a capital-constrained portfolio",
        ],
    }
    target = pathlib.Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if detail_out:
        detail = pathlib.Path(detail_out)
        detail.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(detail, "wt", encoding="utf-8") as handle:
            json.dump({"experiment_id": EXPERIMENT_ID, "pairs": pairs}, handle, ensure_ascii=False, separators=(",", ":"))
    return report


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    annual = subparsers.add_parser("year")
    annual.add_argument("--input-dir", required=True)
    annual.add_argument("--cache-dir", default="work/eodhd-cache")
    annual.add_argument("--year", type=int, required=True)
    annual.add_argument("--out-dir", required=True)
    combined = subparsers.add_parser("aggregate")
    combined.add_argument("--input-dir", required=True)
    combined.add_argument("--out", required=True)
    combined.add_argument("--detail-out")
    args = parser.parse_args()
    result = (
        enrich_year(args.input_dir, args.cache_dir, args.year, args.out_dir)
        if args.command == "year" else aggregate(args.input_dir, args.out, args.detail_out)
    )
    print(json.dumps(result.get("coverage", result), ensure_ascii=False))


if __name__ == "__main__":
    main()
