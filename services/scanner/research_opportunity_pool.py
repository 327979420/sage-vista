"""Publish a compact, read-only replay of point-in-time research signals.

Selection fields come only from the signal date. Forward returns are carried in
a separate evaluation object and must never be used to rank the rows.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


SOURCE = Path("research/backtest/output/signals.jsonl")
OUTPUT = Path("public/research-opportunity-pool.json")


def build(source=SOURCE):
    rows = [json.loads(line) for line in Path(source).read_text().splitlines() if line]
    recent = [row for row in rows if row["date"] >= "2026-01-01"]
    recent.sort(key=lambda row: (row["date"], -row["tracker_ranking"]), reverse=True)
    opportunities = []
    for row in recent:
        active_factors = [name for name, hit in row.get("factor_states", {}).items() if hit is True]
        opportunities.append({
            "symbol": row["ticker"],
            "signal_date": row["date"],
            "signal_status": row["status"],
            "signal_rank": row["tracker_ranking"],
            "signal_price": row["signal_close"],
            "macd_rank_score": row["macd_ranking_score"],
            "multi_factor_score": row["multi_factor_total_score"],
            "strict_long_trend": row["strict_long_trend"],
            "support_source": row["support_source"],
            "support_level": row["support_level"],
            "active_factors": active_factors,
            "evaluation": {
                "entry_date": row.get("entry_date"),
                "return_5d": row.get("forward_returns", {}).get("5"),
                "return_20d": row.get("forward_returns", {}).get("20"),
                "return_40d": row.get("forward_returns", {}).get("40"),
            },
        })
    dates = sorted({row["signal_date"] for row in opportunities})
    return {
        "version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "ranking_policy": "signal-time tracker rank only; forward results never affect ranking",
        "coverage": {
            "first": dates[0] if dates else None,
            "last": dates[-1] if dates else None,
            "signals": len(opportunities),
            "missing_after": dates[-1] if dates else None,
        },
        "opportunities": opportunities,
    }


def run(source=SOURCE, output=OUTPUT):
    payload = build(source)
    Path(output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


if __name__ == "__main__":
    print(json.dumps(run()["coverage"], ensure_ascii=False))
