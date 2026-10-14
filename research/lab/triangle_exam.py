"""Training and one exam for the weekly triangle (lab-triangle-exam-v1; research/lab/triangle.py 1.0; 08 rules #triangle-exam).

Written down before the run:
1 scan the 1,228 known stocks once; on 2005-2016 trade the frozen triangle (baseline) and each one-change variant in the research
  account, against same-day random stocks from the same pool with the same stop distance in weekly ATRs, the same reward-to-risk
  target and the same exits;
2 adopt a change only when it beats the baseline by the pre-registered margins on the training window (two option choices that
  contradict each other: the one with the higher training Sharpe);
3 run the chosen rule once on each of four shards of stocks no rule has seen (2005 to mid-2025), each against its own random accounts,
  and judge the four shards together by the pre-registered criteria;
4 report, without judging, the same rule on the known stocks after the training window (2017 to mid-2025).
Shards are loaded one at a time so the exam fits in a small runner.
"""
from __future__ import annotations

import bisect
import multiprocessing
import os
from collections import Counter

from research.lab import account, buytrain, selection, timeframe, triangle
from research.lab.buysystem import PARAMS


def _scan_one(args):
    symbol, pool, start, end = args
    s = triangle.PRICES[symbol]
    out = []
    for cand in triangle.scan_symbol(symbol):
        for name, o in cand["options"].items():
            if not start <= o["fill"] <= end:
                continue
            i = bisect.bisect_left(s["date"], o["signal_week"])
            if i >= len(s["date"]) or s["date"][i] != o["signal_week"] or not buytrain.tradable(s, i, pool):
                continue
            out.append({"symbol": symbol, "kind": "week", "option": name, "decision_date": o["signal_week"], "fill_date": o["fill"],
                        "entry": o["entry"], "stop": o["stop"], "target": cand["target"], "rr": o["rr"], "entry_at": "stop_order",
                        "nested": cand["nested"], "confluence_count": cand["confluence_count"], "volume_ratio": o.get("volume_ratio"),
                        "priority": (0 if cand["nested"] else 1, -cand["confluence_count"])})
    return out


def scan(prices, excluded, pool, window, workers=None):
    """Every C and B buy filled inside `window` whose signal week ends on a day the stock is in SV's pool, in a fixed order."""
    triangle.PRICES = prices
    jobs = [(symbol, pool, *window) for symbol in sorted(prices) if symbol not in excluded]
    workers = workers if workers is not None else (os.cpu_count() or 1)
    if workers > 1 and "fork" in multiprocessing.get_all_start_methods():
        with multiprocessing.get_context("fork").Pool(workers) as procs:
            chunks = procs.map(_scan_one, jobs, chunksize=4)
    else:
        chunks = [_scan_one(j) for j in jobs]
    triangle.PRICES = None  # let a shard be freed once its exam is done
    return sorted((c for chunk in chunks for c in chunk), key=lambda c: (c["fill_date"], c["priority"], c["symbol"], c["option"]))


VARIANT_KEYS = {"options", "target_r", "min_volume_ratio", "min_confluence", "market_filter", "max_sessions"}


def apply(cards, changes):
    """The cards one rule trades. `options` keeps only C or B buys; `target_r` replaces the first high with a fixed multiple of the
    risk; `min_volume_ratio` asks the cross week (C) or the breakout week (B) to trade that multiple of its ten-week average volume;
    `min_confluence` keeps buys with at least that many confluence pluses (nested triangles are common, so nesting only ranks)."""
    unknown = set(changes) - VARIANT_KEYS
    if unknown:
        raise KeyError(f"unknown triangle change {sorted(unknown)}")
    out = []
    for c in cards:
        if "options" in changes and c["option"] not in changes["options"]:
            continue
        if changes.get("min_volume_ratio") and (c["volume_ratio"] or 0) < changes["min_volume_ratio"]:
            continue
        if changes.get("min_confluence") and c["confluence_count"] < changes["min_confluence"]:
            continue
        if changes.get("target_r"):
            c = {**c, "target": round(c["entry"] + changes["target_r"] * (c["entry"] - c["stop"]), 4), "rr": changes["target_r"]}
        out.append(c)
    return out


def params(changes):
    return buytrain.override(PARAMS, {"exit.max_sessions": changes["max_sessions"]} if changes.get("max_sessions") else {})


def combine(adopted, variants, arms):
    """The adopted changes together; of two contradicting option choices the one with the higher training Sharpe wins."""
    final = {}
    for name in sorted(adopted, key=lambda n: -(arms[n]["sv"]["sharpe"] or -9)):
        for k, v in variants[name].items():
            final.setdefault(k, v)
    return final


def pooled(rows):
    paired = [r for r in rows if r["net"] is not None and r.get("random_net") is not None]
    return timeframe.compare([r["net"] - r["random_net"] for r in paired], [r["decision_date"][:7] for r in paired],
                             [r["net"] for r in paired], [r["random_net"] for r in paired])


def verdict(shards, trades, crit):
    beat = sum((s["random"]["sv_beats_share_sharpe"] or 0) >= crit["min_random_share"] for s in shards)
    checks = {"shards_beating_random_accounts": beat >= crit["min_shards"],
              "trades_beat_random_same_day": trades.get("t_monthly", 0) >= crit["min_trade_excess_t"] and trades.get("median_difference", -1) > 0
                                             and trades.get("difference_winsorized", -1) > 0,
              "enough_trades": trades.get("signals", 0) >= crit["min_exam_trades"]}
    goal = sum(s["goal_1"]["met"] for s in shards)
    sharper = sum((s["sv"]["sharpe"] or -9) >= (s["spy"]["sharpe"] or 9) for s in shards)
    return checks, all(checks.values()), {"shards_meeting_goal_1": goal, "shards_sharpe_at_least_spy": sharper,
                                          "met": sharper >= crit["min_shards"]}


def run(spec, data, dataset_entry, cost, benchmark, load_exam, workers=None):
    scenario = account.approved_scenario()
    spy = benchmark["series"]
    train, holdout, exam_window = spec["windows"]["train"], spec["windows"]["holdout"], spec["windows"]["exam"]
    prices = data["prices"]
    flagged = selection.impossible_jumps(prices)
    train_raw = all("raw_close" in s for s in prices.values())
    for changes in spec["variants"].values():
        apply([], changes)  # an unknown change stops the run before any work
    cards = scan(prices, flagged, spec["pool"], (train[0], holdout[1]), workers)
    atr = buytrain.WeeklyATR(prices)
    market_ok = buytrain.market_filter_days(spy)
    all_rows = []

    def judge(name, changes, px, cds, window, at, fl, label):
        chosen, market = apply(cds, changes), market_ok if changes.get("market_filter") else None
        summary, rows = buytrain.evaluate(chosen, px, params(changes), spec, window, spy, at, scenario, cost, fl, market_ok=market)
        summary["by_option"] = dict(sorted(Counter(c["option"] for c in chosen if window[0] <= c["fill_date"] <= window[1]
                                                   and (market is None or c["decision_date"] in market)).items()))
        all_rows.extend({"arm": name, "window": label, **r} for r in rows)
        return summary

    arms = {"baseline": judge("baseline", {}, prices, cards, train, atr, flagged, "train") | {"changes": {}}}
    for name, changes in spec["variants"].items():
        arms[name] = judge(name, changes, prices, cards, train, atr, flagged, "train") | {"changes": changes}
    adopted = [name for name in spec["variants"] if buytrain.adopt(arms["baseline"], arms[name], spec["selection"])]
    final = combine(adopted, spec["variants"], arms)
    known_later = judge("final", final, prices, cards, holdout, atr, flagged, "holdout_known_stocks")
    # release the known stocks before the first shard loads (the runner keeps no other use for them)
    del cards, atr, prices
    data["prices"] = {}

    shards, exam_rows = [], []
    for ds in spec["exam_datasets"]:
        shard_data, shard_entry = load_exam(ds)
        px = shard_data["prices"]
        fl = selection.impossible_jumps(px)
        before = len(all_rows)
        summary = judge(f"final@{ds['id']}", final, px, scan(px, fl, spec["pool"], exam_window, workers), exam_window,
                        buytrain.WeeklyATR(px), fl, "exam")
        exam_rows.extend(all_rows[before:])
        shards.append({"dataset": {k: shard_entry[k] for k in ("dataset_id", "asset", "sha256", "symbols")},
                       "raw_close": all("raw_close" in s for s in px.values()), "excluded_symbols": sorted(fl), **summary})
        del shard_data, px
    trades = pooled(exam_rows)
    checks, passed, goal = verdict(shards, trades, spec["criteria"])
    result = {"kind": "triangle_exam", "spec_id": spec["id"], "experiment_id": spec["experiment_id"], "group": spec["group"], "question": spec["question"],
              "dataset": {k: dataset_entry[k] for k in ("dataset_id", "asset", "sha256", "symbols")},
              "benchmark": {"symbol": benchmark["symbol"], **{k: benchmark["entry"][k] for k in ("dataset_id", "asset", "sha256")}},
              "engine": {"pattern": triangle.P, "document": "research/lab/triangle.py 1.0", "exit": PARAMS["exit"], "runner": PARAMS["kinds"]["week"]["runner"]},
              "windows": spec["windows"], "pool": spec["pool"], "account_rules": spec["account"], "cost_per_side": cost,
              "excluded_symbols": sorted(flagged), "train_raw_close": train_raw,
              "selection": spec["selection"], "criteria": spec["criteria"], "train": arms, "adopted": adopted, "final_changes": final,
              "holdout_known_stocks": known_later, "exam": {"shards": shards, "pooled_trades": trades, "checks": checks, "passed": passed, "goal": goal},
              "passed": passed, "champion": "final" if passed else None, "next_step": spec.get("next_step")}
    return result, all_rows


def render(result):
    pct = lambda x, d=1: "—" if x is None else f"{x * 100:.{d}f}%"
    num = lambda x: "—" if x is None else f"{x:.2f}"
    tr = result["windows"]["train"]
    lines = [f"# {result['spec_id']}", "", f"Plain-language report written by the research lab on {(result.get('completed_at') or '—')[:10]}. "
             "Every number comes from `result.json` in this folder.", "", "## The question", "", result["question"], "",
             f"## Training on the known stocks ({tr[0]} to {tr[1]})", "",
             "| Rule | Changes | Signals (C/B) | Trades | Sharpe | CAGR | Max DD | Beats random accounts | Excess vs random (t) | Win rate | Payoff | Adopted |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, arm in result["train"].items():
        wl, tl = arm["win_loss"]["sv"], arm["trade_level"]
        changes = ", ".join(f"{k}={v}" for k, v in arm.get("changes", {}).items()) or "—"
        opts = "/".join(str(arm["by_option"].get(o, 0)) for o in ("C", "B"))
        lines.append(f"| {name} | {changes} | {arm['signals']} ({opts}) | {arm['sv']['trades_taken']} | {num(arm['sv']['sharpe'])} | {pct(arm['sv']['cagr'])} | "
                     f"{pct(arm['sv']['max_drawdown'])} | {pct(arm['random']['sv_beats_share_sharpe'])} | {pct(tl.get('difference_winsorized'), 2)} "
                     f"({num(tl.get('t_monthly'))}) | {pct(wl.get('win_rate'))} | {num(wl.get('payoff_ratio'))} | "
                     f"{'—' if name == 'baseline' else ('yes' if name in result['adopted'] else 'no')} |")
    ex = result["exam"]
    lines += ["", f"Adopted: {', '.join(result['adopted']) or 'none, so the frozen baseline goes to the exam'}; final changes "
              f"{result['final_changes'] or '{}'}.", "", f"## The exam: stocks no rule has seen ({result['windows']['exam'][0]} to {result['windows']['exam'][1]}), run once", "",
              "| Shard | Stocks | Signals | Trades | Sharpe | SPY Sharpe | CAGR | SPY CAGR | Max DD | Beats random accounts | Excess vs random (t) | Win rate | Payoff |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in ex["shards"]:
        wl, tl = s["win_loss"]["sv"], s["trade_level"]
        lines.append(f"| {s['dataset']['dataset_id']} | {s['dataset']['symbols']} | {s['signals']} | {s['sv']['trades_taken']} | {num(s['sv']['sharpe'])} | "
                     f"{num(s['spy']['sharpe'])} | {pct(s['sv']['cagr'])} | {pct(s['spy']['cagr'])} | {pct(s['sv']['max_drawdown'])} | "
                     f"{pct(s['random']['sv_beats_share_sharpe'])} | {pct(tl.get('difference_winsorized'), 2)} ({num(tl.get('t_monthly'))}) | "
                     f"{pct(wl.get('win_rate'))} | {num(wl.get('payoff_ratio'))} |")
    t = ex["pooled_trades"]
    k = result["holdout_known_stocks"]
    lines += ["", f"All four shards together: {t.get('signals', 0)} trades; excess over same-day random {pct(t.get('difference_winsorized'), 2)} per trade "
              f"(t {num(t.get('t_monthly'))}, median {pct(t.get('median_difference'), 2)}); win rate {pct(t.get('sv_win_rate'))}.", "",
              "| Check | Passed |", "|---|---|", *[f"| {name} | {'yes' if v else 'no'} |" for name, v in ex["checks"].items()], "",
              f"**Passed: {'yes' if ex['passed'] else 'no'}.** The user's goal (Sharpe at least SPY's) in {ex['goal']['shards_sharpe_at_least_spy']} of "
              f"{len(ex['shards'])} shards; full goal 1 (Sharpe and Calmar at least SPY's, drawdown at most 25%) in {ex['goal']['shards_meeting_goal_1']}.", "",
              f"## Reported, not judged: the known stocks after training ({result['windows']['holdout'][0]} to {result['windows']['holdout'][1]})", "",
              f"- Signals {k['signals']}; trades {k['sv']['trades_taken']}; Sharpe {num(k['sv']['sharpe'])} (SPY {num(k['spy']['sharpe'])}); CAGR "
              f"{pct(k['sv']['cagr'])} (SPY {pct(k['spy']['cagr'])}); beats {pct(k['random']['sv_beats_share_sharpe'])} of random accounts; excess vs random "
              f"{pct(k['trade_level'].get('difference_winsorized'), 2)} (t {num(k['trade_level'].get('t_monthly'))})."]
    if result.get("next_step"):
        lines += ["", "## Next step", "", result["next_step"]]
    return "\n".join(lines) + "\n"
