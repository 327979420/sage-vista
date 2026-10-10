"""Point-in-time structure checks for trading SV opportunities by level (E7b).

Every function takes a compact price series ({"date": [...], "open": [...],
"high": [...], "low": [...], "close": [...], "volume": [...]}, as stored in the
frozen datasets) and the index of the completed signal day, and reads nothing
after it, so a check gives the same answer on the signal date as years later.

- `value_area`: the daily volume profile's value area (Market Profile: J. Peter
  Steidlmayer at the CBOT; James Dalton, "Mind Over Markets"). Each day's volume
  is spread evenly across its high-low range, the price range is cut into equal
  rows, and the area grows one row at a time from the busiest price (the point
  of control) towards the busier neighbour until it holds 70% of the volume.
  Daily bars only approximate a real profile; this is not intraday order flow.
- `deep_drawdown`: a stock that fell more than 70% from its five-year high and
  has neither reclaimed 0.618 of the fall nor based for a year since its low
  (the user's 70% / 0.618 rule, docs/DECISION_LOG_ZH.md 2026-08-30; Weinstein's
  stage analysis: a stage-4 decline is tradable only after a stage-1 base).
- `wide_box`: a wide range crossed edge to edge more than once, with the signal
  well below the top: a bet inside a box, not a trend resuming (Darvas boxes;
  Minervini's trend template keeps buys within 25% of the 52-week high).
- Supply flags (labels only, never a reason to skip): rounds of bearish pressure
  (TTD), multiple tops with top exhaustion (AEVA) and a chain of down gaps
  (DLTR), from docs/CASE_REVIEW_LEDGER_ZH.md. They tell one supply story, so
  they are reported together as one flag and never added up.

Parameters were calibrated on the seen ledger cases only (acceptance, not
evidence); the 20-year experiment is the test.
"""
from __future__ import annotations

PARAMS = {
    "value_area": {"lookback": 120, "bins": 50, "share": 0.70},
    "deep_drawdown": {"lookback": 1260, "drop": 0.70, "retrace": 0.618, "base": 252},
    "wide_box": {"sessions": 252, "min_ratio": 2.0, "zone": 0.25, "min_traversals": 2, "near_high": 0.75},
    "bearish_pressure": {"lookback": 40, "min_rounds": 2, "big_body_atr": 0.6, "follow": 2, "gap": 3},
    "multiple_tops": {"lookback": 120, "tolerance": 0.06, "min_tops": 3, "valley": 0.08, "recent": 20},
    "gap_supply": {"lookback": 504, "min_gaps": 3, "size": 0.04, "key_window": 120},
}


def columns(bars):
    """Bars as a list of dicts -> the compact column form used here."""
    return {"date": [b["date"] for b in bars], **{k: [float(b[k]) for b in bars] for k in ("open", "high", "low", "close", "volume")}}


def value_area(s, end, lookback=120, bins=50, share=0.70):
    """Value area of the `lookback` sessions ending at `end`: {"available", "val", "poc", "vah", ...}."""
    if end + 1 < lookback:
        return {"available": False, "reason": "insufficient_history"}
    start = end - lookback + 1
    lows, highs, volumes = s["low"][start:end + 1], s["high"][start:end + 1], s["volume"][start:end + 1]
    lo, hi = min(lows), max(highs)
    if hi <= lo:
        return {"available": False, "reason": "flat_price_range"}
    width = (hi - lo) / bins
    profile = [0.0] * bins
    for low, high, volume in zip(lows, highs, volumes):
        if volume <= 0:
            continue
        a, z = (low - lo) / width, (high - lo) / width
        if z - a < 1e-12:
            profile[min(bins - 1, int(a))] += volume
            continue
        for k in range(int(a), min(bins - 1, int(z)) + 1):
            overlap = min(z, k + 1) - max(a, k)
            if overlap > 0:
                profile[k] += volume * overlap / (z - a)
    total = sum(profile)
    if total <= 0:
        return {"available": False, "reason": "volume_unavailable"}
    poc = max(range(bins), key=lambda k: (profile[k], -k))
    low_row, high_row, covered = poc, poc, profile[poc]
    while covered < share * total and (low_row > 0 or high_row < bins - 1):
        up = profile[high_row + 1] if high_row < bins - 1 else -1.0
        down = profile[low_row - 1] if low_row > 0 else -1.0
        if up >= down:
            high_row += 1
            covered += up
        else:
            low_row -= 1
            covered += down
    return {"available": True, "val": round(lo + low_row * width, 6), "poc": round(lo + (poc + 0.5) * width, 6),
            "vah": round(lo + (high_row + 1) * width, 6), "share": round(covered / total, 4), "lookback": lookback, "bins": bins}


def deep_drawdown(s, end, lookback=1260, drop=0.70, retrace=0.618, base=252):
    """Fell more than `drop` from the `lookback` high, without reclaiming `retrace` of the fall or basing `base` sessions."""
    start = max(0, end - lookback + 1)
    closes = s["close"][start:end + 1]
    high_close = max(closes)
    top = closes.index(high_close)
    low_close = min(closes[top:])
    low = len(closes) - 1 - closes[::-1].index(low_close)  # the latest session at the low
    close = closes[-1]
    fall = 1 - low_close / high_close if high_close > 0 else 0.0
    reclaim = low_close + retrace * (high_close - low_close)
    since_low = len(closes) - 1 - low
    triggered, repaired, based = fall > drop, close >= reclaim, since_low >= base
    return {"reject": triggered and not repaired and not based, "fall": round(fall, 4), "high_date": s["date"][start + top],
            "low_date": s["date"][start + low], "reclaim_level": round(reclaim, 4), "sessions_since_low": since_low,
            "repaired": repaired, "based": based}


def wide_box(s, end, sessions=252, min_ratio=2.0, zone=0.25, min_traversals=2, near_high=0.75):
    """A range at least `min_ratio` wide, crossed edge to edge `min_traversals` times, and a signal below `near_high` of its top.

    The range is the highest high and lowest low of the last `sessions` (fewer
    for a young listing). A traversal is a close in the bottom `zone` of the
    range followed later by one in the top `zone`, or the reverse. A stock
    trending up crosses once; a box goes back and forth.
    """
    start = max(0, end - sessions + 1)
    top, bottom = max(s["high"][start:end + 1]), min(s["low"][start:end + 1])
    ratio = top / bottom if bottom > 0 else 0.0
    span = top - bottom
    side, traversals = None, 0
    for close in s["close"][start:end + 1]:
        where = (close - bottom) / span if span > 0 else 0.5
        now = "low" if where <= zone else "high" if where >= 1 - zone else None
        if now and side and now != side:
            traversals += 1
        side = now or side
    below = s["close"][end] < near_high * top
    return {"reject": ratio >= min_ratio and traversals >= min_traversals and below, "ratio": round(ratio, 3), "traversals": traversals,
            "box_top": round(top, 4), "box_bottom": round(bottom, 4), "sessions": end - start + 1, "below_top_zone": below}


def _atr(s, end, period=14):
    if end < period:
        return None
    total = 0.0
    for i in range(end - period + 1, end + 1):
        h, l, prev = s["high"][i], s["low"][i], s["close"][i - 1]
        total += max(h - l, abs(h - prev), abs(l - prev))
    return total / period


def _ema(s, end, period):
    value, alpha = None, 2 / (period + 1)
    for c in s["close"][max(0, end - 4 * period):end + 1]:
        value = c if value is None else alpha * c + (1 - alpha) * value
    return value


def _bearish_engulfing(s, i):
    """03 rules exit.structure.bearish_engulfing: a down body covering the prior up body."""
    po, pc, o, c = s["open"][i - 1], s["close"][i - 1], s["open"][i], s["close"][i]
    return pc > po and c < o and o >= pc and c <= po


def bearish_pressure(s, end, lookback=40, min_rounds=2, big_body_atr=0.6, follow=2, gap=3):
    """Rounds of selling not yet repaired (case ledger TTD, candidate unresolved_bearish_pressure_rounds).

    A round is a bearish engulfing or a down candle with a body of at least
    `big_body_atr` x ATR14, followed within `follow` sessions by a lower close.
    Candles closer than `gap` sessions belong to one round. Flagged with at
    least `min_rounds` rounds in the last `lookback` sessions while EMA20 is
    still below EMA50 on the signal day.
    """
    rounds, last = [], None
    for i in range(max(15, end - lookback + 1), end + 1):
        atr = _atr(s, i - 1)
        body = s["open"][i] - s["close"][i]
        if not (_bearish_engulfing(s, i) or (atr and body >= big_body_atr * atr)):
            continue
        if not any(s["close"][j] < s["close"][i] for j in range(i + 1, min(end, i + follow) + 1)):
            continue
        if last is None or i - last > gap:
            rounds.append(s["date"][i])
        last = i
    ema20, ema50 = _ema(s, end, 20), _ema(s, end, 50)
    weak = ema20 is not None and ema50 is not None and ema20 < ema50
    return {"flag": len(rounds) >= min_rounds and weak, "rounds": rounds, "ema20_below_ema50": weak}


def _swing_highs(s, start, end, wing=2):
    """Highs above the `wing` sessions on each side, all on or before `end`."""
    highs = s["high"]
    return [i for i in range(start + wing, end - wing + 1)
            if all(highs[i] >= highs[j] for j in range(i - wing, i + wing + 1) if j != i)]


def multiple_tops(s, end, lookback=120, tolerance=0.06, min_tops=3, valley=0.08, recent=20):
    """At least `min_tops` separate tests of the same high, and top exhaustion back near that level lately (case ledger AEVA).

    A test is a swing high within `tolerance` of the highest one; two tests are
    separate only if price fell at least `valley` between them (otherwise the
    higher of the two counts once), as in the classic double and triple top.
    Exhaustion is a bearish engulfing or a shooting-star / gravestone candle
    (upper shadow at least twice the body and half the range) in the last
    `recent` sessions, with its high in the top zone.
    """
    start = max(0, end - lookback + 1)
    highs = _swing_highs(s, start, end)
    if not highs:
        return {"flag": False, "tops": [], "exhaustion": []}
    zone = max(s["high"][i] for i in highs) * (1 - tolerance)
    tops = []
    for i in (i for i in highs if s["high"][i] >= zone):
        between = s["low"][tops[-1] + 1:i] if tops else None
        if tops and (not between or min(between) > s["high"][tops[-1]] * (1 - valley)):
            if s["high"][i] > s["high"][tops[-1]]:
                tops[-1] = i
            continue
        tops.append(i)
    exhaustion = []
    for i in range(max(start + 1, end - recent + 1), end + 1):
        o, h, l, c = s["open"][i], s["high"][i], s["low"][i], s["close"][i]
        if h < zone:
            continue
        upper, body, span = h - max(o, c), abs(c - o), h - l
        if (span > 0 and upper >= 2 * body and upper >= 0.5 * span) or _bearish_engulfing(s, i):
            exhaustion.append(s["date"][i])
    return {"flag": len(tops) >= min_tops and bool(exhaustion), "tops": [s["date"][i] for i in tops], "exhaustion": exhaustion}


def gap_supply(s, end, lookback=504, min_gaps=3, size=0.04, key_window=120):
    """A chain of big down gaps: at least `min_gaps` in two years, the latest recent and still unfilled (case ledger DLTR).

    A big down gap opens at least `size` below the prior close and never trades
    back up to the prior low that day. Filled means a later close at or above
    that prior low.
    """
    o, h, l, c = s["open"], s["high"], s["low"], s["close"]
    gaps = [i for i in range(max(1, end - lookback + 1), end + 1) if o[i] <= c[i - 1] * (1 - size) and h[i] < l[i - 1]]
    latest = gaps[-1] if gaps else None
    unfilled = latest is not None and end - latest < key_window and max(c[latest:end + 1]) < l[latest - 1]
    return {"flag": len(gaps) >= min_gaps and unfilled, "big_gaps": [s["date"][i] for i in gaps], "latest_unfilled": unfilled}


def rejection(s, end, params=None):
    """The hard checks only (fast path for random picks): the first that rejects, or None."""
    p = params or PARAMS
    if deep_drawdown(s, end, **p["deep_drawdown"])["reject"]:
        return "deep_drawdown"
    if wide_box(s, end, **p["wide_box"])["reject"]:
        return "wide_box"
    return None


def assess(s, end, params=None):
    """Every check for one signal day: the hard rejection, then the supply flags."""
    p = params or PARAMS
    details = {"deep_drawdown": deep_drawdown(s, end, **p["deep_drawdown"]), "wide_box": wide_box(s, end, **p["wide_box"]),
               "bearish_pressure": bearish_pressure(s, end, **p["bearish_pressure"]),
               "multiple_tops": multiple_tops(s, end, **p["multiple_tops"]), "gap_supply": gap_supply(s, end, **p["gap_supply"])}
    reject = "deep_drawdown" if details["deep_drawdown"]["reject"] else "wide_box" if details["wide_box"]["reject"] else None
    flags = [k for k in ("bearish_pressure", "multiple_tops", "gap_supply") if details[k]["flag"]]
    return {"reject": reject, "flags": flags, "supply_flag": bool(flags), "details": details}
