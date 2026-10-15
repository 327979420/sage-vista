"""Weekly triangle, shape draft 1.5 and trade rule 1.7 (the user's rules as of 2026-10-15; case ledger section 17).

Shape 1.5: a C "bottom golden cross" of the weekly triangle (research/lab/triangle.py push lines and bottoms) with
- flat bottoms: the last bottom at most 10% over the lowest bottom; pullback from the first push 10%..60%; span 10..90 weeks;
- the weekly golden cross in the signal week, after DIF sat under DEA for at least four weeks, and under the zero line;
- a bullish signal week whose low is within 1.5 weekly ATR of the last bottom; target 1 = the nearest swing high inside the
  triangle at least 7% over the signal close, 3% under it.
Trade rule 1.7: a limit buy 2% under the signal close, alive 8 weeks, cancelled if the stop or target 1 trades first; stop 1% under
the last bottom and at least 0.5 weekly ATR under the entry; everything sold at target 1; skipped if the planned reward to risk is
under 1.5; 13-week time stop; skipped if the monthly MACD is high and about to cross down. The daily MACD is reported (a sizing
plus for the user), never a gate.
Taste model v1 (research/lab/cases/taste-model-v1.json) scores how much the user is likely to accept a shape.
Ported from the exploratory scripts used for the blind tests (work/v3w: v13.py, rule16.py, mtf.py, taste.py), same logic."""
from __future__ import annotations

import json
import math
import pathlib
import statistics

from research.lab import buysystem as BS, buytrain, triangle as T
from research.lab.v3weekly import pivots
from services.scanner.favorite_pattern_tracker import _atr

ROOT = pathlib.Path(__file__).resolve().parents[2]
POOL = {"min_history": 420, "min_close": 5.0, "min_dollar_volume": 1e7, "raw_close": True}
FUNDS = set("DIA GLD HYG IWM LQD QQQ RSP SOXX SPY TLT VTI XBI XLE ICLN".split())
HOLD, WAIT = 65, 40


def signals(series, start="2005-01-01", end="2099-12-31", pool=POOL):
    """Shape-1.5 signals of one stock: dicts with the weekly index t, signal day index, pushes, bottoms, stop level, target 1."""
    T.P["span"] = (10, 90)
    W = BS.periods(series, "week")
    n = len(W["close"]) - 1
    if n < 80:
        return []
    rows = [{"date": W["date"][k], "open": W["open"][k], "high": W["high"][k], "low": W["low"][k], "close": W["close"][k]} for k in range(n)]
    atr = _atr(rows)
    h = [a - b for a, b in zip(W["dif"], W["dea"])]
    highs = pivots([r["high"] for r in rows], "high")
    out, last = [], -99
    for t in range(60, n - 1):
        r = rows[t]
        if not r["close"] > r["open"] or t - last < 13 or not (h[t] > 0 and all(h[j] < 0 for j in range(t - 4, t))):
            continue
        for ln in T.push_lines(rows, highs, t, broken=None):
            bots = T.bottoms_of(rows, ln["pushes"], t + 1)
            if not (bots and bots[-1][0] < t and r["low"] <= bots[-1][1] + 1.5 * atr[t] and T.converging(ln["line"], bots, ln["pushes"][0], t)):
                continue
            got = _shape(rows, highs, atr, ln, bots, t)
            if got:
                out.append(got); last = t
                break
    res = []
    for e in out:
        d = W["end"][e["t"]]
        # the zero-line rule filters afterwards: a cross above zero still blocks the next 13 weeks, as in the blind tests
        if W["dif"][e["t"]] < 0 and start <= e["week"] <= end and buytrain.tradable(series, d, pool):
            e["day"] = d
            res.append(e)
    return res


def _shape(rows, highs, atr, ln, bots, t):
    p = ln["pushes"]
    H1i = p[0]; H1 = rows[H1i]["high"]
    L1 = min(v for _, v in bots); Lk = bots[-1][1]
    if (H1 - L1) / H1 < T.P["min_pullback"] or (H1 - L1) / H1 > 0.60 or Lk > L1 * 1.10 or len(bots) < 2:
        return None
    if L1 < min(x["low"] for x in rows[max(0, H1i - 156):H1i + 1]) * 0.9:
        return None
    level, stop = rows[t]["high"] * 1.001, Lk * 0.99
    if level - stop < T.P["stop_min_atr"] * atr[t]:
        return None
    piv = sorted(set([i for i in highs if p[0] <= i <= t - 2] + list(p)))
    cands = sorted({rows[i]["high"] * 0.97 for i in piv if rows[i]["high"] * 0.97 >= rows[t]["close"] * 1.07})
    if not cands or cands[0] <= stop:
        return None
    t1 = cands[0]
    if t1 <= level or (t1 - level) / (level - stop) < 1.5:
        if (t1 + 1.5 * stop) / 2.5 - stop < T.P["stop_min_atr"] * atr[t]:
            return None
    return {"t": t, "week": rows[t]["date"], "stop": stop, "t1": cands[0], "pushes": list(p), "bottoms": [j for j, _ in bots]}


def monthly_veto(series, d0):
    """Monthly MACD high and about to cross down (last completed month): DIF > 0 over DEA with the histogram shrinking two months,
    or DIF > 0 with a cross down in the last two completed months."""
    M = BS.periods(series, "month")
    m = BS.completed(M, d0, len(series["close"]))
    if m < 3:
        return False
    dif, dea = M["dif"], M["dea"]
    h = [dif[k] - dea[k] for k in range(m - 2, m + 1)]
    if dif[m] > 0 and h[2] > 0 and h[2] < h[1] < h[0]:
        return True
    return dif[m] > 0 and h[2] <= 0 and (h[1] > 0 or h[0] > 0)


def daily_state(series, d0):
    """Daily MACD at the signal day: "crossed" (golden cross in the last 10 sessions), "about" (under, rising three days), else "neither"."""
    D = BS.daily_bars(series)
    h = [a - b for a, b in zip(D["dif"], D["dea"])]
    if h[d0] < 0 and h[d0] > h[d0 - 1] > h[d0 - 2] > h[d0 - 3]:
        return "about"
    if h[d0] > 0 and any(h[k] <= 0 for k in range(d0 - 9, d0)):
        return "crossed"
    return "neither"


def plan(series, sig, weekly_atr):
    """Rule 1.7 order for a signal: level, stop, target, planned R:R and whether it is taken."""
    c0 = series["close"][sig["day"]]
    level = c0 * 0.98
    stop = min(sig["stop"], level - 0.5 * weekly_atr)
    if not 0 < stop < level < sig["t1"]:
        return {"level": level, "stop": stop, "t1": sig["t1"], "rr": None, "go": False, "why": "no geometry"}
    rr = (sig["t1"] - level) / (level - stop)
    veto = monthly_veto(series, sig["day"])
    why = "monthly veto" if veto else ("R:R under 1.5" if rr < 1.5 else "")
    return {"level": level, "stop": stop, "t1": sig["t1"], "rr": rr, "go": not why, "why": why}


def trade(series, d0, level, stop, t1, hold=HOLD, wait=WAIT):
    """The limit order and its exit. Returns {"status": ...} with fill and exit details; statuses: waiting, cancelled, open, win,
    loss, time (13 weeks over). A stop touched on the fill day counts (the worse reading)."""
    o, hi, lo, c, n = series["open"], series["high"], series["low"], series["close"], len(series["close"])
    fill = None
    for d in range(d0 + 1, min(d0 + 1 + wait, n)):
        if o[d] <= stop:
            return {"status": "cancelled", "why": "stop before the fill", "day": d}
        if lo[d] <= level:
            fill = (d, min(o[d], level))
            break
        if hi[d] >= t1:
            return {"status": "cancelled", "why": "target before the fill", "day": d}
    if fill is None:
        return {"status": "waiting" if d0 + wait >= n - 1 else "cancelled", "why": "no fill in 8 weeks"}
    d, e = fill
    risk = e - stop
    base = {"fill_day": d, "entry": e}
    for k in range(d, min(d + hold, n)):
        if k > d and o[k] <= stop:
            return {**base, "status": "loss", "exit_day": k, "exit": o[k], "R": (o[k] - e) / risk}
        if lo[k] <= stop:
            return {**base, "status": "loss", "exit_day": k, "exit": stop, "R": (stop - e) / risk}
        if hi[k] >= t1:
            x = max(o[k], t1) if k > d else t1
            return {**base, "status": "win", "exit_day": k, "exit": x, "R": (x - e) / risk}
    k = min(d + hold, n) - 1
    status = "time" if d + hold <= n else "open"
    return {**base, "status": status, "exit_day": k, "exit": c[k], "R": (c[k] - e) / risk}


TASTE_FEATURES = ["depth", "span", "bottom_rise", "bottom_gap", "since_bottom", "tight26", "vol26", "swings", "prior_adv", "ema20_dist",
                  "ema20_slope", "pos156", "dif_depth", "hist_slope", "weeks_below", "vol_ratio", "line_slope", "n_pushes", "undercuts13",
                  "body_atr", "to_line", "bottom_tests", "ema200_dist", "ret13"]


def taste_features(W, t, P, Bt):
    c, h, l, o = W["close"], W["high"], W["low"], W["open"]
    H1 = h[P[0]]; lows = [l[j] for j in Bt]; L = min(lows); rng = H1 - L
    a = W["atr"][t] or 1e-9
    last = range(max(0, t - 25), t + 1)
    rets = [abs(c[j] / c[j - 1] - 1) for j in last if j > 0]
    sw, d, ref = 0, 0, c[P[0]]
    for j in range(P[0], t + 1):
        if d >= 0 and c[j] < ref - a:
            sw += d > 0; d, ref = -1, c[j]
        elif d <= 0 and c[j] > ref + a:
            sw += d < 0; d, ref = 1, c[j]
        elif (d > 0 and c[j] > ref) or (d < 0 and c[j] < ref):
            ref = c[j]
    pre = max(0, P[0] - 52)
    w156 = range(max(0, t - 155), t + 1)
    lo156, hi156 = min(l[j] for j in w156), max(h[j] for j in w156)
    hist = [W["dif"][j] - W["dea"][j] for j in range(t + 1)]
    wb = 0
    for j in range(t - 1, 0, -1):
        if hist[j] < 0:
            wb += 1
        else:
            break
    v = W["volume"]; v4 = statistics.fmean(v[t - 3:t + 1]); v26 = statistics.fmean(v[max(0, t - 25):t + 1]) or 1
    slope = (h[P[-1]] - h[P[0]]) / (P[-1] - P[0]) if P[-1] > P[0] else 0
    line_t = h[P[0]] + slope * (t - P[0])
    return [rng / H1, t - P[0], (lows[-1] - L) / L, Bt[-1] - Bt[-2] if len(Bt) > 1 else 0, t - Bt[-1],
            (max(h[j] for j in last) - min(l[j] for j in last)) / rng, statistics.fmean(rets), sw,
            c[P[0]] / c[pre] - 1, c[t] / W["ema20"][t] - 1, W["ema20"][t] / W["ema20"][max(0, t - 10)] - 1,
            (c[t] - lo156) / (hi156 - lo156 or 1), W["dif"][t] / c[t], hist[t] - hist[t - 3], wb, v4 / v26,
            slope / c[t], len(P), sum(c[j] < lows[-1] for j in range(max(Bt[-1] + 1, t - 12), t + 1)), abs(c[t] - o[t]) / a,
            (line_t - c[t]) / c[t], sum(l[j] <= L * 1.03 for j in range(P[0], t + 1)), c[t] / W["ema200"][t] - 1, c[t] / c[max(0, t - 13)] - 1]


def taste(W, sig, model=None):
    model = model or json.loads((ROOT / "research/lab/cases/taste-model-v1.json").read_text())
    x = taste_features(W, sig["t"], sig["pushes"], sig["bottoms"])
    z = model["b"] + sum(w * (xi - m) / s for w, xi, m, s in zip(model["w"], x, model["mu"], model["sd"]))
    return 1 / (1 + math.exp(-max(-30, min(30, z))))
