"""Proven multi-asset portfolios, rebalanced the way their authors published them.

A portfolio is data in the spec, never new code:

- `static`: fixed weights, rebalanced monthly or each December
  (60/40, Harry Browne's Permanent Portfolio, Ray Dalio's All Weather, Ivy);
- `timing`: Meb Faber's rule; at each month end an asset is held only if its
  close is above the average of its last 10 month-end closes, otherwise that
  slice moves to the cash fund;
- `dual_momentum`: Gary Antonacci's Global Equities Momentum; at each month
  end, if US stocks beat cash over 12 months, hold the stronger of US and
  international stocks, otherwise hold bonds.

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

    def month_end_closes(self, symbol, day, count):
        """The last `count` month-end closes up to and including `day`."""
        s = self.series[symbol]
        ends = [d for d in month_ends(s["date"]) if d <= day]
        if len(ends) < count:
            raise ValueError(f"not_enough_history:{symbol}:{day}")
        return [self.close(symbol, d) for d in ends[-count:]]


def target_weights(portfolio, prices, day):
    rule = portfolio["rule"]
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
