"""Weekly V3, third draft (2026-10-14 after batch 1: location is a plus, stop under the nearest support, doji or engulfing
signal bar, equal bottoms count, MACD crossed or red bars shrinking, targets: prior high and fixed 1.5R both kept for the test).
Buy below the rebound high between the two bottoms (no chasing; ROP 2010 and HPQ 2016 bought after the move).
Second definition (the user's CSGP 2007 lesson, 2026-10-14). DRAFT: the user is labelling candidates; not yet
used by any registered experiment. Run: python3 -m research.lab.v3weekly OUT.json [SYMBOL]

1 Two bottom ZONES: the second bottom is the lowest low of the last 12 weeks before the signal week; the first is the lowest low
  6-60 weeks earlier; a rebound between them of at least 10% and 2 weekly ATRs; the second low is not more than one tolerance below
  the first and comes back at most 3/4 of the rebound; no deeper low between them. A zone is the run of weeks whose low stays
  within the tolerance (max 6%, 1 weekly ATR) of the zone's lowest low.
2 Location (V3): a bottom within 6% of the weekly EMA20/50/200, or the lower bottom at 50-70% of the prior advance.
3 Three-or-more-push downtrend line from descending weekly highs, no weekly close above it between the pushes.
4 Signal week t: a weekly bullish engulfing (after a bearish or doji week) 1-10 weeks after the second low, inside the zone (CSGP)
  or at the breakout (NLY); weekly MACD crossed or about to cross at t.
5 Entry: a buy-stop at the higher of week t's high and the line's level, alive for three weeks, cancelled if the stop is hit first
  (gap above: the open).
6 Stop at the second zone's low; first target the prior high (highest high of the 52 weeks before the first bottom); R >= 1.5.
Rules added 2026-10-14: a higher second bottom; a long-term uptrend (weekly EMA200 rising over 26 weeks, close above it); a pullback
of at least 15% from the prior high into the first bottom (replaces the flat-line test, which rejected the CSGP model case); too deep
(prior advance start broken by >10%); the V3 bearish-pressure gate is recorded.
"""
import bisect, itertools, json, multiprocessing, sys
from research.lab import datasets, selection, buysystem as B
from services.scanner.favorite_pattern_tracker import _atr, _bearish_risk_gate
from services.scanner.technical import ema

PRICES = None


def pivots(vals, mode, left=2, right=2):
    out = []
    for i in range(left, len(vals) - right):
        nb = vals[i - left:i] + vals[i + 1:i + right + 1]
        if (mode == "low" and vals[i] <= min(nb)) or (mode == "high" and vals[i] >= max(nb)):
            out.append(i)
    return out


def macd_ok(h, dif, dea, k):
    """The user's rule (2026-10-14): crossed, or the red bars at least shrinking; never red bars growing."""
    if dif[k] > dea[k]:
        return "crossed"
    return "rising" if h[k] > h[k - 1] else None


def bullish_engulf(r, k):
    """A bullish body that covers the previous bearish (or doji) body (0.5% tolerance; NLY 2009-05-01 follows a doji)."""
    a, b = r[k - 1], r[k]
    doji = abs(a["close"] - a["open"]) <= 0.1 * max(a["high"] - a["low"], 1e-9)
    return (b["close"] > b["open"] and (a["close"] < a["open"] or doji) and b["open"] <= min(a["open"], a["close"]) * 1.005
            and b["close"] >= max(a["open"], a["close"]) * 0.995)


def doji(r, k):
    b = r[k]
    return abs(b["close"] - b["open"]) <= 0.1 * max(b["high"] - b["low"], 1e-9)


def signal_bar(r, k):
    """A weekly bullish engulfing or a doji (user, 2026-10-14: STNG); the buy-stop goes above its high."""
    return "engulfing" if bullish_engulf(r, k) else "doji" if doji(r, k) else None


def zone(rows, j, tol, last=None):
    """The run of weeks around j whose low stays within the tolerance of week j's low; it never reaches past week `last`."""
    lo = rows[j]["low"]
    last = len(rows) - 1 if last is None else last
    s = j
    while s > 0 and rows[s - 1]["low"] <= lo * (1 + tol):
        s -= 1
    e = j
    while e + 1 <= last and rows[e + 1]["low"] <= lo * (1 + tol):
        e += 1
    return s, e


def best_line(rows, highs, start, t, entry_week, bottoms=None):
    """The three-or-more-push line. With `bottoms` (j1, L1, j2, L2) it must also make a visible triangle with them (user,
    2026-10-14): the first bottom falls between the first and the last push, and the gap between this line and the line
    through the two bottoms at the signal week is at most half the gap at the first push."""
    cand = [p for p in highs if start <= p <= t - 2]
    best = None
    for a, b, c in itertools.combinations(cand, 3):
        v = [rows[x]["high"] for x in (a, b, c)]
        if not (v[1] <= v[0] * 0.995 and v[2] <= v[1] * 0.995) or c - a < 4:
            continue
        slope = (v[2] - v[0]) / (c - a)
        if abs(v[1] / (v[0] + slope * (b - a)) - 1) > 0.08:
            continue
        line = lambda j: v[0] + slope * (j - a)
        if any(rows[j]["close"] > line(j) * 1.01 for j in range(a + 1, t)):
            continue  # a line already closed above before the signal week is stale, not the breakout line (TRN 2005)
        if bottoms:
            j1, L1, j2, L2 = bottoms
            if not a < j1 < c:
                continue
            lower = lambda j: L1 + (L2 - L1) / (j2 - j1) * (j - j1)
            gap_a, gap_t = line(a) - lower(a), line(t) - lower(t)
            if gap_a <= 0 or gap_t > 0.5 * gap_a:
                continue
        key = (v[0], c)
        if best is None or key > best["key"]:
            best = {"key": key, "idx": [a, b, c], "level_next": line(entry_week), "prices": v, "a": v[0], "slope": slope}
    return best


def scan_symbol(symbol):
    s = PRICES[symbol]
    W = B.periods(s, "week")
    n = len(W["close"]) - 1
    rows = [{"date": W["date"][k], "open": W["open"][k], "high": W["high"][k], "low": W["low"][k], "close": W["close"][k]} for k in range(n)]
    if len(rows) < 120:
        return []
    atr = _atr(rows)
    closes = [r["close"] for r in rows]
    e20, e50, e200 = ema(closes, 20), ema(closes, 50), ema(closes, 200)
    h, dif, dea = W["hist"], W["dif"], W["dea"]
    lows_p, highs = pivots([r["low"] for r in rows], "low"), pivots([r["high"] for r in rows], "high")
    M = B.periods(s, "month")
    out, last = [], -99
    for t in range(80, n - 1):
        kind_t = signal_bar(rows, t) if t - last >= 8 else None
        if not kind_t:
            continue
        state = macd_ok(h, dif, dea, t)
        if not state:
            continue
        j2 = min(range(t - 12, t), key=lambda j: (rows[j]["low"], -j))
        L2 = rows[j2]["low"]
        tol = max(0.06, atr[j2] / rows[j2]["close"])
        if t - j2 > 12:
            continue  # the signal bar comes within twelve weeks of the second bottom, in the zone (CSGP) or at the breakout (NLY)
        j1 = min(range(max(0, j2 - 60), j2 - 6 + 1), key=lambda j: (rows[j]["low"], j))
        L1 = rows[j1]["low"]
        H = max(r["high"] for r in rows[j1 + 1:j2])
        if H < max(L1, L2) * 1.10 or H - max(L1, L2) < 2 * atr[j2]:
            continue
        if L2 < L1 - atr[j2] or L2 > L1 + 0.75 * (H - L1):
            continue  # the second bottom is not lower than the first by more than one weekly ATR (equal bottoms count: CHRW 2012)
        if min(r["low"] for r in rows[j1:j2 + 1]) < min(L1, L2):
            continue
        z1, z2 = zone(rows, j1, tol, j2 - 1), zone(rows, j2, tol, t)  # no week after the signal is looked at
        if z1[1] >= z2[0]:
            continue  # the two zones must be separate
        prior_i = max(range(max(0, j1 - 52), j1 + 1), key=lambda j: rows[j]["high"])
        prior_high = rows[prior_i]["high"]
        # location (V3)
        lower = min(L1, L2)
        ema_hits = [f"EMA{p}@{nm}" for nm, idx in (("1", j1), ("2", j2)) for p, vals in ((20, e20), (50, e50), (200, e200)) if vals[idx] and abs(rows[idx]["low"] / vals[idx] - 1) <= 0.06]
        base_i = min(range(max(0, prior_i - 156), prior_i + 1), key=lambda j: rows[j]["low"])
        base = rows[base_i]["low"]
        retr = (prior_high - lower) / (prior_high - base) if prior_high > base else None
        gp = retr is not None and 0.5 <= retr <= 0.7
        location = bool(gp or ema_hits)  # a plus for ranking, not a filter (user, 2026-10-14)
        if lower < base * 0.9:
            continue  # too deep: the prior advance's start broken by more than 10%
        if (prior_high - L1) / prior_high < 0.15:
            continue  # a real pullback into the first bottom (V3's objective pullback, weekly scale)
        line = best_line(rows, highs, max(0, prior_i - 4), t, t + 1, (j1, L1, j2, L2))
        if not line:
            continue
        if not (e200[t] > e200[t - 26] and rows[t]["close"] > e200[t]):
            continue  # the user's bet: the long-term uptrend continues (weekly EMA200 rising, price above it)
        day_t = W["end"][t]
        mk = B.completed(M, day_t, day_t + 1)
        supports = [("signal_low", rows[t]["low"] * 0.99), ("second_bottom", L2 * 0.99)]
        if e200[t] < rows[t]["high"]:
            supports.append(("ema200", e200[t] * 0.99))
        fill_day = None
        # buy-stop above the engulfing week's high and the line, alive for up to three weeks (user, 2026-10-14);
        # cancelled if price reaches the stop first
        far_enough = [(nm, v) for nm, v in supports if v <= rows[t]["high"] * 1.001 - 0.5 * atr[t]]
        if not far_enough:
            continue
        stop_name, stop = max(far_enough, key=lambda x: x[1])  # the nearest support below the entry (user, 2026-10-14)
        for w in range(t + 1, min(t + 4, n)):
            level = max(rows[t]["high"], line["a"] + line["slope"] * (w - line["idx"][0])) * 1.001
            for d in range(W["start"][w], W["end"][w] + 1):
                if s["low"][d] <= stop and s["high"][d] < level:
                    break
                if s["high"][d] >= level:
                    fill_day, entry = d, max(s["open"][d], level)
                    break
            else:
                continue
            break
        if fill_day is None:
            continue
        if entry - stop < 0.5 * atr[t]:
            continue
        if entry > H:
            continue  # no chasing: the buy stays below the rebound high between the two bottoms (CSGP, NLY, CHRW all bought below it)
        rr = (prior_high - entry) / (entry - stop) if entry > stop else None
        if rr is None or rr < 1.5:
            continue
        risk = _bearish_risk_gate(rows[:t + 1], atr[:t + 1], e20[:t + 1], e50[:t + 1], [x for x in highs if x <= t - 2])
        out.append({"symbol": symbol, "signal_week": rows[t]["date"], "fill": s["date"][fill_day], "entry": round(entry, 4), "stop": round(stop, 4),
                    "target": round(prior_high, 4), "rr": round(rr, 2), "prior_high_week": rows[prior_i]["date"],
                    "zone1": [rows[z1[0]]["date"], rows[z1[1]]["date"]], "zone2": [rows[z2[0]]["date"], rows[z2[1]]["date"]], "L1": round(L1, 4), "L2": round(L2, 4),
                    "pushes": [rows[x]["date"] for x in line["idx"]], "push_prices": [round(x, 4) for x in line["prices"]], "macd": state,
                    "signal_bar": kind_t, "stop_basis": stop_name, "location": location, "target_1_5r": round(entry + 1.5 * (entry - stop), 4),
                    "gp": gp, "ema_hits": ema_hits, "risk_blocked": risk["blocked"], "monthly_cross": M["dif"][mk] > M["dea"][mk]})
        last = t
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
        s = PRICES[c["symbol"]]; d = bisect.bisect_left(s["date"], c["fill"]) - 1
        # dollar volume only: the $5 floor on split-adjusted prices drops the early years of stocks that later split (look-ahead);
        # it returns once the datasets keep the unadjusted close (2026-10-14)
        if d >= 420 and s["close"][d] * s["volume"][d] >= 1e7:
            out.append(c)
    json.dump(out, open(sys.argv[1], "w"))
    from collections import Counter
    print("candidates", len(out), "risk_blocked", sum(c["risk_blocked"] for c in out))
    print(sorted(Counter(c["fill"][:4] for c in out).items()))
