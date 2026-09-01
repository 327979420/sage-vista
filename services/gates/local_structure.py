"""Point-in-time local 0.618/70% structure facts for M03 shadow output."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from services.scanner.detectors import load_config, pivots


def assess_local_structure(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Describe the latest confirmed upswing without reading a future pivot."""

    if len(rows) < 10:
        return {"status": "unavailable", "reason": "insufficient_history"}
    pivot_facts = pivots(rows, len(rows) - 1, load_config())
    highs = pivot_facts["highs"]
    lows = pivot_facts["lows"]
    candidates: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for high in highs:
        prior = [low for low in lows if low["index"] < high["index"] and low.get("major")]
        if prior:
            candidates.append((prior[-1], high))
    if not candidates:
        return {
            "status": "unavailable",
            "reason": "no_confirmed_upswing",
            "confirmation_delay": pivot_facts["confirmation_delay"],
        }
    low, high = candidates[-1]
    span = high["price"] - low["price"]
    if span <= 0:
        return {"status": "unavailable", "reason": "invalid_confirmed_upswing"}
    post_high_low = min(row["low"] for row in rows[high["index"] :])
    retracement = max(0.0, (high["price"] - post_high_low) / span)
    fib_618 = high["price"] - 0.618 * span
    latest_close = rows[-1]["close"]
    if retracement <= 0.618:
        classification = "structure_intact"
    elif retracement <= 0.70:
        classification = "deep_pullback_warning"
    elif latest_close >= fib_618:
        classification = "deep_sweep_reclaimed"
    else:
        classification = "structure_broken"
    return {
        "status": "observed",
        "classification": classification,
        "swing_low": low["price"],
        "swing_low_date": rows[low["index"]]["date"],
        "swing_low_confirmation_date": rows[low["confirmed_index"]]["date"],
        "swing_high": high["price"],
        "swing_high_date": rows[high["index"]]["date"],
        "swing_high_confirmation_date": rows[high["confirmed_index"]]["date"],
        "retracement": round(retracement, 8),
        "fib_618": round(fib_618, 8),
        "latest_close": latest_close,
    }

