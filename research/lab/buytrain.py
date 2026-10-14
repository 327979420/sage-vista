"""Training and test run for the buy system (lab-buysystem-train-v1; docs/BUY_SYSTEM_ZH.md 0.2.0; 08 rules #buysystem-train).

Every step is automatic and written down before the run:
1 scan every stock for monthly and weekly opportunities under the baseline and under each one-change variant; one scan covers
  the training start to the test end, and the windows split it by fill date;
2 on the training window, trade each variant's signals in the research account, and trade same-day random stocks from the same
  pool under the same rules (the same stop distance in weekly ATRs, the same first-target R multiple, the same exits);
3 adopt a change only when it beats the baseline by the pre-registered margins on the training window;
4 run the baseline plus the adopted changes once on the test window and judge it by the pre-registered criteria.
Trades are cut at their window's last session, so the training window never sees a test-window price.
"""
from __future__ import annotations

import bisect
import copy
import multiprocessing
import os
import random
import statistics
from collections import Counter

from research.lab import account, buysystem as B, levels, selection, timeframe
from research.lab.exit_rules import period_key

_PRICES = None  # shared with forked scan workers


def override(params, changes):
    """A copy of the parameters with dotted keys replaced, e.g. {"kinds.week.a.min_pullback": 0.08}; unknown keys are an error."""
    p = copy.deepcopy(params)
    for key, value in changes.items():
        node = p
        *path, last = key.split(".")
        for part in path:
            node = node[part]
        if last not in node:
            raise KeyError(f"unknown parameter {key}")
        node[last] = value
    return p


def engine_changes(changes):
    return {k: v for k, v in changes.items() if not k.startswith("account.")}


def tradable(series, i, pool):
    """SV's floor on day i. With `raw_close` in the pool rules the $5 price floor reads the unadjusted close when the dataset keeps it
    (a stock that later split 10:1 traded at ten times its adjusted price); dollar volume stays adjusted close times split-adjusted
    volume."""
    price = series["raw_close"][i] if pool.get("raw_close") and "raw_close" in series else series["close"][i]
    return i >= pool["min_history"] and price >= pool["min_close"] and series["close"][i] * series["volume"][i] >= pool["min_dollar_volume"]


def _scan_one(args):
    symbol, p, start, end, pool = args
    s = _PRICES[symbol]
    out = []
    for kind in ("month", "week"):
        for card in B.scan(s, kind, p, start=start, end=end, fast=True)["signals"]:
            i = bisect.bisect_left(s["date"], card["decision_date"])
            if tradable(s, i, pool):
                out.append({"symbol": symbol, **card})
    return out


def scan_universe(prices, p, start, end, pool, excluded, workers=None):
    """Every signal of both kinds inside the tradable pool, in a fixed order (in parallel when the platform can fork)."""
    global _PRICES
    _PRICES = prices
    jobs = [(symbol, p, start, end, pool) for symbol in sorted(prices) if symbol not in excluded]
    workers = workers if workers is not None else (os.cpu_count() or 1)
    if workers > 1 and "fork" in multiprocessing.get_all_start_methods():
        with multiprocessing.get_context("fork").Pool(workers) as procs:
            chunks = procs.map(_scan_one, jobs, chunksize=4)
    else:
        chunks = [_scan_one(j) for j in jobs]
    signals = [c for chunk in chunks for c in chunk]
    return sorted(signals, key=lambda c: (c["fill_date"], 0 if c["kind"] == "month" else 1, c["symbol"]))


class WeeklyATR:
    """A stock's weekly ATR from the last completed week at a given day, weekly bars built once per stock."""

    def __init__(self, prices):
        self.prices, self.cache = prices, {}

    def at(self, symbol, day_index):
        if symbol not in self.cache:
            self.cache[symbol] = B.periods(self.prices[symbol], "week")
        W = self.cache[symbol]
        w = B.completed(W, day_index, len(self.prices[symbol]["close"]))
        return W["atr"][w] if w >= 0 else None


def simulate(series, limit, entry_index, stop, target, fraction, runner, max_hold, cost_per_side, entry_price=None):
    """The buy system's exit (exit_rules.simulate with a level stop, one price target, breakeven and the runner's trend exit after
    the target) on plain columns, cut at `limit` sessions. Same results as exit_rules.simulate (tests/test_buytrain.py checks it);
    it exists because the random null trades a few hundred thousand times.
    `entry_price` is a buy-stop filled during the entry session instead of at its open: that session's open came before the buy, and
    a low at or under the stop that session counts as stopped (the order of the high and the low is unknown; the worse reading)."""
    date, opens, highs, lows, closes = series["date"], series["open"], series["high"], series["low"], series["close"]
    if entry_index <= 0 or entry_index >= limit:
        return {"status": "no_entry"}
    entry = float(opens[entry_index]) if entry_price is None else float(entry_price)
    if not 0 < stop < entry:
        return {"status": "skipped", "reason": "no_executable_stop"}
    risk_stop, risk, n = stop, entry - stop, runner["length"]
    per_period = {"day": 1, "week": 5, "month": 21}[runner.get("period", "day")]
    start = max(0, entry_index - (n + 2) * per_period - 5)
    end = min(limit - 1, entry_index + max_hold)
    weekly = runner["kind"] == "period_sma"
    # Running sums of closes (daily rule) or the closes of completed periods (weekly rule) from `start`, built as the trade advances.
    prefix, period_close, built = [0.0], [], start

    def extend(upto):
        nonlocal built
        while built <= upto:
            c = float(closes[built])
            if weekly:
                if built + 1 <= min(limit - 1, end + 1) and period_key(date[built], runner["period"]) != period_key(date[built + 1], runner["period"]):
                    period_close.append((built, c))
            else:
                prefix.append(prefix[-1] + c)
            built += 1

    remaining, gross, fills, target_open, target_hit = 1.0, 0.0, [], fraction, False
    exit_next_open = False

    def fill(price, part, reason, day):
        nonlocal remaining, gross
        gross += part * (price / entry - 1)
        remaining = round(remaining - part, 10)
        fills.append({"date": day, "price": round(price, 6), "fraction": round(part, 6), "reason": reason})

    for held in range(1, max_hold + 1):
        i = entry_index + held - 1
        if i >= limit:
            return {"status": "observing", "entry": entry, "stop": risk_stop, "held": held - 1}
        o, h, l, c = float(opens[i]), float(highs[i]), float(lows[i]), float(closes[i])
        if exit_next_open:
            fill(o, remaining, "trend_exit", date[i])
            break
        if o <= stop and not (entry_price is not None and held == 1):
            fill(o, remaining, "stop_gap", date[i])
            break
        if l <= stop:
            fill(stop, remaining, "stop", date[i])
            break
        if target_open and (o >= target or h >= target):
            fill(target, min(target_open, remaining), "target", date[i])
            target_open, target_hit = 0, True
            stop = max(stop, entry)
        if remaining <= 1e-9:
            break
        if held == max_hold:
            fill(c, remaining, "time", date[i])
            break
        if target_hit and i <= end:
            extend(i)
            if weekly:
                if period_close and period_close[-1][0] == i and len(period_close) >= n:
                    exit_next_open = c < sum(x for _, x in period_close[-n:]) / n
            else:
                k = i - start
                exit_next_open = k + 1 >= n and c < (prefix[k + 1] - prefix[k + 1 - n]) / n
    net = gross - 2 * cost_per_side
    return {"status": "resolved", "entry_date": date[entry_index], "entry": round(entry, 6), "stop": round(risk_stop, 6), "risk_pct": round(risk / entry, 8),
            "gross_return": round(gross, 8), "net_return": round(net, 8), "r_multiple": round(net / (risk / entry), 6),
            "held": held, "exit_reason": fills[-1]["reason"], "fills": fills}


def candidate(series, limit, entry_index, result, event_id, symbol, signal_date, priority, data_end):
    """account.candidate on plain columns cut at `limit` sessions."""
    last = entry_index + result["held"] - 1
    fills = [(f["date"], f["price"], f["fraction"]) for f in result.get("fills", [])]
    data_ended = result["status"] == "observing" and series["date"][limit - 1] < data_end
    if data_ended:
        fills = [(series["date"][last], float(series["close"][last]), 1.0)]
    return {"event_id": event_id, "symbol": symbol, "signal_date": signal_date, "priority": priority, "entry_date": series["date"][entry_index],
            "entry_price": float(result["entry"]), "stop": float(result["stop"]), "fills": fills, "data_ended": data_ended,
            "closes": list(zip(series["date"][entry_index:last + 1], map(float, series["close"][entry_index:last + 1])))}


def trade(series, limit, entry_index, kind, stop, target, p, cost, entry_price=None):
    return simulate(series, limit, entry_index, stop, target, p["exit"]["first_fraction"], p["kinds"][kind]["runner"], p["exit"]["max_sessions"], cost,
                    entry_price)


def random_trade(series, card, atr_multiple, p, cost, limit, atr, symbol):
    """A random stock bought at its open on the signal's fill day with the signal's shape; None when it cannot be traded."""
    i = bisect.bisect_left(series["date"], card["fill_date"])
    if i < 1 or i >= limit or series["date"][i] != card["fill_date"]:
        return None
    w_atr = atr.at(symbol, i - 1)
    entry = float(series["open"][i])
    if not w_atr or entry <= 0:
        return None
    stop = entry - atr_multiple * w_atr
    if stop <= 0 or (entry - stop) / entry > p["risk"]["max_stop"]:
        return None
    result = trade(series, limit, i, card["kind"], stop, entry + card["rr"] * (entry - stop), p, cost)
    if result["status"] not in ("resolved", "observing"):
        return None
    return i, result, (entry - stop) / entry


def relative_strength(prices, spy, lookback=126):
    """The stock's six-month return minus SPY's at the decision day (O'Neil, Minervini); higher ranks first."""
    spy_index = {d: i for i, d in enumerate(spy["date"])}

    def rs(card):
        s = prices[card["symbol"]]
        i = bisect.bisect_left(s["date"], card["decision_date"])
        j = spy_index.get(card["decision_date"])
        if i < lookback or j is None or j < lookback:
            return 0.0
        return s["close"][i] / s["close"][i - lookback] - spy["close"][j] / spy["close"][j - lookback]
    return rs


def market_filter_days(spy, length=200):
    """Days with SPY's close above its 200-day average (Faber; the E7b market check)."""
    ok, closes = set(), spy["close"]
    for i in range(length - 1, len(closes)):
        if closes[i] > sum(closes[i - length + 1:i + 1]) / length:
            ok.add(spy["date"][i])
    return ok


def evaluate(signals, prices, p, spec, window, spy, atr, scenario, cost, flagged, rank=None, market_ok=None):
    """One rule on one window: its account and trades, against random accounts and same-day random trades. Returns (summary, rows)."""
    start, end = window
    rules, initial, runs, seed = spec["account"], scenario["initial_cash"], spec["random"]["runs"], spec["random"]["seed"]
    dates = [d for d in spy["date"] if start <= d <= end]
    spy_rets = account.benchmark_returns(spy, dates)
    spy_stats = account.curve_stats(account.compound(spy_rets, initial), dates, initial)
    pool_rules = {**spec["pool"], "exclude": flagged}
    taken, skipped = [], Counter()
    for card in signals:
        if not start <= card["fill_date"] <= end:
            continue
        if market_ok is not None and card["decision_date"] not in market_ok:
            skipped["market_filter"] += 1
            continue
        taken.append(card)
    limits = {}

    def limit_of(symbol):
        if symbol not in limits:
            limits[symbol] = bisect.bisect_right(prices[symbol]["date"], end)
        return limits[symbol]

    sv_cands, rows = [], []
    for n, card in enumerate(taken):
        s, symbol = prices[card["symbol"]], card["symbol"]
        i = bisect.bisect_left(s["date"], card["fill_date"])
        # a card may carry its own priority (the weekly triangle: nested first, then more confluence) and a buy-stop entry price
        priority = card["priority"] if "priority" in card else (0 if card["kind"] == "month" else 1, -round(rank(card), 6) if rank else 0.0)
        result = trade(s, limit_of(symbol), i, card["kind"], card["stop"], card["target"], p, cost,
                       card["entry"] if card.get("entry_at") == "stop_order" else None)
        if result["status"] in ("resolved", "observing"):
            sv_cands.append(candidate(s, limit_of(symbol), i, result, f"sv-{n:05d}", symbol, card["decision_date"], priority, end))
        w_atr = atr.at(symbol, i - 1)
        rows.append({"symbol": symbol, "kind": card["kind"], "decision_date": card["decision_date"], "fill_date": card["fill_date"],
                     "entry": card["entry"], "stop": card["stop"], "target": card["target"], "rr": card["rr"], "priority": priority,
                     "risk": (card["entry"] - card["stop"]) / card["entry"], "atr_multiple": (card["entry"] - card["stop"]) / w_atr if w_atr else None,
                     "net": result.get("net_return"), "exit": result.get("exit_reason"), "held": result.get("held")})
    sv_path = account.run_account(account.align(sv_cands, dates)[0], len(dates), scenario, rules=rules)
    sv = account.curve_stats(sv_path["equity"], dates, initial) | {"trades_taken": len(sv_path["trades"]), "open_at_end": sv_path["open_at_end"],
                                                                   "average_exposure": round(statistics.fmean(sv_path["exposure"]), 4), "skipped": sv_path["skipped"]}
    matched = account.compound([0.0] + [x * r for x, r in zip(sv_path["exposure"], spy_rets[1:])], initial)
    pools, outcome, accounts, sums, counts, rnd_pool, unmatched = {}, {}, [], [0.0] * len(rows), [0] * len(rows), [], 0
    for k in range(runs):
        rng = random.Random(seed + k)
        cands = []
        for j, row in enumerate(rows):
            if row["atr_multiple"] is None:
                continue
            day = row["decision_date"]
            if day not in pools:
                pools[day] = sorted(selection.eligible_pool(prices, day, pool_rules))
            got = None
            for _ in range(spec["random"]["max_draws"] if pools[day] else 0):
                symbol = rng.choice(pools[day])
                key = (symbol, j)
                if key not in outcome:
                    outcome[key] = random_trade(prices[symbol], {"fill_date": row["fill_date"], "kind": row["kind"], "rr": row["rr"]},
                                                row["atr_multiple"], p, cost, limit_of(symbol), atr, symbol)
                if outcome[key] is not None:
                    got = symbol
                    break
            if got is None:
                unmatched += 1
                continue
            i, res, risk = outcome[(got, j)]
            cands.append(candidate(prices[got], limit_of(got), i, res, f"r{k:03d}-{j:05d}", got, day, row["priority"], end))
            if res.get("net_return") is not None:
                sums[j] += res["net_return"]
                counts[j] += 1
                rnd_pool.append((res["net_return"], risk))
        st = account.curve_stats(account.run_account(account.align(cands, dates)[0], len(dates), scenario, rules=rules)["equity"], dates, initial)
        accounts.append({"sharpe": st["sharpe"], "cagr": st["cagr"], "max_drawdown": st["max_drawdown"]})
    for j, row in enumerate(rows):
        row["random_net"] = sums[j] / counts[j] if counts[j] else None
    paired = [(row, row["net"], row["random_net"]) for row in rows if row["net"] is not None and row["random_net"] is not None]
    trades = timeframe.compare([a - b for _, a, b in paired], [r["decision_date"][:7] for r, _, _ in paired], [a for _, a, _ in paired], [b for _, _, b in paired])
    beats = round(sum((sv["sharpe"] or -9) > (a["sharpe"] or -9) for a in accounts) / len(accounts), 4) if accounts else None
    summary = {"window": {"start": dates[0], "end": dates[-1], "sessions": len(dates)}, "signals": len(taken), "skipped": dict(skipped),
               "by_kind": dict(sorted(Counter(r["kind"] for r in rows).items())), "sv": sv, "spy": spy_stats,
               "same_exposure_spy": account.curve_stats(matched, dates, initial),
               "random": {"runs": runs, "unmatched": unmatched, "sharpe": account.distribution([a["sharpe"] for a in accounts]),
                          "cagr": account.distribution([a["cagr"] for a in accounts]), "max_drawdown": account.distribution([a["max_drawdown"] for a in accounts]),
                          "sv_beats_share_sharpe": beats},
               "trade_level": trades,
               "win_loss": {"sv": levels.win_loss([(r["net"], r["risk"]) for r in rows if r["net"] is not None]), "random": levels.win_loss(rnd_pool)},
               "exit_reasons": dict(sorted(Counter(r["exit"] for r in rows if r["exit"]).items())),
               "held_median_sessions": {kind: statistics.median(v) for kind in ("month", "week")
                                        if (v := [r["held"] for r in rows if r["kind"] == kind and r["held"] and r["net"] is not None])},
               "goal_1": {"sharpe_vs_spy": round((sv["sharpe"] or 0) - (spy_stats["sharpe"] or 0), 4),
                          "met": (sv["sharpe"] or -9) >= (spy_stats["sharpe"] or 9) and (sv["calmar"] or -9) >= (spy_stats["calmar"] or 9)
                                 and sv["max_drawdown"] <= 0.25}}
    return summary, rows


def adopt(base, variant, sel):
    """The pre-registered adoption rule on the training window."""
    if variant["sv"]["trades_taken"] < sel["min_trades"]:
        return False
    sharpe_gain = (variant["sv"]["sharpe"] or -9) - (base["sv"]["sharpe"] or -9)
    beat_gain = (variant["random"]["sv_beats_share_sharpe"] or 0) - (base["random"]["sv_beats_share_sharpe"] or 0)
    return sharpe_gain >= sel["sharpe_gain"] - 1e-9 and beat_gain >= sel["beat_share_gain"] - 1e-9


def verdict(test, crit):
    trades = test["trade_level"]
    checks = {"beats_random_accounts": (test["random"]["sv_beats_share_sharpe"] or 0) >= crit["min_random_share"],
              "trades_beat_random_same_day": trades.get("t_monthly", 0) >= crit["min_trade_excess_t"] and trades.get("median_difference", -1) > 0
                                             and trades.get("difference_winsorized", -1) > 0,
              "enough_signals": test["signals"] >= crit["min_test_signals"]}
    return checks, all(checks.values())


def run(spec, data, dataset_entry, cost, benchmark, workers=None):
    prices = data["prices"]
    scenario = account.approved_scenario()
    flagged = selection.impossible_jumps(prices)
    spy = benchmark["series"]
    atr = WeeklyATR(prices)
    train, test = spec["windows"]["train"], spec["windows"]["test"]
    scans, all_rows = {}, []

    def signals_for(changes):
        key = tuple(sorted(engine_changes(changes).items()))
        if key not in scans:
            scans[key] = scan_universe(prices, override(B.PARAMS, dict(key)), train[0], test[1], spec["pool"], flagged, workers)
        return scans[key]

    def judge(name, changes, window, label):
        p = override(B.PARAMS, engine_changes(changes))
        rank = relative_strength(prices, spy) if changes.get("account.rank") == "rs_6m" else None
        market_ok = market_filter_days(spy) if changes.get("account.market_filter") else None
        summary, rows = evaluate(signals_for(changes), prices, p, spec, window, spy, atr, scenario, cost, flagged, rank, market_ok)
        all_rows.extend({"arm": name, "window": label, **r} for r in rows)
        return summary

    for name, changes in spec["variants"].items():
        override(B.PARAMS, engine_changes(changes))  # an unknown parameter stops the run before any work
    arms = {"baseline": judge("baseline", {}, train, "train") | {"changes": {}}}
    for name, changes in spec["variants"].items():
        arms[name] = judge(name, changes, train, "train") | {"changes": changes}
    adopted = [name for name in spec["variants"] if adopt(arms["baseline"], arms[name], spec["selection"])]
    final_changes = {k: v for name in adopted for k, v in spec["variants"][name].items()}
    test_result = judge("final", final_changes, test, "test")
    checks, passed = verdict(test_result, spec["criteria"])
    result = {"kind": "buysystem_train", "spec_id": spec["id"], "experiment_id": spec["experiment_id"], "group": spec["group"], "question": spec["question"],
              "dataset": {k: dataset_entry[k] for k in ("dataset_id", "asset", "sha256", "symbols")},
              "benchmark": {"symbol": benchmark["symbol"], **{k: benchmark["entry"][k] for k in ("dataset_id", "asset", "sha256")}},
              "engine": {"params": B.PARAMS, "document": "docs/BUY_SYSTEM_ZH.md 0.2.0"},
              "windows": spec["windows"], "pool": spec["pool"], "account_rules": spec["account"], "cost_per_side": cost, "excluded_symbols": sorted(flagged),
              "selection": spec["selection"], "criteria": spec["criteria"], "train": arms, "adopted": adopted, "final_changes": final_changes,
              "test": test_result | {"checks": checks, "passed": passed}, "passed": passed, "champion": "final" if passed else None,
              "next_step": spec.get("next_step")}
    return result, all_rows


def render(result):
    pct = lambda x, d=1: "—" if x is None else f"{x * 100:.{d}f}%"
    num = lambda x: "—" if x is None else f"{x:.2f}"
    tr, te = result["windows"]["train"], result["windows"]["test"]
    lines = [f"# {result['spec_id']}", "", f"Plain-language report written by the research lab on {(result.get('completed_at') or '—')[:10]}. "
             "Every number comes from `result.json` in this folder.", "", "## The question", "", result["question"], "",
             f"## Training window ({tr[0]} to {tr[1]})", "",
             "| Rule | Changes | Signals | Trades | Sharpe | CAGR | Max DD | Beats random accounts | Excess vs random (t) | Win rate | Payoff | Adopted |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, arm in result["train"].items():
        wl, tl = arm["win_loss"]["sv"], arm["trade_level"]
        changes = ", ".join(f"{k}={v}" for k, v in arm.get("changes", {}).items()) or "—"
        lines.append(f"| {name} | {changes} | {arm['signals']} | {arm['sv']['trades_taken']} | {num(arm['sv']['sharpe'])} | {pct(arm['sv']['cagr'])} | "
                     f"{pct(arm['sv']['max_drawdown'])} | {pct(arm['random']['sv_beats_share_sharpe'])} | {pct(tl.get('difference_winsorized'), 2)} "
                     f"({num(tl.get('t_monthly'))}) | {pct(wl.get('win_rate'))} | {num(wl.get('payoff_ratio'))} | "
                     f"{'—' if name == 'baseline' else ('yes' if name in result['adopted'] else 'no')} |")
    t = result["test"]
    lines += ["", f"Adopted: {', '.join(result['adopted']) or 'none, so the baseline goes to the test'}.", "",
              f"## Test window ({te[0]} to {te[1]}), run once", "",
              f"- Signals {t['signals']} {t['by_kind']}; trades taken {t['sv']['trades_taken']}; Sharpe {num(t['sv']['sharpe'])}, "
              f"CAGR {pct(t['sv']['cagr'])}, max drawdown {pct(t['sv']['max_drawdown'])}, average exposure {pct(t['sv']['average_exposure'])}.",
              f"- Beats {pct(t['random']['sv_beats_share_sharpe'])} of {t['random']['runs']} random accounts (random Sharpe median "
              f"{num((t['random']['sharpe'] or {}).get('median'))}); trade excess vs same-day random {pct(t['trade_level'].get('difference_winsorized'), 2)} "
              f"(t {num(t['trade_level'].get('t_monthly'))}, median {pct(t['trade_level'].get('median_difference'), 2)}).",
              f"- SPY: Sharpe {num(t['spy']['sharpe'])}, CAGR {pct(t['spy']['cagr'])}; SPY at the account's exposure: Sharpe "
              f"{num(t['same_exposure_spy']['sharpe'])}, CAGR {pct(t['same_exposure_spy']['cagr'])}.",
              f"- Win rate {pct(t['win_loss']['sv'].get('win_rate'))}, payoff {num(t['win_loss']['sv'].get('payoff_ratio'))}, expectancy "
              f"{num(t['win_loss']['sv'].get('expectancy_r'))}R; random: {pct(t['win_loss']['random'].get('win_rate'))}, "
              f"{num(t['win_loss']['random'].get('payoff_ratio'))}, {num(t['win_loss']['random'].get('expectancy_r'))}R.",
              f"- Exits: {t['exit_reasons']}.",
              "", "| Check | Passed |", "|---|---|", *[f"| {k} | {'yes' if v else 'no'} |" for k, v in t["checks"].items()],
              "", f"**Passed: {'yes' if t['passed'] else 'no'}.**"]
    if result.get("next_step"):
        lines += ["", "## Next step", "", result["next_step"]]
    return "\n".join(lines) + "\n"
