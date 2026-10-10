"""Data-driven trade simulation for the quant research lab.

One function, `simulate`, runs any exit/stop variant described as data, so a
new idea is a new spec entry rather than new code. Semantics follow the
production policy in services/scanner/support_risk.py (which the "support_cap"
stop with a single 2R target reproduces exactly):

- entry at the open of `bars[entry_index]` (the session after the signal);
- daily bars only, so a stop is checked before a target on the same bar;
- an open below the stop fills at that open; a target fills at the target;
- trailing stops and indicators use completed bars only and never move down;
- a "structure" stop holds the opportunity until a close of its own
  timeframe (day, week or month) ends below the opportunity's structure
  floor, then sells at the next open; a wide disaster stop guards gaps;
- an optional `trend_exit` sells at the next open once the trend ends, in
  the published forms: a weekly or monthly close below its N-period average
  (Weinstein's 30 weeks, O'Neil's 10 weeks, Faber's 10 months), a daily close
  below the prior N-day low (Turtle System 2) or the N-day average, or a
  month-end close below the close N months earlier (time-series momentum).

Options for trading by opportunity level (E7b), all off unless given:
- a "level" stop: a fixed price frozen at the signal (for example 2% below the
  daily volume profile's value-area low), checked intraday like any stop;
- `min_hold` sessions and `min_periods` ({"period", "count"}: full weeks or
  months after the entry's own period) before any exit other than the stop;
- `max_periods`: a time exit at the close that completes that many full
  periods after the entry's period (for example five monthly bars);
- `no_progress` ({"sessions", "gain"}): if no close reached entry x (1 + gain)
  by the close of that session, sell at the next open (case ledger BTDR);
- `"arm": true` on a trend exit: it can only fire after a completed bar on the
  right side of its line, because a pullback buy often starts below it while
  the published systems buy above it.
"""
from __future__ import annotations

import datetime as _dt

from services.scanner.support_risk import executable_stop

# Exits that fill at the session open; every other exit fills during or at the close of its bar.
OPEN_FILLS = {"stop_gap", "trail_gap", "trend_exit", "structure_exit", "no_progress"}


def period_key(day, period):
    if period == "day":
        return day
    if period == "week":
        return _dt.date.fromisoformat(day).isocalendar()[:2]
    if period == "month":
        return day[:7]
    raise ValueError(f"unknown period {period}")


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
    if kind == "structure":
        # Only the disaster level is an intraday stop; the floor is checked on period closes.
        return entry * (1 - stop_rule["disaster"])
    if kind == "level":
        return stop_rule["price"] if 0 < stop_rule["price"] < entry else None
    raise ValueError(f"unknown stop kind {kind}")


def trend_ended(trend, i, close, start, prefix, lows, period_pos, period_close):
    """True when the completed bar `i` ends the trend under the published rule."""
    n, kind = trend["length"], trend["kind"]
    k = i - start
    if kind == "daily_sma":
        return k + 1 >= n and close < (prefix[k + 1] - prefix[k + 1 - n]) / n
    if kind == "prior_low":
        return k >= n and close < min(lows[k - n:k])
    if i not in period_pos:
        return False
    m = period_pos[i]
    if kind == "period_sma":
        return m + 1 >= n and close < sum(period_close[m - n + 1:m + 1]) / n
    if kind == "period_momentum":
        return m >= n and close < period_close[m - n]
    raise ValueError(f"unknown trend exit {kind}")


def trend_state(trend, i, close, start, prefix, lows, period_pos, period_close):
    """True when bar `i` ends the trend, False when it is on the trend's side of the line, None when the rule cannot judge this bar."""
    n, kind = trend["length"], trend["kind"]
    k = i - start
    if kind == "daily_sma":
        return close < (prefix[k + 1] - prefix[k + 1 - n]) / n if k + 1 >= n else None
    if kind == "prior_low":
        return close < min(lows[k - n:k]) if k >= n else None
    if i not in period_pos:
        return None
    m = period_pos[i]
    if kind == "period_sma":
        return close < sum(period_close[m - n + 1:m + 1]) / n if m + 1 >= n else None
    if kind == "period_momentum":
        return close < period_close[m - n] if m >= n else None
    raise ValueError(f"unknown trend exit {kind}")


def _period_end(bars, i, period):
    return i + 1 < len(bars) and period_key(bars[i]["date"], period) != period_key(bars[i + 1]["date"], period)


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
    structure = variant["stop"] if variant["stop"]["kind"] == "structure" else None
    # Risk is measured to the nearer of the floor and the disaster stop.
    risk_stop = max(stop, min(structure["floor"], entry * 0.999)) if structure else stop
    risk = entry - risk_stop
    targets = sorted(({"price": entry + t["r"] * risk, "fraction": t["fraction"]} for t in variant.get("targets", [])), key=lambda t: t["price"])
    trail, trail_after = variant.get("trail"), variant.get("trail_after_target", False)
    max_hold = variant["max_hold"]
    # Only the moving-average exit needs the whole close history.
    ema = ema_series([float(b["close"]) for b in bars], trail["period"]) if trail and trail["kind"] == "ma_close" else None
    trend = variant.get("trend_exit")
    if trend:
        # Precompute only the stretch of history the trend rule can look at.
        per_period = {"day": 1, "week": 5, "month": 21}[trend.get("period", "day")]
        start = max(0, entry_index - (trend["length"] + 2) * per_period - 5)
        end = min(len(bars) - 1, entry_index + max_hold)
        window = [float(bars[j]["close"]) for j in range(start, end + 1)]
        prefix = [0.0]
        for v in window:
            prefix.append(prefix[-1] + v)
        lows = [float(bars[j]["low"]) for j in range(start, end + 1)] if trend["kind"] == "prior_low" else None
        period_pos, period_close = {}, []
        if trend["kind"] in ("period_sma", "period_momentum"):
            keys = [period_key(bars[j]["date"], trend["period"]) for j in range(start, min(len(bars) - 1, end + 1) + 1)]
            for j in range(start, end + 1):
                if j + 1 - start < len(keys) and keys[j - start] != keys[j + 1 - start]:
                    period_pos[j] = len(period_close)
                    period_close.append(window[j - start])
    remaining, gross, fills, highest = 1.0, 0.0, [], entry
    trailing_active = bool(trail) and not trail_after
    trail_stop, exit_next_open, exit_reason_next = None, False, "trend_exit"
    min_hold, min_periods, max_periods = variant.get("min_hold", 0), variant.get("min_periods"), variant.get("max_periods")
    no_progress = variant.get("no_progress")
    counted = min_periods or max_periods
    entry_period = period_key(bars[entry_index]["date"], counted["period"]) if counted else None
    periods_done, armed, best_close = 0, False, 0.0

    def fill(price, fraction, reason, day):
        nonlocal remaining, gross
        gross += fraction * (price / entry - 1)
        remaining = round(remaining - fraction, 10)
        fills.append({"date": day, "price": round(price, 6), "fraction": round(fraction, 6), "reason": reason})

    for held in range(1, max_hold + 1):
        i = entry_index + held - 1
        if i >= len(bars):
            return {"status": "observing", "entry": entry, "stop": risk_stop, "held": held - 1}
        bar = bars[i]
        o, h, l, c = (float(bar[k]) for k in ("open", "high", "low", "close"))
        if exit_next_open:
            fill(o, remaining, exit_reason_next, bar["date"])
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
        if counted and _period_end(bars, i, counted["period"]) and period_key(bar["date"], counted["period"]) != entry_period:
            periods_done += 1
        if held == max_hold or (max_periods and periods_done >= max_periods["count"]):
            fill(c, remaining, "time", bar["date"])
            break
        # Exits other than the stop wait for the minimum holding period.
        allowed = held >= min_hold and (not min_periods or periods_done >= min_periods["count"])
        best_close = max(best_close, c)
        if no_progress and held == no_progress["sessions"] and allowed and best_close < entry * (1 + no_progress["gain"]) and i + 1 < len(bars):
            exit_next_open = True
            exit_reason_next = "no_progress"
        if structure and i + 1 < len(bars) and c < structure["floor"] \
                and period_key(bar["date"], structure["period"]) != period_key(bars[i + 1]["date"], structure["period"]):
            exit_next_open = True
            exit_reason_next = "structure_exit"
        if trend and not exit_next_open:
            if trend.get("arm") or min_hold or min_periods:
                state = trend_state(trend, i, c, start, prefix, lows, period_pos, period_close)
                armed = armed or state is False
                if state and allowed and (armed or not trend.get("arm")):
                    exit_next_open = True
                    exit_reason_next = "trend_exit"
            elif trend_ended(trend, i, c, start, prefix, lows, period_pos, period_close):
                exit_next_open = True
                exit_reason_next = "trend_exit"
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
    return {"status": "resolved", "entry_date": bars[entry_index]["date"], "entry": round(entry, 6), "stop": round(risk_stop, 6), "risk_pct": round(risk / entry, 8),
            "gross_return": round(gross, 8), "net_return": round(net, 8), "r_multiple": round(net / (risk / entry), 6),
            "held": held, "exit_reason": fills[-1]["reason"], "fills": fills}
