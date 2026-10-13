"""The monthly-led and weekly-led buy system (docs/BUY_SYSTEM_ZH.md 0.2.0). Research only.

One engine, two kinds of opportunity that differ only in their timeframes:

  kind     filter                 direction   place    timing
  month    -                      month       week     day
  week     month (not against)    week        day      day

For each kind, every layer must pass in order:
  1 background on the direction timeframe: A pullback (15-50%) inside a long uptrend, or B completed base (a second bottom);
  2 confirmation on the direction timeframe: a descending trendline broken in step with MACD, or a fresh second bottom with a
    follow-through bar and a turning MACD;
  3 place on the place timeframe inside the confirmation window: T1 retest of the trendline, neckline, EMA20 or EMA50; T3 back to
    half of a confirming candle; T4 launch from converged EMAs;
  4 timing on daily bars: a close above the previous day's high with a rising MACD histogram, bought at the next open unless that
    open gaps down by more than one daily ATR;
  5 one shared list of vetoes, a stop under the nearest unbroken swing low of the direction timeframe, targets where a Fibonacci
    line of the decline is confirmed by two bar highs, and at least 1.5R to the first target.
Exits: two thirds at the first target, then the stop moves to the entry and the last third rides until the kind's trend line
breaks (30-week average for a monthly opportunity, 50-day average for a weekly one).

Point in time: weekly and monthly bars count only once their last session has closed; a swing point is lower (higher) than the
two bars on its left and the one on its right, so it is known one bar later; EMAs and MACD are causal; nothing is traded before
the confirmation that allows it is known.
"""
from __future__ import annotations

import datetime as dt

from research.lab import structure

FIELDS = ("open", "high", "low", "close", "volume")

PARAMS = {
    "swing": {"left": 2, "right": 1},
    "trendline": {"anchor_lookback": {"month": 36, "week": 52}, "min_gap": 3, "break_pct": 0.01, "touch_pct": 0.02, "touch_atr": 0.5},
    "sync": {"before": 3, "after": 3, "slow_after": 6, "rising_bars": 3},
    "place": {"tol_pct": 0.02, "tol_atr": 0.5, "min_pullback_atr": 1.0, "confirm_body_atr": 1.0, "converge_pct": 0.02, "converge_atr": 1.0,
              "t3_place_bars": {"week": 6, "day": 10}, "t3_direction_bars": 3, "t4_low_bars": {"week": 8, "day": 40}, "t4": True},
    "daily": {"window": 10, "zone_atr": 1.0, "gap_atr": 1.0},
    "veto": {"chase_atr": 2.0, "up_weeks": 3, "up_months": 5, "recent_bars": 3, "big_bear_atr": 1.5, "ema50_lost_bars": 8,
             "box_weeks": 52, "box_slope": 0.03, "box_ratio": 0.5, "place_macd": True},
    "risk": {"buffer_pct": 0.01, "buffer_atr": 0.25, "min_rr": 1.5, "max_stop": 0.40, "fibs": [0.382, 0.5, 0.618, 0.786],
             "confirm_pct": 0.03, "confirm_bars": 2},
    "exit": {"first_fraction": 2 / 3, "max_sessions": 5040},
    "kinds": {
        "month": {
            "filter": None, "direction": "month", "place": "week", "window": 6,
            "a": {"rise": 6, "min_bars_ema200": 200, "high_lookback": 24, "leg_lookback": 60, "min_pullback": 0.15, "max_pullback": 0.50,
                  "touch_pct": 0.02, "touch_atr": 0.5, "gp": [0.5, 0.7]},
            "b": {"lookback": 36, "tol_pct": 0.03, "tol_atr": 0.5, "min_gap": 3, "follow_bars": 3, "follow_body_atr": 0.5},
            "runner": {"kind": "period_sma", "period": "week", "length": 30},
        },
        "week": {
            "filter": "month", "direction": "week", "place": "day", "window": 6,
            "a": {"rise": 26, "min_bars_ema200": 200, "high_lookback": 52, "leg_lookback": 156, "min_pullback": 0.15, "max_pullback": 0.50,
                  "touch_pct": 0.02, "touch_atr": 0.5, "gp": [0.5, 0.7]},
            "b": {"lookback": 78, "tol_pct": 0.03, "tol_atr": 0.5, "min_gap": 4, "follow_bars": 3, "follow_body_atr": 0.5},
            "runner": {"kind": "daily_sma", "length": 50},
        },
    },
}


# ---------------------------------------------------------------- bars and indicators

def _key(day, period):
    if period == "month":
        return day[:7]
    return dt.date.fromisoformat(day).isocalendar()[:2]


def periods(s, period):
    """Weekly or monthly bars from daily columns; `start` and `end` are each bar's first and last daily index."""
    out = {"date": [], "start": [], "end": [], **{k: [] for k in FIELDS}}
    key = None
    for i, day in enumerate(s["date"]):
        k = _key(day, period)
        if k != key:
            key = k
            out["start"].append(i)
            out["end"].append(i)
            out["date"].append(day)
            for f in FIELDS:
                out[f].append(s[f][i])
            continue
        out["end"][-1] = i
        out["date"][-1] = day
        out["high"][-1] = max(out["high"][-1], s["high"][i])
        out["low"][-1] = min(out["low"][-1], s["low"][i])
        out["close"][-1] = s["close"][i]
        out["volume"][-1] += s["volume"][i]
    return _indicators(out)


def daily_bars(s):
    """Daily bars in the same form as weekly and monthly ones (each bar starts and ends on its own day)."""
    out = _indicators({"date": list(s["date"]), **{k: list(s[k]) for k in FIELDS}})
    out["start"] = out["end"] = list(range(len(s["close"])))
    out["daily"] = True
    return out


def _ema(values, n):
    out, e, k = [], None, 2 / (n + 1)
    for x in values:
        e = x if e is None else x * k + e * (1 - k)
        out.append(e)
    return out


def _indicators(b):
    c = b["close"]
    for n in (20, 50, 200):
        b[f"ema{n}"] = _ema(c, n)
    fast, slow = _ema(c, 12), _ema(c, 26)
    b["dif"] = [x - y for x, y in zip(fast, slow)]
    b["dea"] = _ema(b["dif"], 9)
    b["hist"] = [x - y for x, y in zip(b["dif"], b["dea"])]
    tr = [b["high"][i] - b["low"][i] if i == 0 else max(b["high"][i] - b["low"][i], abs(b["high"][i] - c[i - 1]), abs(b["low"][i] - c[i - 1]))
          for i in range(len(c))]
    b["atr"] = [sum(tr[max(0, i - 13):i + 1]) / len(tr[max(0, i - 13):i + 1]) for i in range(len(tr))]
    b["sma30"] = [sum(c[max(0, i - 29):i + 1]) / len(c[max(0, i - 29):i + 1]) for i in range(len(c))]
    return b


def completed(b, day_index, total_days):
    """Index of the last bar whose final session is at or before `day_index` (the data's last bar counts only if more data follows)."""
    lo, hi, found = 0, len(b["end"]) - 1, -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if b["end"][mid] <= day_index:
            found, lo = mid, mid + 1
        else:
            hi = mid - 1
    if found == len(b["end"]) - 1 and b["end"][found] == total_days - 1 and not b.get("daily"):
        found -= 1  # an open week or month at the end of the data is not complete
    return found


def pivots(values, mode, left=2, right=1):
    """Swing points: at least as low (high) as the `left` bars before and the `right` bars after; index j is known at bar j + right."""
    out = []
    for j in range(left, len(values) - right):
        around = values[j - left:j] + values[j + 1:j + right + 1]
        if (mode == "high" and values[j] >= max(around)) or (mode == "low" and values[j] <= min(around)):
            out.append(j)
    return out


def _known(points, k, right):
    return [j for j in points if j + right <= k]


def _tol(b, i, pct, atr_mult, price=None):
    price = b["close"][i] if price is None else price
    return max(price * pct, b["atr"][i] * atr_mult)


def _bull_engulf(b, i):
    if i < 1:
        return False
    po, pc, o, c = b["open"][i - 1], b["close"][i - 1], b["open"][i], b["close"][i]
    return pc < po and c > o and o <= pc and c >= po


def _bear_engulf(b, i):
    if i < 1:
        return False
    po, pc, o, c = b["open"][i - 1], b["close"][i - 1], b["open"][i], b["close"][i]
    return pc > po and c < o and o >= pc and c <= po


# ---------------------------------------------------------------- layer 1: background on the direction timeframe

def background(X, k, cfg, lows, W=None, w=None):
    """A (pullback inside a long uptrend) or B (completed base) at completed direction bar k; returns (bg, reason).
    A second bottom takes precedence: it is the more specific pattern (DVN 2013 had both)."""
    if k < 12:
        return None, "history_too_short"
    a = cfg["a"]
    c, lo = X["close"], X["low"]
    found_a = None
    if k + 1 >= a["min_bars_ema200"]:
        up = X["ema50"][k] > X["ema200"][k] and X["ema200"][k] > X["ema200"][k - a["rise"]] and c[k] >= X["ema200"][k]
        basis = "ema200"
    else:
        # Too young for a 200-bar average: a rising EMA50, plus a rising 30-week line when the direction is monthly.
        weekly_up = W is None or (w is not None and w >= 35 and W["sma30"][w] > W["sma30"][w - 5] and W["close"][w] >= W["sma30"][w])
        up = X["ema50"][k] > X["ema50"][k - a["rise"]] and c[k] >= X["ema50"][k] * 0.9 and weekly_up
        basis = "ema50_fallback"
    h_idx = max(range(max(0, k - a["high_lookback"]), k + 1), key=lambda i: (X["high"][i], i))
    if up and h_idx < k:  # the pullback comes after the high's own bar
        high = X["high"][h_idx]
        low_after = min(lo[h_idx + 1:k + 1])
        depth = 1 - low_after / high
        touched = sorted({n for n in ("ema20", "ema50") for t in range(h_idx + 1, k + 1)
                          if lo[t] <= X[n][t] + _tol(X, t, a["touch_pct"], a["touch_atr"], X[n][t])})
        leg_low = min(lo[max(0, h_idx - a["leg_lookback"]):h_idx + 1])
        retrace = (high - low_after) / (high - leg_low) if high > leg_low else 0
        # A pullback, not a collapse: deeper than max_pullback must qualify as a completed base instead.
        if depth <= a["max_pullback"] and (depth >= a["min_pullback"] or touched or a["gp"][0] <= retrace <= a["gp"][1]):
            found_a = {"kind": "A", "basis": basis, "swing_high": (X["date"][h_idx], round(high, 4)), "pullback_low": round(low_after, 4),
                       "depth": round(depth, 4), "touched": touched, "retrace": round(retrace, 4), "structure_low": low_after, "_top": h_idx}
    b = second_bottom(X, k, cfg["b"], lows)
    if b:
        b["uptrend_context"] = bool(found_a)
        return b, None
    if found_a:
        return found_a, None
    return None, "no_pullback_or_base"


def second_bottom(X, k, bp, lows):
    """B: two lows after the decline's high, the second confirmed by a strong follow-through bar. The second bottom may be a higher
    low (BABA 2025 on its weekly EMA50) but not lower than the first beyond the tolerance and no higher than halfway up the rebound."""
    c, lo = X["close"], X["low"]
    top = max(range(max(0, k - bp["lookback"]), k + 1), key=lambda i: (X["high"][i], i))
    known = [j for j in lows if top < j and j + 1 <= k]
    if len(known) < 2:
        return None
    floor = min(lo[j] for j in known)
    for second in known[::-1]:
        for first in [j for j in known if second - j >= bp["min_gap"]]:
            tol = _tol(X, second, bp["tol_pct"], bp["tol_atr"], lo[first])
            base = min(lo[first], lo[second])
            between = X["high"][first + 1:second]
            if not between or lo[first] > floor + tol or min(lo[first:second + 1]) < base - tol:
                continue
            neck = max(between)
            if lo[second] < lo[first] - tol or lo[second] > lo[first] + 0.5 * (neck - lo[first]):
                continue
            if neck - max(lo[first], lo[second]) < X["atr"][second] or min(lo[second:k + 1]) < base - tol:
                continue
            follow = [f for f in range(second + 1, min(second + bp["follow_bars"], k) + 1)
                      if c[f] > X["open"][f] and c[f] > c[second] and c[f] - X["open"][f] >= bp["follow_body_atr"] * X["atr"][f]]
            if follow:
                return {"kind": "B", "decline_high": (X["date"][top], round(X["high"][top], 4)),
                        "first_bottom": (X["date"][first], round(lo[first], 4)), "second_bottom": (X["date"][second], round(lo[second], 4)),
                        "follow_through": X["date"][follow[0]], "neckline": round(neck, 4), "structure_low": base,
                        "_top": top, "_first": first, "_second": second, "_follow": follow[0]}
    return None


# ---------------------------------------------------------------- layer 2: confirmation on the direction timeframe

def trendline(b, k, period, p, highs):
    """The descending line from the major high before bar k, through the swing high that keeps every later swing high under it."""
    tp, right = p["trendline"], p["swing"]["right"]
    lo = max(0, k - tp["anchor_lookback"][period])
    known = [j for j in _known(highs, k - 1, right) if j >= lo]
    if len(known) < 2:
        return None
    a = max(known, key=lambda j: (b["high"][j], -j))
    after = [j for j in known if j - a >= tp["min_gap"] and b["high"][j] < b["high"][a] * 0.995]
    if not after:
        return None
    slope, second = max(((b["high"][j] - b["high"][a]) / (j - a), j) for j in after)
    if slope >= 0:
        return None
    line = lambda x: b["high"][a] + slope * (x - a)
    if any(b["close"][x] > line(x) * (1 + tp["break_pct"]) for x in range(second + 1, k)):
        return None  # already broken before k
    touches = [j for j in known if j >= a and abs(b["high"][j] - line(j)) <= _tol(b, j, tp["touch_pct"], tp["touch_atr"], line(j))]
    return {"anchor": a, "second": second, "slope": slope, "line": line, "pushes": len(touches)}


def crosses(b):
    return [c for c in range(1, len(b["dif"])) if b["dif"][c - 1] <= b["dea"][c - 1] and b["dif"][c] > b["dea"][c]]


def sync(b, k, p, cross_list):
    """When the breakout at bar k counts as in step with MACD: (valid bar, kind) or None."""
    sp = p["sync"]
    near = [c for c in cross_list if k - sp["before"] <= c <= k + sp["after"]]
    if near:
        return max(k, near[0]), "golden_cross"
    h = b["hist"]
    if k >= sp["rising_bars"] and h[k] < 0 and all(h[k - n] > h[k - n - 1] for n in range(sp["rising_bars"])):
        return k, "about_to_cross"
    if b["dif"][k] > b["dea"][k] and h[k] >= h[k - 1]:
        return k, "already_crossed_rising"
    late = [c for c in cross_list if k + sp["after"] < c <= k + sp["slow_after"]]
    if late:
        return late[0], "slow_cross"
    return None


def confirmations(X, period, cfg, p, lows):
    """Every confirmation on the direction timeframe, with the bar it becomes known: trendline breakouts in step with MACD, and fresh
    second bottoms (the follow-through bar) whose MACD histogram is turning up or above its signal line."""
    highs = pivots(X["high"], "high", p["swing"]["left"], p["swing"]["right"])
    cross_list, out = crosses(X), []
    for k in range(30, len(X["close"])):
        line = trendline(X, k, period, p, highs)
        if line and X["close"][k] > line["line"](k) * (1 + p["trendline"]["break_pct"]):
            s = sync(X, k, p, cross_list)
            if s:
                out.append({"source": "trendline", "at": k, "valid": s[0], "sync": s[1], "line": line})
        b = second_bottom(X, k, cfg["b"], lows)
        if b and b["_follow"] == k and (X["hist"][k] > X["hist"][k - 1] or X["dif"][k] > X["dea"][k]):
            out.append({"source": "second_bottom", "at": k, "valid": k, "sync": "macd_turning", "line": None, "base": b})
    return sorted(out, key=lambda s: s["valid"])


# ---------------------------------------------------------------- layers 3 and 4: place and daily timing

def daily_entry(D, Dd, first, p):
    """Timing (user, 2026-10-12): from `first`, within the window, the first day that closes above the previous day's high while the
    daily MACD histogram rises; buy at the next open. An open more than one daily ATR below the signal close cancels that day's order
    and the search goes on."""
    dp = p["daily"]
    last = min(first + dp["window"] - 1, len(D["close"]) - 2)
    for i in range(max(1, first), last + 1):
        if D["close"][i] > D["high"][i - 1] and Dd["hist"][i] > Dd["hist"][i - 1]:
            if D["open"][i + 1] < D["close"][i] - dp["gap_atr"] * Dd["atr"][i]:
                continue
            return i, i + 1, D["open"][i + 1]
    return None


def _zone_touch(D, Dd, level, first, last, atr_mult):
    """First day whose range reaches `level` +/- atr_mult daily ATRs."""
    for i in range(first, min(last, len(D["close"]) - 1) + 1):
        a = atr_mult * Dd["atr"][i]
        if D["low"][i] <= level + a and D["high"][i] >= level - a:
            return i
    return None


def places(D, Dd, X, P, setup, kind, p, valid_day, last_day):
    """Places on the place timeframe inside the confirmation window, each timed by the daily layer; earliest fill first.
    T1 retest of the trendline, neckline, EMA20 or EMA50 after a real pullback; T3 back to half of a confirming candle (place or
    direction timeframe); T4 launch from converged EMAs with a MACD cross. (An engulfing with follow-through is the daily timing
    itself, so it is not a separate place.)"""
    pp, n, out = p["place"], len(D["close"]), []
    place_tf, direction_tf = p["kinds"][kind]["place"], p["kinds"][kind]["direction"]

    def add(t, bar, place_day, stop_base, **info):
        found = daily_entry(D, Dd, max(place_day, valid_day + 1), p)
        if found:
            out.append({"type": t, "bar": bar, "place_day": place_day, "signal_day": found[0], "fill_day": found[1], "entry": found[2],
                        "stop_base": stop_base, **info})

    line, neck = setup["line"], (setup.get("base") or {}).get("neckline")
    j0, j1 = completed(P, valid_day, n) + 1, completed(P, last_day, n)
    post_high = None
    for j in range(max(1, j0), j1 + 1):
        place_day = P["end"][j]
        post_high = P["high"][j] if post_high is None else max(post_high, P["high"][j])
        if post_high - P["low"][j] >= pp["min_pullback_atr"] * P["atr"][j]:
            supports = [("ema20", P["ema20"][j]), ("ema50", P["ema50"][j])]
            if line:
                supports.insert(0, ("trendline", line["line"](completed(X, place_day, n) + 1)))
            if neck:
                supports.insert(0, ("neckline", neck))
            for name, sup in supports:
                tol = max(pp["tol_pct"] * sup, pp["tol_atr"] * P["atr"][j])
                if sup - tol <= P["low"][j] <= sup + tol and P["close"][j] > sup:
                    add("T1", (place_tf, j), place_day, P["low"][j], support=name, support_level=round(sup, 4))
                    break
        body = P["close"][j] - P["open"][j]
        if body > 0 and (_bull_engulf(P, j) or body >= pp["confirm_body_atr"] * P["atr"][j]):
            half = P["open"][j] + body / 2
            last = P["end"][min(j + pp["t3_place_bars"][place_tf], len(P["end"]) - 1)]
            touch = _zone_touch(D, Dd, half, place_day + 1, last, p["daily"]["zone_atr"])
            if touch is not None:
                add("T3", (place_tf, j), touch, P["low"][j], candle="engulfing" if _bull_engulf(P, j) else "big_body", half=round(half, 4))
        e = (P["ema20"][j - 1], P["ema50"][j - 1], P["ema200"][j - 1])
        spread = max(e) - min(e)
        if pp["t4"] and (spread <= pp["converge_pct"] * P["close"][j - 1] or spread <= pp["converge_atr"] * P["atr"][j - 1]) \
                and P["close"][j] > max(P["ema20"][j], P["ema50"][j], P["ema200"][j]) and P["dif"][j - 1] <= P["dea"][j - 1] and P["dif"][j] > P["dea"][j]:
            add("T4", (place_tf, j), place_day, min(P["low"][max(0, j - pp["t4_low_bars"][place_tf] + 1):j + 1]), spread=round(spread / P["close"][j - 1], 4))
    for k in range(setup["valid"], min(setup["valid"] + p["kinds"][kind]["window"], len(X["close"]) - 1) + 1):
        body = X["close"][k] - X["open"][k]
        if body > 0 and (_bull_engulf(X, k) or body >= pp["confirm_body_atr"] * X["atr"][k]) and X["end"][k] >= valid_day:
            half = X["open"][k] + body / 2
            last = X["end"][min(k + pp["t3_direction_bars"], len(X["end"]) - 1)]
            touch = _zone_touch(D, Dd, half, X["end"][k] + 1, last, p["daily"]["zone_atr"])
            if touch is not None:
                add("T3", (direction_tf, k), touch, X["low"][k], candle="engulfing" if _bull_engulf(X, k) else "big_body", half=round(half, 4))
    return sorted(out, key=lambda t: t["fill_day"])


# ---------------------------------------------------------------- layer 5a: one shared list of vetoes

def vetoes(D, Dd, bars, kind, day, entry, bg, p, lows):
    """The vetoes, the same for both kinds. Direction checks read the direction timeframe; chasing always reads the weekly and monthly
    bars; place checks read the place timeframe."""
    cfg, vp, n, out = p["kinds"][kind], p["veto"], len(D["close"]), []
    X, P, W, M = bars[cfg["direction"]], bars[cfg["place"]], bars["week"], bars["month"]
    k, j, w, m = completed(X, day, n), completed(P, day, n), completed(W, day, n), completed(M, day, n)
    right = p["swing"]["right"]
    # The higher timeframe must not be against the trade (weekly opportunities only).
    if cfg["filter"]:
        F = bars[cfg["filter"]]
        f = completed(F, day, n)
        fl = _known(lows[cfg["filter"]], f, right)
        if len(fl) >= 2 and F["low"][fl[-1]] < F["low"][fl[-2]] and F["hist"][f] < 0 and F["hist"][f] < F["hist"][f - 1]:
            out.append(f"{cfg['filter']}_still_falling")
    # Direction: still falling.
    xl = _known(lows[cfg["direction"]], k, right)
    if bg["kind"] == "A" and len(xl) >= 2 and X["low"][xl[-1]] < X["low"][xl[-2]] and X["close"][k] < X["ema200"][k]:
        out.append("still_falling")
    if bg["kind"] == "B" and X["hist"][k] < X["hist"][k - 1] < 0:
        out.append("macd_not_turned")
    checks = structure.assess(D, day)
    if checks["details"]["deep_drawdown"]["reject"] and bg["kind"] != "B":
        out.append("deep_fall_no_base")
    if checks["details"]["wide_box"]["reject"]:
        out.append("wide_box")
    if checks["details"]["bearish_pressure"]["flag"]:
        out.append("bearish_pressure")
    # Chasing, read on weekly and monthly bars for both kinds.
    if entry > W["ema20"][w] + vp["chase_atr"] * W["atr"][w]:
        out.append("far_above_weekly_ema20")
    for name, B_, i0, limit in (("weeks", W, w, vp["up_weeks"]), ("months", M, m, vp["up_months"])):
        run = 0
        for i in range(i0, 0, -1):
            if B_["close"][i] > B_["close"][i - 1]:
                run += 1
            else:
                break
        if run >= limit:
            out.append(f"up_{run}_{name}_in_a_row")
    lo_w = max(0, w - vp["box_weeks"] + 1)
    hi, lo = max(W["high"][lo_w:w + 1]), min(W["low"][lo_w:w + 1])
    if w >= 13 and abs(W["ema50"][w] / W["ema50"][w - 13] - 1) <= vp["box_slope"] and hi / lo - 1 <= vp["box_ratio"] and W["close"][w] > lo + (hi - lo) / 2:
        out.append("upper_half_of_box")
    # Place timeframe: momentum, a bearish bar not taken back, EMA50 lost and not taken back.
    h = P["hist"]
    if vp["place_macd"] and not (h[j] > h[j - 1] or (P["dif"][j] > P["dea"][j] and not (h[j] < h[j - 1] < h[j - 2]))):
        out.append("macd_weakening")
    for i in range(max(1, j - vp["recent_bars"] + 1), j + 1):
        big = P["open"][i] - P["close"][i] >= vp["big_bear_atr"] * P["atr"][i]
        if (_bear_engulf(P, i) or big) and P["close"][j] < P["open"][i]:
            out.append("bearish_bar_not_reclaimed")
            break
    for i in range(j, max(1, j - vp["ema50_lost_bars"] + 1) - 1, -1):
        if P["close"][i - 1] >= P["ema50"][i - 1] and P["close"][i] < P["ema50"][i]:
            if all(P["close"][x] < P["ema50"][x] for x in range(i, j + 1)):
                out.append("ema50_lost")
            break
    return out, checks


# ---------------------------------------------------------------- layer 5b: stop, targets, R

def confluence(D, T, last, start_day, day, entry, neckline, rp):
    """Resistance above the entry on timeframe T: Fibonacci lines of the decline (its highest high since `start_day` to the lowest low
    after it) confirmed by two bar highs within 3%, the prior high and a base's neckline; plus the levels the entry sits just under."""
    highs = D["high"][start_day:day + 1]
    top = start_day + max(range(len(highs)), key=lambda i: (highs[i], -i))
    leg_high, leg_low = D["high"][top], min(D["low"][top:day + 1])
    first = completed(T, top - 1, len(D["close"])) + 1
    bars = [(T["date"][j], T["high"][j]) for j in range(max(0, first), last + 1)]
    levels = []
    for f in rp["fibs"]:
        price = leg_low + f * (leg_high - leg_low)
        near = [d for d, h in bars if abs(h - price) <= rp["confirm_pct"] * price]
        if len(near) >= rp["confirm_bars"]:
            levels.append({"price": price, "source": f"fib_{f}", "confirmed_by": near})
    levels.append({"price": leg_high, "source": "prior_high", "confirmed_by": [D["date"][top]]})
    if neckline:
        levels.append({"price": neckline, "source": "neckline", "confirmed_by": []})
    inside = [x for x in levels if x["price"] * (1 - rp["confirm_pct"]) <= entry < x["price"]]
    above = sorted((x for x in levels if x["price"] > entry * 1.005), key=lambda x: x["price"])
    return above, {"leg_high": leg_high, "leg_high_date": D["date"][top], "leg_low": leg_low, "inside": inside}


def nearest_unbroken_low(low, known, k, below):
    """The highest swing low under `below` that no later bar (up to k) traded under; one backward pass over the swing lows."""
    best, running, upto = None, float("inf"), k
    for j in reversed(known):
        if upto > j:
            running = min(running, min(low[j + 1:upto + 1]))
            upto = j
        if low[j] <= running and low[j] < below and (best is None or low[j] > best):
            best = low[j]
        if best is not None and running < best:
            break  # every earlier unbroken low is at most `running`, so none can beat `best`
    return best


def plan(D, bars, kind, day, entry, setup, bg, p, lows):
    """Stop under the nearest unbroken swing low of the direction timeframe; first target at the nearest confirmed resistance."""
    rp, cfg, n = p["risk"], p["kinds"][kind], len(D["close"])
    X, W = bars[cfg["direction"]], bars["week"]
    k, w = completed(X, day, n), completed(W, day, n)
    right = p["swing"]["right"]
    nearest = nearest_unbroken_low(X["low"], _known(lows[cfg["direction"]], k, right), k, entry * 0.995)
    base, basis = (nearest, "nearest_unbroken_low") if nearest is not None else (bg["structure_low"], "structure_low")
    stop = base - max(rp["buffer_pct"] * base, rp["buffer_atr"] * W["atr"][w])
    if not 0 < stop < entry:
        return None, "no_stop_below_entry"
    if (entry - stop) / entry > rp["max_stop"]:
        return {"stop": stop, "stop_basis": basis}, "stop_too_far"
    start = setup["line"]["anchor"] if setup["line"] else bg["_top"]
    zones, leg = confluence(D, X, k, X["start"][start], day, entry, bg.get("neckline"), rp)
    if leg["inside"]:
        return {"stop": stop, "stop_basis": basis, "inside": leg["inside"]}, "entry_inside_resistance"
    if not zones:
        return {"stop": stop, "stop_basis": basis}, "no_resistance_above"
    first = zones[0]["price"]
    final = zones[1]["price"] if len(zones) > 1 else first
    risk = entry - stop
    out = {"stop": stop, "stop_basis": basis, "target": first, "target2": final, "target_source": zones[0]["source"],
           "target_confirmed_by": zones[0]["confirmed_by"], "target2_source": zones[1]["source"] if len(zones) > 1 else "same",
           "rr": (first - entry) / risk, "rr2": (final - entry) / risk, "leg": leg}
    return out, ("rr_below_1.5" if out["rr"] < rp["min_rr"] else None)


# ---------------------------------------------------------------- scan and trade

def scan(D, kind="month", p=None, start=None, end=None, fast=False):
    """Signals and near misses of one kind for one stock (daily columns), with fill dates inside [start, end].
    `fast` returns the same signals without near-miss cards (the stop and target are checked before the slower vetoes)."""
    p = p or PARAMS
    cfg, n = p["kinds"][kind], len(D["close"])
    W, M, Dd = periods(D, "week"), periods(D, "month"), daily_bars(D)
    bars = {"month": M, "week": W, "day": Dd}
    X, P = bars[cfg["direction"]], bars[cfg["place"]]
    sw = p["swing"]
    lows = {tf: pivots(b["low"], "low", sw["left"], sw["right"]) for tf, b in bars.items() if tf != "day"}
    signals, misses, used = [], [], set()
    for setup in confirmations(X, cfg["direction"], cfg, p, lows[cfg["direction"]]):
        valid_day = X["end"][setup["valid"]]
        if valid_day >= n - 1:
            continue
        last_day = X["end"][min(setup["valid"] + cfg["window"], len(X["end"]) - 1)]
        for trig in places(D, Dd, X, P, setup, kind, p, valid_day, last_day):
            day = trig["signal_day"]
            if day <= valid_day or trig["fill_day"] in used:
                continue
            if (start and D["date"][trig["fill_day"]] < start) or (end and D["date"][trig["fill_day"]] > end):
                continue
            k = completed(X, day, n)
            if k < 12:
                continue
            bg, why = background(X, k, cfg, lows[cfg["direction"]], W if kind == "month" else None, completed(W, day, n))
            if bg is None:
                if not fast:
                    misses.append(_card(D, bars, kind, setup, {"kind": None, "reason": why}, trig, None, ["no_background"], None, day))
                continue
            if min(D["low"][valid_day:day + 1]) < bg["structure_low"] * (1 - cfg["b"]["tol_pct"]):
                if not fast:
                    misses.append(_card(D, bars, kind, setup, bg, trig, None, ["structure_broken"], None, day))
                continue
            risk, reason = plan(D, bars, kind, day, trig["entry"], setup, bg, p, lows)
            if fast and reason:
                continue
            vetoed, checks = vetoes(D, Dd, bars, kind, day, trig["entry"], bg, p, lows)
            if vetoed or reason:
                if not fast:
                    misses.append(_card(D, bars, kind, setup, bg, trig, risk, vetoed, reason, day, checks))
                continue
            card = _card(D, bars, kind, setup, bg, trig, risk, vetoed, reason, day, checks)
            signals.append(card)
            used.update(range(trig["fill_day"] - 10, trig["fill_day"] + 11))
            break
    return {"signals": signals, "near_misses": misses}


def _card(D, bars, kind, setup, bg, trig, risk, vetoed, reason, day, checks=None):
    """The evidence card: everything the machine saw and decided, in the order the layers ran."""
    X = bars[PARAMS["kinds"][kind]["direction"]]
    tb, ti = trig["bar"]
    T = bars[tb]
    line = setup["line"]
    card = {
        "kind": kind, "decision_date": D["date"][day], "fill_date": D["date"][trig["fill_day"]], "entry": round(trig["entry"], 4),
        "background": {k: v for k, v in bg.items() if k != "structure_low" and not k.startswith("_")},
        "confirmation": {"source": setup["source"], "date": X["date"][setup["at"]], "valid": X["date"][setup["valid"]], "sync": setup["sync"]},
        "place": {"type": trig["type"], "bar": (tb, T["date"][ti]), "known": D["date"][trig["place_day"]],
                  **{k: v for k, v in trig.items() if k not in ("type", "bar", "place_day", "signal_day", "fill_day", "entry", "stop_base")}},
        "timing": D["date"][trig["signal_day"]], "vetoes": vetoed, "gate5": reason, "flags": (checks or {}).get("flags", []),
    }
    if line:
        card["confirmation"]["trendline"] = {"start": (X["date"][line["anchor"]], round(X["high"][line["anchor"]], 4)),
                                              "second": (X["date"][line["second"]], round(X["high"][line["second"]], 4)), "pushes": line["pushes"]}
    if risk:
        for key in ("stop", "target", "target2", "rr", "rr2"):
            if risk.get(key) is not None:
                card[key] = round(risk[key], 4 if key not in ("rr", "rr2") else 2)
        for key in ("stop_basis", "target_source", "target2_source", "target_confirmed_by", "leg", "inside"):
            if risk.get(key):
                card[key] = risk[key]
    card["passed"] = not vetoed and reason is None
    return card


def trade(D, card, p=None, cost_per_side=0.001):
    """Two thirds at the first target; then the stop moves to the entry and the last third rides until the kind's trend line breaks
    (a weekly close under the 30-week average for a monthly opportunity, a daily close under the 50-day average for a weekly one),
    sold at the next open; no time limit."""
    from research.lab.datasets import BarsView
    from research.lab.exit_rules import simulate
    p = p or PARAMS
    variant = {"stop": {"kind": "level", "price": card["stop"]},
               "targets": [{"price": card["target"], "fraction": p["exit"]["first_fraction"]}],
               "breakeven_after_target": True, "trend_after_target": True,
               "trend_exit": dict(p["kinds"][card["kind"]]["runner"]), "max_hold": p["exit"]["max_sessions"]}
    return simulate(BarsView(D), D["date"].index(card["fill_date"]), variant, cost_per_side=cost_per_side)
