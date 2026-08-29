"""Winner/loser driven factor discovery and frozen challenger optimization.

The experiment consumes the audited V2 event artifacts.  Annual jobs join only
the already-restored price cache to add point-in-time continuous features.  The
aggregate job discovers thresholds and weights before reading validation
performance, then reports 2025 and 2026 without changing production scoring.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import pathlib
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from research.backtest.reused_event_study_v2 import (
    _load_enriched,
    _spearman,
    deduplicate,
    metrics,
    percentile,
)
from services.scanner.factor_registry import FACTORS_BY_ID
from services.scanner.macd_factor_backtest import adjusted_rows
from services.scanner.technical import atr, ema, macd, rsi


EXPERIMENT_ID = "winner-loser-strategy-optimization-v1.0.0-2026-08-29"
PRIMARY_HORIZON = 20
MAX_COHORT = 100
MAX_SELECTED = 8
SPLITS = (
    ("discovery", "2001-01-01", "2018-12-31"),
    ("calibration", "2019-01-01", "2024-12-31"),
    ("validation_2025", "2025-01-01", "2025-12-31"),
    ("forward_2026", "2026-01-01", "9999-12-31"),
)


FEATURES = {
    "trend.ema21_vs_50_pct": ("trend", "EMA21相对EMA50"),
    "trend.ema50_slope_20_pct": ("trend", "EMA50二十日斜率"),
    "trend.ema200_slope_60_pct": ("trend", "EMA200六十日斜率"),
    "momentum.return_5_pct": ("momentum", "信号前5日涨跌"),
    "momentum.return_20_pct": ("momentum", "信号前20日涨跌"),
    "momentum.return_60_pct": ("momentum", "信号前60日涨跌"),
    "location.pullback_60d_pct": ("location", "距60日高点回撤"),
    "location.range_60d_position": ("location", "60日区间位置"),
    "location.ema21_distance_pct": ("location", "距EMA21"),
    "location.ema50_distance_pct": ("location", "距EMA50"),
    "location.ema200_distance_pct": ("location", "距EMA200"),
    "momentum.rsi14": ("momentum", "RSI14"),
    "momentum.macd_histogram_pct": ("momentum", "MACD柱占价格"),
    "momentum.macd_histogram_change_3_pct": ("momentum", "MACD柱三日变化"),
    "volume.relative_20": ("volume", "当日相对20日量"),
    "volume.average_5_vs_20": ("volume", "5日均量相对20日"),
    "volatility.atr14_pct": ("volatility", "ATR14占价格"),
    "volatility.realized_20": ("volatility", "20日已实现波动"),
    "candle.close_location": ("candle", "收盘在当日区间位置"),
    "candle.body_atr": ("candle", "实体相对ATR"),
    "candle.open_gap_pct": ("candle", "信号日开盘跳空"),
}

MARKET_FEATURES = {
    "market.spy_above_ema200_pct": ("market", "SPY距EMA200"),
    "market.spy_pullback_60d_pct": ("market", "SPY距60日高点"),
    "market.spy_return_20_pct": ("market", "SPY近20日涨跌"),
    "market.qqq_above_ema200_pct": ("market", "QQQ距EMA200"),
    "market.qqq_pullback_60d_pct": ("market", "QQQ距60日高点"),
    "market.qqq_return_20_pct": ("market", "QQQ近20日涨跌"),
}

MODEL_13_SHADOW = {
    "volume.bottom_expansion",
    "structure.support_bullish_engulfing",
    "structure.trendline_three_push",
    "structure.bottom_bullish_engulfing",
    "macd.weekly_histogram_improving",
}


def split_of(value: str) -> str | None:
    return next((name for name, lo, hi in SPLITS if lo <= value <= hi), None)


def _safe_ratio(first: float | None, second: float | None) -> float | None:
    if first is None or second in (None, 0):
        return None
    return first / second


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


@dataclass
class FeatureSeries:
    rows: list[dict]

    def __post_init__(self):
        self.index = {row["date"]: index for index, row in enumerate(self.rows)}
        self.closes = [float(row["close"]) for row in self.rows]
        self.volumes = [float(row.get("volume") or 0) for row in self.rows]
        self.ema21 = ema(self.closes, 21)
        self.ema50 = ema(self.closes, 50)
        self.ema200 = ema(self.closes, 200)
        self.rsi14 = rsi(self.closes, 14)
        self.atr14 = atr(self.rows, 14)
        line, signal = macd(self.closes)
        self.histogram = [first - second for first, second in zip(line, signal)]

    def _return(self, index: int, sessions: int) -> float | None:
        if index < sessions or self.closes[index - sessions] <= 0:
            return None
        return self.closes[index] / self.closes[index - sessions] - 1

    def technical(self, signal_date: str) -> dict[str, float | None]:
        index = self.index.get(signal_date)
        if index is None or index < 200:
            return {name: None for name in FEATURES}
        row = self.rows[index]
        close = self.closes[index]
        prior60 = self.rows[max(0, index - 60):index]
        range60 = self.rows[max(0, index - 59):index + 1]
        high60 = max(float(item["high"]) for item in prior60) if prior60 else None
        low_range = min(float(item["low"]) for item in range60)
        high_range = max(float(item["high"]) for item in range60)
        range_width = high_range - low_range
        prior20_volume = self.volumes[max(0, index - 20):index]
        recent5_volume = self.volumes[max(0, index - 4):index + 1]
        avg20_volume = statistics.fmean(prior20_volume) if prior20_volume else None
        avg5_volume = statistics.fmean(recent5_volume) if recent5_volume else None
        daily_returns = [
            self.closes[position] / self.closes[position - 1] - 1
            for position in range(max(1, index - 19), index + 1)
            if self.closes[position - 1] > 0
        ]
        bar_range = float(row["high"]) - float(row["low"])
        atr_value = self.atr14[index]
        prior_close = self.closes[index - 1]
        values = {
            "trend.ema21_vs_50_pct": _safe_ratio(self.ema21[index], self.ema50[index]),
            "trend.ema50_slope_20_pct": _safe_ratio(self.ema50[index], self.ema50[index - 20]),
            "trend.ema200_slope_60_pct": _safe_ratio(self.ema200[index], self.ema200[index - 60]),
            "momentum.return_5_pct": self._return(index, 5),
            "momentum.return_20_pct": self._return(index, 20),
            "momentum.return_60_pct": self._return(index, 60),
            "location.pullback_60d_pct": _safe_ratio(close, high60),
            "location.range_60d_position": (close - low_range) / range_width if range_width > 0 else None,
            "location.ema21_distance_pct": _safe_ratio(close, self.ema21[index]),
            "location.ema50_distance_pct": _safe_ratio(close, self.ema50[index]),
            "location.ema200_distance_pct": _safe_ratio(close, self.ema200[index]),
            "momentum.rsi14": self.rsi14[index],
            "momentum.macd_histogram_pct": _safe_ratio(self.histogram[index], close),
            "momentum.macd_histogram_change_3_pct": _safe_ratio(self.histogram[index] - self.histogram[index - 3], close),
            "volume.relative_20": _safe_ratio(self.volumes[index], avg20_volume),
            "volume.average_5_vs_20": _safe_ratio(avg5_volume, avg20_volume),
            "volatility.atr14_pct": _safe_ratio(atr_value, close),
            "volatility.realized_20": statistics.pstdev(daily_returns) if len(daily_returns) >= 10 else None,
            "candle.close_location": (close - float(row["low"])) / bar_range if bar_range > 0 else None,
            "candle.body_atr": abs(close - float(row["open"])) / atr_value if atr_value and atr_value > 0 else None,
            "candle.open_gap_pct": float(row["open"]) / prior_close - 1 if prior_close > 0 else None,
        }
        for key in (
            "trend.ema21_vs_50_pct",
            "trend.ema50_slope_20_pct",
            "trend.ema200_slope_60_pct",
            "location.pullback_60d_pct",
            "location.ema21_distance_pct",
            "location.ema50_distance_pct",
            "location.ema200_distance_pct",
        ):
            if values[key] is not None:
                values[key] -= 1
        return {key: value if _finite(value) else None for key, value in values.items()}

    def market(self, signal_date: str, prefix: str) -> dict[str, float | None]:
        index = self.index.get(signal_date)
        if index is None or index < 200:
            return {
                f"market.{prefix}_above_ema200_pct": None,
                f"market.{prefix}_pullback_60d_pct": None,
                f"market.{prefix}_return_20_pct": None,
            }
        close = self.closes[index]
        prior60 = self.closes[max(0, index - 60):index]
        return {
            f"market.{prefix}_above_ema200_pct": close / self.ema200[index] - 1,
            f"market.{prefix}_pullback_60d_pct": close / max(prior60) - 1 if prior60 else None,
            f"market.{prefix}_return_20_pct": self._return(index, 20),
        }


class FeatureLoader:
    def __init__(self, cache_dir: str | pathlib.Path):
        self.cache_dir = pathlib.Path(cache_dir)
        self.cache: dict[str, FeatureSeries | None] = {}

    def __call__(self, symbol: str) -> FeatureSeries | None:
        if symbol not in self.cache:
            path = self.cache_dir / f"{symbol}.json"
            try:
                raw = json.loads(path.read_text()) if path.exists() else None
                self.cache[symbol] = FeatureSeries(adjusted_rows(raw)) if raw else None
            except (json.JSONDecodeError, KeyError, TypeError, ValueError, statistics.StatisticsError):
                self.cache[symbol] = None
        return self.cache[symbol]


def enrich_year(input_dir, cache_dir, year: int, out_dir):
    rows = [row for row in _load_enriched(input_dir) if int(row["date"][:4]) == int(year)]
    loader = FeatureLoader(cache_dir)
    spy, qqq = loader("SPY"), loader("QQQ")
    enriched, missing = [], 0
    for row in rows:
        series = loader(row["symbol"])
        if series is None:
            missing += 1
            continue
        features = series.technical(row["date"])
        if not any(_finite(value) for value in features.values()):
            missing += 1
            continue
        market = {}
        market.update(spy.market(row["date"], "spy") if spy else {})
        market.update(qqq.market(row["date"], "qqq") if qqq else {})
        enriched.append({**row, "optimization_split": split_of(row["date"]), "features": features, "market_features": market})
    target = pathlib.Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    event_path = target / f"winner-loser-events-{year}.jsonl.gz"
    with gzip.open(event_path, "wt", encoding="utf-8") as handle:
        for row in enriched:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    summary = {
        "schema_version": "winner-loser-strategy-optimization-year-v1.0.0",
        "experiment_id": EXPERIMENT_ID,
        "year": int(year),
        "source_events": len(rows),
        "feature_events": len(enriched),
        "missing_feature_events": missing,
        "future_data_used": False,
        "industry_point_in_time_available": False,
    }
    (target / f"annual-{year}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def _load_feature_rows(input_dir) -> list[dict]:
    rows = []
    for path in sorted(pathlib.Path(input_dir).rglob("winner-loser-events-*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    return rows


def _eligible(rows: list[dict]) -> list[dict]:
    return [row for row in rows if _finite(row.get("returns", {}).get(str(PRIMARY_HORIZON)))]


def _ordered(rows: list[dict]) -> list[dict]:
    return sorted(_eligible(rows), key=lambda row: row["returns"][str(PRIMARY_HORIZON)])


def _tail_groups(rows: list[dict]) -> dict[str, list[dict]]:
    ordered = _ordered(rows)
    decile = max(1, math.ceil(len(ordered) * 0.10)) if ordered else 0
    return {
        "all": ordered,
        "top100": ordered[-MAX_COHORT:],
        "bottom100": ordered[:MAX_COHORT],
        "top_decile": ordered[-decile:] if decile else [],
        "bottom_decile": ordered[:decile] if decile else [],
    }


def _rate(rows: list[dict], condition) -> float | None:
    return sum(condition(row) for row in rows) / len(rows) if rows else None


def _factor_commonality(rows: list[dict]) -> list[dict]:
    groups = _tail_groups(rows)
    factors = sorted({factor for row in groups["all"] for factor in row.get("factors", [])})
    output = []
    for factor in factors:
        condition = lambda row, factor=factor: factor in row.get("factors", [])
        rates = {name: _rate(group, condition) for name, group in groups.items()}
        registered = FACTORS_BY_ID.get(factor)
        output.append({
            "factor_id": factor,
            "family": registered.evidence_family if registered else "unclassified",
            "rates": rates,
            "top100_vs_bottom100_pp": round(100 * ((rates["top100"] or 0) - (rates["bottom100"] or 0)), 3),
            "top_decile_enrichment": round((rates["top_decile"] or 0) / rates["all"], 4) if rates["all"] else None,
            "bottom_decile_enrichment": round((rates["bottom_decile"] or 0) / rates["all"], 4) if rates["all"] else None,
        })
    return sorted(output, key=lambda item: abs(item["top100_vs_bottom100_pp"]), reverse=True)


def _feature_commonality(rows: list[dict], namespace: str = "features") -> list[dict]:
    groups = _tail_groups(rows)
    names = FEATURES if namespace == "features" else MARKET_FEATURES
    output = []
    for feature, (family, label) in names.items():
        medians = {}
        for group_name, group in groups.items():
            values = [row.get(namespace, {}).get(feature) for row in group]
            values = [value for value in values if _finite(value)]
            medians[group_name] = statistics.median(values) if values else None
        all_values = [row.get(namespace, {}).get(feature) for row in groups["all"]]
        all_values = [value for value in all_values if _finite(value)]
        scale = statistics.pstdev(all_values) if len(all_values) > 1 else 0
        contrast = (
            (medians["top100"] - medians["bottom100"]) / scale
            if scale and medians["top100"] is not None and medians["bottom100"] is not None
            else None
        )
        output.append({"feature_id": feature, "name_zh": label, "family": family, "medians": medians, "standardized_top100_bottom100": round(contrast, 5) if contrast is not None else None})
    return sorted(output, key=lambda item: abs(item["standardized_top100_bottom100"] or 0), reverse=True)


def _delta_metrics(rows: list[dict], condition) -> dict:
    hit = [row for row in rows if condition(row)]
    miss = [row for row in rows if not condition(row)]
    with_metrics, without_metrics = metrics(hit, PRIMARY_HORIZON), metrics(miss, PRIMARY_HORIZON)
    return {
        "with": with_metrics,
        "without": without_metrics,
        "delta": {
            key: round((with_metrics.get(key) or 0) - (without_metrics.get(key) or 0), 4)
            for key in ("win_rate_pct", "median_pct", "trimmed_mean_pct", "profit_factor", "expectancy_pct")
        },
    }


def _candidate_record(candidate_id, name_zh, family, source, direction, threshold, condition, split_rows):
    periods = {name: _delta_metrics(rows, condition) for name, rows in split_rows.items()}
    discovery_groups = _tail_groups(split_rows["discovery"])
    rates = {name: _rate(group, condition) for name, group in discovery_groups.items()}
    annual = {}
    development_rows = split_rows["discovery"] + split_rows["calibration"]
    for year in sorted({row["date"][:4] for row in development_rows}):
        year_rows = [row for row in development_rows if row["date"].startswith(year)]
        annual[year] = _delta_metrics(year_rows, condition)["delta"]["trimmed_mean_pct"] if year_rows else None
    annual_values = [value for value in annual.values() if value is not None]
    expected_sign = 1 if direction == "positive" else -1
    annual_consistency = sum(value * expected_sign > 0 for value in annual_values) / len(annual_values) if annual_values else 0
    return {
        "candidate_id": candidate_id,
        "name_zh": name_zh,
        "family": family,
        "source": source,
        "direction": direction,
        "threshold": threshold,
        "discovery_tail_rates": rates,
        "periods": periods,
        "annual_trimmed_mean_delta_pct": annual,
        "annual_direction_consistency": round(annual_consistency, 4),
    }


def _candidate_conditions(primary: list[dict]):
    split_rows = {name: [row for row in primary if row.get("optimization_split") == name] for name, _, _ in SPLITS}
    discovery = split_rows["discovery"]
    candidates, conditions = [], {}
    factors = sorted({factor for row in discovery for factor in row.get("factors", [])})
    for factor in factors:
        registered = FACTORS_BY_ID.get(factor)
        family = registered.evidence_family if registered else "unclassified"
        name_zh = registered.name_zh if registered else factor
        condition = lambda row, factor=factor: factor in row.get("factors", [])
        groups = _tail_groups(discovery)
        top, bottom = _rate(groups["top100"], condition) or 0, _rate(groups["bottom100"], condition) or 0
        direction = "positive" if top >= bottom else "negative"
        candidate_id = f"existing:{factor}"
        candidates.append(_candidate_record(candidate_id, name_zh, family, "existing_factor", direction, None, condition, split_rows))
        conditions[candidate_id] = condition
    for feature, (family, label) in FEATURES.items():
        values = [row.get("features", {}).get(feature) for row in discovery]
        values = [value for value in values if _finite(value)]
        low, high = percentile(values, 0.20), percentile(values, 0.80)
        if low is None or high is None:
            continue
        for side, threshold, operator in (("low", low, "<="), ("high", high, ">=")):
            if side == "low":
                condition = lambda row, feature=feature, threshold=threshold: _finite(row.get("features", {}).get(feature)) and row["features"][feature] <= threshold
            else:
                condition = lambda row, feature=feature, threshold=threshold: _finite(row.get("features", {}).get(feature)) and row["features"][feature] >= threshold
            groups = _tail_groups(discovery)
            top, bottom = _rate(groups["top100"], condition) or 0, _rate(groups["bottom100"], condition) or 0
            direction = "positive" if top >= bottom else "negative"
            candidate_id = f"new:{feature}:{side}"
            candidates.append(_candidate_record(candidate_id, f"{label}（{side}）", family, "continuous_feature", direction, {"operator": operator, "value": threshold}, condition, split_rows))
            conditions[candidate_id] = condition
    return candidates, conditions, split_rows


def _select_candidates(candidates: list[dict]) -> list[dict]:
    qualified = []
    for item in candidates:
        sign = 1 if item["direction"] == "positive" else -1
        rates = item["discovery_tail_rates"]
        tail_gap = ((rates.get("top100") or 0) - (rates.get("bottom100") or 0)) * sign
        discovery = item["periods"]["discovery"]
        calibration = item["periods"]["calibration"]
        discovery_delta = discovery["delta"]["trimmed_mean_pct"] * sign
        calibration_delta = calibration["delta"]["trimmed_mean_pct"] * sign
        calibration_pf = calibration["delta"]["profit_factor"] * sign
        enough = discovery["with"]["samples"] >= 100 and calibration["with"]["samples"] >= 100
        if not (enough and tail_gap >= 0.05 and discovery_delta > 0 and calibration_delta > 0 and calibration_pf > 0 and item["annual_direction_consistency"] >= 0.50):
            continue
        strength = tail_gap * 4 + discovery_delta + calibration_delta + abs(calibration_pf)
        weight = 2 if tail_gap >= 0.15 and calibration_delta >= 0.25 and item["annual_direction_consistency"] >= 0.60 else 1
        qualified.append({**item, "weight": weight * sign, "selection_strength": round(strength, 5)})
    chosen = []
    for item in sorted(qualified, key=lambda row: row["selection_strength"], reverse=True):
        if item["family"] in {row["family"] for row in chosen}:
            continue
        chosen.append(item)
        if len(chosen) >= MAX_SELECTED:
            break
    return chosen


def _model13_score(row: dict) -> float:
    groups = set()
    score = 0.0
    for factor_id in sorted(MODEL_13_SHADOW.intersection(row.get("factors", []))):
        registered = FACTORS_BY_ID.get(factor_id)
        group = registered.redundancy_group if registered else factor_id
        if group not in groups:
            score += 1
            groups.add(group)
    return score


def _score_rows(rows: list[dict], selected: list[dict], conditions: dict) -> None:
    for row in rows:
        challenger = sum(item["weight"] for item in selected if conditions[item["candidate_id"]](row))
        row.setdefault("scores", {})["model_1_3_shadow"] = _model13_score(row)
        row["scores"]["winner_loser_challenger"] = challenger


def _midrank_quintiles(rows: list[dict], score_name: str) -> dict[int, list[dict]]:
    groups: dict[int, list[dict]] = defaultdict(list)
    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_day[row["date"]].append(row)
    for day_rows in by_day.values():
        ordered = sorted(day_rows, key=lambda row: row.get("scores", {}).get(score_name, 0))
        total = len(ordered)
        start = 0
        while start < total:
            end = start + 1
            while end < total and ordered[end].get("scores", {}).get(score_name, 0) == ordered[start].get("scores", {}).get(score_name, 0):
                end += 1
            midrank = ((start + 1) + end) / 2
            quintile = min(5, max(1, math.ceil(5 * midrank / total)))
            groups[quintile].extend(ordered[start:end])
            start = end
    return groups


def _score_report(rows: list[dict], score_name: str) -> dict:
    groups = _midrank_quintiles(rows, score_name)
    return {
        "samples": len(_eligible(rows)),
        "spearman_20d": _spearman(rows, score_name, PRIMARY_HORIZON),
        "daily_midrank_quintiles": {
            str(group): metrics(groups.get(group, []), PRIMARY_HORIZON)
            for group in range(1, 6)
        },
        "exact_scores": {
            str(score): metrics([row for row in rows if row.get("scores", {}).get(score_name, 0) == score], PRIMARY_HORIZON)
            for score in sorted({row.get("scores", {}).get(score_name, 0) for row in rows})
        },
    }


def _cohort_detail(rows: list[dict]) -> dict:
    groups = _tail_groups(rows)
    def compact(row):
        return {
            "symbol": row["symbol"],
            "date": row["date"],
            "return_20d_pct": round(100 * row["returns"][str(PRIMARY_HORIZON)], 4),
            "factors": row.get("factors", []),
            "features": row.get("features", {}),
            "market_features": row.get("market_features", {}),
        }
    return {"top100": [compact(row) for row in reversed(groups["top100"])], "bottom100": [compact(row) for row in groups["bottom100"]]}


def _challenger_verdict(split_rows: dict[str, list[dict]], score_reports: dict) -> tuple[str, dict]:
    checks = {}
    for name in ("validation_2025", "forward_2026"):
        all_metrics = metrics(split_rows[name], PRIMARY_HORIZON, 50)
        top_metrics = score_reports[name]["daily_midrank_quintiles"]["5"]["cost_sensitivity"]["50"] if score_reports[name]["daily_midrank_quintiles"]["5"].get("cost_sensitivity") else metrics([], PRIMARY_HORIZON, 50)
        top_raw = score_reports[name]["daily_midrank_quintiles"]["5"]
        checks[name] = {
            "top_samples": top_raw["samples"],
            "spearman_positive": (score_reports[name]["spearman_20d"] or 0) > 0,
            "net_expectancy_uplift_pct": round((top_metrics.get("expectancy_pct") or 0) - (all_metrics.get("expectancy_pct") or 0), 4),
            "profit_factor_uplift": round((top_metrics.get("profit_factor") or 0) - (all_metrics.get("profit_factor") or 0), 4),
        }
    passed = (
        checks["validation_2025"]["top_samples"] >= 100
        and checks["forward_2026"]["top_samples"] >= 75
        and checks["validation_2025"]["spearman_positive"]
        and checks["forward_2026"]["spearman_positive"]
        and checks["validation_2025"]["net_expectancy_uplift_pct"] > 0
        and checks["validation_2025"]["profit_factor_uplift"] > 0
        and checks["forward_2026"]["net_expectancy_uplift_pct"] >= 0
        and checks["forward_2026"]["profit_factor_uplift"] >= 0
    )
    return ("validated_challenger" if passed else "not_validated"), checks


def aggregate(input_dir, out, detail_out=None):
    all_rows = _load_feature_rows(input_dir)
    if not all_rows:
        raise RuntimeError("No enriched winner/loser checkpoints found")
    primary = deduplicate(all_rows, 120)
    candidates, conditions, split_rows = _candidate_conditions(primary)
    selected = _select_candidates(candidates)
    _score_rows(primary, selected, conditions)
    split_rows = {name: [row for row in primary if row.get("optimization_split") == name] for name, _, _ in SPLITS}
    score_reports = {
        name: {
            score_name: _score_report(rows, score_name)
            for score_name in ("current", "model_1_3_shadow", "winner_loser_challenger")
        }
        for name, rows in split_rows.items()
    }
    challenger_reports = {name: report["winner_loser_challenger"] for name, report in score_reports.items()}
    verdict, checks = _challenger_verdict(split_rows, challenger_reports)
    development_rows = split_rows["discovery"] + split_rows["calibration"]
    full_commonality = _factor_commonality(development_rows)
    feature_commonality = _feature_commonality(development_rows)
    market_commonality = _feature_commonality(development_rows, "market_features")
    report = {
        "schema_version": "winner-loser-strategy-optimization-v1.0.0",
        "experiment_id": EXPERIMENT_ID,
        "generated_at": datetime.now().astimezone().isoformat(),
        "production_scoring_changed": False,
        "coverage": {
            "all_feature_events": len(all_rows),
            "primary_120_session_deduplicated_events": len(primary),
            "split_events": {name: len(_eligible(rows)) for name, rows in split_rows.items()},
            "start": min(row["date"] for row in all_rows),
            "end": max(row["date"] for row in all_rows),
        },
        "definitions": {
            "primary_horizon_sessions": PRIMARY_HORIZON,
            "full_development_review":"top and bottom 100 in 2001-2024",
            "discovery":"2001-2018 only",
            "internal_calibration":"2019-2024 only",
            "validation_lock":"2025 and 2026 never select features, thresholds or weights",
            "continuous_thresholds":"discovery 20th/80th percentiles only",
            "industry":"historical stock-level industry factors unavailable without dated membership",
        },
        "development_commonality": {
            "existing_factors": full_commonality,
            "continuous_features": feature_commonality,
            "separate_market_features": market_commonality,
        },
        "candidate_count": len(candidates),
        "selected_challenger": [{key: value for key, value in item.items() if key not in {"periods", "annual_trimmed_mean_delta_pct"}} for item in selected],
        "candidate_evidence": candidates,
        "score_comparison": score_reports,
        "validation_checks": checks,
        "verdict": verdict,
        "recommended_changes": {
            "add_or_reweight": [{"candidate_id": item["candidate_id"], "name_zh": item["name_zh"], "weight": item["weight"], "family": item["family"]} for item in selected],
            "production_action": "open a separately approved model version" if verdict == "validated_challenger" else "keep production 1.3.0 unchanged",
        },
        "industry_result": {
            "historical_stock_industry_optimization":"unavailable",
            "reason":"No point-in-time stock-industry membership exists for the full history; current labels are not backfilled.",
            "usable_evidence":"Keep industry ETF pullback-at-support research separate and continue dated stock-theme forward linkage from 2026-08-26.",
        },
        "limitations": [
            "historical delisted and ticker-change coverage remains partial",
            "candidate-universe coverage expands materially from 2019 onward",
            "top/bottom 100 are discovery cohorts, not standalone proof",
            "event-level results are not a capital-constrained portfolio",
            "industry membership is unavailable historically and is not imputed",
        ],
    }
    target = pathlib.Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    detail = {
        "experiment_id": EXPERIMENT_ID,
        "development_2001_2024": _cohort_detail(development_rows),
        "discovery_2001_2018": _cohort_detail(split_rows["discovery"]),
    }
    if detail_out:
        detail_path = pathlib.Path(detail_out)
        detail_path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(detail_path, "wt", encoding="utf-8") as handle:
            json.dump(detail, handle, ensure_ascii=False, separators=(",", ":"))
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
    if args.command == "year":
        result = enrich_year(args.input_dir, args.cache_dir, args.year, args.out_dir)
    else:
        result = aggregate(args.input_dir, args.out, args.detail_out)
    print(json.dumps(result.get("coverage", result), ensure_ascii=False))


if __name__ == "__main__":
    main()
