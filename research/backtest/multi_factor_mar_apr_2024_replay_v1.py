"""Replay the March-April 2024 multi-factor ranking from archived evidence.

This audit never recalculates historical indicators.  It reuses the immutable
point-in-time factor hits produced by model 1.2.0, preserves that model's
original rank, and separately applies the current 1.4.0 count/resonance formula.
That separation prevents a retrospective ranking from overwriting history.
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

from research.backtest.reused_event_study_v2 import (
    _midrank_quintiles,
    _spearman,
    deduplicate,
    metrics,
)
from services.scanner.factor_registry import FACTORS_BY_ID, REGISTRY_VERSION
from services.scanner.unified_v2_scan import MODEL_VERSION, _resonance_summary


EXPERIMENT_ID = "multi-factor-mar-apr-2024-replay-v1.0.0-2026-08-30"
HORIZONS = (5, 10, 20, 40)


def load_events(directory: Path) -> list[dict]:
    """Load each archived point-in-time event once from the weekly shards."""
    rows: list[dict] = []
    for path in sorted(directory.glob("events-*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    return [row for row in rows if row.get("year") == 2024]


def load_archived_ranks(directory: Path) -> dict[tuple[str, str], dict]:
    """Recover the exact rank, signal price and support plan shown in 2024."""
    lookup: dict[tuple[str, str], dict] = {}
    for path in sorted(directory.glob("v2-2024-*.json")):
        report = json.loads(path.read_text())
        for day in report.get("days", []):
            for rank, candidate in enumerate(day.get("candidate_pool", []), 1):
                lookup[(day["date"], candidate["symbol"])] = {
                    "archived_rank": rank,
                    "signal_price": candidate.get("price"),
                    "support_plan": candidate.get("support_plan"),
                    "market": day.get("market"),
                }
    return lookup


def enrich(rows: list[dict], archived: dict[tuple[str, str], dict]) -> None:
    """Attach the current replay score without changing archived score fields."""
    by_date: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        row["replay_resonance"] = _resonance_summary(set(row["factors"]))
        row["scores"]["replay_count_resonance"] = row["replay_resonance"][
            "technical_resonance_score"
        ]
        row.update(archived.get((row["date"], row["symbol"]), {}))
        by_date[row["date"]].append(row)

    # This is the exact model 1.4 ranking order.  Industry is unavailable and
    # the market state is shared by every candidate on the same day, so neither
    # can create a technical difference in this historical slice.
    for day_rows in by_date.values():
        day_rows.sort(
            key=lambda row: (
                -row["replay_resonance"]["technical_resonance_score"],
                -row["replay_resonance"]["timeframe_resonance_bonus"],
                -row["replay_resonance"]["family_count"],
                -row["replay_resonance"]["positive_hit_count"],
                row["symbol"],
            )
        )
        for rank, row in enumerate(day_rows, 1):
            row["replay_rank"] = rank


def pct(value: float | None) -> float | None:
    return round(100 * value, 4) if value is not None else None


def card(row: dict) -> dict:
    """Keep enough evidence for a human to reproduce one winner or loser."""
    positive_ids = row["replay_resonance"]["positive_factor_ids"]
    return {
        "date": row["date"],
        "symbol": row["symbol"],
        "signal_price": row.get("signal_price"),
        "archived_rank": row.get("archived_rank"),
        "archived_scores": {
            key: value
            for key, value in row["scores"].items()
            if key != "replay_count_resonance"
        },
        "replay_rank": row["replay_rank"],
        "replay_score": row["replay_resonance"]["technical_resonance_score"],
        "replay_formula": row["replay_resonance"]["formula"],
        "positive_factor_ids": positive_ids,
        "positive_factor_names_zh": [
            FACTORS_BY_ID[factor_id].name_zh
            for factor_id in positive_ids
            if factor_id in FACTORS_BY_ID
        ],
        "risk_factor_ids": row["replay_resonance"]["risk_factor_ids"],
        "families": row["replay_resonance"]["families"],
        "timeframe_counts": row["replay_resonance"]["timeframe_counts"],
        "returns_pct": {str(horizon): pct(row["returns"].get(str(horizon))) for horizon in HORIZONS},
        "support_plan": row.get("support_plan"),
    }


def horizon_metrics(rows: list[dict]) -> dict:
    return {str(horizon): metrics(rows, horizon) for horizon in HORIZONS}


def factor_rates(rows: list[dict]) -> dict[str, float]:
    counts = Counter(
        factor_id
        for row in rows
        for factor_id in row["replay_resonance"]["positive_factor_ids"]
    )
    return {
        factor_id: round(count / len(rows), 4)
        for factor_id, count in sorted(counts.items())
    } if rows else {}


def factor_comparison(primary: list[dict], winners: list[dict], losers: list[dict]) -> list[dict]:
    """Compare extreme-case frequencies with their real base rate."""
    base, win, loss = factor_rates(primary), factor_rates(winners), factor_rates(losers)
    output = []
    for factor_id in sorted(set(base) | set(win) | set(loss)):
        output.append(
            {
                "factor_id": factor_id,
                "name_zh": FACTORS_BY_ID[factor_id].name_zh if factor_id in FACTORS_BY_ID else factor_id,
                "all_primary_rate": base.get(factor_id, 0.0),
                "winner_top10_rate": win.get(factor_id, 0.0),
                "loser_top10_rate": loss.get(factor_id, 0.0),
            }
        )
    return output


def run(attribution_dir: Path, archive_dir: Path, start: str, end: str) -> dict:
    rows = load_events(attribution_dir)
    archived = load_archived_ranks(archive_dir)
    enrich(rows, archived)

    window = [row for row in rows if start <= row["date"] <= end]
    primary = [row for row in deduplicate(rows, 120) if start <= row["date"] <= end]

    # A realistic ranking strategy only blocks a repeated ticker after that
    # strategy actually selected it.  Therefore Top 1/Top 5 are deduplicated
    # within their own complete-2024 selection streams.
    selections = {
        "all_events": window,
        "primary_120_session_deduplicated": primary,
        "replay_daily_top5_all_events": [row for row in window if row["replay_rank"] <= 5],
        "replay_daily_top1_all_events": [row for row in window if row["replay_rank"] == 1],
        "archived_daily_top5_all_events": [
            row for row in window if row.get("archived_rank", 10**9) <= 5
        ],
        "replay_daily_top5_strategy_deduplicated": [
            row
            for row in deduplicate([item for item in rows if item["replay_rank"] <= 5], 120)
            if start <= row["date"] <= end
        ],
        "replay_daily_top1_strategy_deduplicated": [
            row
            for row in deduplicate([item for item in rows if item["replay_rank"] == 1], 120)
            if start <= row["date"] <= end
        ],
        "archived_daily_top5_strategy_deduplicated": [
            row
            for row in deduplicate([item for item in rows if item.get("archived_rank", 10**9) <= 5], 120)
            if start <= row["date"] <= end
        ],
    }

    winners = sorted(primary, key=lambda row: row["returns"]["20"], reverse=True)[:10]
    losers = sorted(primary, key=lambda row: row["returns"]["20"])[:10]
    top1_window = [row for row in window if row["replay_rank"] == 1]

    quintiles = _midrank_quintiles(window, "replay_count_resonance")
    daily_rankings = []
    by_date: dict[str, list[dict]] = defaultdict(list)
    for row in window:
        by_date[row["date"]].append(row)
    for day in sorted(by_date):
        ordered = sorted(by_date[day], key=lambda row: row["replay_rank"])
        daily_rankings.append(
            {
                "date": day,
                "candidate_count": len(ordered),
                "market": ordered[0].get("market") if ordered else None,
                "replay_top5": [card(row) for row in ordered[:5]],
                "archived_top5": [
                    card(row)
                    for row in sorted(ordered, key=lambda row: row.get("archived_rank", 10**9))[:5]
                ],
            }
        )

    return {
        "schema_version": "multi-factor-mar-apr-2024-replay-v1.0.0",
        "experiment_id": EXPERIMENT_ID,
        "status": "completed_retrospective_audit",
        "future_data_used_for_selection": False,
        "period": {"start": start, "end": end, "sessions_with_events": len(by_date)},
        "source": {
            "event_model": "unified-v2-macd-trigger-1.2.0",
            "event_factor_registry": "0.8.0",
            "replay_ranking_model": MODEL_VERSION,
            "replay_factor_registry": REGISTRY_VERSION,
            "warning": "The replay reorders archived 0.8.0 hits; it does not recreate three factors added later.",
        },
        "definitions": {
            "event_gate": "exact completed daily MACD bullish cross plus archived long-trend qualification",
            "entry": "next adjusted open",
            "winner": "fixed-horizon raw return greater than zero",
            "primary_horizon_sessions": 20,
            "overlap_primary": "first event per ticker within 120 trading sessions on the complete 2024 sequence",
            "execution_excluded": "support stop, 2R target, time exit and active exits are not mixed into this attribution replay",
        },
        "coverage": {
            "source_2024_events": len(rows),
            "window_all_events": len(window),
            "window_primary_events": len(primary),
            "missing_archived_ranks": sum(row.get("archived_rank") is None for row in window),
        },
        "selection_metrics": {
            name: {"sample_count": len(selected), "horizons": horizon_metrics(selected)}
            for name, selected in selections.items()
        },
        "score_diagnostics": {
            "20_session_spearman_all_events": _spearman(window, "replay_count_resonance", 20),
            "daily_midrank_quintiles_20_session": {
                str(group): metrics(quintiles.get(group, []), 20) for group in range(1, 6)
            },
        },
        "highest_replay_scores_primary": [
            card(row)
            for row in sorted(
                primary,
                key=lambda row: (
                    -row["replay_resonance"]["technical_resonance_score"],
                    -row["replay_resonance"]["timeframe_resonance_bonus"],
                    row["date"],
                    row["symbol"],
                ),
            )[:10]
        ],
        "winner_top10_primary": [card(row) for row in winners],
        "loser_top10_primary": [card(row) for row in losers],
        "daily_top1_best5": [
            card(row) for row in sorted(top1_window, key=lambda row: row["returns"]["20"], reverse=True)[:5]
        ],
        "daily_top1_worst5": [
            card(row) for row in sorted(top1_window, key=lambda row: row["returns"]["20"])[:5]
        ],
        "factor_base_rate_comparison": factor_comparison(primary, winners, losers),
        "daily_rankings": daily_rankings,
        "limitations": [
            "This two-month period is already seen and cannot validate a new score.",
            "Factor registry 0.8.0 lacks three later factors, so this is not a full 39-factor historical rerun.",
            "Historical delisted and ticker-change coverage remains partial.",
            "Fixed-horizon event returns are not a capital-constrained portfolio or an execution backtest.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attribution-dir", required=True, type=Path)
    parser.add_argument("--archive-dir", required=True, type=Path)
    parser.add_argument("--start", default="2024-03-01")
    parser.add_argument("--end", default="2024-04-30")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    report = run(args.attribution_dir, args.archive_dir, args.start, args.end)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"out": str(args.out), "coverage": report["coverage"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
