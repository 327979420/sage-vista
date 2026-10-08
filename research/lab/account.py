"""Daily account simulation: the deciding test for lab exit rules.

Mirrors the approved research account (research/backtest/account-scenario.json
and the 08 rules "可复用研究运行接线"): $100,000; each new position is 10% of
initial cash in whole shares; at most 10 positions; 0.1% cost per side taken
from cash; long only, no leverage. Each session runs new entries at the open
in signal priority (skipped when the stock is already held, every slot is
full, or cash or whole shares fall short), then that session's exits, then the
end-of-day account value. Sale proceeds are never reused by the same session's
entries.

Portfolio experiments may pass `rules` instead, the sizing used by mature
trading programs: each position risks `risk_per_trade` of the previous
session's account value at its stop (Elder, Van Tharp, the Turtles), is
capped at `position_cap` of that value, at most `max_positions` are held, and
the total loss if every open stop hit stays within `heat_cap`.

The legacy account books the same rules through VectorBT. The lab uses this
small pure-Python equivalent because a Monte Carlo check runs the account
hundreds of times per rule (tests compare the two where VectorBT is installed).
A held stock without a bar on a benchmark session is valued at its last close
and counted, instead of failing a 20-year run on one trading halt.
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import math
import pathlib
import random
import statistics
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCENARIO = ROOT / "research/backtest/account-scenario.json"
TRADING_DAYS = 252
EULER = 0.5772156649015329
NORMAL = statistics.NormalDist()


def approved_scenario(path=SCENARIO):
    config = json.loads(pathlib.Path(path).read_text())
    if config.get("approved") is not True:
        raise ValueError("account_scenario_not_approved")
    return {k: config[k] for k in ("initial_cash", "allocation_fraction", "max_positions", "cost_rate", "fractional_shares")}


def candidate(event, bars, entry_index, result, priority, data_end):
    """One lab trade plus the closes needed to value it while held.

    A trade still open when its stock's prices stop before `data_end` (for
    example a delisting) is sold at the stock's last close and flagged
    `data_ended`. A trade open only because the data stops (a forward test)
    keeps no fills: the account holds it and values it at the last close.
    """
    last = entry_index + result["held"] - 1
    fills = [(f["date"], f["price"], f["fraction"]) for f in result.get("fills", [])]
    data_ended = result["status"] == "observing" and bars[-1]["date"] < data_end
    if data_ended:
        fills = [(bars[last]["date"], float(bars[last]["close"]), 1.0)]
    return {"event_id": event["event_id"], "symbol": event["symbol"], "signal_date": event["signal_date"], "priority": priority,
            "entry_date": bars[entry_index]["date"], "entry_price": float(result["entry"]), "stop": float(result["stop"]),
            "fills": fills, "data_ended": data_ended,
            "closes": [(bars[i]["date"], float(bars[i]["close"])) for i in range(entry_index, last + 1)]}


def align(candidates, calendar):
    """Map dates to calendar positions and precompute each trade's daily value per share."""
    aligned, mismatched, stale, data_ended = [], 0, 0, 0
    for c in candidates:
        entry_ci = bisect.bisect_left(calendar, c["entry_date"])
        if entry_ci >= len(calendar):
            continue
        mismatched += calendar[entry_ci] != c["entry_date"]
        data_ended += c.get("data_ended", False)
        exits = [(min(bisect.bisect_left(calendar, d), len(calendar) - 1), p, f) for d, p, f in c["fills"]]
        last_ci = max(ci for ci, _, _ in exits) if exits else len(calendar) - 1
        values, j, close = [], 0, c["entry_price"]
        for ci in range(entry_ci, last_ci + 1):
            day = calendar[ci]
            had_bar = False
            while j < len(c["closes"]) and c["closes"][j][0] <= day:
                had_bar = c["closes"][j][0] == day
                close = c["closes"][j][1]
                j += 1
            stale += not had_bar
            values.append(close)
        aligned.append({**c, "entry_ci": entry_ci, "exits": exits, "values": values})
    return aligned, {"calendar_mismatches": mismatched, "stale_valuations": stale, "sold_when_prices_ended": data_ended}


def run_account(trades, n_days, scenario, rng=None, rules=None):
    """Book one account path. `rng` shuffles same-day signals (Monte Carlo); None keeps priority order.

    `rules` None keeps the approved preset (a fixed 10% of initial cash per position).
    """
    entries = defaultdict(list)
    for k, t in enumerate(trades):
        entries[t["entry_ci"]].append(k)
    for ks in entries.values():
        if rng is None:
            ks.sort(key=lambda k: (trades[k]["priority"], trades[k]["event_id"]))
        else:
            ks.sort(key=lambda k: trades[k]["event_id"])
            rng.shuffle(ks)
    cash = float(scenario["initial_cash"])
    nominal = scenario["initial_cash"] * scenario["allocation_fraction"]
    fee = scenario["cost_rate"]
    limit = rules["max_positions"] if rules else scenario["max_positions"]
    held, equity, exposure, booked, skipped = {}, [], [], [], Counter()
    for ci in range(n_days):
        # Sizes use the last completed end-of-day value, never today's prices.
        base = equity[-1] if equity else float(scenario["initial_cash"])
        for k in entries.get(ci, ()):
            t = trades[k]
            if t["symbol"] in held:
                skipped["same_stock_held"] += 1
                continue
            if len(held) >= limit:
                skipped["position_limit"] += 1
                continue
            per_share_risk = max(t["entry_price"] - t["stop"], 1e-9)
            if rules:
                qty = min(rules["position_cap"] * base / t["entry_price"], rules["risk_per_trade"] * base / per_share_risk)
            else:
                qty = nominal / t["entry_price"]
            if not scenario["fractional_shares"]:
                qty = math.floor(qty)
            if rules and rules.get("heat_cap") is not None:
                open_risk = sum(p["shares"] * p["risk_per_share"] for p in held.values())
                if open_risk + qty * per_share_risk > rules["heat_cap"] * base + 1e-9:
                    skipped["open_risk_limit"] += 1
                    continue
            cost = qty * t["entry_price"] * (1 + fee)
            if qty <= 0 or cost > cash + 1e-9:
                skipped["cash_or_whole_share_insufficient"] += 1
                continue
            cash -= cost
            held[t["symbol"]] = {"t": t, "shares": qty, "original": qty, "next": 0, "cost": cost, "proceeds": 0.0,
                                 "risk_per_share": per_share_risk}
        for symbol in list(held):
            p = held[symbol]
            t = p["t"]
            while p["next"] < len(t["exits"]) and t["exits"][p["next"]][0] == ci:
                _, price, fraction = t["exits"][p["next"]]
                p["next"] += 1
                last = p["next"] == len(t["exits"])
                qty = p["shares"] if last else min(p["shares"], math.floor(p["original"] * fraction))
                proceeds = qty * price * (1 - fee)
                cash += proceeds
                p["proceeds"] += proceeds
                p["shares"] -= qty
            if t["exits"] and p["next"] == len(t["exits"]):
                booked.append({"event_id": t["event_id"], "symbol": symbol, "signal_date": t["signal_date"], "shares": p["original"],
                               "pnl": round(p["proceeds"] - p["cost"], 4), "return": round(p["proceeds"] / p["cost"] - 1, 6)})
                del held[symbol]
        invested = sum(p["shares"] * p["t"]["values"][ci - p["t"]["entry_ci"]] for p in held.values())
        nav = cash + invested
        equity.append(nav)
        exposure.append(invested / nav if nav > 0 else 0.0)
    return {"equity": equity, "exposure": exposure, "trades": booked, "open_at_end": len(held), "skipped": dict(skipped)}


def _mean_sd(values):
    # statistics.stdev uses exact fractions and is slow on 5,000-session series run hundreds of times.
    n = len(values)
    mean = math.fsum(values) / n
    sd = math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (n - 1)) if n > 1 else 0.0
    return mean, sd


def returns_from(equity, initial):
    out, previous = [], initial
    for value in equity:
        out.append(value / previous - 1)
        previous = value
    return out


def curve_stats(equity, dates, initial):
    """CAGR, drawdown and risk-adjusted ratios from end-of-day account values (risk-free rate 0, 252 sessions)."""
    rets = returns_from(equity, initial)
    years = max((dt.date.fromisoformat(dates[-1]) - dt.date.fromisoformat(dates[0])).days / 365.25, 1 / 365.25)
    cagr = (equity[-1] / initial) ** (1 / years) - 1
    peak, mdd = initial, 0.0
    for value in equity:
        peak = max(peak, value)
        mdd = max(mdd, 1 - value / peak)
    mean, sd = _mean_sd(rets)
    downside = math.sqrt(math.fsum(min(r, 0.0) ** 2 for r in rets) / len(rets))
    skew = math.fsum(((r - mean) / sd) ** 3 for r in rets) / len(rets) if sd else 0.0
    kurt = math.fsum(((r - mean) / sd) ** 4 for r in rets) / len(rets) if sd else 3.0
    return {"final_equity": round(equity[-1], 2), "total_return": round(equity[-1] / initial - 1, 6), "cagr": round(cagr, 6),
            "max_drawdown": round(mdd, 6), "sharpe": round(mean / sd * math.sqrt(TRADING_DAYS), 4) if sd else None,
            "sortino": round(mean / downside * math.sqrt(TRADING_DAYS), 4) if downside else None,
            "calmar": round(cagr / mdd, 4) if mdd else None, "daily_sharpe": round(mean / sd, 8) if sd else 0.0,
            "skew": round(skew, 4), "kurtosis": round(kurt, 4), "sessions": len(equity)}


def benchmark_returns(series, dates):
    """Daily benchmark returns on the account calendar: bought at the first session's open, then close to close."""
    index = {d: i for i, d in enumerate(series["date"])}
    first = index[dates[0]]
    out = [series["close"][first] / series["open"][first] - 1]
    for prev, day in zip(dates, dates[1:]):
        out.append(series["close"][index[day]] / series["close"][index[prev]] - 1)
    return out


def compound(rets, initial):
    equity, value = [], initial
    for r in rets:
        value *= 1 + r
        equity.append(value)
    return equity


def versus(account_rets, bench_rets):
    """Beta, annual alpha, information ratio and correlation of daily account returns against the benchmark."""
    n = len(bench_rets)
    mb, ma = math.fsum(bench_rets) / n, math.fsum(account_rets) / n
    var_b = math.fsum((b - mb) ** 2 for b in bench_rets) / n
    var_a = math.fsum((a - ma) ** 2 for a in account_rets) / n
    cov = math.fsum((a - ma) * (b - mb) for a, b in zip(account_rets, bench_rets)) / n
    beta = cov / var_b if var_b else 0.0
    mean_active, sd_active = _mean_sd([a - b for a, b in zip(account_rets, bench_rets)])
    sd_a, sd_b = math.sqrt(var_a), math.sqrt(var_b)
    return {"beta": round(beta, 4), "alpha_annual": round((ma - beta * mb) * TRADING_DAYS, 6),
            "information_ratio": round(mean_active / sd_active * math.sqrt(TRADING_DAYS), 4) if sd_active else None,
            "correlation": round(cov / (sd_a * sd_b), 4) if sd_a and sd_b else None}


def period_returns(equity, dates, initial, splits):
    out = {}
    for s in splits:
        idx = [i for i, d in enumerate(dates) if s["from"] <= d <= s["to"]]
        if not idx:
            out[s["id"]] = None
            continue
        start = equity[idx[0] - 1] if idx[0] else initial
        out[s["id"]] = round(equity[idx[-1]] / start - 1, 6)
    return out


def deflated_sharpe(daily_sharpe, sessions, skew, kurtosis, n_trials, trial_variance):
    """Bailey and Lopez de Prado (2014): probability the Sharpe ratio beats the best of `n_trials` lucky ones."""
    if n_trials > 1 and trial_variance > 0:
        sr0 = math.sqrt(trial_variance) * ((1 - EULER) * NORMAL.inv_cdf(1 - 1 / n_trials) + EULER * NORMAL.inv_cdf(1 - 1 / (n_trials * math.e)))
    else:
        sr0 = 0.0
    denom = 1 - skew * daily_sharpe + (kurtosis - 1) / 4 * daily_sharpe ** 2
    if denom <= 0 or sessions < 2:
        return None
    return round(NORMAL.cdf((daily_sharpe - sr0) * math.sqrt(sessions - 1) / math.sqrt(denom)), 4)


def distribution(values):
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return None
    pick = lambda q: ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1) + 0.5))]
    return {"p5": round(pick(0.05), 6), "median": round(pick(0.5), 6), "p95": round(pick(0.95), 6)}


def monte_carlo(trades, dates, scenario, runs, seed, rules=None):
    """Same rule, same signals; only which same-day signals win the free slots changes."""
    stats = {"cagr": [], "max_drawdown": [], "sharpe": []}
    for run in range(runs):
        path = run_account(trades, len(dates), scenario, random.Random(seed + run), rules)
        s = curve_stats(path["equity"], dates, scenario["initial_cash"])
        for key in stats:
            stats[key].append(s[key])
    return {"runs": runs, "seed": seed, **{k: distribution(v) for k, v in stats.items()}}


def evaluate(item, baseline, benchmark, criteria):
    """Pre-registered account checks; every check is reported, not only the verdict."""
    a = item["account"]
    checks = {"enough_trades": a["trades_taken"] >= criteria.get("min_trades", 0),
              "max_drawdown": a["max_drawdown"] <= criteria["max_drawdown"]}
    for metric in criteria.get("beat_baseline", []):
        checks[f"{metric}_beats_current_rule"] = (a.get(metric) or -9) > (baseline["account"].get(metric) or -9)
    for metric in criteria.get("beat_benchmark", []):
        checks[f"{metric}_beats_spy"] = (a.get(metric) or -9) > (benchmark.get(metric) or -9)
    if criteria.get("mc_runs"):
        checks["luck_check_median_sharpe_beats_current_rule"] = item["monte_carlo"]["sharpe"]["median"] > baseline["monte_carlo"]["sharpe"]["median"]
        if "mc_p5_cagr_min" in criteria:
            checks["luck_check_worst_5pct_still_grows"] = item["monte_carlo"]["cagr"]["p5"] > criteria["mc_p5_cagr_min"]
    if criteria.get("every_split_positive"):
        checks["every_period_positive"] = all(r is None or r > 0 for r in item["splits"].values())
    if "min_deflated_sharpe" in criteria:
        checks["deflated_sharpe"] = (item.get("deflated_sharpe") or 0) >= criteria["min_deflated_sharpe"]
    return {"passed": all(checks.values()), "checks": checks}
