"""Completed-period and long-horizon facts for M03 shadow assessment."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence


def completed_period_bars(
    rows: Sequence[Mapping[str, Any]], *, as_of: str, period: str
) -> tuple[dict[str, Any], ...]:
    """Aggregate only natural weeks/months already closed before ``as_of``."""

    cutoff = date.fromisoformat(as_of)
    groups: list[tuple[tuple[int, int], dict[str, Any]]] = []
    for row in rows:
        day = date.fromisoformat(row["date"])
        key = (day.isocalendar().year, day.isocalendar().week) if period == "weekly" else (day.year, day.month)
        if not groups or groups[-1][0] != key:
            groups.append((key, dict(row)))
        else:
            bar = groups[-1][1]
            bar["high"] = max(bar["high"], row["high"])
            bar["low"] = min(bar["low"], row["low"])
            bar["close"] = row["close"]
            bar["volume"] += row["volume"]
            bar["date"] = row["date"]
    current_key = (cutoff.isocalendar().year, cutoff.isocalendar().week) if period == "weekly" else (cutoff.year, cutoff.month)
    return tuple(bar for key, bar in groups if key < current_key)


def multi_year_drawdown(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Record the worst point-in-time peak-to-trough fact without a trade verdict."""

    if not rows:
        return {"status": "unavailable", "reason": "no_history"}
    peak = rows[0]["high"]
    peak_date = rows[0]["date"]
    worst = 0.0
    worst_peak_date = peak_date
    trough_date = rows[0]["date"]
    for row in rows:
        if row["high"] > peak:
            peak = row["high"]
            peak_date = row["date"]
        drawdown = (peak - row["low"]) / peak
        if drawdown > worst:
            worst = drawdown
            worst_peak_date = peak_date
            trough_date = row["date"]
    return {
        "status": "observed",
        "peak_date": worst_peak_date,
        "trough_date": trough_date,
        "max_drawdown": round(worst, 8),
        "history_first_date": rows[0]["date"],
        "history_last_date": rows[-1]["date"],
    }


def supply_risk_facts(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """List downward gaps and later fills; never convert them into a gate result."""

    gaps: list[dict[str, Any]] = []
    for index in range(1, len(rows)):
        previous, current = rows[index - 1], rows[index]
        if current["high"] >= previous["low"]:
            continue
        fill = next(
            (row["date"] for row in rows[index + 1 :] if row["high"] >= previous["low"]),
            None,
        )
        gaps.append({
            "gap_date": current["date"],
            "lower": current["high"],
            "upper": previous["low"],
            "filled_on": fill,
            "status": "filled" if fill else "unfilled",
        })
    return {"status": "observed", "down_gap_count": len(gaps), "gaps": gaps}


def assess_long_term(
    rows: Sequence[Mapping[str, Any]], *, as_of: str, baseline_long_trend: bool,
    local_structure: Mapping[str, Any],
) -> dict[str, Any]:
    """Return only states supported by frozen facts; ambiguous cases stay unavailable."""

    monthly = completed_period_bars(rows, as_of=as_of, period="monthly")
    weekly = completed_period_bars(rows, as_of=as_of, period="weekly")
    drawdown = multi_year_drawdown(rows)
    classification = local_structure.get("classification")
    if baseline_long_trend and classification in {
        "structure_intact", "deep_pullback_warning", "deep_sweep_reclaimed"
    }:
        state = "uptrend_pullback"
    elif drawdown.get("max_drawdown", 0) >= 0.70 and classification == "structure_broken":
        state = "structural_damage"
    else:
        # Long-base and range thresholds have not been approved. Returning
        # unavailable preserves the facts without inventing a business rule.
        state = "unavailable"
    return {
        "long_term_state": state,
        "multi_year_drawdown": drawdown,
        "monthly_state": {
            "status": "observed" if monthly else "unavailable",
            "completed_count": len(monthly),
            "completed_through": monthly[-1]["date"] if monthly else None,
        },
        "weekly_state": {
            "status": "observed" if weekly else "unavailable",
            "completed_count": len(weekly),
            "completed_through": weekly[-1]["date"] if weekly else None,
        },
        "supply_risk": supply_risk_facts(rows),
    }
