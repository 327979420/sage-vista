"""Data-driven trade simulation for the quant research lab.

One function, `simulate`, runs any exit/stop variant described as data, so a
new idea is a new spec entry rather than new code. Semantics follow the
production policy in services/scanner/support_risk.py (which the "support_cap"
stop with a single 2R target reproduces exactly):

- entry at the open of `bars[entry_index]` (the session after the signal);
- daily bars only, so a stop is checked before a target on the same bar;
- an open below the stop fills at that open; a target fills at the target;
- trailing stops and indicators use completed bars only and never move down.
"""
from __future__ import annotations

from services.scanner.support_risk import executable_stop

# Exits that fill at the session open; every other exit fills during or at the close of its bar.
OPEN_FILLS = {"stop_gap", "trail_gap", "trend_exit"}


def atr(bars, end, period):
    """Simple average true range over `period` completed bars ending at `end`."""
    if end < period:
        return None
    ranges = []
    for i in range(end - period + 1, end + 1):
        high, low, prev = float(bars[i]["high"]), float(bars[i]["low"]), float(bars[i - 1]["close"])
        ranges.append(max(high - low, abs(high - prev), abs(low - prev)))
    return sum(ranges) / period


def ema_series(closes, period):
    alpha, value, out = 2 / (period + 1), None, []
    for close in closes:
        value = close if value is None else alpha * close + (1 - alpha) * value
        out.append(value)
    return out


def initial_stop(bars, entry_index, entry, stop_rule, support_plan):
    kind = stop_rule["kind"]
    if kind == "support_cap":
        # Production rule: support - buffer, never more than `cap` below entry.
        if (stop_rule.get("buffer"), stop_rule.get("cap")) != (0.05, 0.10):
            level = (support_plan or {}).get("level")
            cap = entry * (1 - stop_rule["cap"])
            stop = max(cap, float(level) * (1 - stop_rule["buffer"])) if level else cap
            return stop if 0 < stop < entry else None
        plan = executable_stop(entry, support_plan or {})
        return plan["stop"] if plan["executable"] else None
    if kind == "atr":
        value = atr(bars, entry_index - 1, stop_rule["period"])
        stop = entry - stop_rule["mult"] * value if value else None
        return stop if stop and 0 < stop < entry else None
    if kind == "pct":
        return entry * (1 - stop_rule["pct"])
    raise ValueError(f"unknown stop kind {kind}")


def simulate(bars, entry_index, variant, support_plan=None, cost_per_side=0.001):
    """Return one trade record, or a skipped/observing status.

    `variant`: {"stop": {...}, "targets": [{"r": 2.0, "fraction": 1.0}],
    "trail": {...} | None, "trail_after_target": bool, "max_hold": int}.
    """
    if entry_index <= 0 or entry_index >= len(bars):
        return {"status": "no_entry"}
    entry = float(bars[entry_index]["open"])
    stop = initial_stop(bars, entry_index, entry, variant["stop"], support_plan)
    if stop is None:
        return {"status": "skipped", "reason": "no_executable_stop"}
    risk = entry - stop
    targets = sorted(({"price": entry + t["r"] * risk, "fraction": t["fraction"]} for t in variant.get("targets", [])), key=lambda t: t["price"])
    trail, trail_after = variant.get("trail"), variant.get("trail_after_target", False)
    max_hold = variant["max_hold"]
    closes = [float(b["close"]) for b in bars]
    ema = ema_series(closes, trail["period"]) if trail and trail["kind"] == "ma_close" else None
    remaining, gross, fills, highest = 1.0, 0.0, [], entry
    trailing_active = bool(trail) and not trail_after
    trail_stop, exit_next_open = None, False

    def fill(price, fraction, reason, day):
        nonlocal remaining, gross
        gross += fraction * (price / entry - 1)
        remaining = round(remaining - fraction, 10)
        fills.append({"date": day, "price": round(price, 6), "fraction": round(fraction, 6), "reason": reason})

    for held in range(1, max_hold + 1):
        i = entry_index + held - 1
        if i >= len(bars):
            return {"status": "observing", "entry": entry, "stop": stop, "held": held - 1}
        bar = bars[i]
        o, h, l, c = (float(bar[k]) for k in ("open", "high", "low", "close"))
        if exit_next_open:
            fill(o, remaining, "trend_exit", bar["date"])
            break
        active_stop = max(stop, trail_stop) if trail_stop else stop
        if o <= active_stop:
            fill(o, remaining, "stop_gap" if active_stop == stop else "trail_gap", bar["date"])
            break
        if l <= active_stop:
            fill(active_stop, remaining, "stop" if active_stop == stop else "trail", bar["date"])
            break
        for target in targets:
            if target["fraction"] and (o >= target["price"] or h >= target["price"]):
                fill(target["price"], min(target["fraction"], remaining), "target", bar["date"])
                target["fraction"] = 0
                if trail and trail_after:
                    trailing_active = True
        if remaining <= 1e-9:
            break
        if held == max_hold:
            fill(c, remaining, "time", bar["date"])
            break
        # Update exits for the next bar from this completed bar only.
        highest = max(highest, c)
        if trail and trailing_active:
            if trail["kind"] == "chandelier":
                value = atr(bars, i, trail["period"])
                candidate = highest - trail["mult"] * value if value else None
            elif trail["kind"] == "pct_close":
                candidate = highest * (1 - trail["pct"])
            elif trail["kind"] == "ma_close":
                candidate, exit_next_open = None, c < ema[i]
            else:
                raise ValueError(f"unknown trail kind {trail['kind']}")
            if candidate and candidate < c:
                trail_stop = max(trail_stop or 0, candidate)
    net = gross - 2 * cost_per_side
    return {"status": "resolved", "entry_date": bars[entry_index]["date"], "entry": round(entry, 6), "stop": round(stop, 6), "risk_pct": round(risk / entry, 8),
            "gross_return": round(gross, 8), "net_return": round(net, 8), "r_multiple": round(net / (risk / entry), 6),
            "held": held, "exit_reason": fills[-1]["reason"], "fills": fills}
