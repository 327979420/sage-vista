"""Trade SV's opportunities by their own level under the user's rules (E7b), against random picks under the same rules.

The rules follow docs/rules/09_RISK_AND_EXECUTION.md and the user's choices of
2026-10-10 (recorded with the E7b pre-registration in docs/rules/08):

- Entry at the open after the signal close. If that open is at or below the
  stop, wait up to `reclaim_sessions` sessions for a close back above the stop
  and buy at the next open, provided it is above the stop; otherwise skip.
- Stop: `buffer` below the value-area low of the daily volume profile of the
  `value_area.lookback` sessions up to the signal day, frozen at the signal.
  No value area below the signal close means no support: skip. A stop more
  than `max_stop_distance` below the actual entry: skip. Every trade risks the
  same share of the account, so a wider stop means a smaller position.
- Hard rejections from the case ledger (a deep fall without a base, a wide
  box) apply to SV and random picks alike. Supply flags are labels only.
- Holding by level, with no profit target: a daily opportunity at most 20
  sessions; a weekly one at least 15 and at most 60; a monthly one at least
  three and at most five full monthly bars after the entry month. Within the
  minimum only the stop can sell. Families add the BTDR no-progress exit or
  the published trend-ending exits of mature systems.
- Random picks: the same signal day, from SV's tradable pool that day, traded
  under every rule above with the same level; a pick the rules would skip
  (rejected, no support, stop too far, opened below the stop) is redrawn from
  the same day's pool, so only the choice of stock differs.

The run also reports what each rule removes (skip reasons), the hard checks'
value (the same rules with the checks off), a second stop definition, splits
by level, market state, sector and supply flag (leads only), and each five-year
period against SPY.
"""
from __future__ import annotations

import bisect
import random
import statistics
from collections import Counter, defaultdict

from research.lab import account, datasets, selection, structure, timeframe
from research.lab.exit_rules import simulate

LEVEL = timeframe.LEVEL
PERIODS = [("2005-2009", "2005-01-01", "2009-12-31"), ("2010-2014", "2010-01-01", "2014-12-31"), ("2015-2019", "2015-01-01", "2019-12-31"),
           ("2020-2024", "2020-01-01", "2024-12-31"), ("2025-2026", "2025-01-01", "2026-12-31")]


def plan(series, day, rules, vetoes=True):
    """Entry, stop and checks for one stock on one signal day under `rules`, or {"skip": reason}."""
    dates = series["date"]
    i = bisect.bisect_left(dates, day)
    if i >= len(dates) or dates[i] != day:
        return {"skip": "no_signal_bar"}
    if i + 1 >= len(dates):
        return {"skip": "no_entry_bar"}
    if vetoes:
        reason = structure.rejection(series, i, rules["structure"])
        if reason:
            return {"skip": f"veto_{reason}"}
    va = structure.value_area(series, i, **rules["value_area"])
    if not va["available"]:
        return {"skip": "no_volume_profile"}
    if series["close"][i] <= va["val"]:
        return {"skip": "no_support"}
    stop = va["val"] * (1 - rules["buffer"])
    entry_index = i + 1
    if series["open"][entry_index] <= stop:
        entry_index = None
        for k in range(i + 1, min(i + 1 + rules["reclaim_sessions"], len(dates) - 1)):
            if series["close"][k] > stop:
                entry_index = k + 1 if series["open"][k + 1] > stop else None
                break
        if entry_index is None:
            return {"skip": "opened_below_stop"}
    entry = series["open"][entry_index]
    distance = 1 - stop / entry
    if distance > rules["max_stop_distance"]:
        return {"skip": "stop_too_wide"}
    return {"entry_index": entry_index, "stop": stop, "distance": distance, "waited": entry_index - i - 1}


def variant(level, family, hold, stop):
    """The exit rule for one trade: the level's holding window plus the family's extra exits."""
    rule = {"stop": {"kind": "level", "price": stop}, "targets": [], **hold[level]}
    if family.get("uncapped"):
        rule.pop("max_periods", None)
        rule["max_hold"] = family["uncapped"]["max_hold"]
    extra = (family.get("exits") or {}).get(level) or {}
    if extra.get("trend"):
        rule["trend_exit"] = {**extra["trend"], "arm": True}
    if extra.get("no_progress"):
        rule["no_progress"] = extra["no_progress"]
    return rule


def trade(symbol, series, signal_date, p, level, family, hold, cost, data_end, priority, event_id):
    """(account candidate, net return, exit reason, sessions held) for one planned trade, or Nones."""
    bars = datasets.BarsView(series)
    result = simulate(bars, p["entry_index"], variant(level, family, hold, p["stop"]), cost_per_side=cost)
    if result["status"] not in ("resolved", "observing"):
        return None, None, None, None
    c = account.candidate({"event_id": event_id, "symbol": symbol, "signal_date": signal_date}, bars, p["entry_index"], result, priority, data_end)
    return c, result.get("net_return"), result.get("exit_reason"), result.get("held")


def random_picks(events, prices, pool_rules, runs, seed, rules, vetoes, cache, max_draws):
    """runs x events random stocks that the same rules would trade on SV's signal day; None when none is found."""
    pools, out = {}, []
    for k in range(runs):
        rng = random.Random(seed + k)
        picks = []
        for e in events:
            day = e["signal_date"]
            if day not in pools:
                pools[day] = selection.eligible_pool(prices, day, pool_rules)
            chosen = None
            for _ in range(max_draws if pools[day] else 0):
                symbol = rng.choice(pools[day])
                if (symbol, day) not in cache:
                    cache[(symbol, day)] = plan(prices[symbol], day, rules, vetoes)
                if "skip" not in cache[(symbol, day)]:
                    chosen = symbol
                    break
            picks.append(chosen)
        out.append(picks)
    return out


def win_loss(trades):
    """Win rate, average win and loss, payoff ratio, profit factor and expectancy in R from (net return, stop distance) pairs."""
    if not trades:
        return {"trades": 0}
    wins = [n for n, _ in trades if n > 0]
    losses = [n for n, _ in trades if n <= 0]
    avg_win = statistics.fmean(wins) if wins else None
    avg_loss = statistics.fmean(losses) if losses else None
    lost = -sum(losses)
    rs = [n / d for n, d in trades if d > 0]
    return {"trades": len(trades), "win_rate": round(len(wins) / len(trades), 4), "average_win": round(avg_win, 6) if avg_win is not None else None,
            "average_loss": round(avg_loss, 6) if avg_loss is not None else None,
            "payoff_ratio": round(avg_win / -avg_loss, 3) if avg_win is not None and avg_loss else None,
            "profit_factor": round(sum(wins) / lost, 3) if lost > 0 else None, "expectancy_r": round(statistics.fmean(rs), 4) if rs else None}


def period_stats(equity, dates, initial, spy_equity):
    """Each five-year period: the account and SPY bought and held over the same sessions."""
    out = {}
    for name, start, end in PERIODS:
        idx = [i for i, d in enumerate(dates) if start <= d <= end]
        if len(idx) < 60:
            continue
        a, b = idx[0], idx[-1]
        base, spy_base = (equity[a - 1], spy_equity[a - 1]) if a else (initial, initial)
        sv = account.curve_stats(equity[a:b + 1], dates[a:b + 1], base)
        spy = account.curve_stats(spy_equity[a:b + 1], dates[a:b + 1], spy_base)
        out[name] = {"sv_sharpe": sv["sharpe"], "sv_return": sv["total_return"], "sv_max_drawdown": sv["max_drawdown"],
                     "spy_sharpe": spy["sharpe"], "spy_return": spy["total_return"], "spy_max_drawdown": spy["max_drawdown"],
                     "sv_sharpe_above_spy": (sv["sharpe"] or -9) > (spy["sharpe"] or -9)}
    return out


def _rules(spec, override=None):
    rules = {**spec["rules"], "structure": {**structure.PARAMS, **spec["rules"].get("structure", {})}}
    for key, value in (override or {}).items():
        rules[key] = {**rules[key], **value} if isinstance(value, dict) else value
    return rules


def run(spec, data, dataset_entry, cost, benchmark, root, signal_priority):
    """Every pre-registered family, and each extra check, against random accounts and same-day random trades."""
    scenario = account.approved_scenario()
    acct, initial, criteria, hold = spec["account"], scenario["initial_cash"], spec["criteria"], spec["hold"]
    prices = data["prices"]
    flagged = selection.impossible_jumps(prices)
    pool_rules = {**spec["pool"], "exclude": flagged}
    events = sorted((e for e in data["events"] if e["symbol"] not in flagged and e.get("timeframe") in LEVEL), key=lambda e: (e["signal_date"], e["event_id"]))
    series = benchmark["series"]
    dates = [d for d in series["date"] if spec["window"]["start"] <= d <= spec["window"]["end"]]
    spy_equity = account.compound(account.benchmark_returns(series, dates), initial)
    spy = account.curve_stats(spy_equity, dates, initial)
    data_end = max(s["date"][-1] for s in prices.values())
    markets = timeframe.market_labels(series, sorted({e["signal_date"] for e in events}))
    sectors = timeframe.sector_labels(root)
    # Faber's market filter, judged on the completed signal-day close.
    market_ok = {day for day, (trend, _) in markets.items() if trend == "SPY above 200-day"}
    base_rules = _rules(spec)
    supply, run_up = {}, {}
    for e in events:
        s = prices[e["symbol"]]
        i = bisect.bisect_left(s["date"], e["signal_date"])
        if i < len(s["date"]) and s["date"][i] == e["signal_date"]:
            supply[e["event_id"]] = structure.assess(s, i, base_rules["structure"])["flags"]
            # How far the signal close already sits above the last ten sessions' low: is the signal late?
            run_up[e["event_id"]] = s["close"][i] / min(s["low"][max(0, i - 9):i + 1]) - 1
    labels = {"timeframe": lambda e: LEVEL[e["timeframe"]], "market_trend": lambda e: markets[e["signal_date"]][0],
              "market_volatility": lambda e: markets[e["signal_date"]][1], "sector": lambda e: sectors.get(e["symbol"], "unknown"),
              "supply_flag": lambda e: "flagged" if supply.get(e["event_id"]) else "not flagged",
              # The fixed score groups of the 08 rules (E5a found higher scores did worse under the old rule).
              "run_up_10d": lambda e: "unknown" if e["event_id"] not in run_up else "<3%" if run_up[e["event_id"]] < 0.03 else "3-6%" if run_up[e["event_id"]] < 0.06
                                       else "6-10%" if run_up[e["event_id"]] < 0.10 else ">=10%",
              "score_group": lambda e: "<30" if e.get("score", 0) < 30 else "30-45" if e["score"] < 45 else "45-60" if e["score"] < 60 else ">=60"}
    arms = [{"id": "main", "families": list(spec["families"]), "rules": base_rules, "vetoes": True, "account": acct, "market_filter": False}]
    for check in spec.get("extra_checks", []):
        arms.append({"id": check["id"], "families": [check["family"]], "rules": _rules(spec, check.get("rules")), "vetoes": check.get("vetoes", True),
                     "account": {**acct, **check.get("account", {})}, "market_filter": check.get("market_filter", False)})
    out_arms = {}
    for arm in arms:
        rules = arm["rules"]
        plans, skipped = {}, defaultdict(Counter)
        for e in events:
            if arm["market_filter"] and e["signal_date"] not in market_ok:
                skipped[LEVEL[e["timeframe"]]]["market_filter"] += 1
                continue
            p = plan(prices[e["symbol"]], e["signal_date"], rules, arm["vetoes"])
            if "skip" in p:
                skipped[LEVEL[e["timeframe"]]][p["skip"]] += 1
            else:
                plans[e["event_id"]] = p
                skipped[LEVEL[e["timeframe"]]]["traded"] += 1
        taken = [e for e in events if e["event_id"] in plans]
        runs = max(spec["runs"][f] for f in arm["families"])
        cache = {}
        picks = random_picks(taken, prices, pool_rules, runs, spec["seed"], rules, arm["vetoes"], cache, spec.get("max_draws", 30))
        distances = [plans[e["event_id"]]["distance"] for e in taken]
        families = {}
        for name in arm["families"]:
            family = spec["families"][name]
            sv_cands, sv_net, sv_exit, sv_held = [], [], [], defaultdict(list)
            for e in taken:
                lv = LEVEL[e["timeframe"]]
                c, net, why, held = trade(e["symbol"], prices[e["symbol"]], e["signal_date"], plans[e["event_id"]], lv, family, hold, cost, data_end,
                                          signal_priority(e), e["event_id"])
                sv_net.append(net)
                sv_exit.append(why)
                if c:
                    sv_cands.append(c)
                if held:
                    sv_held[lv].append(held)
            sv_path = account.run_account(account.align(sv_cands, dates)[0], len(dates), scenario, rules=arm["account"])
            sv = account.curve_stats(sv_path["equity"], dates, initial) | {"trades_taken": len(sv_path["trades"]),
                                                                           "average_exposure": round(statistics.fmean(sv_path["exposure"]), 4)}
            matched = account.compound([0.0] + [x * r for x, r in zip(sv_path["exposure"], account.benchmark_returns(series, dates)[1:])], initial)
            outcomes, sums, counts, accounts, rnd_pool = {}, [0.0] * len(taken), [0] * len(taken), [], []
            for k in range(spec["runs"][name]):
                cands = []
                for j, (symbol, e) in enumerate(zip(picks[k], taken)):
                    if not symbol:
                        continue
                    key = (symbol, e["signal_date"], e["timeframe"])
                    if key not in outcomes:
                        outcomes[key] = trade(symbol, prices[symbol], e["signal_date"], cache[(symbol, e["signal_date"])], LEVEL[e["timeframe"]], family, hold,
                                              cost, data_end, signal_priority(e), f"{e['event_id']}~{symbol}")
                    c, net, _, _ = outcomes[key]
                    if c:
                        cands.append({**c, "event_id": f"{e['event_id']}~{k}"})
                    if net is not None:
                        sums[j] += net
                        counts[j] += 1
                        rnd_pool.append((net, cache[(symbol, e["signal_date"])]["distance"]))
                st = account.curve_stats(account.run_account(account.align(cands, dates)[0], len(dates), scenario, rules=arm["account"])["equity"], dates, initial)
                accounts.append({"sharpe": st["sharpe"], "cagr": st["cagr"], "max_drawdown": st["max_drawdown"]})
            rows = [(e, sv_net[j], sums[j] / counts[j]) for j, e in enumerate(taken) if sv_net[j] is not None and counts[j]]

            def summary(subset):
                return timeframe.compare([a - b for _, a, b in subset], [e["signal_date"][:7] for e, _, _ in subset],
                                         [a for _, a, _ in subset], [b for _, _, b in subset])
            segments = {}
            if arm["id"] == "main":
                for seg, fn in labels.items():
                    groups = defaultdict(list)
                    for row in rows:
                        groups[fn(row[0])].append(row)
                    segments[seg] = {label: summary(group) for label, group in sorted(groups.items())}
            beats = round(sum((sv["sharpe"] or -9) > (a["sharpe"] or -9) for a in accounts) / len(accounts), 4)
            trades = summary(rows)
            checks = {"beats_random_accounts": beats >= criteria["min_random_percentile"],
                      "trades_beat_random_same_day": trades.get("t_monthly", 0) >= criteria["min_trade_excess_t"]
                                                     and trades.get("median_difference", -1) > 0 and trades.get("difference_winsorized", -1) > 0}
            periods = period_stats(sv_path["equity"], dates, initial, spy_equity)
            families[name] = {
                "rule": family, "sv": sv, "same_exposure_spy": account.curve_stats(matched, dates, initial),
                "random": {"runs": spec["runs"][name], "sharpe": account.distribution([a["sharpe"] for a in accounts]),
                           "cagr": account.distribution([a["cagr"] for a in accounts]),
                           "max_drawdown": account.distribution([a["max_drawdown"] for a in accounts]), "sv_beats_share_sharpe": beats},
                "trade_level": trades, "win_loss": {"sv": win_loss([(n, plans[e["event_id"]]["distance"]) for n, e in zip(sv_net, taken) if n is not None]),
                                                    "random": win_loss(rnd_pool)},
                "segments": segments, "sv_exit_reasons": dict(Counter(w for w in sv_exit if w)),
                "held_median_sessions": {lv: statistics.median(v) for lv, v in sv_held.items() if v},
                "goal_1": {"sharpe_vs_spy": round((sv["sharpe"] or 0) - (spy["sharpe"] or 0), 4), "calmar_vs_spy": round((sv["calmar"] or 0) - (spy["calmar"] or 0), 4),
                           "met": (sv["sharpe"] or -9) >= (spy["sharpe"] or 9) and (sv["calmar"] or -9) >= (spy["calmar"] or 9) and sv["max_drawdown"] <= 0.25},
                "periods": periods, "goal_2_some_period_beats_spy": any(v["sv_sharpe_above_spy"] for v in periods.values()),
                "leads": [{"segment": seg, "label": lab, **vals} for seg, groups in segments.items() for lab, vals in groups.items()
                          if vals.get("signals", 0) >= criteria["min_lead_signals"] and vals.get("t_monthly", 0) >= criteria["lead_t"]],
                "verdict": {"checks": checks, "passed": all(checks.values())}}
        out_arms[arm["id"]] = {"vetoes": arm["vetoes"], "account": arm["account"], "market_filter": arm["market_filter"], "rules": {k: v for k, v in rules.items() if k != "structure"} | {"structure": rules["structure"] if arm["vetoes"] else None},
                               "skipped_by_level": {lv: dict(c) for lv, c in skipped.items()}, "traded": len(taken),
                               "random_unmatched": sum(1 for run in picks for x in run if x is None),
                               "stop_distance": {"p10": round(statistics.quantiles(distances, n=10)[0], 4), "median": round(statistics.median(distances), 4),
                                                 "p90": round(statistics.quantiles(distances, n=10)[-1], 4)} if len(distances) > 1 else None,
                               "waited_for_reclaim": sum(1 for e in taken if plans[e["event_id"]]["waited"]), "families": families}
    main = out_arms["main"]["families"]
    passed = [n for n, f in main.items() if f["verdict"]["passed"]]
    champion = max(passed, key=lambda n: (round(main[n]["sv"]["sharpe"] or -9, 2), -main[n]["sv"]["max_drawdown"])) if passed else None
    if champion:
        close = [n for n in passed if (main[champion]["sv"]["sharpe"] or 0) - (main[n]["sv"]["sharpe"] or 0) <= criteria.get("tie_sharpe", 0.01)]
        champion = min(close, key=lambda n: main[n]["sv"]["max_drawdown"])
    # One pre-registered choice across everything that passed (families and extra checks): evidence, not preference, picks the rule.
    passing = [(a, n) for a, arm in out_arms.items() for n, f in arm["families"].items() if f["verdict"]["passed"]]
    chosen = None
    if passing:
        best = max((out_arms[a]["families"][n]["sv"]["sharpe"] or -9) for a, n in passing)
        close = [(a, n) for a, n in passing if best - (out_arms[a]["families"][n]["sv"]["sharpe"] or -9) <= criteria.get("tie_sharpe", 0.01)]
        a, n = min(close, key=lambda x: out_arms[x[0]]["families"][x[1]]["sv"]["max_drawdown"])
        chosen = {"arm": a, "family": n, "sv": out_arms[a]["families"][n]["sv"]}
    vetoes_help = None
    off_check = next((c for c in spec.get("extra_checks", []) if c["id"] == "veto_off"), None)
    if off_check:
        on, off = main[off_check["family"]]["sv"], out_arms["veto_off"]["families"][off_check["family"]]["sv"]
        vetoes_help = {"sharpe_with": on["sharpe"], "sharpe_without": off["sharpe"], "calmar_with": on["calmar"], "calmar_without": off["calmar"],
                       "helps": (on["sharpe"] or -9) > (off["sharpe"] or -9) and (on["calmar"] or -9) > (off["calmar"] or -9)}
    return {"kind": "levels", "spec_id": spec["id"], "experiment_id": spec["experiment_id"], "group": spec["group"], "question": spec["question"],
            "dataset": {k: dataset_entry[k] for k in ("dataset_id", "asset", "sha256", "events", "symbols")},
            "benchmark": {"symbol": benchmark["symbol"], **{k: benchmark["entry"][k] for k in ("dataset_id", "asset", "sha256")}},
            "window": {"start": dates[0], "end": dates[-1], "sessions": len(dates)}, "cost_per_side": cost, "account_rules": acct, "hold": hold,
            "pool": dict(spec["pool"]), "excluded_symbols": sorted(flagged), "signals": len(events), "spy": spy,
            "supply_flagged_signals": sum(1 for v in supply.values() if v), "criteria": criteria, "arms": out_arms,
            "passed_families": passed, "extra_checks_passed": [a for a in out_arms if a != "main" and all(f["verdict"]["passed"] for f in out_arms[a]["families"].values())],
            "vetoes_help": vetoes_help, "champion": champion, "chosen": chosen, "next_step": spec.get("next_step")}


def run_cases(spec, data, dataset_entry):
    """The case-ledger acceptance check: does each seen case get the expected verdict (reject, flag or accept)?"""
    rules = _rules(spec)
    rows = []
    for case in spec["cases"]:
        s = data["prices"].get(case["symbol"])
        i = bisect.bisect_left(s["date"], case["signal_date"]) if s else 0
        if not s or i >= len(s["date"]) or s["date"][i] != case["signal_date"]:
            rows.append({**case, "available": False, "got": None, "passed": False})
            continue
        checks = structure.assess(s, i, rules["structure"])
        va = structure.value_area(s, i, **rules["value_area"])
        got = "reject" if checks["reject"] else "flag" if checks["supply_flag"] else "accept"
        passed = {"reject": got == "reject", "flag": got in ("flag", "reject"), "accept": got != "reject"}[case["expect"]]
        stop = va["val"] * (1 - rules["buffer"]) if va.get("available") else None
        rows.append({**case, "available": True, "got": got, "reason": checks["reject"], "flags": checks["flags"], "passed": passed,
                     "signal_close": s["close"][i], "value_area": va, "stop": round(stop, 4) if stop else None,
                     "stop_distance_from_close": round(1 - stop / s["close"][i], 4) if stop else None, "details": checks["details"]})
    return {"kind": "cases", "spec_id": spec["id"], "experiment_id": spec["experiment_id"], "group": spec["group"], "question": spec["question"],
            "dataset": {k: dataset_entry[k] for k in ("dataset_id", "asset", "sha256", "events", "symbols")}, "rules": {k: v for k, v in rules.items()},
            "cases": rows, "passed": all(r["passed"] for r in rows), "champion": None, "chosen": None, "next_step": spec.get("next_step")}


def _pct(x, d=1):
    return "—" if x is None else f"{x * 100:.{d}f}%"


def _num(x):
    return "—" if x is None else f"{x:.2f}"


def render(result):
    """Plain-language REPORT.md for a levels run."""
    main = result["arms"]["main"]
    lines = [f"# {result['spec_id']}", "", f"Plain-language report written by the research lab on {result.get('completed_at', '—')[:10]}. Every number comes from `result.json` in this folder.", "",
             "## The question", "", result["question"], "", "## The short answer", "",
             f"- Families that beat random picks under the pre-registered bar: {', '.join(result['passed_families']) or 'none'}.",
             f"- Extra checks that passed: {', '.join(result['extra_checks_passed']) or 'none'}.",
             f"- Champion (highest SV Sharpe among passing families): {result['champion'] or 'none'}.",
             f"- Rule chosen across every passing family and extra check: {(result['chosen'] or {}).get('arm', 'none')} {(result['chosen'] or {}).get('family', '')}.",
             f"- SPY bought and held over the same window: Sharpe {_num(result['spy']['sharpe'])}, CAGR {_pct(result['spy']['cagr'])}, worst fall {_pct(result['spy']['max_drawdown'])}, "
             f"Calmar {_num(result['spy']['calmar'])}.", ""]
    if result.get("vetoes_help"):
        v = result["vetoes_help"]
        lines += [f"- Hard checks (deep fall, wide box) on vs off, same family: Sharpe {_num(v['sharpe_with'])} vs {_num(v['sharpe_without'])}, "
                  f"Calmar {_num(v['calmar_with'])} vs {_num(v['calmar_without'])}; they help: **{'yes' if v['helps'] else 'no'}**.", ""]
    for arm_id, arm in result["arms"].items():
        lines += [f"## {arm_id}: account and trades against random picks", "",
                  f"Signals traded: {arm['traded']}; median stop distance {_pct((arm['stop_distance'] or {}).get('median'))}; "
                  f"bought after waiting for a reclaim: {arm['waited_for_reclaim']}.", "",
                  "| Family | SV Sharpe | SV CAGR | SV worst fall | Beats random accounts | Trade difference (winsorized) | t | Median difference | Goal 1 vs SPY | Some period beats SPY | Passed |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for name, f in arm["families"].items():
            tl = f["trade_level"]
            lines.append(f"| {name} | {_num(f['sv']['sharpe'])} | {_pct(f['sv']['cagr'])} | {_pct(f['sv']['max_drawdown'])} | {_pct(f['random']['sv_beats_share_sharpe'], 1)} | "
                         f"{_pct(tl.get('difference_winsorized'), 2)} | {_num(tl.get('t_monthly'))} | {_pct(tl.get('median_difference'), 2)} | "
                         f"{'yes' if f['goal_1']['met'] else 'no'} | {'yes' if f['goal_2_some_period_beats_spy'] else 'no'} | {'**yes**' if f['verdict']['passed'] else 'no'} |")
        lines += ["", "Win rate and reward against risk (SV trades vs all random trades; returns are per trade, before position size):", "",
                  "| Family | SV win rate | SV avg win | SV avg loss | SV payoff | SV profit factor | SV E[R] | Random win rate | Random payoff | Random profit factor | Random E[R] |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for name, f in arm["families"].items():
            sv, rnd = f["win_loss"]["sv"], f["win_loss"]["random"]
            lines.append(f"| {name} | {_pct(sv.get('win_rate'))} | {_pct(sv.get('average_win'))} | {_pct(sv.get('average_loss'))} | {_num(sv.get('payoff_ratio'))} | "
                         f"{_num(sv.get('profit_factor'))} | {_num(sv.get('expectancy_r'))} | {_pct(rnd.get('win_rate'))} | {_num(rnd.get('payoff_ratio'))} | "
                         f"{_num(rnd.get('profit_factor'))} | {_num(rnd.get('expectancy_r'))} |")
        lines += ["", "Signals by level and what happened to them:", "", "| Level | " + " | ".join(sorted({k for c in arm["skipped_by_level"].values() for k in c})) + " |"]
        keys = sorted({k for c in arm["skipped_by_level"].values() for k in c})
        lines.append("|---|" + "---|" * len(keys))
        for lv, c in sorted(arm["skipped_by_level"].items()):
            lines.append(f"| {lv} | " + " | ".join(str(c.get(k, 0)) for k in keys) + " |")
        lines.append("")
    for name, f in main["families"].items():
        lines += [f"## {name}: five-year periods against SPY", "", "| Period | SV Sharpe | SPY Sharpe | SV return | SPY return | SV worst fall | SPY worst fall |", "|---|---|---|---|---|---|---|"]
        for period, v in f["periods"].items():
            lines.append(f"| {period} | {_num(v['sv_sharpe'])} | {_num(v['spy_sharpe'])} | {_pct(v['sv_return'])} | {_pct(v['spy_return'])} | {_pct(v['sv_max_drawdown'])} | {_pct(v['spy_max_drawdown'])} |")
        lines += ["", f"## {name}: by segment (exploratory)", "", "| Segment | Group | Signals | SV average | Random average | Difference | t |", "|---|---|---|---|---|---|---|"]
        for seg, groups in f["segments"].items():
            for label, v in groups.items():
                if v.get("signals"):
                    lines.append(f"| {seg} | {label} | {v['signals']} | {_pct(v['sv_mean'], 2)} | {_pct(v['random_mean'], 2)} | {_pct(v['difference_winsorized'], 2)} | {_num(v['t_monthly'])} |")
        if f["leads"]:
            lines += ["", "Leads to confirm on unseen data: " + "; ".join(f"{l['segment']} = {l['label']} (t {_num(l['t_monthly'])})" for l in f["leads"])]
        lines.append("")
    if result.get("next_step"):
        lines += ["## Next step (planned before the run)", "", result["next_step"]]
    return "\n".join(lines) + "\n"


def render_cases(result):
    lines = [f"# {result['spec_id']}", "", f"Case-ledger acceptance check written by the research lab on {result.get('completed_at', '—')[:10]}. "
             "These are seen cases: they check the rules do what the user's reviews say, they are not evidence of returns.", "",
             f"All cases as expected: **{'yes' if result['passed'] else 'no'}**", "",
             "| Case | Signal | Expected | Got | Reason / flags | Stop below close | As expected |", "|---|---|---|---|---|---|---|"]
    for r in result["cases"]:
        lines.append(f"| {r['symbol']} | {r['signal_date']} | {r['expect']} | {r['got'] or 'no data'} | {r.get('reason') or ', '.join(r.get('flags') or []) or '—'} | "
                     f"{_pct(r.get('stop_distance_from_close'))} | {'yes' if r['passed'] else '**no**'} |")
    if result.get("next_step"):
        lines += ["", "## Next step (planned before the run)", "", result["next_step"]]
    return "\n".join(lines) + "\n"
