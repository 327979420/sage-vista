"""Point-in-time structural support and the V2 execution policy.

Selection and execution are separate: support is frozen at the completed
signal close, while the final risk cap is calculated from the next adjusted
open.  No future bar can move the original support level.
"""
from __future__ import annotations

from .detectors import pivots
from .macd_factor_backtest import ema, volume_profile_level


EXECUTION_POLICY_VERSION = "support-5pct-cap-10pct-2r-v1"
MAX_HOLD_SESSIONS = 40
TARGET_R = 2.0


def signal_support_plan(rows, end=None):
    """Choose the highest confirmed support below the signal close."""
    if not rows:
        return {"available": False, "level": None, "source": "unavailable", "candidates": []}
    end = len(rows) - 1 if end is None else end
    close = float(rows[end]["close"])
    closes = [float(row["close"]) for row in rows[: end + 1]]
    curves = {period: ema(closes, period) for period in (21, 50, 200)}
    candidates = []

    profile = volume_profile_level(rows, end)
    profile_level = profile.get("level")
    if profile.get("hit") and profile_level and 0 < profile_level < close:
        candidates.append((float(profile_level), "volume-profile-poc"))

    for period in (21, 50, 200):
        value = float(curves[period][end])
        if 0 < value < close and close / value - 1 <= 0.12:
            candidates.append((value, f"EMA{period}"))

    prior = rows[max(0, end - 20) : end]
    if prior:
        value = min(float(row["low"]) for row in prior)
        if 0 < value < close:
            candidates.append((value, "prior-20D-low"))

    window = rows[max(0, end - 180) : end + 1]
    confirmed = pivots(window, len(window) - 1)["lows"]
    if confirmed:
        value = float(confirmed[-1]["price"])
        if 0 < value < close:
            candidates.append((value, "confirmed-swing-low"))

    compact = [
        {"level": round(level, 4), "source": source, "distance_pct": round((close / level - 1) * 100, 3)}
        for level, source in sorted(candidates, reverse=True)
    ]
    if not candidates:
        return {
            "available": False,
            "level": None,
            "source": "unavailable",
            "signal_close": round(close, 4),
            "candidates": [],
            "volume_profile": profile,
        }
    level, source = max(candidates, key=lambda item: item[0])
    return {
        "available": True,
        "level": round(level, 4),
        "source": source,
        "signal_close": round(close, 4),
        "support_buffer_pct": 5,
        "max_loss_pct": 10,
        "structural_stop": round(level * 0.95, 4),
        "candidates": compact,
        "volume_profile": profile,
    }


def executable_stop(entry, support_plan):
    """Use support minus 5%, capped so planned entry risk cannot exceed 10%."""
    entry = float(entry)
    cap = entry * 0.90
    level = support_plan.get("level") if support_plan else None
    structural = float(level) * 0.95 if level else None
    stop = max(cap, structural) if structural else cap
    source = support_plan.get("source") if structural and structural >= cap else "max-loss-10pct-cap"
    if stop <= 0 or stop >= entry:
        return {"executable": False, "reason": "entry_at_or_below_planned_stop", "entry": round(entry, 6), "stop": round(stop, 6)}
    risk = entry - stop
    return {
        "executable": True,
        "policy_version": EXECUTION_POLICY_VERSION,
        "entry": round(entry, 6),
        "support_level": round(float(level), 6) if level else None,
        "support_source": support_plan.get("source", "unavailable") if support_plan else "unavailable",
        "structural_stop": round(structural, 6) if structural else None,
        "max_loss_stop": round(cap, 6),
        "stop": round(stop, 6),
        "stop_source": source,
        "risk_pct": round(risk / entry, 8),
        "target_r": TARGET_R,
        "target": round(entry + TARGET_R * risk, 6),
        "max_hold_sessions": MAX_HOLD_SESSIONS,
    }


def simulate_execution(entry, support_plan, path):
    """Stop-first daily-bar simulation with gap-aware fills and a 2R target."""
    plan = executable_stop(entry, support_plan)
    if not plan["executable"]:
        return {**plan, "status": "skipped"}
    if not path:
        return {**plan, "status": "pending"}
    stop = plan["stop"]
    target = plan["target"]
    risk = float(entry) - stop
    window = path[:MAX_HOLD_SESSIONS]
    for held, bar in enumerate(window, 1):
        if float(bar["open"]) <= stop:
            fill, reason = float(bar["open"]), "stop_gap"
        elif float(bar["low"]) <= stop:
            fill, reason = stop, "stop"
        elif float(bar["open"]) >= target:
            fill, reason = target, "target"
        elif float(bar["high"]) >= target:
            fill, reason = target, "target"
        else:
            continue
        return {
            **plan,
            "status": "resolved",
            "exit_date": bar["date"],
            "exit_price": round(fill, 6),
            "exit_reason": reason,
            "holding_sessions": held,
            "return": round(fill / float(entry) - 1, 8),
            "r_multiple": round((fill - float(entry)) / risk, 6),
        }
    if len(path) < MAX_HOLD_SESSIONS:
        return {**plan, "status": "observing", "holding_sessions": len(path)}
    fill = float(window[-1]["close"])
    return {
        **plan,
        "status": "resolved",
        "exit_date": window[-1]["date"],
        "exit_price": round(fill, 6),
        "exit_reason": "time_40d",
        "holding_sessions": MAX_HOLD_SESSIONS,
        "return": round(fill / float(entry) - 1, 8),
        "r_multiple": round((fill - float(entry)) / risk, 6),
    }
