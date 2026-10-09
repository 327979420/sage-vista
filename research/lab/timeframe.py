"""Trade each SV opportunity by its own timeframe, against random picks under the same rules.

Sage Vista classifies every opportunity as daily, weekly or monthly (08 rules,
2026-09-15). Here a monthly opportunity is held for months and sold only when a
monthly close ends below its structure floor; a weekly one by weekly closes; a
daily one by daily closes. A wide disaster stop guards against gaps. There is
no profit target.

The random null copies every rule in percentage terms: the same signal day,
the same holding length, a floor the same distance below the random stock's
own signal-day close, and the same disaster stop. Only the stock differs.
"""
from __future__ import annotations

import bisect
import csv
import glob
import json
import math
import statistics
from collections import defaultdict

from research.lab import account, datasets, selection
from research.lab.exit_rules import simulate

PERIOD = {"daily": "day", "weekly_completed": "week", "monthly_completed": "month"}
LEVEL = {"daily": "daily", "weekly_completed": "weekly", "monthly_completed": "monthly"}


def join_structure(events, csv_path):
    """Add each event's structure-floor distance below its signal close, from the frozen observation receipt."""
    floors = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            key = f"{row['symbol']}-{row['signal_date']}-{row['episode_id']}"
            if key not in floors and row.get("structure_floor") and row.get("signal_close"):
                floors[key] = 1 - float(row["structure_floor"]) / float(row["signal_close"])
    return [{**e, "floor_distance": floors[e["event_id"]]} for e in events if e["event_id"] in floors and e.get("timeframe") in PERIOD]


def trade(symbol, series, day, event, family, disaster, cost, data_end, priority, event_id):
    """One trade of `series` from signal `day` under the event's timeframe rules: (candidate, net return, exit reason)."""
    i = bisect.bisect_left(series["date"], day)
    if i >= len(series["date"]) or series["date"][i] != day or i + 1 >= len(series["date"]):
        return None, None, None
    bars = datasets.BarsView(series)
    level = LEVEL[event["timeframe"]]
    floor = float(series["close"][i]) * (1 - event["floor_distance"])
    variant = {"stop": {"kind": "structure", "floor": floor, "period": PERIOD[event["timeframe"]], "disaster": disaster},
               "targets": [], "max_hold": family["hold"][level], "trend_exit": (family.get("trend") or {}).get(level)}
    result = simulate(bars, i + 1, variant, cost_per_side=cost)
    if result["status"] not in ("resolved", "observing"):
        return None, None, None
    c = account.candidate({"event_id": event_id, "symbol": symbol, "signal_date": day}, bars, i + 1, result, priority, data_end)
    return c, result.get("net_return"), result.get("exit_reason")


def market_labels(series, dates):
    """For each signal day: is SPY above its 200-day average, and is its 20-day volatility above its one-year median?"""
    closes = series["close"]
    out = {}
    vols = []
    for i in range(len(closes)):
        if i >= 20:
            rets = [closes[j] / closes[j - 1] - 1 for j in range(i - 19, i + 1)]
            m = sum(rets) / 20
            vols.append(math.sqrt(sum((r - m) ** 2 for r in rets) / 19))
        else:
            vols.append(None)
    for day in dates:
        i = bisect.bisect_right(series["date"], day) - 1
        if i < 252:
            out[day] = ("unknown", "unknown")
            continue
        sma = sum(closes[i - 199:i + 1]) / 200
        recent = [v for v in vols[i - 251:i + 1] if v is not None]
        trend = "SPY above 200-day" if closes[i] > sma else "SPY below 200-day"
        calm = "calm (volatility below 1-year median)" if vols[i] <= statistics.median(recent) else "stormy (volatility above 1-year median)"
        out[day] = (trend, calm)
    return out


def sector_labels(root):
    """Today's sector labels (research only, approved 2026-10-08); stocks without one are 'unknown'."""
    files = sorted(glob.glob(str(root / "data/industry/finance-database-*.json")))
    if not files:
        return {}
    return {c["symbol"]: c.get("sector") or "unknown" for c in json.loads(open(files[-1]).read()).get("companies", [])}


def compare(diffs, clusters, sv, rnd):
    """Trade-level summary of SV minus same-day random, winsorized, with a month-clustered t."""
    if not diffs:
        return {"signals": 0}
    mean, t = selection.clustered_t(selection.winsorize(diffs), clusters)
    return {"signals": len(diffs), "difference_winsorized": round(mean, 6), "t_monthly": round(t, 3), "median_difference": round(statistics.median(diffs), 6),
            "sv_mean": round(statistics.fmean(sv), 6), "sv_median": round(statistics.median(sv), 6), "random_mean": round(statistics.fmean(rnd), 6),
            "sv_win_rate": round(sum(x > 0 for x in sv) / len(sv), 4)}


def run(spec, data, dataset_entry, cost, benchmark, root, signal_priority):
    """Every pre-registered family of timeframe rules: SV's account and trades against random accounts and trades."""
    scenario = account.approved_scenario()
    rules, initial, criteria, disaster = spec["account"], scenario["initial_cash"], spec["criteria"], spec["disaster"]
    flagged = selection.impossible_jumps(data["prices"])
    pool = {**spec["pool"], "exclude": flagged}
    events = join_structure([e for e in data["events"] if e["symbol"] not in flagged], root / spec["structure_csv"])
    events = sorted(events, key=lambda e: (e["signal_date"], e["event_id"]))
    series = benchmark["series"]
    dates = [d for d in series["date"] if spec["window"]["start"] <= d <= spec["window"]["end"]]
    data_end = max(s["date"][-1] for s in data["prices"].values())
    markets = market_labels(series, sorted({e["signal_date"] for e in events}))
    sectors = sector_labels(root)
    labels = {"timeframe": lambda e: LEVEL[e["timeframe"]], "market_trend": lambda e: markets[e["signal_date"]][0],
              "market_volatility": lambda e: markets[e["signal_date"]][1], "sector": lambda e: sectors.get(e["symbol"], "unknown")}
    picks_all = selection.draws(events, data["prices"], max(spec["runs"].values()), spec["seed"], pool)
    families = {}
    for name, family in spec["families"].items():
        runs = spec["runs"][name]
        sv_cands, sv_net, sv_exit = [], [], []
        for e in events:
            c, net, why = trade(e["symbol"], data["prices"][e["symbol"]], e["signal_date"], e, family, disaster, cost, data_end, signal_priority(e), e["event_id"])
            sv_net.append(net)
            sv_exit.append(why)
            if c:
                sv_cands.append(c)
        sv_path = account.run_account(account.align(sv_cands, dates)[0], len(dates), scenario, rules=rules)
        sv = account.curve_stats(sv_path["equity"], dates, initial) | {"trades_taken": len(sv_path["trades"]), "average_exposure": round(statistics.fmean(sv_path["exposure"]), 4)}
        sums, counts, accounts = [0.0] * len(events), [0] * len(events), []
        for k in range(runs):
            cands = []
            for j, (symbol, e) in enumerate(zip(picks_all[k], events)):
                if not symbol:
                    continue
                c, net, _ = trade(symbol, data["prices"][symbol], e["signal_date"], e, family, disaster, cost, data_end, signal_priority(e), f"{e['event_id']}~{k}")
                if c:
                    cands.append(c)
                if net is not None:
                    sums[j] += net
                    counts[j] += 1
            st = account.curve_stats(account.run_account(account.align(cands, dates)[0], len(dates), scenario, rules=rules)["equity"], dates, initial)
            accounts.append({"sharpe": st["sharpe"], "cagr": st["cagr"], "max_drawdown": st["max_drawdown"]})
        rows = [(e, sv_net[j], sums[j] / counts[j]) for j, e in enumerate(events) if sv_net[j] is not None and counts[j]]
        def summary(subset):
            return compare([a - b for _, a, b in subset], [e["signal_date"][:7] for e, _, _ in subset], [a for _, a, _ in subset], [b for _, _, b in subset])
        segments = {}
        for seg, fn in labels.items():
            groups = defaultdict(list)
            for row in rows:
                groups[fn(row[0])].append(row)
            segments[seg] = {label: summary(group) for label, group in sorted(groups.items())}
        beats = round(sum((sv["sharpe"] or -9) > (a["sharpe"] or -9) for a in accounts) / len(accounts), 4)
        trades = summary(rows)
        checks = {"beats_random_accounts": beats >= criteria["min_random_percentile"],
                  "trades_beat_random_same_day": trades.get("t_monthly", 0) >= criteria["min_trade_excess_t"] and trades.get("median_difference", -1) > 0
                                                 and trades.get("difference_winsorized", -1) > 0}
        exits = defaultdict(int)
        for why in sv_exit:
            if why:
                exits[why] += 1
        families[name] = {"rule": family, "sv": sv, "random": {"runs": runs, "sharpe": account.distribution([a["sharpe"] for a in accounts]),
                          "cagr": account.distribution([a["cagr"] for a in accounts]), "max_drawdown": account.distribution([a["max_drawdown"] for a in accounts]),
                          "sv_beats_share_sharpe": beats},
                          "trade_level": trades, "segments": segments, "sv_exit_reasons": dict(exits),
                          "leads": [{"segment": seg, "label": lab, **vals} for seg, groups in segments.items() for lab, vals in groups.items()
                                    if vals.get("signals", 0) >= criteria["min_lead_signals"] and vals.get("t_monthly", 0) >= criteria["lead_t"]],
                          "verdict": {"checks": checks, "passed": all(checks.values())}}
    return {"kind": "timeframe", "spec_id": spec["id"], "experiment_id": spec["experiment_id"], "group": spec["group"], "question": spec["question"],
            "dataset": {k: dataset_entry[k] for k in ("dataset_id", "asset", "sha256", "events", "symbols")},
            "benchmark": {"symbol": benchmark["symbol"], **{k: benchmark["entry"][k] for k in ("dataset_id", "asset", "sha256")}},
            "window": {"start": dates[0], "end": dates[-1], "sessions": len(dates)}, "cost_per_side": cost, "account_rules": rules, "disaster": disaster,
            "pool": {k: v for k, v in spec["pool"].items()}, "excluded_symbols": sorted(flagged), "signals": len(events),
            "criteria": criteria, "families": families, "passed_families": [n for n, f in families.items() if f["verdict"]["passed"]],
            "champion": None, "chosen": None, "next_step": spec.get("next_step")}


def render(result):
    pct = lambda x, d=1: "—" if x is None else f"{x * 100:.{d}f}%"
    num = lambda x: "—" if x is None else f"{x:.2f}"
    lines = [f"# {result['spec_id']}", "", f"Plain-language report written by the research lab on {result.get('completed_at', '—')[:10]}. Every number comes from `result.json` in this folder.", "",
             "## The question", "", result["question"], "", "## The short answer", "",
             f"- Families that beat random picks under the pre-registered bar: {', '.join(result['passed_families']) or 'none'}.", "",
             "| Family | SV Sharpe | Beats random accounts | Trade difference (winsorized) | t | Median difference | SV win rate |", "|---|---|---|---|---|---|---|"]
    for name, f in result["families"].items():
        tl = f["trade_level"]
        lines.append(f"| {name} | {num(f['sv']['sharpe'])} | {pct(f['random']['sv_beats_share_sharpe'], 0)} | {pct(tl.get('difference_winsorized'), 2)} | {num(tl.get('t_monthly'))} | "
                     f"{pct(tl.get('median_difference'), 2)} | {pct(tl.get('sv_win_rate'))} |")
    for name, f in result["families"].items():
        lines += ["", f"## {name}: by segment (exploratory)", "", "| Segment | Group | Signals | SV average | Random average | Difference | t |", "|---|---|---|---|---|---|---|"]
        for seg, groups in f["segments"].items():
            for label, v in groups.items():
                if v.get("signals"):
                    lines.append(f"| {seg} | {label} | {v['signals']} | {pct(v['sv_mean'], 2)} | {pct(v['random_mean'], 2)} | {pct(v['difference_winsorized'], 2)} | {num(v['t_monthly'])} |")
        if f["leads"]:
            lines.append("")
            lines.append("Leads to confirm on unseen data: " + "; ".join(f"{l['segment']} = {l['label']} (t {num(l['t_monthly'])})" for l in f["leads"]))
    if result.get("next_step"):
        lines += ["", "## Next step (planned before the run)", "", result["next_step"]]
    return "\n".join(lines) + "\n"
