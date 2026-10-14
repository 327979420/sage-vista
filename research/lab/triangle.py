"""The weekly triangle (the user's V3 on weekly bars, version 1.0, frozen 2026-10-14 for lab-triangle-exam-v1; docs/CASE_REVIEW_LEDGER_ZH.md
section 17; research/lab/cases/triangle-answer-key-v1.json).

A triangle is what a reader sees at a glance: three or more weekly highs stepping down on one line (the middle push within 8% of the
line drawn through the outer two, no weekly close above the line before the signal), with two or more bottoms between and after the
pushes, the last bottom at most 1% under the lowest earlier one (a right triangle when they are level, a converging one when they
rise); by the signal the gap between the line and the bottoms has at least halved. The pullback from the first high is at least 10%,
the last bottom stays in the lower half of it, and the lowest bottom did not break the prior advance's start by more than 10%.

The user buys only two ways (2026-10-14), never the breakout itself and never above the highest rebound between the bottoms:
  C bottom golden cross: price still at the last bottom (within 1.5 weekly ATR), a bullish week, and the weekly MACD crossing up this
    week or last (DIF through DEA, or touching it within 0.02% of the price and lifting); a buy-stop above that week's high for three
    weeks, cancelled if the stop trades first; stop 1% under the last bottom.
  B retest: within eight weeks of the first weekly close more than 1% above the line, a bullish week whose low comes back within one
    weekly ATR of the line and whose close holds it; a buy-stop above that week's high for three weeks; stop under the nearest support
    (that week's low, the last bottom, the weekly EMA200 when below the buy).
Every stop is at least half a weekly ATR under the buy; the first target is the triangle's first high and the reward to risk there is
at least 1.5. Pluses (for ranking only): a nested smaller triangle inside this one, and the confluence count (MACD crossed; a bottom
within 6% of the weekly EMA20/50/200; a bottom at the 0.5-0.786 retracement of the prior advance; a bullish weekly FVG swept by a bottom
and closed back above; a bullish weekly RSI divergence between the lowest and the last bottom).

Run: python3 -m research.lab.triangle OUT.json [SYMBOL]
"""
import bisect, json, multiprocessing, sys
from research.lab import datasets, selection, buysystem as B
from research.lab.v3weekly import pivots, macd_ok, signal_bar
from services.scanner.favorite_pattern_tracker import _atr
from services.scanner.technical import ema

PRICES = None
P = {"lows_tol": 0.01, "push_drop": 0.995, "push_fit": 0.08, "min_pushes": 3, "min_bottoms": 2, "converge": 0.5, "span": (10, 104),
     "min_pullback": 0.10, "retest_weeks": 8, "order_weeks": 3, "retest_atr": 1.0, "min_rr": 1.5, "stop_min_atr": 0.5}


def push_lines(rows, highs, t, broken=True):
    """Every three-push line broken by week t's close: descending pivot highs, the middle one near the line, and no weekly close
    above the line between the first push and week t (a line broken earlier is stale)."""
    cand = [p for p in highs if t - P["span"][1] <= p <= t - 2]
    out = []
    for i, a in enumerate(cand):
        for j in range(i + 1, len(cand)):
            b = cand[j]
            for c in cand[j + 1:]:
                va, vb, vc = rows[a]["high"], rows[b]["high"], rows[c]["high"]
                if not (vb <= va * P["push_drop"] and vc <= vb * P["push_drop"]) or t - a < P["span"][0]:
                    continue
                slope = (vc - va) / (c - a)
                line = lambda x, va=va, a=a, slope=slope: va + slope * (x - a)
                if abs(vb / line(b) - 1) > P["push_fit"]:
                    continue
                if broken is not None and (rows[t]["close"] > line(t) * 1.01) != broken:
                    continue
                if any(rows[x]["close"] > line(x) * 1.01 for x in range(a + 1, t)):
                    continue
                out.append({"pushes": [a, b, c], "line": line})
    return out


def bottoms_of(rows, pushes, t):
    """The lowest week between each pair of pushes and after the last push. Only the main bottoms matter (AMGN 2016: a minor low in
    between may sit higher): the last bottom may not undercut the lowest earlier one by more than 1% (DHI 2014).
    Returned: the lowest earlier bottom, any bottoms after it, and the last."""
    segs = list(zip(pushes, pushes[1:])) + [(pushes[-1], t)]
    bots = []
    for lo, hi in segs:
        if hi - lo < 2:
            continue
        j = min(range(lo + 1, hi), key=lambda x: rows[x]["low"])
        bots.append((j, rows[j]["low"]))
    if len(bots) < P["min_bottoms"]:
        return None
    earlier = bots[:-1]
    k = min(range(len(earlier)), key=lambda x: earlier[x][1])  # the main first bottom: the lowest before the last
    if bots[-1][1] < earlier[k][1] * (1 - P["lows_tol"]):
        return None  # the last bottom undercuts the main one by more than 1% (DHI 2014)
    return bots[k:]


def converging(line, bots, a, t):
    (l1, v1), (l2, v2) = bots[0], bots[-1]
    lower = lambda j: v1 + (v2 - v1) / (l2 - l1) * (j - l1)
    gap_a, gap_t = line(a) - lower(a), line(t) - lower(t)
    return gap_a > 0 and gap_t <= P["converge"] * gap_a


def volume_ratio(W, k, weeks=10):
    """Week k's volume over the average of the ten weeks before it (O'Neil and Bulkowski read breakout volume this way)."""
    prior = W["volume"][max(0, k - weeks):k]
    mean = sum(prior) / len(prior) if prior else 0
    return round(W["volume"][k] / mean, 3) if mean > 0 else None


def order(s, W, rows, t, n, level, stop):
    """A buy-stop above `level` for three weeks after week t, cancelled if the stop is reached first."""
    for w in range(t + 1, min(t + 1 + P["order_weeks"], n)):
        for d in range(W["start"][w], W["end"][w] + 1):
            if s["low"][d] <= stop and s["high"][d] < level:
                return None
            if s["high"][d] >= level:
                return d, max(s["open"][d], level)
    return None


def nearest_stop(rows, t, e200, atr, last_bottom, entry_level):
    supports = [("signal_low", rows[t]["low"] * 0.99), ("last_bottom", last_bottom * 0.99)]
    if e200[t] < entry_level:
        supports.append(("ema200", e200[t] * 0.99))
    ok = [(nm, v) for nm, v in supports if v <= entry_level - P["stop_min_atr"] * atr[t]]
    return max(ok, key=lambda x: x[1]) if ok else None


def rsi(closes, n=14):
    """Wilder's RSI."""
    out, gain, loss = [50.0] * len(closes), 0.0, 0.0
    for i in range(1, len(closes)):
        ch = closes[i] - closes[i - 1]
        g, l = max(ch, 0.0), max(-ch, 0.0)
        if i <= n:
            gain += g / n; loss += l / n
        else:
            gain = (gain * (n - 1) + g) / n; loss = (loss * (n - 1) + l) / n
        out[i] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return out


def rsi_divergence(rows, rs, bots):
    """A bullish RSI divergence (HSI 2024-01, user 2026-10-14): the last bottom is no higher than 3% above the lowest bottom,
    while the weekly RSI there is at least three points higher."""
    (jl, vl) = min(bots, key=lambda x: x[1])
    (jk, vk) = bots[-1]
    return jk != jl and vk <= vl * 1.03 and rs[jk] >= rs[jl] + 3


def bullish_fvg_swept(rows, j, lookback=52):
    """A bullish weekly gap (a week's low above the high two weeks earlier) that bottom week j traded into and closed back above."""
    for k in range(max(2, j - lookback), j):
        lo, hi = rows[k - 2]["high"], rows[k]["low"]
        if hi > lo and rows[j]["low"] <= hi and rows[j]["close"] >= lo:
            return True
    return False


def retest(s, W, rows, n, line, b, e200, atr, last_bottom, H1, neck):
    """Option B: within eight weeks of breakout week b, a week back at the line that holds it with an engulfing or a doji."""
    for k in range(b + 1, min(b + 1 + P["retest_weeks"], n - 1)):
        rk = rows[k]
        # back at the line and holding it with a bullish week (AME 2009: "after the breakout wait for the retest, then buy")
        if rk["low"] <= line(k) + P["retest_atr"] * atr[k] and rk["close"] >= line(k) and rk["close"] > rk["open"]:
            stop = nearest_stop(rows, k, e200, atr, last_bottom, rk["high"] * 1.001)
            got = order(s, W, rows, k, n, rk["high"] * 1.001, stop[1]) if stop else None
            if got:
                d, entry = got
                rr = (H1 - entry) / (entry - stop[1])
                if entry <= neck and rr >= P["min_rr"]:
                    return {"breakout_week": rows[b]["date"], "signal_week": rows[k]["date"], "signal_bar": signal_bar(rows, k) or "bullish", "fill": s["date"][d],
                            "entry": round(entry, 4), "stop": round(stop[1], 4), "stop_basis": stop[0], "rr": round(rr, 2),
                            "volume_ratio": volume_ratio(W, b)}
            return None
    return None


def scan_symbol(symbol):
    """Candidates with up to two buys the user takes (2026-10-14): C, a weekly MACD golden cross while price still sits at the last
    bottom of an intact triangle; B, the retest after that triangle's line breaks. A plain breakout buy is not offered."""
    s = PRICES[symbol]
    W = B.periods(s, "week")
    n = len(W["close"]) - 1
    rows = [{"date": W["date"][k], "open": W["open"][k], "high": W["high"][k], "low": W["low"][k], "close": W["close"][k]} for k in range(n)]
    if n < 80:
        return []
    atr = _atr(rows)
    closes = [r["close"] for r in rows]
    e20, e50, e200 = ema(closes, 20), ema(closes, 50), ema(closes, 200)
    dif, dea = W["dif"], W["dea"]
    rs = rsi(closes)
    highs = pivots([r["high"] for r in rows], "high")
    out, last_event, used = [], -99, set()
    for t in range(60, n - 1):  # the EMA200 rule is gone, so a stock needs only a year or so of weekly history (AXTA listed 2014-11)
        if t - last_event < 13:
            continue
        r = rows[t]
        if not r["close"] > r["open"]:
            continue
        # a golden cross this week or last week: DIF crossing up through DEA, or coming down to touch it (within 0.02% of the price)
        # and lifting again (CHRW 2012-04-16). Lines already above and still rising are not a new cross (CHRW 2012-03: the user saw
        # no cross there)
        def crossed(k):
            d0, d1, d2 = dif[k] - dea[k], dif[k - 1] - dea[k - 1], dif[k - 2] - dea[k - 2]
            return d0 > 0 and (d1 <= 0 or (d1 <= 0.0002 * rows[k - 1]["close"] and d2 > d1))
        cross = dif[t] > dea[t] and (crossed(t) or crossed(t - 1))
        mode = None
        tris = []
        if cross:  # C: still under the line, at the bottom
            for ln in push_lines(rows, highs, t, broken=None):  # the cross week may also break the line (A 2005)
                bots = bottoms_of(rows, ln["pushes"], t + 1)
                if bots and bots[-1][0] < t and r["low"] <= bots[-1][1] + 1.5 * atr[t] and converging(ln["line"], bots, ln["pushes"][0], t):
                    tris.append((ln, bots))
            mode = "C" if tris else None
        if not tris:  # a breakout this week of a triangle not offered yet: only the retest can be bought
            for ln in push_lines(rows, highs, t, broken=True):
                bots = bottoms_of(rows, ln["pushes"], t)
                if bots and converging(ln["line"], bots, ln["pushes"][0], t) and tuple(ln["pushes"]) not in used:
                    tris.append((ln, bots))
            mode = "B" if tris else None
        if not tris:
            continue
        tris.sort(key=lambda x: (x[0]["pushes"][0], -x[0]["pushes"][2]))
        ln, bots = tris[0]
        line, pushes = ln["line"], ln["pushes"]
        nested = any(x[0]["pushes"][0] > pushes[0] for x in tris)
        H1i = pushes[0]; H1 = rows[H1i]["high"]
        L1i, L1 = min(bots, key=lambda x: x[1])
        Lki, Lk = bots[-1]
        if (H1 - L1) / H1 < P["min_pullback"] or Lk > L1 + 0.5 * (H1 - L1):
            continue  # the weekly-EMA200 uptrend rule is gone (A 2005); the last bottom must stay in the lower half
        base = min(x["low"] for x in rows[max(0, H1i - 156):H1i + 1])
        if L1 < base * 0.9:
            continue
        neck = max(x["high"] for x in rows[L1i:t + 1])
        options = {}
        if mode == "C":
            stop = ("last_bottom", Lk * 0.99) if Lk * 0.99 <= r["high"] * 1.001 - P["stop_min_atr"] * atr[t] else None
            got = order(s, W, rows, t, n, r["high"] * 1.001, stop[1]) if stop else None
            if got:
                d, entry = got
                rr = (H1 - entry) / (entry - stop[1])
                if entry <= neck * 1.001 and rr >= P["min_rr"]:
                    options["C"] = {"signal_week": rows[t]["date"], "fill": s["date"][d], "entry": round(entry, 4), "stop": round(stop[1], 4),
                                    "stop_basis": stop[0], "rr": round(rr, 2), "volume_ratio": volume_ratio(W, t)}
            for b in range(t + 1, min(t + 53, n - 1)):  # the same line's later breakout, if the bottom holds until then
                if rows[b]["low"] < Lk * 0.99:
                    break
                if rows[b]["close"] > line(b) * 1.01:
                    got_b = retest(s, W, rows, n, line, b, e200, atr, Lk, H1, max(neck, max(x["high"] for x in rows[L1i:b + 1])))
                    if got_b:
                        options["B"] = got_b
                    break
        else:
            got_b = retest(s, W, rows, n, line, t, e200, atr, Lk, H1, neck)
            if got_b:
                options["B"] = got_b
        if not options:
            continue
        used.add(tuple(pushes))
        bottoms = [i for i, _ in bots]
        base_i = min(range(max(0, H1i - 156), H1i + 1), key=lambda j: rows[j]["low"])
        fib = any(0.5 <= (H1 - rows[j]["low"]) / (H1 - rows[base_i]["low"]) <= 0.786 for j in bottoms) if H1 > rows[base_i]["low"] else False
        confluence = {"macd_crossed": True if mode == "C" else dif[t] > dea[t],
                      "bottom_near_ema": any(abs(rows[j]["low"] / v[j] - 1) <= 0.06 for j in bottoms for v in (e20, e50, e200)),
                      "bottom_at_fib": fib, "fvg_swept": any(bullish_fvg_swept(rows, j) for j in bottoms),
                      "rsi_divergence": rsi_divergence(rows, rs, bots)}
        out.append({"symbol": symbol, "found_week": rows[t]["date"], "trigger": mode, "options": options, "nested": nested,
                    "confluence": confluence, "confluence_count": sum(confluence.values()),
                    "pushes": [rows[i]["date"] for i in pushes], "push_prices": [round(rows[i]["high"], 4) for i in pushes],
                    "bottoms": [rows[i]["date"] for i, _ in bots], "bottom_prices": [round(v, 4) for _, v in bots],
                    "first_high_week": rows[H1i]["date"], "target": round(H1, 4), "neck": round(neck, 4)})
        last_event = t
    return out


if __name__ == "__main__":
    e = datasets.manifest("universe-1985-v1")
    PRICES = datasets.load("work/lab/" + e["asset"], e["sha256"])["prices"]
    if len(sys.argv) > 2:
        for c in scan_symbol(sys.argv[2]):
            print(json.dumps(c, ensure_ascii=False))
        sys.exit()
    flagged = selection.impossible_jumps(PRICES)
    syms = sorted(x for x in PRICES if x not in flagged)
    with multiprocessing.get_context("fork").Pool(8) as pool:
        chunks = pool.map(scan_symbol, syms, chunksize=4)
    out = []
    for c in (c for ch in chunks for c in ch):
        s = PRICES[c["symbol"]]
        first = min(o["fill"] for o in c["options"].values())
        d = bisect.bisect_left(s["date"], first) - 1
        if d >= 420 and s["close"][d] * s["volume"][d] >= 1e7:
            out.append(c)
    json.dump(out, open(sys.argv[1], "w"))
    from collections import Counter
    print("candidates", len(out), sorted(Counter(c["found_week"][:4] for c in out if "2005" <= c["found_week"][:4] <= "2025").items()))
