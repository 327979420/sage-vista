"""Reuse archived Unified V2 event pools for the full score/factor study.

The scanner already made the point-in-time selection.  This module only joins
those immutable events to the audited price cache, adds completed-week/month
MACD audits, archives enriched natural weeks, and aggregates the frozen study.
"""
from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import json
import math
import pathlib
import statistics
from collections import defaultdict
from datetime import date, datetime

from services.scanner.factor_registry import FACTORS_BY_ID
from services.scanner.macd_factor_backtest import adjusted_rows, completed_groups
from services.scanner.technical import macd

HORIZONS = (5, 10, 15, 20, 40, 60, 100, 120)
PERIODS = (
    ("development", "2001-01-01", "2024-12-31"),
    ("validation_2025", "2025-01-01", "2025-12-31"),
    ("forward_2026", "2026-01-01", "9999-12-31"),
)
FACTOR_MINIMUMS = {"development": 300, "validation_2025": 100}
PAIR_MINIMUMS = {"development": 200, "validation_2025": 75}
FROZEN_PAIRS = (
    ("volume.bottom_expansion", "structure.bottom_bullish_engulfing"),
    ("volume.bottom_expansion", "risk.overhead_unfilled_gap"),
    ("structure.bottom_bullish_engulfing", "risk.overhead_unfilled_gap"),
)
RESEARCH_WEEKLY_CROSS = "macd.weekly_bull_cross"
PRIMARY_HORIZON = 20


def period_of(value: str) -> str | None:
    return next((name for name, lo, hi in PERIODS if lo <= value <= hi), None)


def _week(value: str) -> str:
    parsed = date.fromisoformat(value)
    iso = parsed.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_reports(parts_dir: str | pathlib.Path) -> tuple[list[dict], list[dict]]:
    paths = sorted(pathlib.Path(parts_dir).glob("*.json"))
    reports = [json.loads(path.read_text()) for path in paths]
    days_by_date = {}
    for report in reports:
        for day in report.get("days", []):
            existing = days_by_date.get(day.get("date"))
            if existing is None or len(day.get("candidate_pool", [])) > len(existing.get("candidate_pool", [])):
                days_by_date[day["date"]] = day
    return [days_by_date[key] for key in sorted(days_by_date)], [
        {"name": path.name, "sha256": _sha256(path)} for path in paths
    ]


def _cross_keys(groups: list[list]) -> set[tuple]:
    if len(groups) < 2:
        return set()
    closes = [float(item[1]["close"]) for item in groups]
    line, signal = macd(closes)
    return {
        groups[index][0]
        for index in range(1, len(groups))
        if line[index] > signal[index] and line[index - 1] <= signal[index - 1]
    }


class PriceSeries:
    def __init__(self, raw: list[dict]):
        self.rows = adjusted_rows(raw)
        self.index = {row["date"]: index for index, row in enumerate(self.rows)}
        closes = [float(row["close"]) for row in self.rows]
        line, signal = macd(closes) if closes else ([], [])
        self.daily_cross_dates = {
            self.rows[index]["date"]
            for index in range(1, len(self.rows))
            if line[index] > signal[index] and line[index - 1] <= signal[index - 1]
        }
        self.weekly_groups = completed_groups(self.rows, "weekly")
        self.monthly_groups = completed_groups(self.rows, "monthly")
        self.weekly_keys = [item[0] for item in self.weekly_groups]
        self.monthly_keys = [item[0] for item in self.monthly_groups]
        self.weekly_cross_keys = _cross_keys(self.weekly_groups)
        self.monthly_cross_keys = _cross_keys(self.monthly_groups)

    @staticmethod
    def _latest_completed(keys: list[tuple], current: tuple) -> tuple | None:
        position = bisect.bisect_left(keys, current) - 1
        return keys[position] if position >= 0 else None

    def higher_timeframe_crosses(self, signal_date: str) -> tuple[bool, bool]:
        parsed = date.fromisoformat(signal_date)
        weekly_key = (parsed.isocalendar().year, parsed.isocalendar().week)
        monthly_key = (parsed.year, parsed.month)
        completed_week = self._latest_completed(self.weekly_keys, weekly_key)
        completed_month = self._latest_completed(self.monthly_keys, monthly_key)
        return completed_week in self.weekly_cross_keys, completed_month in self.monthly_cross_keys

    def returns(self, signal_date: str) -> tuple[int | None, dict[str, float | None]]:
        signal_index = self.index.get(signal_date)
        empty = {str(horizon): None for horizon in HORIZONS}
        if signal_index is None or signal_index + 1 >= len(self.rows):
            return signal_index, empty
        entry = float(self.rows[signal_index + 1]["open"])
        if entry <= 0:
            return signal_index, empty
        values = {}
        for horizon in HORIZONS:
            exit_index = signal_index + horizon
            values[str(horizon)] = (
                float(self.rows[exit_index]["close"]) / entry - 1
                if exit_index < len(self.rows)
                else None
            )
        return signal_index, values


class PriceLoader:
    def __init__(self, cache_dir: str | pathlib.Path):
        self.cache_dir = pathlib.Path(cache_dir)
        self.cache: dict[str, PriceSeries | None] = {}

    def __call__(self, symbol: str) -> PriceSeries | None:
        if symbol not in self.cache:
            path = self.cache_dir / f"{symbol}.json"
            try:
                self.cache[symbol] = PriceSeries(json.loads(path.read_text())) if path.exists() else None
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                self.cache[symbol] = None
        return self.cache[symbol]


def _dependency_safe_factors(factor_ids: list[str]) -> list[str]:
    hits = set(factor_ids)
    changed = True
    while changed:
        changed = False
        for factor_id in tuple(hits):
            registered = FACTORS_BY_ID.get(factor_id)
            if registered and registered.depends_on and not all(parent in hits for parent in registered.depends_on):
                hits.remove(factor_id)
                changed = True
    return sorted(hits)


def enrich_year(parts_dir, cache_dir, year, out_dir):
    year = int(year)
    days, source_files = _read_reports(parts_dir)
    if not days:
        raise RuntimeError(f"No archived candidate-pool days found for {year}")
    days = [day for day in days if str(day.get("date", "")).startswith(str(year))]
    if not days:
        raise RuntimeError(f"Archived reports contain no sessions for {year}")

    load = PriceLoader(cache_dir)
    weeks: dict[str, list[dict]] = defaultdict(list)
    source_candidates = with_price = daily_gate_mismatches = monthly_audit_mismatches = 0
    mature = {str(horizon): 0 for horizon in HORIZONS}
    factor_counts: dict[str, int] = defaultdict(int)
    model_versions, registry_versions = set(), set()

    for day in days:
        # Preserve every source natural week, including weeks with zero events.
        weeks.setdefault(_week(day["date"]), [])
        model_versions.add(day.get("model_version"))
        registry_versions.add(day.get("factor_registry_version"))
        for candidate in day.get("candidate_pool", []):
            source_candidates += 1
            symbol = candidate.get("symbol")
            series = load(symbol) if symbol else None
            if series is None:
                continue
            signal_index, returns = series.returns(day["date"])
            if signal_index is None:
                continue
            with_price += 1
            exact_daily = day["date"] in series.daily_cross_dates
            if not exact_daily:
                daily_gate_mismatches += 1
                # The pre-registered ticket is an exact completed daily cross.
                # Cache revisions can reveal an old archived event that no
                # longer reproduces; retain its audit count but never analyse it.
                continue
            weekly_cross, monthly_cross = series.higher_timeframe_crosses(day["date"])
            archived_factors = _dependency_safe_factors(candidate.get("hit_factor_ids", []))
            if weekly_cross:
                archived_factors.append(RESEARCH_WEEKLY_CROSS)
            archived_monthly = "macd.monthly_bull_cross" in archived_factors
            if archived_monthly != monthly_cross:
                monthly_audit_mismatches += 1
            # The exact completed-month calculation is authoritative for this
            # migration experiment; the archived bit remains in the audit.
            archived_factors = [factor for factor in archived_factors if factor != "macd.monthly_bull_cross"]
            if monthly_cross:
                archived_factors.append("macd.monthly_bull_cross")
            factors = sorted(set(archived_factors))
            for factor in factors:
                factor_counts[factor] += 1
            for horizon, value in returns.items():
                if value is not None:
                    mature[horizon] += 1
            points = (candidate.get("timeframe_profile") or {}).get("points") or {}
            daily_points = float(points.get("daily") or 0)
            weekly_points = float(points.get("weekly") or 0)
            monthly_points = float(points.get("monthly") or 0)
            event = {
                "symbol": symbol,
                "date": day["date"],
                "year": year,
                "period": period_of(day["date"]),
                "signal_index": signal_index,
                "daily_gate_audit": exact_daily,
                "model_version": day.get("model_version"),
                "factor_registry_version": day.get("factor_registry_version"),
                "scores": {
                    "current": float(candidate.get("technical_score") or 0),
                    "timeframe_equal": daily_points + weekly_points + monthly_points,
                    "timeframe_v3": daily_points + 1.5 * weekly_points + 2 * monthly_points,
                },
                "timeframe_points": {"daily": daily_points, "weekly": weekly_points, "monthly": monthly_points},
                "factors": factors,
                "higher_timeframe_audit": {
                    "weekly_exact_bull_cross": weekly_cross,
                    "monthly_exact_bull_cross": monthly_cross,
                    "archived_monthly_cross": archived_monthly,
                },
                "returns": returns,
            }
            weeks[_week(day["date"])].append(event)

    target_dir = pathlib.Path(out_dir)
    week_dir = target_dir / "weeks"
    week_dir.mkdir(parents=True, exist_ok=True)
    for week, events in sorted(weeks.items()):
        with gzip.open(week_dir / f"events-{week}.jsonl.gz", "wt", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")

    summary = {
        "schema_version": "score-timeframe-attribution-year-v2.0.0",
        "experiment_id": "score-timeframe-attribution-v2.0.0-2026-08-29",
        "year": year,
        "event_gate": "exact completed daily MACD bullish cross",
        "future_data_used_for_selection": False,
        "market_and_industry_mixed_into_technical_test": False,
        "coverage": {
            "start": days[0]["date"],
            "end": days[-1]["date"],
            "sessions": len(days),
            "natural_week_checkpoints": len(weeks),
            "source_candidates": source_candidates,
            "events_joined_to_price_cache": with_price,
            "audited_gate_events": with_price - daily_gate_mismatches,
            "missing_price_events": source_candidates - with_price,
            "mature_outcomes": mature,
        },
        "audits": {
            "daily_gate_mismatches": daily_gate_mismatches,
            "monthly_cross_mismatches": monthly_audit_mismatches,
        },
        "model_versions": sorted(value for value in model_versions if value),
        "factor_registry_versions": sorted(value for value in registry_versions if value),
        "factor_hit_counts": dict(sorted(factor_counts.items())),
        "source_files": source_files,
        "limitations": [
            "historical delisted and ticker-change coverage remains partial",
            "the candidate universe expands materially from 2019 onward",
            "immature horizons remain null and are never imputed",
        ],
    }
    summary_path = target_dir / f"annual-{year}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return summary


def _load_enriched(input_dir) -> list[dict]:
    rows = []
    for path in sorted(pathlib.Path(input_dir).rglob("events-*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    return [row for row in rows if row.get("period")]


def deduplicate(rows: list[dict], window_sessions: int = 120) -> list[dict]:
    kept, last_index = [], {}
    for row in sorted(rows, key=lambda item: (item["date"], item["symbol"])):
        prior = last_index.get(row["symbol"])
        current = row.get("signal_index")
        if prior is not None and current is not None and current <= prior + window_sessions:
            continue
        kept.append(row)
        if current is not None:
            last_index[row["symbol"]] = current
    return kept


def percentile(values: list[float], q: float) -> float | None:
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * q
    lower, upper = math.floor(position), math.ceil(position)
    return values[lower] if lower == upper else values[lower] + (values[upper] - values[lower]) * (position - lower)


def trimmed_mean(values: list[float], proportion: float = 0.01) -> float | None:
    values = sorted(values)
    if not values:
        return None
    cut = int(len(values) * proportion)
    values = values[cut:-cut] if cut and len(values) > 2 * cut else values
    return statistics.fmean(values)


def metrics(rows: list[dict], horizon: int, cost_bps: int = 0) -> dict:
    values = [row.get("returns", {}).get(str(horizon)) for row in rows]
    values = [value - cost_bps / 10_000 for value in values if value is not None and math.isfinite(value)]
    if not values:
        return {"samples": 0, "win_rate_pct": None, "median_pct": None, "trimmed_mean_pct": None, "profit_factor": None, "expectancy_pct": None}
    gains = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    result = {
        "samples": len(values),
        "win_rate_pct": round(100 * sum(value > 0 for value in values) / len(values), 3),
        "median_pct": round(100 * statistics.median(values), 4),
        "trimmed_mean_pct": round(100 * trimmed_mean(values), 4),
        "profit_factor": round(gains / losses, 4) if losses else None,
        "expectancy_pct": round(100 * statistics.fmean(values), 4),
    }
    if cost_bps == 0:
        result["cost_sensitivity"] = {str(cost): metrics(rows, horizon, cost) for cost in (20, 50)}
    return result


def normal_mean_pvalue(first: list[float], second: list[float]) -> float:
    if len(first) < 2 or len(second) < 2:
        return 1.0
    variance = statistics.variance(first) / len(first) + statistics.variance(second) / len(second)
    if variance <= 0:
        return 1.0
    score = abs(statistics.fmean(first) - statistics.fmean(second)) / math.sqrt(variance)
    return math.erfc(score / math.sqrt(2))


def bh_adjust(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    adjusted = [1.0] * len(values)
    running = 1.0
    for rank, (index, value) in reversed(list(enumerate(ordered, start=1))):
        running = min(running, value * len(values) / rank)
        adjusted[index] = round(min(1.0, running), 6)
    return adjusted


def _delta(hit: list[dict], miss: list[dict], horizon: int) -> dict:
    with_factor, without_factor = metrics(hit, horizon), metrics(miss, horizon)
    first = [row["returns"][str(horizon)] for row in hit if row["returns"].get(str(horizon)) is not None]
    second = [row["returns"][str(horizon)] for row in miss if row["returns"].get(str(horizon)) is not None]
    fields = ("win_rate_pct", "median_pct", "trimmed_mean_pct", "profit_factor", "expectancy_pct")
    return {
        "with": with_factor,
        "without": without_factor,
        "delta": {
            field: round((with_factor.get(field) or 0) - (without_factor.get(field) or 0), 4)
            for field in fields
        },
        "mean_difference_p": round(normal_mean_pvalue(first, second), 7),
    }


def _enrichment(rows: list[dict], factor: str, horizon: int) -> dict:
    eligible = [row for row in rows if row["returns"].get(str(horizon)) is not None]
    values = [row["returns"][str(horizon)] for row in eligible]
    cutoff = percentile(values, 0.9)
    groups = {
        "all": eligible,
        "winners": [row for row in eligible if row["returns"][str(horizon)] > 0],
        "high_return_top_decile": [row for row in eligible if cutoff is not None and row["returns"][str(horizon)] >= cutoff],
        "high_return_absolute_10pct": [row for row in eligible if row["returns"][str(horizon)] >= 0.10],
        "losers": [row for row in eligible if row["returns"][str(horizon)] <= 0],
    }
    rates = {
        name: round(sum(factor in row["factors"] for row in group) / len(group), 6) if group else None
        for name, group in groups.items()
    }
    baseline = rates["all"]
    return {
        "eligible_samples": len(eligible),
        "top_decile_cutoff_pct": round(100 * cutoff, 4) if cutoff is not None else None,
        "factor_base_rates": rates,
        "winner_enrichment_ratio": round(rates["winners"] / baseline, 4) if baseline and rates["winners"] is not None else None,
        "top_decile_enrichment_ratio": round(rates["high_return_top_decile"] / baseline, 4) if baseline and rates["high_return_top_decile"] is not None else None,
        "loser_enrichment_ratio": round(rates["losers"] / baseline, 4) if baseline and rates["losers"] is not None else None,
    }


def _midrank_quintiles(rows: list[dict], score_name: str) -> dict[int, list[dict]]:
    groups: dict[int, list[dict]] = defaultdict(list)
    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_day[row["date"]].append(row)
    for day_rows in by_day.values():
        ordered = sorted(day_rows, key=lambda row: row["scores"][score_name])
        total = len(ordered)
        start = 0
        while start < total:
            end = start + 1
            while end < total and ordered[end]["scores"][score_name] == ordered[start]["scores"][score_name]:
                end += 1
            midrank = ((start + 1) + end) / 2
            quintile = min(5, max(1, int(math.ceil(5 * midrank / total))))
            groups[quintile].extend(ordered[start:end])
            start = end
    return groups


def _spearman(rows: list[dict], score_name: str, horizon: int) -> float | None:
    pairs = [(row["scores"][score_name], row["returns"].get(str(horizon))) for row in rows]
    pairs = [(score, result) for score, result in pairs if result is not None]
    if len(pairs) < 3 or len({score for score, _ in pairs}) < 2:
        return None

    def ranks(values):
        order = sorted(range(len(values)), key=values.__getitem__)
        output = [0.0] * len(values)
        start = 0
        while start < len(values):
            end = start + 1
            while end < len(values) and values[order[end]] == values[order[start]]:
                end += 1
            rank = ((start + 1) + end) / 2
            for position in order[start:end]:
                output[position] = rank
            start = end
        return output

    first, second = ranks([item[0] for item in pairs]), ranks([item[1] for item in pairs])
    first_mean, second_mean = statistics.fmean(first), statistics.fmean(second)
    numerator = sum((a - first_mean) * (b - second_mean) for a, b in zip(first, second))
    denominator = math.sqrt(sum((a - first_mean) ** 2 for a in first) * sum((b - second_mean) ** 2 for b in second))
    return round(numerator / denominator, 6) if denominator else None


def score_study(rows: list[dict]) -> dict:
    output = {}
    for score_name in ("current", "timeframe_equal", "timeframe_v3"):
        periods = {}
        for period, _, _ in PERIODS:
            subset = [row for row in rows if row["period"] == period]
            quintiles = _midrank_quintiles(subset, score_name)
            exact_values = sorted({row["scores"][score_name] for row in subset})
            periods[period] = {
                "daily_midrank_quintiles": {
                    str(group): {str(horizon): metrics(quintiles.get(group, []), horizon) for horizon in HORIZONS}
                    for group in range(1, 6)
                },
                "spearman": {str(horizon): _spearman(subset, score_name, horizon) for horizon in HORIZONS},
                "exact_scores": {
                    str(value): {str(horizon): metrics([row for row in subset if row["scores"][score_name] == value], horizon) for horizon in HORIZONS}
                    for value in exact_values
                },
            }
        output[score_name] = periods
    return output


def baseline_study(rows: list[dict]) -> dict:
    return {
        period: {
            str(horizon): metrics([row for row in rows if row["period"] == period], horizon)
            for horizon in HORIZONS
        }
        for period, _, _ in PERIODS
    }


def factor_study(rows: list[dict]) -> list[dict]:
    common_gate_factors = {"macd.daily_bull_cross", "qualification.long_trend"}
    factors = sorted({factor for row in rows for factor in row["factors"] if factor not in common_gate_factors})
    output, pvalues = [], []
    for factor in factors:
        periods = {}
        for period, _, _ in PERIODS:
            subset = [row for row in rows if row["period"] == period]
            hit = [row for row in subset if factor in row["factors"]]
            miss = [row for row in subset if factor not in row["factors"]]
            periods[period] = {
                str(horizon): {**_delta(hit, miss, horizon), "enrichment": _enrichment(subset, factor, horizon)}
                for horizon in HORIZONS
            }
        pvalues.append(periods["development"][str(PRIMARY_HORIZON)]["mean_difference_p"])
        registered = FACTORS_BY_ID.get(factor)
        output.append({
            "factor_id": factor,
            "family": registered.evidence_family if registered else "macd" if factor == RESEARCH_WEEKLY_CROSS else "unclassified",
            "timeframe": registered.timeframe if registered else "weekly_completed" if factor == RESEARCH_WEEKLY_CROSS else "unknown",
            "periods": periods,
        })
    for row, qvalue in zip(output, bh_adjust(pvalues)):
        row["development_20d_bh_q"] = qvalue
        primary = {period: row["periods"][period][str(PRIMARY_HORIZON)] for period, _, _ in PERIODS}
        enough = (
            primary["development"]["with"]["samples"] >= FACTOR_MINIMUMS["development"]
            and primary["validation_2025"]["with"]["samples"] >= FACTOR_MINIMUMS["validation_2025"]
        )
        same_direction = all(item["delta"]["trimmed_mean_pct"] > 0 and item["delta"]["profit_factor"] > 0 for item in primary.values())
        cost_positive = all((item["with"].get("cost_sensitivity", {}).get("50", {}).get("expectancy_pct") or 0) > 0 for item in primary.values())
        significant = qvalue <= 0.10
        row["verdict"] = (
            "validated" if enough and same_direction and cost_positive and significant
            else "sample_insufficient" if not enough
            else "unstable" if not same_direction
            else "not_validated"
        )
    return output


def pair_study(rows: list[dict]) -> list[dict]:
    output = []
    for first, second in FROZEN_PAIRS:
        periods = {}
        for period, _, _ in PERIODS:
            subset = [row for row in rows if row["period"] == period]
            both = [row for row in subset if first in row["factors"] and second in row["factors"]]
            first_hit = [row for row in subset if first in row["factors"]]
            second_hit = [row for row in subset if second in row["factors"]]
            periods[period] = {}
            for horizon in HORIZONS:
                periods[period][str(horizon)] = {
                    "both": metrics(both, horizon),
                    "all": metrics(subset, horizon),
                    "first_factor": metrics(first_hit, horizon),
                    "second_factor": metrics(second_hit, horizon),
                }
        primary = {period: periods[period][str(PRIMARY_HORIZON)] for period, _, _ in PERIODS}
        enough = (
            primary["development"]["both"]["samples"] >= PAIR_MINIMUMS["development"]
            and primary["validation_2025"]["both"]["samples"] >= PAIR_MINIMUMS["validation_2025"]
        )
        uplift = all(
            item["both"]["trimmed_mean_pct"] is not None
            and item["both"]["trimmed_mean_pct"] > max(
                item["all"]["trimmed_mean_pct"] or -math.inf,
                item["first_factor"]["trimmed_mean_pct"] or -math.inf,
                item["second_factor"]["trimmed_mean_pct"] or -math.inf,
            )
            for item in primary.values()
        )
        output.append({
            "factor_ids": [first, second],
            "periods": periods,
            "verdict": "validated" if enough and uplift else "sample_insufficient" if not enough else "not_validated",
        })
    return output


def _normalized_annual_summary(summary: dict) -> dict:
    coverage = summary.setdefault("coverage", {})
    source_files = summary.get("source_files", [])
    observed = int(coverage.get("natural_week_checkpoints") or 0)
    # Historical inputs are one archived file per requested natural-week
    # partition, including an occasional zero-session edge partition.  The
    # 2026 forward input is one consolidated report, so its observed ISO weeks
    # remain authoritative.
    source_checkpoints = len(source_files) if len(source_files) > 1 else observed
    coverage["source_natural_week_checkpoints"] = source_checkpoints
    coverage["natural_week_checkpoints"] = max(observed, source_checkpoints)
    return summary


def aggregate(input_dir, out, annual_out_dir=None):
    all_events = _load_enriched(input_dir)
    if not all_events:
        raise RuntimeError("No enriched natural-week checkpoints found")
    primary = deduplicate(all_events, 120)
    annual = []
    for path in sorted(pathlib.Path(input_dir).rglob("annual-*.json")):
        annual.append(_normalized_annual_summary(json.loads(path.read_text())))
    if annual_out_dir:
        annual_target = pathlib.Path(annual_out_dir)
        annual_target.mkdir(parents=True, exist_ok=True)
        for item in annual:
            (annual_target / f"annual-{item['year']}.json").write_text(json.dumps(item, ensure_ascii=False, indent=2) + "\n")
    report = {
        "schema_version": "score-timeframe-attribution-v2.0.0",
        "experiment_id": "score-timeframe-attribution-v2.0.0-2026-08-29",
        "generated_at": datetime.now().astimezone().isoformat(),
        "event_gate": "exact completed daily MACD bullish cross",
        "technical_only_primary_test": True,
        "market_and_industry_mixed_into_technical_test": False,
        "production_scoring_changed": False,
        "coverage": {
            "start": min(row["date"] for row in all_events),
            "end": max(row["date"] for row in all_events),
            "all_events": len(all_events),
            "primary_120_session_deduplicated_events": len(primary),
            "natural_week_checkpoints": sum(item["coverage"]["natural_week_checkpoints"] for item in annual),
            "natural_weeks_with_events": len({_week(row["date"]) for row in all_events}),
            "annual_summaries": len(annual),
            "period_events": {period: sum(row["period"] == period for row in all_events) for period, _, _ in PERIODS},
            "primary_period_events": {period: sum(row["period"] == period for row in primary) for period, _, _ in PERIODS},
            "mature_outcomes": {str(horizon): sum(row["returns"].get(str(horizon)) is not None for row in primary) for horizon in HORIZONS},
        },
        "definitions": {
            "high_score": "daily midrank quintiles; exact score sensitivity also reported",
            "winner": "fixed-horizon raw return > 0",
            "high_return": "top decile within period and horizon; absolute >=10% sensitivity",
            "effective_factor": "same-direction robust uplift in development/2025/2026, frozen samples, BH q<=0.10 and positive 50bps expectancy",
            "primary_overlap": "first event per ticker inside 120 trading sessions",
            "primary_factor_horizon_sessions": PRIMARY_HORIZON,
        },
        "primary_deduplicated": {
            "baseline_fixed_horizon": baseline_study(primary),
            "score_monotonicity": score_study(primary),
            "single_factors": factor_study(primary),
            "frozen_pairs": pair_study(primary),
        },
        "all_event_sensitivity": {
            "baseline_fixed_horizon": baseline_study(all_events),
            "score_monotonicity": score_study(all_events),
            "single_factors": factor_study(all_events),
            "frozen_pairs": pair_study(all_events),
        },
        "annual_coverage": sorted(annual, key=lambda item: item["year"]),
        "limitations": [
            "historical delisted and ticker-change coverage remains partial",
            "the cached candidate universe expands materially from 2019 onward",
            "2026 long-horizon outcomes are immature and remain null",
            "normal-approximation p-values are screened with BH and interpreted with robust metrics, not alone",
            "raw fixed-horizon attribution is separate from stop-loss, trailing-stop and active-exit experiments",
        ],
    }
    target = pathlib.Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def matrix(start_year: int, end_year: int, github_output: str | None = None):
    if start_year > end_year:
        raise ValueError("start_year must not exceed end_year")
    payload = [{"year": year} for year in range(start_year, end_year + 1)]
    value = json.dumps(payload, separators=(",", ":"))
    if github_output:
        with pathlib.Path(github_output).open("a") as handle:
            handle.write(f"matrix={value}\n")
    return payload


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    years = subparsers.add_parser("matrix")
    years.add_argument("--start-year", type=int, required=True)
    years.add_argument("--end-year", type=int, required=True)
    years.add_argument("--github-output")
    annual = subparsers.add_parser("year")
    annual.add_argument("--parts-dir", required=True)
    annual.add_argument("--cache-dir", default="work/eodhd-cache")
    annual.add_argument("--year", type=int, required=True)
    annual.add_argument("--out-dir", required=True)
    combined = subparsers.add_parser("aggregate")
    combined.add_argument("--input-dir", required=True)
    combined.add_argument("--out", required=True)
    combined.add_argument("--annual-out-dir")
    args = parser.parse_args()
    if args.command == "matrix":
        result = matrix(args.start_year, args.end_year, args.github_output)
    elif args.command == "year":
        result = enrich_year(args.parts_dir, args.cache_dir, args.year, args.out_dir)
    else:
        result = aggregate(args.input_dir, args.out, args.annual_out_dir)
    printable = result.get("coverage", result) if isinstance(result, dict) else result
    print(json.dumps(printable, ensure_ascii=False))


if __name__ == "__main__":
    main()
