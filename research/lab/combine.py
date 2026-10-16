"""Pure monthly sleeve allocation, task 001.

Returns are close-to-close on a shared calendar. A month-end decision is applied
before the next session's return. Fees are cost * L1 change in risky sleeve
weights, deducted once from pre-return NAV; cash is not an additional fee leg.
Targets describe post-fee weights. Between trades, both sleeves and zero-yield
cash drift. Initial capital is already equally allocated (no synthetic initial
rebalance); underlying sleeve entry costs are already in their returns.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics
from collections.abc import Callable, Mapping, Sequence


def equal_weights(history: Mapping[str, Sequence[float]]) -> dict[str, float]:
    return {name: 1 / len(history) for name in history}


def inverse_volatility(history: Mapping[str, Sequence[float]]) -> dict[str, float]:
    """252 observed sessions, inclusive of the decision day; sample stdev."""
    if min(map(len, history.values())) < 252:
        return equal_weights(history)
    vol = {name: statistics.stdev(values[-252:]) for name, values in history.items()}
    zeros = [name for name, value in vol.items() if value == 0]
    if zeros:
        # Continuous inverse-vol limit, without an arbitrary epsilon parameter.
        return {name: (1 / len(zeros) if name in zeros else 0.0) for name in history}
    inverse = {name: 1 / value for name, value in vol.items()}
    total = math.fsum(inverse.values())
    return {name: value / total for name, value in inverse.items()}


def volatility_target(history: Mapping[str, Sequence[float]],
                      p2_history: Sequence[float]) -> dict[str, float]:
    """P2 weights scaled to 10% annual volatility using 63 net P2 returns.

    No scaling before a full 63-session window exists; never lever up.
    The caller must pass P2 history only through the same decision day.
    """
    if any(len(values) != len(p2_history) for values in history.values()):
        raise ValueError("P2 history must end on the same decision day")
    scale = 1.0
    if len(p2_history) >= 63:
        vol = statistics.stdev(p2_history[-63:]) * math.sqrt(252)
        scale = min(1.0, 0.10 / vol) if vol else 1.0
    return {name: value * scale for name, value in inverse_volatility(history).items()}


def combine(dates: Sequence[str], returns: Mapping[str, Sequence[float]],
            target_rule: Callable, cost_per_side: float = 0.001,
            initial: float = 100000.0) -> dict:
    """Combine sleeves. The rule receives only observed returns through month end.

    Output includes daily pre-return and closing weights, fees in dollars,
    turnover fractions and an auditable decision/execution ledger.
    """
    dates = list(dates)
    names = list(returns)
    n = len(dates)
    if not names or not n or len(set(dates)) != n or dates != sorted(dates):
        raise ValueError("Nonempty, strictly increasing common calendar required")
    for day in dates:
        dt.date.fromisoformat(day)
    if not math.isfinite(initial) or initial <= 0 or not 0 <= cost_per_side < 1:
        raise ValueError("Invalid initial value or cost")
    data = {name: tuple(returns[name]) for name in names}
    if any(len(rs) != n or any(not math.isfinite(r) or r <= -1 for r in rs)
           for rs in data.values()):
        raise ValueError("Aligned finite returns greater than -1 required")
    weights = equal_weights(data)
    nav = initial
    pending = None
    out = {key: [] for key in ("equity", "returns", "weights", "start_weights",
                               "cash_weight", "fees", "turnover", "decisions")}
    out["dates"] = dates
    for i, day in enumerate(dates):
        previous = nav
        turnover = 0.0
        if pending is not None:
            turnover = math.fsum(abs(pending[name] - weights[name]) for name in names)
            weights = pending
            pending = None
        fee = nav * cost_per_side * turnover
        nav -= fee
        if nav <= 0:
            raise ValueError("Rebalance costs exhausted capital")
        out["start_weights"].append(dict(weights))
        cash = nav * max(0.0, 1 - math.fsum(weights.values()))
        values = {name: nav * weights[name] * (1 + data[name][i]) for name in names}
        nav = cash + math.fsum(values.values())
        weights = {name: value / nav for name, value in values.items()}
        out["equity"].append(nav)
        out["returns"].append(nav / previous - 1)
        out["weights"].append(weights)
        out["cash_weight"].append(cash / nav)
        out["fees"].append(fee)
        out["turnover"].append(turnover)
        if i + 1 < n and day[:7] != dates[i + 1][:7]:
            history = {name: values[:i + 1] for name, values in data.items()}
            target = dict(target_rule(history))
            if (set(target) != set(names) or
                any(not math.isfinite(w) or w < 0 for w in target.values()) or
                math.fsum(target.values()) > 1 + 1e-12):
                raise ValueError("Targets must be finite, long-only, and unlevered")
            pending = target
            out["decisions"].append({"decision_date": day, "execution_date": dates[i + 1],
                                     "target": dict(target)})
    return out


def portfolios(dates: Sequence[str], returns: Mapping[str, Sequence[float]],
               cost_per_side: float = 0.001) -> dict:
    """The three registered portfolios only, with P3 using net P2 history."""
    if set(returns) != {"TREND", "MOMLV", "3W"}:
        raise ValueError("Expected TREND, MOMLV and 3W")
    p1 = combine(dates, returns, equal_weights, cost_per_side)
    p2 = combine(dates, returns, inverse_volatility, cost_per_side)

    def p3_rule(history):
        count = len(next(iter(history.values())))
        return volatility_target(history, p2["returns"][:count])

    return {"P1": p1, "P2": p2,
            "P3": combine(dates, returns, p3_rule, cost_per_side)}
