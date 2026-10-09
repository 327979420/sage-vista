"""Proven multi-asset portfolios, rebalanced the way their authors published them.

A portfolio is data in the spec, never new code:

- `static`: fixed weights, rebalanced monthly or each December
  (60/40, Harry Browne's Permanent Portfolio, Ray Dalio's All Weather, Ivy);
- `timing`: Meb Faber's rule; at each month end an asset is held only if its
  close is above the average of its last 10 month-end closes, otherwise that
  slice moves to the cash fund;
- `dual_momentum`: Gary Antonacci's Global Equities Momentum; at each month
  end, if US stocks beat cash over 12 months, hold the stronger of US and
  international stocks, otherwise hold bonds;
- `overlay`: fixed weights where some slices are scaled down step by step:
  by trend (Faber's 10-month average, or the share of 1/3/12-month returns
  above cash as in Hurst, Ooi and Pedersen) and/or by volatility (target
  divided by recent volatility, Moreira and Muir); the rest goes to cash;
- `rotation`: each month hold the top few funds of a list by average past
  return (industry momentum, Moskowitz and Grinblatt), optionally only those
  beating cash, inside a sleeve next to fixed weights.

Signals use month-end closes known at that close and trade at the next
session's open, with the lab's cost per side on the amount traded. Between
rebalances holdings drift with prices. Prices are adjusted, so dividends and
bond coupons are included.
"""
from __future__ import annotations

import bisect


def month_ends(dates):
    return [d for i, d in enumerate(dates) if i == len(dates) - 1 or d[:7] != dates[i + 1][:7]]


class Prices:
    """Adjusted open/close lookup by symbol and date; a missing session uses the last earlier close."""

    def __init__(self, prices):
        self.series = prices

    def close(self, symbol, day):
        s = self.series[symbol]
        i = bisect.bisect_right(s["date"], day) - 1
        if i < 0:
            raise ValueError(f"no_price_before_{day}:{symbol}")
        return s["close"][i]

    def open(self, symbol, day):
        s = self.series[symbol]
        i = bisect.bisect_left(s["date"], day)
        if i < len(s["date"]) and s["date"][i] == day:
            return s["open"][i]
        return self.close(symbol, day)

    def daily_closes(self, symbol, day, count):
        """The last `count` daily closes up to and including `day`."""
        s = self.series[symbol]
        i = bisect.bisect_right(s["date"], day)
        if i < count:
            raise ValueError(f"not_enough_history:{symbol}:{day}")
        return s["close"][i - count:i]

    def month_end_closes(self, symbol, day, count):
        """The last `count` month-end closes up to and including `day`."""
        s = self.series[symbol]
        ends = [d for d in month_ends(s["date"]) if d <= day]
        if len(ends) < count:
            raise ValueError(f"not_enough_history:{symbol}:{day}")
        return [self.close(symbol, d) for d in ends[-count:]]


def roles(portfolio):
    """Every price series a portfolio can hold."""
    out = set(portfolio.get("weights", {})) | set(portfolio.get("risky", [])) | set(portfolio.get("universe", []))
    out |= {portfolio[k] for k in ("cash", "safe") if portfolio.get(k)}
    return out


def rolling(equities, dates, years, step, benchmark, core):
    """Rolling windows of `years`: Sharpe, total return and worst fall for every portfolio, plus the core against the benchmark."""
    length = int(years * 252)
    starts = list(range(0, len(dates) - length, step))
    per, beats = {}, 0
    for name, equity in equities.items():
        sharpes, totals, falls = [], [], []
        for a in starts:
            window = equity[a:a + length + 1]
            rets = [window[i] / window[i - 1] - 1 for i in range(1, len(window))]
            mean = sum(rets) / len(rets)
            sd = (sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5
            peak, fall = window[0], 0.0
            for v in window:
                peak = max(peak, v)
                fall = max(fall, 1 - v / peak)
            sharpes.append(mean / sd * 252 ** 0.5 if sd else 0.0)
            totals.append(window[-1] / window[0] - 1)
            falls.append(fall)
        per[name] = {"sharpe": sharpes, "total": totals, "fall": falls}
    if core in per and benchmark in per:
        beats = sum(c >= b for c, b in zip(per[core]["sharpe"], per[benchmark]["sharpe"]))
    summary = {name: {"sharpe_p5": round(sorted(v["sharpe"])[int(0.05 * (len(v["sharpe"]) - 1))], 4) if v["sharpe"] else None,
                      "sharpe_median": round(sorted(v["sharpe"])[len(v["sharpe"]) // 2], 4) if v["sharpe"] else None,
                      "worst_fall": round(max(v["fall"]), 6) if v["fall"] else None,
                      "lowest_return": round(min(v["total"]), 6) if v["total"] else None,
                      "share_positive": round(sum(t > 0 for t in v["total"]) / len(v["total"]), 4) if v["total"] else None}
               for name, v in per.items()}
    return {"years": years, "windows": len(starts), "first_window": dates[starts[0]] if starts else None, "last_window": dates[starts[-1]] if starts else None,
            "per_portfolio": summary, "core_sharpe_beats_benchmark_share": round(beats / len(starts), 4) if starts and core in per else None}


def _change(prices, symbol, day, months):
    closes = prices.month_end_closes(symbol, day, months + 1)
    return closes[-1] / closes[0] - 1


def trend_score(prices, symbol, day, trend, cash):
    """1 when the trend is fully up, 0 when down, in steps between for several lookbacks."""
    if trend["kind"] == "sma":
        closes = prices.month_end_closes(symbol, day, trend["months"])
        return 1.0 if closes[-1] > sum(closes) / len(closes) else 0.0
    if trend["kind"] == "tsmom":
        hits = [_change(prices, symbol, day, m) > _change(prices, cash, day, m) for m in trend["lookbacks_months"]]
        return sum(hits) / len(hits)
    raise ValueError(f"unknown trend kind {trend['kind']}")


def vol_scale(prices, symbol, day, vol):
    closes = prices.daily_closes(symbol, day, vol["days"] + 1)
    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    mean = sum(rets) / len(rets)
    realized = (sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) ** 0.5 * 252 ** 0.5
    return min(vol.get("cap", 1.0), vol["target"] / realized) if realized else 1.0


def target_weights(portfolio, prices, day):
    rule = portfolio["rule"]
    if rule == "overlay":
        out = dict(portfolio["weights"])
        cash = portfolio["cash"]
        for symbol, rules in portfolio["overlay"].items():
            scale = 1.0
            if rules.get("trend"):
                scale *= trend_score(prices, symbol, day, rules["trend"], cash)
            if rules.get("vol"):
                scale *= vol_scale(prices, symbol, day, rules["vol"])
            moved = out[symbol] * (1 - scale)
            out[symbol] -= moved
            out[cash] = out.get(cash, 0.0) + moved
        return {s: w for s, w in out.items() if w > 0}
    if rule == "rotation":
        out = dict(portfolio.get("weights", {}))
        score = {s: sum(_change(prices, s, day, m) for m in portfolio["lookbacks_months"]) / len(portfolio["lookbacks_months"]) for s in portfolio["universe"]}
        picks = sorted(portfolio["universe"], key=lambda s: (-score[s], s))[: portfolio["top"]]
        share = portfolio["sleeve"] / portfolio["top"]
        cash = portfolio.get("cash")
        hurdle = (sum(_change(prices, cash, day, m) for m in portfolio["lookbacks_months"]) / len(portfolio["lookbacks_months"])
                  if portfolio.get("absolute") else None)
        for s in picks:
            held = cash if hurdle is not None and score[s] <= hurdle else s
            out[held] = out.get(held, 0.0) + share
        return out
    if rule == "static":
        return dict(portfolio["weights"])
    if rule == "timing":
        out = {}
        for symbol, weight in portfolio["weights"].items():
            closes = prices.month_end_closes(symbol, day, portfolio["months"])
            held = symbol if closes[-1] > sum(closes) / len(closes) else portfolio["cash"]
            out[held] = out.get(held, 0.0) + weight
        return out
    if rule == "dual_momentum":
        months = portfolio["months"] + 1
        change = {s: (lambda c: c[-1] / c[0] - 1)(prices.month_end_closes(s, day, months)) for s in (*portfolio["risky"], portfolio["cash"])}
        if change[portfolio["risky"][0]] > change[portfolio["cash"]]:
            return {max(portfolio["risky"], key=lambda s: change[s]): 1.0}
        return {portfolio["safe"]: 1.0}
    raise ValueError(f"unknown portfolio rule {rule}")


def rebalance_days(portfolio, dates):
    ends = month_ends(dates)
    if portfolio.get("rebalance", "monthly") == "annual":
        return {d for d in ends if d[5:7] == "12"}
    return set(ends)


def simulate(portfolio, prices, dates, cost, initial, signal_day):
    """Daily account values for one portfolio. `signal_day` is the session before `dates[0]`."""
    holdings, cash, equity, weights_log, traded = {}, float(initial), [], [], 0.0
    pending = target_weights(portfolio, prices, signal_day)
    rebalance = rebalance_days(portfolio, dates)
    for day in dates:
        if pending is not None:
            value = cash + sum(q * prices.open(s, day) for s, q in holdings.items())
            symbols = sorted(set(holdings) | set(pending))
            current = {s: holdings.get(s, 0.0) * prices.open(s, day) for s in symbols}
            # Pay the trading cost out of the rebalanced value, so cash never goes below zero.
            fees = sum(abs(pending.get(s, 0.0) * value - current[s]) for s in symbols) * cost
            invest = value - fees
            for symbol in symbols:
                target = pending.get(symbol, 0.0) * invest
                trade = target - current[symbol]
                cash -= trade + abs(trade) * cost
                traded += abs(trade)
                holdings[symbol] = target / prices.open(symbol, day)
            holdings = {s: q for s, q in holdings.items() if q > 0}
            weights_log.append({"date": day, "weights": {s: round(w, 4) for s, w in sorted(pending.items())}})
            pending = None
        nav = cash + sum(q * prices.close(s, day) for s, q in holdings.items())
        equity.append(nav)
        if day in rebalance and day != dates[-1]:
            pending = target_weights(portfolio, prices, day)
    return {"equity": equity, "rebalances": weights_log, "turnover": traded}
