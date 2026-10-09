"""Is SV's stock selection skill, or would random picks have done as well?

The null keeps everything SV decides except *which* stock: every SV signal is
replaced by a random stock from the same universe that traded that day, bought
the next session and sold by the same rule (its own support stop, computed
only from bars up to the signal day). Many such random accounts form the
distribution SV is ranked against. Because the random picks come from the same
universe, the universe's own biases (survivorship, the kind of stocks that ever
produced a signal) are shared by both sides.
"""
from __future__ import annotations

import bisect
import math
import random
from collections import defaultdict

from research.lab import datasets
from research.lab.exit_rules import simulate
from services.scanner.support_risk import signal_support_plan

MIN_HISTORY = 260  # about a year of bars, so long averages in the support plan exist


class Closes:
    """(date, close) pairs of one stock between two indexes, read from the frozen series without copying."""

    def __init__(self, series, start, end):
        self.dates, self.closes, self.start, self.end = series["date"], series["close"], start, end

    def __len__(self):
        return self.end - self.start + 1

    def __getitem__(self, j):
        i = self.start + j
        return self.dates[i], float(self.closes[i])


def eligible_pool(prices, day, rules=None):
    """Stocks with a bar on `day`, enough history before it and at least one bar after it.

    `rules` (optional) applies SV's own tradability floor on that day, so the
    random picks come from the stocks SV could actually have picked:
    {"min_history", "min_close", "min_dollar_volume", "exclude"}.
    """
    rules = rules or {}
    history = rules.get("min_history", MIN_HISTORY)
    excluded = rules.get("exclude", ())
    pool = []
    for symbol, series in prices.items():
        if symbol in excluded:
            continue
        i = bisect.bisect_left(series["date"], day)
        if not (i < len(series["date"]) and series["date"][i] == day and i >= history and i + 1 < len(series["date"])):
            continue
        if rules.get("min_close") or rules.get("min_dollar_volume"):
            close = float(series["close"][i])
            if close < rules.get("min_close", 0) or close * float(series["volume"][i]) < rules.get("min_dollar_volume", 0):
                continue
        pool.append(symbol)
    return pool


def impossible_jumps(prices, up=4.0, down=0.1):
    """Stocks whose close ever moves more than 4x up or 90% down in one session: provider adjustment errors."""
    bad = set()
    for symbol, series in prices.items():
        c = series["close"]
        if any(c[i - 1] > 0 and not (down <= c[i] / c[i - 1] <= up) for i in range(1, len(c))):
            bad.add(symbol)
    return bad


def winsorize(values, low=0.01, high=0.99):
    ordered = sorted(values)
    lo, hi = ordered[round(low * (len(ordered) - 1))], ordered[round(high * (len(ordered) - 1))]
    return [min(max(v, lo), hi) for v in values]


def draws(events, prices, runs, seed, rules=None):
    """runs x events random symbols, one per SV signal, reproducible from the seed."""
    pools = {}
    out = []
    for k in range(runs):
        rng = random.Random(seed + k)
        picks = []
        for e in events:
            day = e["signal_date"]
            if day not in pools:
                pools[day] = eligible_pool(prices, day, rules)
            picks.append(rng.choice(pools[day]) if pools[day] else None)
        out.append(picks)
    return out


def outcomes(needed, prices, variant, cost, data_end):
    """Trade every needed (symbol, signal day) once with the same exit rule; returns a lookup of candidates."""
    by_symbol = defaultdict(set)
    for symbol, day in needed:
        by_symbol[symbol].add(day)
    out = {}
    for symbol in sorted(by_symbol):
        series = prices[symbol]
        bars = datasets.expand(series)
        for day in sorted(by_symbol[symbol]):
            i = bisect.bisect_left(series["date"], day)
            plan = signal_support_plan(bars, end=i)
            result = simulate(bars, i + 1, variant, support_plan=plan, cost_per_side=cost)
            if result["status"] not in ("resolved", "observing"):
                out[(symbol, day)] = None
                continue
            last = i + result["held"]
            fills = [(f["date"], f["price"], f["fraction"]) for f in result.get("fills", [])]
            data_ended = result["status"] == "observing" and series["date"][-1] < data_end
            if data_ended:
                fills = [(series["date"][last], float(series["close"][last]), 1.0)]
            out[(symbol, day)] = {"symbol": symbol, "entry_date": series["date"][i + 1], "entry_price": float(result["entry"]),
                                  "stop": float(result["stop"]), "fills": fills, "data_ended": data_ended,
                                  "closes": Closes(series, i + 1, last), "net_return": result.get("net_return")}
    return out


def ols(y, xs):
    """Least squares of y on columns xs plus an intercept; returns coefficients and their t values."""
    n, k = len(y), len(xs) + 1
    rows = [[1.0, *(x[i] for x in xs)] for i in range(n)]
    xtx = [[sum(r[a] * r[b] for r in rows) for b in range(k)] for a in range(k)]
    xty = [sum(r[a] * yi for r, yi in zip(rows, y)) for a in range(k)]
    inv = _invert(xtx)
    beta = [sum(inv[a][b] * xty[b] for b in range(k)) for a in range(k)]
    resid = [yi - sum(b * v for b, v in zip(beta, r)) for r, yi in zip(rows, y)]
    s2 = sum(e * e for e in resid) / (n - k)
    t = [beta[a] / math.sqrt(s2 * inv[a][a]) if s2 * inv[a][a] > 0 else 0.0 for a in range(k)]
    return beta, t


def _invert(m):
    n = len(m)
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(m)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(a[r][c]))
        a[c], a[p] = a[p], a[c]
        pivot = a[c][c]
        a[c] = [v / pivot for v in a[c]]
        for r in range(n):
            if r != c:
                f = a[r][c]
                a[r] = [v - f * w for v, w in zip(a[r], a[c])]
    return [row[n:] for row in a]


def clustered_t(values, clusters):
    """Mean and t value of `values`, treating each cluster (signal month) as one observation."""
    groups = defaultdict(list)
    for v, c in zip(values, clusters):
        groups[c].append(v)
    means = [sum(g) / len(g) for g in groups.values()]
    if len(means) < 2:
        return (means[0] if means else 0.0), 0.0
    mean = sum(means) / len(means)
    sd = math.sqrt(sum((m - mean) ** 2 for m in means) / (len(means) - 1))
    return sum(values) / len(values), (mean / (sd / math.sqrt(len(means))) if sd else 0.0)
