"""Monthly-led buy system (docs/BUY_SYSTEM_ZH.md): five gates that must all pass.

Research only. `scan` reads one stock's adjusted daily columns and returns
every point-in-time signal with its evidence card, plus the near misses
(setups that reached a trigger but failed a later gate) so the user can see
what was rejected and why.

Point in time: weekly and monthly bars count only once their last session has
closed; swing points need two completed bars on their right; EMAs and MACD are
causal; the structure checks read daily bars up to the decision day. Entries
fill on later daily bars (a close above the trigger bar's high, then the next
open; or a limit order at half of a confirming candle).

Gates, as in the document:
  1 monthly background: A uptrend pullback, or B base completed (second bottom
    or compression breakout);
  2 pattern and sync: a descending trendline from the major high broken by a
    close 1% above it, with MACD crossing within 3 bars (or about to cross, or
    already crossed with a rising histogram); a cross 4-6 bars late is "slow";
  3 entry inside the setup window: T1 first retest after a real pullback, T2
    bullish engulfing with follow-through (or two engulfings), T3 half of a
    confirming candle, T4 launch from converged weekly EMAs;
  4 vetoes (any one blocks);
  5 structural stop, nearest real target, at least 1.5R.
"""
from __future__ import annotations

import datetime as dt

from research.lab import structure

PARAMS = {
    "wing": 2,
    "a": {"rise_months": 6, "min_months_ema200": 200, "high_lookback": 24, "leg_lookback": 60, "min_pullback": 0.15, "max_pullback": 0.50,
          "touch_pct": 0.02, "touch_atr": 0.5, "gp": [0.5, 0.7]},
    "b": {"lookback": 36, "tol_pct": 0.03, "tol_atr": 0.5, "min_gap": 3, "follow_bars": 3, "follow_body_atr": 0.5, "min_pushes": 3, "fresh_months": 6,
          "compression_months": 6},
    "trendline": {"anchor_lookback": {"month": 36, "week": 52}, "min_gap": 3, "break_pct": 0.01, "touch_pct": 0.02, "touch_atr": 0.5},
    "sync": {"before": 3, "after": 3, "slow_after": 6, "rising_bars": 3},
    "window": {"month": 6, "week": 13},
    "daily": {"window": 10, "zone_atr": 1.0, "gap_atr": 1.0},
    "entry": {"tol_pct": 0.02, "tol_atr": 0.5, "min_pullback_atr": 1.0, "confirm_body_atr": 1.0, "converge_pct": 0.02, "converge_atr": 1.0,
              "limit_bars": {"week": 6, "month": 3}, "t4_low_weeks": 8},
    "veto": {"chase_atr": 2.0, "up_weeks": 3, "up_months": 5, "big_bear_atr": 1.5, "recent_bars": 3, "box_weeks": 52,
             "box_slope": 0.03, "box_ratio": 0.5, "ema50_lost_weeks": 8},
    "risk": {"buffer_pct": 0.01, "buffer_atr": 0.25, "min_rr": 1.5, "max_stop": 0.40, "fibs": [0.382, 0.5, 0.618, 0.786],
             "confirm_pct": 0.03, "confirm_bars": 2},
    "exit": {"first_fraction": 2 / 3, "runner_ma_weeks": {"month": 30, "week": 10}, "max_sessions": 5040},
    "hold": {"month": 252, "week": 130},
}

FIELDS = ("open", "high", "low", "close", "volume")


# ---------------------------------------------------------------- bars and indicators

def _key(day, period):
    if period == "month":
        return day[:7]
    return dt.date.fromisoformat(day).isocalendar()[:2]


def periods(s, period):
    """Weekly or monthly bars from daily columns; `end` is each bar's last daily index, `start` its first."""
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


def _ema(values, n):
    out, e, k = [], None, 2 / (n + 1)
    for x in values:
        e = x if e is None else x * k + e * (1 - k)
        out.append(e)
    return out


def _indicators(b):
    c = b["close"]
    for n in (20, 50, 100, 200):
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
    """Index of the last bar whose final session is at or before `day_index` (the series' last bar counts only if more data follows)."""
    lo, hi, found = 0, len(b["end"]) - 1, -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if b["end"][mid] <= day_index:
            found, lo = mid, mid + 1
        else:
            hi = mid - 1
    if found == len(b["end"]) - 1 and b["end"][found] == total_days - 1:
        found -= 1  # the open period at the end of the data is not complete
    return found


def pivots(values, mode, wing, right=None):
    """Swing points (index list) by the >=/<= rule of the V3 tracker; index j is known once bar j + right has closed."""
    right = wing if right is None else right
    out = []
    for j in range(wing, len(values) - right):
        around = values[j - wing:j] + values[j + 1:j + right + 1]
        if (mode == "high" and values[j] >= max(around)) or (mode == "low" and values[j] <= min(around)):
            out.append(j)
    return out


def _known(points, k, wing):
    return [j for j in points if j + wing <= k]


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


# ---------------------------------------------------------------- gate 2: trendline and sync

def trendline(b, k, period, p, highs):
    """The descending line from the major high before bar k, through the swing high that keeps every later swing high under it."""
    tp, wing = p["trendline"], p["wing"]
    lo = max(0, k - tp["anchor_lookback"][period])
    known = [j for j in _known(highs, k - 1, wing) if j >= lo]
    if len(known) < 2:
        return None
    a = max(known, key=lambda j: (b["high"][j], -j))
    after = [j for j in known if j - a >= tp["min_gap"] and b["high"][j] < b["high"][a] * 0.995]
    if not after:
        return None
    slopes = [((b["high"][j] - b["high"][a]) / (j - a), j) for j in after]
    slope, second = max(slopes)
    if slope >= 0:
        return None
    line = lambda x: b["high"][a] + slope * (x - a)
    if any(b["close"][x] > line(x) * (1 + tp["break_pct"]) for x in range(second + 1, k)):
        return None  # already broken before k
    touches = [j for j in known if j >= a and abs(b["high"][j] - line(j)) <= _tol(b, j, tp["touch_pct"], tp["touch_atr"], line(j))]
    return {"anchor": a, "second": second, "slope": slope, "line": line, "pushes": len(touches), "touches": touches}


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


def setups(b, period, p):
    """Every trendline breakout on this timeframe that MACD confirms, with the bar it becomes known."""
    highs, cross_list, out = pivots(b["high"], "high", p["wing"]), crosses(b), []
    for k in range(30, len(b["close"])):
        line = trendline(b, k, period, p, highs)
        if not line or b["close"][k] <= line["line"](k) * (1 + p["trendline"]["break_pct"]):
            continue
        s = sync(b, k, p, cross_list)
        if not s:
            out.append({"period": period, "breakout": k, "valid": None, "line": line, "sync": "not_in_step"})
            continue
        out.append({"period": period, "breakout": k, "valid": s[0], "line": line, "sync": s[1]})
    return out


# ---------------------------------------------------------------- gate 1: monthly background

def background(M, m, p, lows, W=None, w=None):
    """Monthly background at completed monthly bar m: {"kind": "A"|"B", ...} or None (with the reason)."""
    if m < 12:
        return None, "history_too_short"
    a, bp = p["a"], p["b"]
    c, lo = M["close"], M["low"]
    # A: long-term uptrend with a real pullback.
    found_a = None
    if m + 1 >= a["min_months_ema200"]:
        up = M["ema50"][m] > M["ema200"][m] and M["ema200"][m] > M["ema200"][m - a["rise_months"]] and c[m] >= M["ema200"][m]
        trend_basis = "monthly_ema200"
    else:
        weekly_up = W is not None and w is not None and w >= 35 and W["sma30"][w] > W["sma30"][w - 5] and W["close"][w] >= W["sma30"][w]
        up = M["ema50"][m] > M["ema50"][m - a["rise_months"]] and c[m] >= M["ema50"][m] * 0.9 and weekly_up
        trend_basis = "fallback_ema50_and_30_week"
    start = max(0, m - a["high_lookback"])
    h_idx = max(range(start, m + 1), key=lambda i: (M["high"][i], i))
    if up and h_idx < m:  # the pullback has to come after the high's own bar
        high = M["high"][h_idx]
        low_after = min(lo[h_idx + 1:m + 1])
        depth = 1 - low_after / high
        touched = [n for n in ("ema20", "ema50") for t in range(h_idx + 1, m + 1)
                   if lo[t] <= M[n][t] + _tol(M, t, a["touch_pct"], a["touch_atr"], M[n][t])]
        leg_low = min(lo[max(0, h_idx - a["leg_lookback"]):h_idx + 1])
        retrace = (high - low_after) / (high - leg_low) if high > leg_low else 0
        in_gp = a["gp"][0] <= retrace <= a["gp"][1]
        # A pullback, not a collapse: deeper than max_pullback has to qualify as a completed base (B) instead (RIG 2010, TT 2009).
        if depth <= a["max_pullback"] and (depth >= a["min_pullback"] or touched or in_gp):
            found_a = {"kind": "A", "trend_basis": trend_basis, "swing_high": (M["date"][h_idx], round(high, 4)), "pullback_low": round(low_after, 4),
                    "depth": round(depth, 4), "touched": sorted(set(touched)), "retrace": round(retrace, 4), "structure_low": low_after,
                    "_first": h_idx, "_top": h_idx}
    # B: base completed (two lows in the base zone, the later one confirmed by a strong follow-through bar).
    # Only lows after the decline's starting high count (an older crash low belongs to another cycle).
    top = max(range(max(0, m - bp["lookback"]), m + 1), key=lambda i: (M["high"][i], i))
    known = [j for j in _known(lows, m, 1) if j > top]
    if len(known) >= 2:
        floor = min(lo[j] for j in known)
        for second in known[::-1]:
            for first in [j for j in known if second - j >= bp["min_gap"]]:
                tol = _tol(M, second, bp["tol_pct"], bp["tol_atr"], lo[first])
                base = min(lo[first], lo[second])
                if abs(lo[second] - lo[first]) > tol or base > floor + tol or min(lo[first:second + 1]) < base - tol:
                    continue
                between = M["high"][first + 1:second]
                if not between or max(between) - max(lo[first], lo[second]) < M["atr"][second]:
                    continue
                if min(lo[second:m + 1]) < base - tol:
                    continue
                follow = [f for f in range(second + 1, min(second + bp["follow_bars"], m) + 1)
                          if c[f] > M["open"][f] and c[f] > c[second] and c[f] - M["open"][f] >= bp["follow_body_atr"] * M["atr"][f]]
                if follow:
                    return {"kind": "B", "path": "second_bottom", "uptrend_context": bool(found_a), "decline_high": (M["date"][top], round(M["high"][top], 4)),
                            "first_bottom": (M["date"][first], round(lo[first], 4)),
                            "second_bottom": (M["date"][second], round(lo[second], 4)), "follow_through": M["date"][follow[0]],
                            "neckline": round(max(between), 4), "structure_low": base, "_first": first, "_top": top, "_second": second}, None
    if found_a:
        return found_a, None
    return None, "no_uptrend_pullback_or_base"


def compression_base(M, m, monthly_setups, p):
    """B by compression: a monthly trendline with at least three pushes broken within the last months, lows holding."""
    bp = p["b"]
    for s in monthly_setups:
        if s["valid"] is None or not (m - bp["compression_months"] <= s["valid"] <= m) or s["line"]["pushes"] < bp["min_pushes"]:
            continue
        a = s["line"]["anchor"]
        lows = M["low"][a:s["breakout"] + 1]
        floor = min(lows)
        if lows.index(floor) + a > s["breakout"] - 3:
            continue  # the lowest low is the breakout's own leg: not a base
        return {"kind": "B", "path": "compression", "pushes": s["line"]["pushes"], "breakout": M["date"][s["breakout"]],
                "structure_low": floor, "first_bottom": (M["date"][lows.index(floor) + a], round(floor, 4)),
                "decline_high": (M["date"][a], round(M["high"][a], 4)), "_first": lows.index(floor) + a, "_top": a}
    return None


# ---------------------------------------------------------------- gate 3: entries

def daily_entry(D, Dd, first, p):
    """The daily layer (user, 2026-10-12): within the window after the weekly place is reached, the first day that closes above the
    previous day's high while the daily MACD histogram rises; buy at the next open. If that open gaps down by more than one daily
    ATR from the signal close, the order is cancelled for that day and the search goes on."""
    dp = p["daily"]
    last = min(first + dp["window"] - 1, len(D["close"]) - 2)
    for i in range(max(1, first), last + 1):
        if D["close"][i] > D["high"][i - 1] and Dd["hist"][i] > Dd["hist"][i - 1]:
            if D["open"][i + 1] < D["close"][i] - dp["gap_atr"] * Dd["atr"][i]:
                continue
            return i, i + 1, D["open"][i + 1]
    return None


def _zone_touch(D, Dd, level, first, last, atr_mult):
    """First day whose range reaches `level` +/- atr_mult daily ATRs (price came back to the half of a confirming candle)."""
    for i in range(first, min(last, len(D["close"]) - 1) + 1):
        a = atr_mult * Dd["atr"][i]
        if D["low"][i] <= level + a and D["high"][i] >= level - a:
            return i
    return None


def triggers(D, Dd, W, M, setup, p, w_from, w_to, line_level, valid_day):
    """The weekly layer finds the place (T1 retest, T2 engulfing with follow-through, T3 back to half of a confirming candle,
    T4 launch from converged EMAs); the daily layer then times the entry. Earliest fill first. Nothing is known before the setup is."""
    ep, out = p["entry"], []

    def add(kind, bar, place_day, stop_base, **info):
        found = daily_entry(D, Dd, max(place_day, valid_day + 1), p)
        if found:
            out.append({"type": kind, "bar": bar, "place_day": place_day, "signal_day": found[0], "fill_day": found[1], "entry": found[2],
                        "stop_base": stop_base, **info})

    level = setup["period"]
    post_high = None
    for w in range(w_from, w_to + 1):
        known = max(W["end"][w], valid_day)
        # T1: first retest after a real pullback.
        post_high = W["high"][w] if post_high is None else max(post_high, W["high"][w])
        if post_high - W["low"][w] >= ep["min_pullback_atr"] * W["atr"][w]:
            supports = {"trendline": line_level(w), "ema20": W["ema20"][w], "ema50": W["ema50"][w]}
            for name, sup in supports.items():
                if sup is None:
                    continue
                tol = _tol(W, w, ep["tol_pct"], ep["tol_atr"], sup)
                if sup - tol <= W["low"][w] <= sup + tol and W["close"][w] > sup:
                    add("T1", ("week", w), known, W["low"][w], support=name, support_level=round(sup, 4))
                    break
        # T2: bullish engulfing with follow-through, or two engulfings.
        if _bull_engulf(W, w - 1) and W["close"][w] > W["close"][w - 1]:
            add("T2", ("week", w), known, min(W["low"][w - 1], W["low"][w]), pattern="engulfing_follow_through")
        elif _bull_engulf(W, w) and _bull_engulf(W, w - 1):
            add("T2", ("week", w), known, min(W["low"][w - 1], W["low"][w]), pattern="double_engulfing")
        # T3: back to half of a confirming weekly candle.
        body = W["close"][w] - W["open"][w]
        if body > 0 and (_bull_engulf(W, w) or body >= ep["confirm_body_atr"] * W["atr"][w]):
            half = W["open"][w] + body / 2
            last = W["end"][min(w + ep["limit_bars"]["week"], len(W["end"]) - 1)]
            touch = _zone_touch(D, Dd, half, known + 1, last, p["daily"]["zone_atr"])
            if touch is not None:
                add("T3", ("week", w), touch, W["low"][w], candle="engulfing" if _bull_engulf(W, w) else "big_body", half=round(half, 4),
                    touched=D["date"][touch])
        # T4: launch from converged weekly EMAs with a cross that week.
        if w >= 1:
            e = (W["ema20"][w - 1], W["ema50"][w - 1], W["ema200"][w - 1])
            spread = max(e) - min(e)
            if (spread <= ep["converge_pct"] * W["close"][w - 1] or spread <= ep["converge_atr"] * W["atr"][w - 1]) \
                    and W["close"][w] > max(W["ema20"][w], W["ema50"][w], W["ema200"][w]) and W["dif"][w - 1] <= W["dea"][w - 1] and W["dif"][w] > W["dea"][w]:
                add("T4", ("week", w), known, min(W["low"][max(0, w - ep["t4_low_weeks"] + 1):w + 1]), spread=round(spread / W["close"][w - 1], 4))
    # T3 on the monthly candle of a monthly setup.
    if level == "month":
        for m in range(setup["valid"], min(setup["valid"] + p["window"]["month"], len(M["close"]) - 1) + 1):
            body = M["close"][m] - M["open"][m]
            if body > 0 and (_bull_engulf(M, m) or body >= ep["confirm_body_atr"] * M["atr"][m]) and M["end"][m] >= valid_day:
                half = M["open"][m] + body / 2
                last = M["end"][min(m + ep["limit_bars"]["month"], len(M["end"]) - 1)]
                touch = _zone_touch(D, Dd, half, M["end"][m] + 1, last, p["daily"]["zone_atr"])
                if touch is not None:
                    add("T3", ("month", m), touch, M["low"][m], candle="engulfing" if _bull_engulf(M, m) else "big_body", half=round(half, 4),
                        touched=D["date"][touch])
    return sorted(out, key=lambda t: t["fill_day"])


# ---------------------------------------------------------------- gate 4: vetoes

def vetoes(D, W, M, w, m, day, bg, trig, p, lows_m):
    """Monthly direction checks, then the weekly layer's conditions, at the daily signal's close."""
    entry = trig["entry"]
    vp, out = p["veto"], []
    # Monthly still falling (lower low without a base), or a base whose MACD has not turned.
    known = _known(lows_m, m, p["wing"])
    if bg["kind"] == "A" and len(known) >= 2 and M["low"][known[-1]] < M["low"][known[-2]] and M["close"][m] < M["ema200"][m]:
        out.append("monthly_still_falling")
    if bg["kind"] == "B" and M["hist"][m] < M["hist"][m - 1] < 0:
        out.append("monthly_macd_not_turned")
    checks = structure.assess(D, day)
    if checks["details"]["deep_drawdown"]["reject"] and bg["kind"] != "B":
        out.append("deep_fall_no_base")
    if checks["details"]["wide_box"]["reject"]:
        out.append("wide_box")
    if checks["details"]["bearish_pressure"]["flag"]:
        out.append("bearish_pressure")
    # Chasing.
    if entry > W["ema20"][w] + vp["chase_atr"] * W["atr"][w]:
        out.append("far_above_weekly_ema20")
    run = 0
    for i in range(w, 0, -1):
        if W["close"][i] > W["close"][i - 1]:
            run += 1
        else:
            break
    if run >= vp["up_weeks"]:
        out.append(f"up_{run}_weeks_in_a_row")
    run = 0
    for i in range(m, 0, -1):
        if M["close"][i] > M["close"][i - 1]:
            run += 1
        else:
            break
    if run >= vp["up_months"]:
        out.append(f"up_{run}_months_in_a_row")
    # Upper half of a sideways box.
    lo_w = max(0, w - vp["box_weeks"] + 1)
    hi, lo = max(W["high"][lo_w:w + 1]), min(W["low"][lo_w:w + 1])
    if w >= 13 and abs(W["ema50"][w] / W["ema50"][w - 13] - 1) <= vp["box_slope"] and hi / lo - 1 <= vp["box_ratio"] and W["close"][w] > lo + (hi - lo) / 2:
        out.append("upper_half_of_box")
    # Weekly momentum (user, 2026-10-12): the histogram is higher than last week, or the fast line is above the slow line and
    # the histogram has not shrunk two weeks running.
    h = W["hist"]
    if not (h[w] > h[w - 1] or (W["dif"][w] > W["dea"][w] and not (h[w] < h[w - 1] < h[w - 2]))):
        out.append("weekly_macd_weakening")
    # A bearish bar not taken back (unless a retest came after it).
    retest_at = trig["bar"][1] if trig["type"] == "T1" else -1
    for i in range(max(1, w - vp["recent_bars"] + 1), w + 1):
        big = W["open"][i] - W["close"][i] >= vp["big_bear_atr"] * W["atr"][i]
        if (_bear_engulf(W, i) or big) and W["close"][w] < W["open"][i] and retest_at <= i:
            out.append("bearish_bar_not_reclaimed")
            break
    # EMA50 lost and not taken back (AEVA, POWL): a weekly close fell through EMA50 from above within the last weeks and every
    # close since stayed below it. A base still rising from below EMA50 has not "lost" it.
    for j in range(w, max(1, w - vp["ema50_lost_weeks"] + 1) - 1, -1):
        if W["close"][j - 1] >= W["ema50"][j - 1] and W["close"][j] < W["ema50"][j]:
            if all(W["close"][x] < W["ema50"][x] for x in range(j, w + 1)):
                out.append("weekly_ema50_lost")
            break
    return out, checks


# ---------------------------------------------------------------- gate 5: stop, target, R

def opportunity_level(setup, bg, m=None, p=None):
    """Monthly when the pattern being traded is monthly: a monthly trendline breakout, or a monthly second bottom formed within
    the last few months (DVN 2013). Otherwise the weekly pattern defines it (BABA 2025, PG 2026: the user's weekly opportunities)."""
    if setup["period"] == "month":
        return "month"
    fresh = (p or PARAMS)["b"]["fresh_months"]
    if bg.get("path") == "second_bottom" and m is not None and m - bg["_second"] <= fresh:
        return "month"
    return "week"


def stop_level(trig, setup, bg, M, m, entry, base_lows, W=None, w=None, wing=2):
    """The structure the stop sits under (user, 2026-10-12). A monthly opportunity: the nearest unbroken monthly low below the
    entry since the base began (TT's July 2009 low, AVTR's prior low); a weekly opportunity: the nearest unbroken weekly swing low."""
    if opportunity_level(setup, bg, m) == "month":
        since = bg.get("_first", 0)
        # Only lows that later prices never broke still count as support.
        lows = [M["low"][j] for j in _known(base_lows, m, 1)
                if j >= since and M["low"][j] < entry * 0.995 and min(M["low"][j:m + 1]) >= M["low"][j]]
        if lows:
            return max(lows), "nearest_monthly_low"
        return bg["structure_low"], "monthly_structure_low"
    # A weekly opportunity: the nearest weekly swing low (two higher weeks on each side) that later prices never broke.
    if W is not None and w is not None:
        lows = [W["low"][j] for j in _known(pivots(W["low"], "low", wing), w, wing)
                if W["low"][j] < entry * 0.995 and min(W["low"][j:w + 1]) >= W["low"][j]]
        if lows:
            return max(lows), "nearest_weekly_low"
    return trig["stop_base"], "weekly_trigger_structure"


def resistance(D, W, M, setup, bg, day, m, w, entry, p):
    """Overhead resistance (user, 2026-10-12): draw the Fibonacci retracements of the decline (its highest high to the lowest low
    after it); a line is resistance when at least two completed bars of the opportunity's own timeframe topped out within 3% of it
    (DVN 2013: 42.74 under the 2011-09, 10, 12 and 2012-01 highs). The prior high and a base's neckline are resistance too.
    Returns the resistance prices above the entry, nearest first, with what confirms each."""
    rp = p["risk"]
    monthly = opportunity_level(setup, bg, m) == "month"
    if monthly:
        start_day = M["start"][setup["line"]["anchor"]] if setup["period"] == "month" else M["start"][bg["_top"]]
    else:
        start_day = W["start"][setup["line"]["anchor"]]
    highs = D["high"][start_day:day + 1]
    top = start_day + max(range(len(highs)), key=lambda i: (highs[i], -i))
    leg_high, leg_low = D["high"][top], min(D["low"][top:day + 1])
    T, last = (M, m) if monthly else (W, w)
    first = completed(T, top - 1, len(D["close"])) + 1
    bars = [(T["date"][j], T["high"][j]) for j in range(max(0, first), last + 1)]
    levels = []
    for f in rp["fibs"]:
        price = leg_low + f * (leg_high - leg_low)
        near = [d for d, h in bars if abs(h - price) <= rp["confirm_pct"] * price]
        if len(near) >= rp["confirm_bars"]:
            levels.append({"price": price, "source": f"fib_{f}", "confirmed_by": near})
    levels.append({"price": leg_high, "source": "prior_high", "confirmed_by": [D["date"][top]]})
    if bg.get("neckline"):
        levels.append({"price": bg["neckline"], "source": "neckline", "confirmed_by": []})
    # Buying inside a resistance band (the entry within 3% under a confirmed level) is buying into resistance (QLYS 2021-10).
    inside = [x for x in levels if x["price"] * (1 - rp["confirm_pct"]) <= entry < x["price"]]
    above = sorted((x for x in levels if x["price"] > entry * 1.005), key=lambda x: x["price"])
    return above, {"leg_high": leg_high, "leg_high_date": D["date"][top], "leg_low": leg_low, "timeframe": "month" if monthly else "week",
                   "inside": inside}


def plan(D, W, M, day, w, m, trig, setup, bg, p, base_lows):
    rp = p["risk"]
    entry = trig["entry"]
    base, basis = stop_level(trig, setup, bg, M, m, entry, base_lows, W, w, p["wing"])
    buffer = max(rp["buffer_pct"] * base, rp["buffer_atr"] * W["atr"][w])
    stop = base - buffer
    if not 0 < stop < entry:
        return None, "no_stop_below_entry"
    if (entry - stop) / entry > rp["max_stop"]:
        return {"stop": stop, "stop_basis": basis}, "stop_too_far"
    zones, leg = resistance(D, W, M, setup, bg, day, m, w, entry, p)
    if leg["inside"]:
        return {"stop": stop, "stop_basis": basis, "inside": leg["inside"]}, "entry_inside_resistance"
    if not zones:
        return {"stop": stop, "stop_basis": basis, **leg}, "no_resistance_target_above"
    first = zones[0]["price"]
    final = zones[1]["price"] if len(zones) > 1 else first
    risk = entry - stop
    rr1, rr2 = (first - entry) / risk, (final - entry) / risk
    out = {"stop": stop, "stop_basis": basis, "target": first, "target2": final, "target_source": zones[0]["source"],
           "target_confirmed_by": zones[0]["confirmed_by"], "target2_source": zones[1]["source"] if len(zones) > 1 else "same",
           "rr": rr1, "rr2": rr2, "level": opportunity_level(setup, bg, m), "leg": leg}
    if rr1 < rp["min_rr"]:
        return out, "rr_below_1.5"
    return out, None


# ---------------------------------------------------------------- scan

def scan(D, p=None, start=None, end=None):
    """All signals and near misses for one stock (daily columns), with fill dates inside [start, end]."""
    p = p or PARAMS
    n = len(D["close"])
    W, M = periods(D, "week"), periods(D, "month")
    Dd = _indicators({k: list(D[k]) for k in ("date",) + FIELDS})
    lows_m = pivots(M["low"], "low", p["wing"])
    base_lows = pivots(M["low"], "low", p["wing"], right=1)
    month_setups, week_setups = setups(M, "month", p), setups(W, "week", p)
    signals, misses, used = [], [], set()
    for setup in sorted(month_setups + week_setups, key=lambda s: ((M if s["period"] == "month" else W)["end"][s["valid"]] if s["valid"] is not None else 10 ** 9)):
        L = M if setup["period"] == "month" else W
        if setup["valid"] is None:
            continue
        valid_day = L["end"][setup["valid"]]
        if valid_day >= n - 1:
            continue
        w0 = completed(W, valid_day, n)
        if w0 < 0:
            continue
        window = p["window"][setup["period"]]
        last_bar = min(setup["valid"] + window, len(L["end"]) - 1)
        w_to = completed(W, L["end"][last_bar], n)
        line = setup["line"]

        def line_level(w, line=line, period=setup["period"]):
            if period == "week":
                return line["line"](w)
            return line["line"](completed(M, W["end"][w], n) + 1)
        for trig in triggers(D, Dd, W, M, setup, p, w0, max(w0, w_to), line_level, valid_day):
            day = trig["signal_day"]  # the daily signal's close: every layer is checked with what is known then
            if trig["fill_day"] in used or (start and D["date"][trig["fill_day"]] < start) or (end and D["date"][trig["fill_day"]] > end):
                continue
            if day <= valid_day:
                continue  # never trade on a setup before it is known
            w, m = completed(W, day, n), completed(M, day, n)
            if m < 12:
                continue
            # Gate 1 is checked when the order is placed.
            bg, why = background(M, m, p, base_lows, W, w)
            if bg is None:
                bg = compression_base(M, m, month_setups, p)
            if bg is None:
                misses.append(_card(D, W, M, setup, {"kind": None, "reason": why}, trig, None, ["no_monthly_background"], None, day))
                continue
            # A base or pullback that has since broken below its structure low is void.
            if min(D["low"][valid_day:day + 1]) < bg["structure_low"] * (1 - p["b"]["tol_pct"]):
                misses.append(_card(D, W, M, setup, bg, trig, None, ["structure_broken"], None, day))
                continue
            vetoed, checks = vetoes(D, W, M, w, m, day, bg, trig, p, lows_m)
            risk, reason = plan(D, W, M, day, w, m, trig, setup, bg, p, base_lows)
            if vetoed or reason:
                misses.append(_card(D, W, M, setup, bg, trig, risk, vetoed, reason, day, checks))
                continue
            signals.append(_card(D, W, M, setup, bg, trig, risk, [], None, day, checks))
            used.update(range(trig["fill_day"] - 10, trig["fill_day"] + 11))
            break
    return {"signals": signals, "near_misses": misses}


def _card(D, W, M, setup, bg, trig, risk, vetoed, reason, day, checks=None):
    L = M if setup["period"] == "month" else W
    line = setup["line"]
    tb, ti = trig["bar"]
    T = M if tb == "month" else W
    card = {
        "decision_date": D["date"][day], "fill_date": D["date"][trig["fill_day"]], "entry": round(trig["entry"], 4),
        "level": setup["period"], "background": {k: v for k, v in bg.items() if k != "structure_low" and not k.startswith("_")},
        "trendline": {"start": (L["date"][line["anchor"]], round(L["high"][line["anchor"]], 4)),
                      "second": (L["date"][line["second"]], round(L["high"][line["second"]], 4)), "pushes": line["pushes"]},
        "breakout": L["date"][setup["breakout"]], "sync": setup["sync"], "sync_date": L["date"][setup["valid"]],
        "entry_type": trig["type"], "trigger_bar": (tb, T["date"][ti]),
        "trigger": {**{k: v for k, v in trig.items() if k not in ("bar", "fill_day", "entry", "stop_base", "place_day", "signal_day")},
                    "place_date": D["date"][trig["place_day"]], "daily_signal_date": D["date"][trig["signal_day"]]},
        "vetoes": vetoed, "gate5": reason,
        "flags": (checks or {}).get("flags", []),
    }
    if risk:
        for key in ("stop", "target", "target2", "rr", "rr2"):
            if risk.get(key) is not None:
                card[key] = round(risk[key], 4 if key not in ("rr", "rr2") else 2)
        for key in ("stop_basis", "target_source", "target2_source", "target_confirmed_by", "leg"):
            if risk.get(key):
                card[key] = risk[key]
        card["opportunity_level"] = risk.get("level")
    card["passed"] = not vetoed and reason is None
    return card


def trade(D, card, p=None, cost_per_side=0.001):
    """Run one signal through the confirmed exits (user, 2026-10-12): two thirds at the first resistance, then the stop moves to
    the entry and the last third rides until a weekly close below its moving average (30 weeks for a monthly opportunity,
    10 weeks for a weekly one), sold at the next open; no time limit."""
    from research.lab.datasets import BarsView
    from research.lab.exit_rules import simulate
    p = p or PARAMS
    ep = p["exit"]
    i = D["date"].index(card["fill_date"])
    variant = {"stop": {"kind": "level", "price": card["stop"]},
               "targets": [{"price": card["target"], "fraction": ep["first_fraction"]}],
               "breakeven_after_target": True, "trend_after_target": True,
               "trend_exit": {"kind": "period_sma", "period": "week", "length": ep["runner_ma_weeks"][card["opportunity_level"]]},
               "max_hold": ep["max_sessions"]}
    return simulate(BarsView(D), i, variant, cost_per_side=cost_per_side)

