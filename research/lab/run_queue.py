"""Run pre-registered lab experiments from research/lab/queue, one at a time.

Each spec is frozen before it runs (its SHA256 is stored with the result). A
spec whose result already exists for the same SHA256 is never re-run, so the
daily background job only spends time on new questions. A spec with
`not_before` waits until that date, so a forward holdout can be registered
before its data exists. Results, a cumulative
scoreboard and the experiment lifecycle event are committed permanently;
negative results are kept exactly like positive ones.

  python3 -m research.lab.run_queue            # local dry run, writes work/lab
  python3 -m research.lab.run_queue --publish  # Actions: commit results to main
"""
from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import pathlib
import statistics
import subprocess

from services.scanner.support_risk import signal_support_plan
from research.lab import account, allocation, datasets, selection
from research.lab.exit_rules import OPEN_FILLS, simulate
from research.lab.metrics import evaluate, summarise

ROOT = pathlib.Path(__file__).resolve().parents[2]
QUEUE = ROOT / "research/lab/queue"
RESULTS = ROOT / "research/lab/results"
SCOREBOARD = ROOT / "research/lab/scoreboard.json"
SCOREBOARD_MD = ROOT / "research/lab/SCOREBOARD.md"
EVENTS = ROOT / "research/experiment-events.jsonl"
WORK = ROOT / "work/lab"


def spec_sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def pending_specs(today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date().isoformat()
    out = []
    for path in sorted(QUEUE.glob("*.json")):
        spec = json.loads(path.read_text())
        done = RESULTS / spec["id"] / "result.json"
        if done.exists() and json.loads(done.read_text())["spec_sha256"] == spec_sha(path):
            continue
        if spec.get("not_before", "") > today:
            continue
        out.append((spec.get("priority", 100), spec["id"], path, spec))
    return [item[2:] for item in sorted(out, key=lambda x: (x[0], x[1]))]


def in_eod_window(now=None):
    """Never publish while the daily EOD release may be pushing to main."""
    now = now or dt.datetime.now(dt.timezone.utc)
    minutes = now.hour * 60 + now.minute
    return minutes >= 23 * 60 + 30 or minutes < 4 * 60 + 30


def ensure_dataset(ds, publish):
    """Load a frozen dataset by id, or build, freeze and upload it once."""
    entry = datasets.manifest(ds["id"])
    if entry:
        return datasets.load(datasets.download(entry, WORK), entry["sha256"]), entry, None
    source = ds["builder"]
    if source == "ledger":
        data = datasets.build_from_ledger(ROOT / "public/opportunity-ledger.json", ROOT / "work/eodhd-cache", ds["id"], ds.get("signal_from"))
    elif source == "observation":
        from services.scanner.eodhd import prices
        data = datasets.build_from_observation(ROOT / ds["events_csv"], ds["id"], lambda s: prices(s, start="2004-01-01"))
    elif source == "symbols":
        from services.scanner.eodhd import prices
        data = datasets.build_from_symbols(ds["symbols"], ds["id"], lambda s: prices(s, start=ds.get("start", "2004-01-01")))
    elif source == "chains":
        from services.scanner.eodhd import get
        data = datasets.build_from_chains(ds["chains"], ds["id"], lambda t: get(f"eod/{t}", **{"from": ds.get("start", "1980-01-01"), "period": "d"}))
    else:
        raise ValueError(f"unknown dataset builder {source}")
    path, entry = datasets.save(data, WORK)
    if publish:
        datasets.upload(path)
    return data, entry, entry


def benchmark_gross(series, entry_date, fills):
    """Gross return of holding the benchmark over the same days and fractions as the trade.

    Entry at the benchmark open on the entry date; each fill at the benchmark
    open when the trade filled at the open, otherwise at its close. A date the
    benchmark did not trade uses its last earlier close.
    """
    def price(day, at_open):
        i = bisect.bisect_right(series["date"], day) - 1
        if i < 0:
            return None
        return series["open" if at_open and series["date"][i] == day else "close"][i]
    start = price(entry_date, True)
    if not start:
        return None
    total = 0.0
    for f in fills:
        end = price(f["date"], f["reason"] in OPEN_FILLS)
        if end is None:
            return None
        total += f["fraction"] * (end / start - 1)
    return total


def variant_results(spec, data, cost, benchmark=None):
    """Yield (variant id, event, bars, entry index, trade) for every variant on every event.

    `benchmark`: {"symbol", "series", "entry"} or None; adds each trade's excess over the benchmark.
    """
    variants = {v["id"]: v for v in spec["variants"]}
    # One stock at a time keeps memory flat even for the 20-year dataset.
    cached_symbol, bars, dates = None, [], []
    for event in sorted(data["events"], key=lambda e: (e["symbol"], e["signal_date"])):
        if event["symbol"] != cached_symbol:
            cached_symbol = event["symbol"]
            bars = datasets.expand(data["prices"][cached_symbol])
            dates = data["prices"][cached_symbol]["date"]
        signal = bisect.bisect_left(dates, event["signal_date"])
        if signal >= len(dates) or dates[signal] != event["signal_date"]:
            continue
        plan = event.get("support_plan") or signal_support_plan(bars, end=signal)
        split = next((s["id"] for s in spec.get("splits", []) if s["from"] <= event["signal_date"] <= s["to"]), None)
        for vid, variant in variants.items():
            result = simulate(bars, signal + 1, variant, support_plan=plan, cost_per_side=cost)
            result["split"], result["cluster"] = split, event["signal_date"][:7]
            if benchmark and result["status"] == "resolved":
                # Same round-trip cost on both sides, so it cancels in the difference.
                bench = benchmark_gross(benchmark["series"], result["entry_date"], result["fills"])
                result["excess_return"] = None if bench is None else round(result["gross_return"] - bench, 8)
            yield vid, event, bars, signal + 1, result


def run_spec(spec, data, dataset_entry, cost, benchmark=None):
    """Trade-level experiment: every signal counted once per variant, no capital limits."""
    variants = {v["id"]: v for v in spec["variants"]}
    trades = {vid: [] for vid in variants}
    rows_out = []
    for vid, event, _, _, result in variant_results(spec, data, cost, benchmark):
        trades[vid].append(result)
        if result["status"] == "resolved":
            rows_out.append([vid, event["event_id"], event["symbol"], event["signal_date"], result["split"], result["exit_reason"],
                             result["held"], result["risk_pct"], result["net_return"], result["r_multiple"], result.get("excess_return")])
    summary = {}
    for vid, items in trades.items():
        overall = summarise(items)
        splits = {s["id"]: summarise([t for t in items if t["split"] == s["id"]]) for s in spec["splits"]}
        stress = summarise([{**t, "net_return": t["net_return"] - 2 * cost, "r_multiple": (t["net_return"] - 2 * cost) / t["risk_pct"]}
                            if t.get("status") == "resolved" else t for t in items])
        summary[vid] = {"label": variants[vid]["label"], "family": variants[vid].get("family", vid), "rule": variants[vid],
                        "overall": overall, "splits": splits, "double_cost": {k: stress.get(k) for k in ("mean_return", "expectancy_r", "profit_factor")}}
    for vid, item in summary.items():
        neighbours = [summary[n]["overall"] for n in spec.get("neighbours", {}).get(vid, [])]
        item["verdict"] = evaluate(item["overall"], item["splits"], neighbours, spec["criteria"])
        base = summary[spec["baseline"]]["overall"]
        item["vs_baseline"] = {k: round((item["overall"].get(k) or 0) - (base.get(k) or 0), 4) for k in ("expectancy_r", "mean_return", "median_return", "win_rate")}
    passed = [vid for vid, item in summary.items() if item["verdict"]["passed"] and vid != spec["baseline"]]
    # E[R] suits variants with similar stops; specs comparing different stop widths pre-register another metric.
    metric = spec.get("champion_metric", "expectancy_r")
    champion = max(passed, key=lambda v: summary[v]["overall"].get(metric) or -9) if passed else None
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["variant", "event_id", "symbol", "signal_date", "split", "exit_reason", "held", "risk_pct", "net_return", "r_multiple", "excess_return"])
    writer.writerows(rows_out)
    result = {"spec_id": spec["id"], "experiment_id": spec["experiment_id"], "group": spec["group"], "question": spec["question"],
              "dataset": {k: dataset_entry[k] for k in ("dataset_id", "asset", "sha256", "events", "symbols")},
              "benchmark": {"symbol": benchmark["symbol"], **{k: benchmark["entry"][k] for k in ("dataset_id", "asset", "sha256")}} if benchmark else None,
              "cost_per_side": cost, "baseline": spec["baseline"], "criteria": spec["criteria"], "variants": summary,
              "champion": champion, "selection_rule": f"highest overall {metric} among variants passing every pre-registered check"}
    return result, gzip.compress(csv_buffer.getvalue().encode(), 9, mtime=0)


def signal_priority(event):
    """Same-day order when signals outnumber free slots: SV score (higher first), else ledger rank."""
    if event.get("score") is not None:
        return -float(event["score"])
    return float(event.get("rank") or 0)


def monthly(dates, values):
    keep = [i for i in range(len(dates)) if i == len(dates) - 1 or dates[i][:7] != dates[i + 1][:7]]
    return [dates[i] for i in keep], [round(values[i]) for i in keep]


EXIT_KEYS = ("stop", "targets", "trail", "trail_after_target", "max_hold")
SETTING_LABELS = {"risk_per_trade": ("Risk", "%"), "position_cap": ("cap", "%"), "max_positions": ("up to", " stocks"), "heat_cap": ("open risk", "%"), "core": ("Core", "")}


def expand_variants(spec):
    """Explicit variants plus a full grid of account settings on one exit rule.

    Returns (variants by id, grid neighbours by id). Neighbours differ in one
    setting by one step, so a choice can be checked for a plateau, not a peak.
    """
    variants = {v["id"]: v for v in spec["variants"]}
    neighbours = {}
    grid = spec.get("grid")
    if not grid:
        return variants, neighbours
    names = list(grid["settings"])
    values = [grid["settings"][n] for n in names]

    def vid(combo):
        return "-".join(f"{n[0].upper()}{v * 100:g}" if isinstance(v, float) else f"{n[0].upper()}{v}" for n, v in zip(names, combo))

    def label(combo):
        parts = []
        for n, v in zip(names, combo):
            word, unit = SETTING_LABELS.get(n, (n, ""))
            if n == "max_positions" and v == 0:
                parts.append("no SV stocks")
            else:
                parts.append(f"{word} {v * 100:g}{unit}" if unit == "%" else f"{word} {v}{unit}")
        return ", ".join(parts)

    combos = [()]
    for vals in values:
        combos = [c + (v,) for c in combos for v in vals]
    for combo in combos:
        variants[vid(combo)] = {**grid["exit"], "id": vid(combo), "family": "grid", "label": label(combo),
                                "account": {**grid.get("fixed", {}), **dict(zip(names, combo))}}
        near = []
        for i, vals in enumerate(values):
            j = vals.index(combo[i])
            for k in (j - 1, j + 1):
                if 0 <= k < len(vals):
                    near.append(vid(combo[:i] + (vals[k],) + combo[i + 1:]))
        neighbours[vid(combo)] = near
    return variants, neighbours


def choose_plateau(summary, neighbours, selection):
    """Pick the grid setting whose own and neighbours' luck-check median Sharpe is best on average.

    Only settings within the drawdown limit are eligible (all, if none is);
    near-ties go to the smaller worst fall.
    """
    sharpe = lambda v: summary[v]["monte_carlo"]["sharpe"]["median"]
    grid = list(neighbours)
    eligible = [v for v in grid if summary[v]["account"]["max_drawdown"] <= selection["max_drawdown"]]
    pool = eligible or grid
    score = {v: statistics.fmean([sharpe(v), *(sharpe(n) for n in neighbours[v])]) for v in pool}
    best = max(score.values())
    close = [v for v in pool if score[v] >= best - selection["tie_tolerance"]]
    chosen = min(close, key=lambda v: (summary[v]["account"]["max_drawdown"], v))
    return {"variant": chosen, "settings": summary[chosen]["rule"].get("account"), "plateau_score": round(score[chosen], 4),
            "within_drawdown_limit": bool(eligible), "rule": selection}


def choose_satellite(summary, variants, selection):
    """Keep SV only if a satellite beats the same core without SV on Sharpe and Calmar within the drawdown limit.

    Near-ties (Sharpe within the tolerance) go to the smaller satellite. The
    same share is then checked on every other core, so a choice that only works
    on one core is visible.
    """
    by = {(v["account"]["core"], v["account"]["max_positions"]): vid for vid, v in variants.items() if (v.get("account") or {}).get("core")}
    core = selection["core"]
    plain = summary[by[(core, 0)]]["account"]
    better = lambda a, b: (a["sharpe"] or -9) > (b["sharpe"] or -9) and (a["calmar"] or -9) > (b["calmar"] or -9)
    sizes = sorted(m for c, m in by if c == core and m > 0)
    ok = [m for m in sizes if better(summary[by[(core, m)]]["account"], plain) and summary[by[(core, m)]]["account"]["max_drawdown"] <= selection["max_drawdown"]]
    if ok:
        best = max(summary[by[(core, m)]]["account"]["sharpe"] for m in ok)
        m = min(x for x in ok if summary[by[(core, x)]]["account"]["sharpe"] >= best - selection["tie_tolerance"])
    else:
        m = 0
    others = {c: better(summary[by[(c, m)]]["account"], summary[by[(c, 0)]]["account"]) for c, mm in by if c != core and mm == m and m > 0}
    vid = by[(core, m)]
    return {"variant": vid, "settings": summary[vid]["rule"]["account"], "sv_added": m > 0, "also_better_on": others,
            "within_drawdown_limit": summary[vid]["account"]["max_drawdown"] <= selection["max_drawdown"], "rule": selection}


def core_series(spec, core_data, dates, cost):
    """Daily returns of each core portfolio and of the cash reserve on the account calendar."""
    prices = allocation.Prices(core_data["prices"])
    spy_dates = core_data["prices"][spec["benchmark"]["symbol"]]["date"]
    signal_day = spy_dates[spy_dates.index(dates[0]) - 1]
    out = {}
    for name, portfolio in spec["core"]["portfolios"].items():
        run = allocation.simulate(portfolio, prices, dates, cost, 1.0, signal_day)
        out[name] = account.returns_from(run["equity"], 1.0)
    cash = account.benchmark_returns(core_data["prices"][spec["core"]["cash_symbol"]], dates)
    month_ends = {i for i, d in enumerate(dates) if i < len(dates) - 1 and d[:7] != dates[i + 1][:7]}
    return {name: {"returns": r, "cash_returns": cash, "cash_buffer": spec["core"]["cash_buffer"], "cost": cost, "month_ends": month_ends}
            for name, r in out.items()}


def run_account_spec(spec, data, dataset_entry, cost, benchmark, core_data=None):
    """Account-level experiment: each rule trades the $100k research account day by day.

    Account results decide (CAGR, drawdown, Sharpe, Calmar, SPY, a Monte Carlo
    luck check and the deflated Sharpe ratio); trade statistics are kept only
    as diagnostics. Variants with an `account` block use those sizing rules;
    the others use the approved preset.
    """
    if not benchmark:
        raise ValueError("account_spec_requires_benchmark")
    scenario = account.approved_scenario()
    if abs(scenario["cost_rate"] - cost) > 1e-12:
        raise ValueError("cost_differs_from_approved_account")
    variants, neighbours = expand_variants(spec)
    # Variants sharing an exit rule share one simulation of every trade.
    signature = {vid: json.dumps({k: v.get(k) for k in EXIT_KEYS}, sort_keys=True) for vid, v in variants.items()}
    exits = {sig: {"id": sig, **json.loads(sig)} for sig in signature.values()}
    trades = {sig: [] for sig in exits}
    candidates = {sig: [] for sig in exits}
    data_end = max(series["date"][-1] for series in data["prices"].values())
    for sig, event, bars, entry_index, result in variant_results({**spec, "variants": list(exits.values())}, data, cost, benchmark):
        trades[sig].append(result)
        if result["status"] in ("resolved", "observing"):
            candidates[sig].append(account.candidate(event, bars, entry_index, result, signal_priority(event), data_end))
    series, initial, criteria = benchmark["series"], scenario["initial_cash"], spec["criteria"]
    start = min(e["signal_date"] for e in data["events"])
    end = max(c["closes"][-1][0] for items in candidates.values() for c in items)
    if spec.get("window"):
        # A fixed window keeps steps comparable; it must still hold every trade to its exit.
        if spec["window"]["end"] < end:
            raise ValueError(f"window_ends_before_last_trade: {end}")
        start, end = spec["window"]["start"], spec["window"]["end"]
    dates = [d for d in series["date"] if start <= d <= end]
    spy_rets = account.benchmark_returns(series, dates)
    spy_equity = account.compound(spy_rets, initial)
    spy = account.curve_stats(spy_equity, dates, initial) | {"splits": account.period_returns(spy_equity, dates, initial, spec["splits"])}
    curve_dates, spy_curve = monthly(dates, spy_equity)
    curves = {"dates": curve_dates, benchmark["symbol"]: spy_curve}
    aligned = {sig: account.align(items, dates) for sig, items in candidates.items()}
    cores = core_series(spec, core_data, dates, cost) if spec.get("core") else {}
    summary, rows_out = {}, []
    for vid, variant in variants.items():
        book, notes = aligned[signature[vid]]
        rules = variant.get("account")
        core = cores[rules["core"]] if rules and rules.get("core") else None
        main = account.run_account(book, len(dates), scenario, rules=rules, core=core)
        stats = account.curve_stats(main["equity"], dates, initial)
        rets = account.returns_from(main["equity"], initial)
        # The benchmark held with the same share of the account invested, one session behind.
        matched = account.compound([0.0] + [x * r for x, r in zip(main["exposure"], spy_rets[1:])], initial)
        summary[vid] = {"label": variant["label"], "family": variant.get("family", vid), "rule": variant,
                        "account": stats | {"trades_taken": len(main["trades"]), "open_at_end": main["open_at_end"], "skipped": main["skipped"],
                                            "average_exposure": round(statistics.fmean(main["exposure"]), 4), **notes},
                        "versus_spy": account.versus(rets, spy_rets) | {"cagr_difference": round(stats["cagr"] - spy["cagr"], 6)},
                        "same_exposure_spy": account.curve_stats(matched, dates, initial),
                        "splits": account.period_returns(main["equity"], dates, initial, spec["splits"]),
                        "monte_carlo": account.monte_carlo(book, dates, scenario, criteria["mc_runs"], spec.get("seed", 0), rules, core) if criteria.get("mc_runs") else None,
                        "trade_diagnostics": summarise(trades[signature[vid]]),
                        "goal_1": {"sharpe_vs_spy": round((stats["sharpe"] or 0) - (spy["sharpe"] or 0), 4), "calmar_vs_spy": round((stats["calmar"] or 0) - (spy["calmar"] or 0), 4),
                                   "met": (stats["sharpe"] or 0) >= (spy["sharpe"] or 0) and (stats["calmar"] or 0) >= (spy["calmar"] or 0)
                                          and stats["max_drawdown"] <= criteria["max_drawdown"]}}
        curves[vid] = monthly(dates, main["equity"])[1]
        rows_out += [[vid, t["event_id"], t["symbol"], t["signal_date"], t["shares"], t["pnl"], t["return"]] for t in main["trades"]]
    # Deflated Sharpe: the best of many tried rules looks better than it is.
    n_trials = spec.get("prior_trials", 0) + len(variants)
    trial_variance = statistics.pvariance([item["account"]["daily_sharpe"] for item in summary.values()]) if len(summary) > 1 else 0.0
    for item in summary.values():
        a = item["account"]
        item["deflated_sharpe"] = account.deflated_sharpe(a["daily_sharpe"], a["sessions"], a["skew"], a["kurtosis"], n_trials, trial_variance)
    baseline = summary[spec["baseline"]]
    for vid, item in summary.items():
        item["verdict"] = account.evaluate(item, baseline, spy, criteria)
    metric = spec.get("champion_metric", "sharpe")
    passed = [vid for vid, item in summary.items() if item["verdict"]["passed"] and vid != spec["baseline"]]
    champion = max(passed, key=lambda v: summary[v]["account"].get(metric) or -9) if passed else None
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["variant", "event_id", "symbol", "signal_date", "shares", "net_pnl", "net_return"])
    writer.writerows(rows_out)
    result = {"spec_id": spec["id"], "experiment_id": spec["experiment_id"], "group": spec["group"], "question": spec["question"], "kind": "account",
              "dataset": {k: dataset_entry[k] for k in ("dataset_id", "asset", "sha256", "events", "symbols")},
              "benchmark": {"symbol": benchmark["symbol"], **{k: benchmark["entry"][k] for k in ("dataset_id", "asset", "sha256")}},
              "account_scenario": scenario | {"source": "research/backtest/account-scenario.json"},
              "window": {"start": dates[0], "end": dates[-1], "sessions": len(dates)}, "cost_per_side": cost,
              "baseline": spec["baseline"], "criteria": criteria, "n_trials": n_trials, "spy": spy, "variants": summary, "curves": curves,
              "champion": champion, "selection_rule": f"highest account {metric} among variants passing every pre-registered check",
              "chosen": (choose_satellite(summary, variants, spec["selection"]) if (spec.get("selection") or {}).get("kind") == "satellite"
                         else choose_plateau(summary, neighbours, spec["selection"]) if spec.get("selection") and neighbours else None),
              "next_step": spec.get("next_step")}
    return result, gzip.compress(csv_buffer.getvalue().encode(), 9, mtime=0)


def run_allocation_spec(spec, data, dataset_entry, cost, benchmark=None):
    """Published portfolios on fund prices, compared with SPY on the same days.

    The core for the next step is chosen by the rule fixed in the spec:
    the highest Sharpe among portfolios within the drawdown limit, near-ties
    to the higher Calmar.
    """
    prices = allocation.Prices(data["prices"])
    initial, criteria = 100000.0, spec["criteria"]
    spy_dates = data["prices"][spec["benchmark_symbol"]]["date"]
    portfolios, excluded = spec["portfolios"], []
    start = spec["window"]["start"]
    if start == "auto":
        # The window opens once every required series exists, plus a warm-up for 10-12 month signals.
        first = {role: data["prices"][role]["date"][0] for role in data["prices"]}
        required = set().union(*(allocation.roles(p) for p in portfolios if not p.get("optional")))
        missing = sorted(r for r in required if r not in first)
        if missing:
            raise ValueError(f"required_series_missing: {missing}")
        opened = max(first[r] for r in required)
        y, m = int(opened[:4]), int(opened[5:7]) + spec["window"].get("warmup_months", 13)
        start = f"{y + (m - 1) // 12:04d}-{(m - 1) % 12 + 1:02d}-01"
        kept = []
        for p in portfolios:
            late = sorted(r for r in allocation.roles(p) if r not in first or first[r] > opened)
            if p.get("optional") and late:
                excluded.append({"portfolio": p["id"], "reason": f"history too short: {', '.join(late)}"})
            else:
                kept.append(p)
        portfolios = kept
    dates = [d for d in spy_dates if start <= d <= spec["window"]["end"]]
    signal_day = spy_dates[spy_dates.index(dates[0]) - 1]
    runs = {p["id"]: allocation.simulate(p, prices, dates, cost, initial, signal_day) for p in portfolios}
    spy_id = spec["benchmark_portfolio"]
    spy_equity = runs[spy_id]["equity"]
    spy_rets = account.returns_from(spy_equity, initial)
    spy = account.curve_stats(spy_equity, dates, initial) | {"splits": account.period_returns(spy_equity, dates, initial, spec["splits"])}
    curve_dates, _ = monthly(dates, spy_equity)
    curves = {"dates": curve_dates}
    summary = {}
    for p in portfolios:
        run = runs[p["id"]]
        stats = account.curve_stats(run["equity"], dates, initial)
        rets = account.returns_from(run["equity"], initial)
        summary[p["id"]] = {"label": p["label"], "family": p.get("source", p["id"]), "rule": p,
                            "account": stats | {"trades_taken": len(run["rebalances"]), "average_exposure": 1.0,
                                                "turnover_per_year": round(run["turnover"] / initial / max(stats["sessions"] / 252, 1e-9), 3)},
                            "versus_spy": account.versus(rets, spy_rets) | {"cagr_difference": round(stats["cagr"] - spy["cagr"], 6)},
                            "splits": account.period_returns(run["equity"], dates, initial, spec["splits"]),
                            "monte_carlo": None, "last_weights": run["rebalances"][-1]["weights"],
                            "goal_1": {"sharpe_vs_spy": round((stats["sharpe"] or 0) - (spy["sharpe"] or 0), 4),
                                       "calmar_vs_spy": round((stats["calmar"] or 0) - (spy["calmar"] or 0), 4),
                                       "met": (stats["sharpe"] or 0) >= (spy["sharpe"] or 0) and (stats["calmar"] or 0) >= (spy["calmar"] or 0)
                                              and stats["max_drawdown"] <= criteria["max_drawdown"]}}
        curves[p["id"]] = monthly(dates, run["equity"])[1]
    n_trials = spec.get("prior_trials", 0) + len(summary)
    trial_variance = statistics.pvariance([item["account"]["daily_sharpe"] for item in summary.values()])
    for vid, item in summary.items():
        a = item["account"]
        item["deflated_sharpe"] = account.deflated_sharpe(a["daily_sharpe"], a["sessions"], a["skew"], a["kurtosis"], n_trials, trial_variance)
        item["verdict"] = account.evaluate(item, summary[spy_id], spy, criteria)
    sel = spec["selection"]
    pool = [v for v in summary if v != spy_id and summary[v]["account"]["max_drawdown"] <= criteria["max_drawdown"]]
    chosen = None
    if sel.get("kind") == "improve_on":
        # Keep the baseline unless a candidate is better on the chosen measure without a lower Sharpe or a deeper fall.
        base = summary[sel["baseline"]]["account"]
        better = [v for v in sel["candidates"] if v in summary
                  and (summary[v]["account"]["sharpe"] or -9) >= (base["sharpe"] or -9) - sel.get("sharpe_tolerance", 0.0)
                  and summary[v]["account"]["max_drawdown"] <= criteria["max_drawdown"]
                  and (summary[v]["account"][sel["metric"]] or -9) > (base[sel["metric"]] or -9)]
        pick = max(better, key=lambda v: (summary[v]["account"][sel["metric"]] or -9, v)) if better else sel["baseline"]
        chosen = {"variant": pick, "settings": {"portfolio": pick}, "improved": bool(better),
                  "within_drawdown_limit": summary[pick]["account"]["max_drawdown"] <= criteria["max_drawdown"], "rule": sel}
        pool = []
    if pool:
        best = max(summary[v]["account"]["sharpe"] for v in pool)
        close = [v for v in pool if summary[v]["account"]["sharpe"] >= best - spec["selection"]["tie_tolerance"]]
        pick = max(close, key=lambda v: (summary[v]["account"]["calmar"] or 0, v))
        chosen = {"variant": pick, "settings": {"portfolio": pick}, "within_drawdown_limit": True, "rule": spec["selection"]}
    passed = [v for v, item in summary.items() if item["verdict"]["passed"] and v != spy_id]
    champion = max(passed, key=lambda v: summary[v]["account"]["sharpe"]) if passed else None
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["portfolio", "date", "weights"])
    for vid, run in runs.items():
        writer.writerows([vid, r["date"], json.dumps(r["weights"], sort_keys=True)] for r in run["rebalances"])
    result = {"spec_id": spec["id"], "experiment_id": spec["experiment_id"], "group": spec["group"], "question": spec["question"], "kind": "allocation",
              "dataset": {k: dataset_entry[k] for k in ("dataset_id", "asset", "sha256", "events", "symbols")},
              "benchmark": {"symbol": spec["benchmark_symbol"], "dataset_id": dataset_entry["dataset_id"], "asset": dataset_entry["asset"], "sha256": dataset_entry["sha256"]},
              "window": {"start": dates[0], "end": dates[-1], "sessions": len(dates)}, "cost_per_side": cost, "initial_cash": initial,
              "baseline": spy_id, "criteria": criteria, "n_trials": n_trials, "spy": spy, "variants": summary, "curves": curves,
              "champion": champion, "selection_rule": "portfolios passing every pre-registered check, highest Sharpe",
              "chosen": chosen, "next_step": spec.get("next_step"), "excluded": excluded,
              "sources": data.get("chains")}
    if spec.get("rolling"):
        r = spec["rolling"]
        roll = allocation.rolling({k: run["equity"] for k, run in runs.items()}, dates, r["years"], r.get("step_sessions", 21), spy_id, r.get("core"))
        if r.get("core"):
            core = roll["per_portfolio"][r["core"]]
            roll["core"] = r["core"]
            roll["core_checks"] = {
                "worst_fall_within_limit": core["worst_fall"] <= r["max_window_drawdown"],
                "every_window_positive": core["share_positive"] == 1.0,
                "sharpe_beats_benchmark_often": roll["core_sharpe_beats_benchmark_share"] >= r["min_share_sharpe_vs_benchmark"]}
            roll["core_passed"] = all(roll["core_checks"].values()) and summary[r["core"]]["goal_1"]["met"]
        result["rolling"] = roll
    if spec.get("comparisons"):
        # Pre-registered pairwise questions, e.g. "does rotation beat SPY on Sharpe".
        result["comparisons"] = [{**c, "a_value": summary[c["a"]]["account"][c["metric"]], "b_value": summary[c["b"]]["account"][c["metric"]],
                                  "holds": (summary[c["a"]]["account"][c["metric"]] or -9) > (summary[c["b"]]["account"][c["metric"]] or -9)}
                                 for c in spec["comparisons"] if c["a"] in summary and c["b"] in summary]
    return result, gzip.compress(csv_buffer.getvalue().encode(), 9, mtime=0)


def run_selection_spec(spec, data, dataset_entry, cost, benchmark, style_data=None):
    """SV's picks against random picks from the same universe on the same days, plus a style check.

    Passes only if SV's account Sharpe beats the pre-registered share of
    random accounts and SV's trades beat the random trades bought the same
    day by a clear margin (t value clustered by signal month).
    """
    scenario = account.approved_scenario()
    rules, variant, initial, criteria = spec["account"], spec["exit"], scenario["initial_cash"], spec["criteria"]
    series = benchmark["series"]
    dates = [d for d in series["date"] if spec["window"]["start"] <= d <= spec["window"]["end"]]
    data_end = max(s["date"][-1] for s in data["prices"].values())
    pool_rules = dict(spec.get("pool") or {})
    flagged = sorted(selection.impossible_jumps(data["prices"])) if pool_rules.pop("exclude_impossible_jumps", False) else []
    if flagged:
        # Provider adjustment errors: dropped from both SV's picks and the random pool.
        pool_rules["exclude"] = set(flagged)
        data = {**data, "events": [e for e in data["events"] if e["symbol"] not in pool_rules["exclude"]]}
    if spec.get("event_filter"):
        # A pre-registered subset of SV's own signals, e.g. only the higher fixed score groups.
        data = {**data, "events": [e for e in data["events"] if (e.get("score") or 0) >= spec["event_filter"]["min_score"]]}
    events, sv_trades = [], []
    for _, event, bars, entry_index, result in variant_results({**spec, "variants": [{"id": "SV", **variant}]}, data, cost):
        if result["status"] in ("resolved", "observing"):
            c = account.candidate(event, bars, entry_index, result, signal_priority(event), data_end)
            c["net_return"] = result.get("net_return")
            sv_trades.append(c)
            events.append(event)
    sv_book, notes = account.align(sv_trades, dates)
    sv_path = account.run_account(sv_book, len(dates), scenario, rules=rules)
    sv = account.curve_stats(sv_path["equity"], dates, initial) | {"trades_taken": len(sv_path["trades"]),
                                                                    "average_exposure": round(statistics.fmean(sv_path["exposure"]), 4), **notes}
    picks = selection.draws(events, data["prices"], spec["random_runs"], spec["seed"], pool_rules or None)
    needed = {(p, e["signal_date"]) for run in picks for p, e in zip(run, events) if p}
    lookup = selection.outcomes(needed, data["prices"], variant, cost, data_end)
    runs, same_day = [], [[] for _ in events]
    for k, run in enumerate(picks):
        candidates = []
        for j, (symbol, event) in enumerate(zip(run, events)):
            o = lookup.get((symbol, event["signal_date"])) if symbol else None
            if not o:
                continue
            candidates.append({**o, "event_id": f"{event['event_id']}~{k}", "signal_date": event["signal_date"], "priority": signal_priority(event)})
            if o["net_return"] is not None:
                same_day[j].append(o["net_return"])
        path = account.run_account(account.align(candidates, dates)[0], len(dates), scenario, rules=rules)
        st = account.curve_stats(path["equity"], dates, initial)
        runs.append({"run": k, "sharpe": st["sharpe"], "cagr": st["cagr"], "max_drawdown": st["max_drawdown"], "final_equity": st["final_equity"],
                     "trades_taken": len(path["trades"])})
    beat = lambda key, better: round(sum(better(sv[key], r[key]) for r in runs) / len(runs), 4)
    diffs, clusters, sv_rets, rnd_rets = [], [], [], []
    for trade, event, rnd in zip(sv_trades, events, same_day):
        if trade["net_return"] is None or not rnd:
            continue
        diffs.append(trade["net_return"] - statistics.fmean(rnd))
        clusters.append(event["signal_date"][:7])
        sv_rets.append(trade["net_return"])
        rnd_rets += rnd
    raw_mean_diff = statistics.fmean(diffs) if diffs else 0.0
    robust = criteria.get("trade_stat") == "winsorized"
    mean_diff, t_diff = selection.clustered_t(selection.winsorize(diffs) if robust and diffs else diffs, clusters)
    median_diff = statistics.median(diffs) if diffs else 0.0
    rets = account.returns_from(sv_path["equity"], initial)
    style = {}
    if style_data:
        style_rets = {s: account.benchmark_returns(style_data["prices"][s], dates) for s in spec["style"]["symbols"]}
        for s, r in style_rets.items():
            matched = account.compound([0.0] + [x * v for x, v in zip(sv_path["exposure"], r[1:])], initial)
            style[s] = {"same_exposure_sharpe": account.curve_stats(matched, dates, initial)["sharpe"]}
        spy = style_rets["SPY"]
        factors = {"SPY": spy, **{f"{s}-SPY": [a - b for a, b in zip(style_rets[s], spy)] for s in spec["style"]["symbols"] if s not in ("SPY", "RSP")}}
        beta, t = selection.ols(rets, list(factors.values()))
        style_regression = {"alpha_annual": round(beta[0] * 252, 6), "alpha_t": round(t[0], 3),
                            "betas": {name: round(b, 4) for name, b in zip(factors, beta[1:])}}
    else:
        style_regression = None
    checks = {"beats_random_accounts": beat("sharpe", lambda a, b: (a or -9) > (b or -9)) >= criteria["min_random_percentile"],
              "trades_beat_random_same_day": t_diff >= criteria["min_trade_excess_t"] and mean_diff > 0 and (not robust or median_diff > 0)}
    dist = lambda key: account.distribution([r[key] for r in runs])
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["run", "sharpe", "cagr", "max_drawdown", "final_equity", "trades_taken"])
    writer.writerows([r["run"], r["sharpe"], r["cagr"], r["max_drawdown"], r["final_equity"], r["trades_taken"]] for r in runs)
    result = {"spec_id": spec["id"], "experiment_id": spec["experiment_id"], "group": spec["group"], "question": spec["question"], "kind": "selection",
              "dataset": {k: dataset_entry[k] for k in ("dataset_id", "asset", "sha256", "events", "symbols")},
              "benchmark": {"symbol": benchmark["symbol"], **{k: benchmark["entry"][k] for k in ("dataset_id", "asset", "sha256")}},
              "window": {"start": dates[0], "end": dates[-1], "sessions": len(dates)}, "cost_per_side": cost, "account_rules": rules, "exit": variant,
              "criteria": criteria, "sv": sv,
              "random": {"runs": len(runs), "seed": spec["seed"], "sharpe": dist("sharpe"), "cagr": dist("cagr"), "max_drawdown": dist("max_drawdown"),
                         "final_equity": dist("final_equity"), "sv_beats_share_sharpe": beat("sharpe", lambda a, b: (a or -9) > (b or -9)),
                         "sv_beats_share_cagr": beat("cagr", lambda a, b: a > b)},
              "pool": {**{k: v for k, v in pool_rules.items() if k != "exclude"}, "excluded_symbols": flagged},
              "event_filter": spec.get("event_filter"), "signals_used": len(events),
              "trade_level": {"signals": len(diffs), "mean_excess_vs_random": round(mean_diff, 6), "t_monthly": round(t_diff, 3),
                              "statistic": "winsorized at 1%/99%" if robust else "mean", "raw_mean_excess": round(raw_mean_diff, 6),
                              "median_excess": round(median_diff, 6),
                              "sv_mean": round(statistics.fmean(sv_rets), 6) if sv_rets else None,
                              "random_mean": round(statistics.fmean(rnd_rets), 6) if rnd_rets else None,
                              "sv_win_rate": round(sum(r > 0 for r in sv_rets) / len(sv_rets), 4) if sv_rets else None,
                              "random_win_rate": round(sum(r > 0 for r in rnd_rets) / len(rnd_rets), 4) if rnd_rets else None},
              "style": {"same_exposure": style, "regression": style_regression},
              "verdict": {"checks": checks, "passed": all(checks.values())}, "champion": None, "chosen": None,
              "next_step": spec.get("next_step")}
    return result, gzip.compress(csv_buffer.getvalue().encode(), 9, mtime=0)


def render_selection_report(result):
    pct = lambda x, d=1: "—" if x is None else f"{x * 100:.{d}f}%"
    num = lambda x: "—" if x is None else f"{x:.2f}"
    sv, rnd, tl, w = result["sv"], result["random"], result["trade_level"], result["window"]
    lines = [f"# {result['spec_id']}", "",
             f"Plain-language report written by the research lab on {result.get('completed_at', '—')[:10]}. Every number comes from `result.json` in this folder.", "",
             "## The question", "", result["question"], "",
             "## The short answer", "",
             f"- SV's account Sharpe {num(sv['sharpe'])} beat {pct(rnd['sv_beats_share_sharpe'], 0)} of {rnd['runs']} random accounts (needed {pct(result['criteria']['min_random_percentile'], 0)}).",
             f"- Trade by trade, SV's picks returned {pct(tl['mean_excess_vs_random'], 2)} more than random stocks bought the same day (t {num(tl['t_monthly'])}, needed {num(result['criteria']['min_trade_excess_t'])}).",
             f"- Selection skill shown: **{'yes' if result['verdict']['passed'] else 'no'}**.", "",
             "## Account, " + f"{w['start']} to {w['end']}", "",
             "| Account | Sharpe | Growth a year | Worst fall |", "|---|---|---|---|",
             f"| SV picks | {num(sv['sharpe'])} | {pct(sv['cagr'])} | {pct(sv['max_drawdown'])} |",
             f"| Random picks, middle result | {num(rnd['sharpe']['median'])} | {pct(rnd['cagr']['median'])} | {pct(rnd['max_drawdown']['median'])} |",
             f"| Random picks, best 5% | {num(rnd['sharpe']['p95'])} | {pct(rnd['cagr']['p95'])} | {pct(rnd['max_drawdown']['p5'])} |",
             f"| Random picks, worst 5% | {num(rnd['sharpe']['p5'])} | {pct(rnd['cagr']['p5'])} | {pct(rnd['max_drawdown']['p95'])} |", "",
             "## Trade by trade", "",
             f"{tl['signals']} SV signals. Average trade: SV {pct(tl['sv_mean'], 2)}, random {pct(tl['random_mean'], 2)}. Winning trades: SV {pct(tl['sv_win_rate'])}, random {pct(tl['random_win_rate'])}."
             + (f" Statistic: {tl['statistic']}; median difference {pct(tl.get('median_excess'), 2)}; raw average difference {pct(tl.get('raw_mean_excess'), 2)}." if tl.get("statistic") else "")]
    if result.get("pool", {}).get("excluded_symbols"):
        lines += ["", f"Random picks use SV's tradability floor on the signal day ({', '.join(f'{k} {v}' for k, v in result['pool'].items() if k != 'excluded_symbols')}). "
                  f"Excluded from both sides for provider price errors: {', '.join(result['pool']['excluded_symbols'])}."]
    reg = result["style"].get("regression")
    if reg:
        lines += ["", "## Style check", "",
                  "Same share of the account in each fund on the same days: " + ", ".join(f"{k} Sharpe {num(v['same_exposure_sharpe'])}" for k, v in result["style"]["same_exposure"].items()) + ".",
                  f"After removing market, Nasdaq-100 and small-cap tilts, SV's extra return is {pct(reg['alpha_annual'], 2)} a year (t {num(reg['alpha_t'])})."]
    if result.get("next_step"):
        lines += ["", "## Next step (planned before the run)", "", result["next_step"]]
    return "\n".join(lines) + "\n"


def _account_table(result):
    pct = lambda x, d=1: "—" if x is None else f"{x * 100:.{d}f}%"
    num = lambda x: "—" if x is None else f"{x:.2f}"
    spy = result["spy"]
    lines = ["| Rule | CAGR | Max drawdown | Sharpe | Calmar | CAGR vs SPY | Invested | Trades | Luck check: median Sharpe | Luck check: worst-5% CAGR | Deflated Sharpe | Passed |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|",
             f"| SPY buy and hold | {pct(spy['cagr'])} | {pct(spy['max_drawdown'])} | {num(spy['sharpe'])} | {num(spy['calmar'])} | — | 100% | — | — | — | — | benchmark |"]
    for vid, v in result["variants"].items():
        a, mc = v["account"], v.get("monte_carlo") or {}
        lines.append(f"| {vid} {v['label']} | {pct(a['cagr'])} | {pct(a['max_drawdown'])} | {num(a['sharpe'])} | {num(a['calmar'])} | "
                     f"{pct(v['versus_spy']['cagr_difference'])} | {pct(a['average_exposure'], 0)} | {a['trades_taken']} | "
                     f"{num((mc.get('sharpe') or {}).get('median'))} | {pct((mc.get('cagr') or {}).get('p5'))} | {num(v.get('deflated_sharpe'))} | "
                     f"{'**yes**' if v['verdict']['passed'] else 'no'} |")
    return lines


CHECK_WORDS = {
    "enough_trades": "Enough trades to judge",
    "max_drawdown": "Worst fall within the limit",
    "sharpe_beats_current_rule": "Better Sharpe than the current rule",
    "calmar_beats_current_rule": "Better growth per worst fall (Calmar) than the current rule",
    "sharpe_beats_spy": "Better Sharpe than holding SPY",
    "calmar_beats_spy": "Better growth per worst fall than holding SPY",
    "luck_check_median_sharpe_beats_current_rule": "Still beats the current rule when same-day signal order is shuffled",
    "luck_check_worst_5pct_still_grows": "Even the unluckiest 5% of shuffled runs still grow",
    "every_period_positive": "Account grew in every five-year period",
    "deflated_sharpe": "Not explained by having tried many rules",
}


def render_report(result):
    """Plain-language account report written next to every account result."""
    money = lambda x: f"${x:,.0f}"
    pct = lambda x, d=1: "—" if x is None else f"{x * 100:.{d}f}%"
    num = lambda x: "—" if x is None else f"{x:.2f}"
    spy, w, variants = result["spy"], result["window"], result["variants"]
    chosen = (result.get("chosen") or {}).get("variant")
    met = [vid for vid, v in variants.items() if v.get("goal_1", {}).get("met")]
    best = max(variants, key=lambda v: variants[v]["account"]["sharpe"] or -9)
    lines = [f"# {result['spec_id']}", "",
             f"Plain-language report written by the research lab on {result.get('completed_at', '—')[:10]}. Every number comes from `result.json` in this folder.", "",
             "## The question", "", result["question"], "",
             "## The short answer", ""]
    if result["champion"]:
        lines.append(f"- **{result['champion']}** ({variants[result['champion']]['label']}) passed every check written down before the run.")
    elif result.get("kind") == "allocation":
        lines.append("- No portfolio passed every check written down before the run.")
    else:
        lines.append("- No rule passed every check written down before the run, so the current rule stays.")
    if chosen:
        rule = result["chosen"]["rule"]
        how = rule.get("rule") or rule.get("metric") or "best luck-check Sharpe averaged with its neighbouring settings"
        lines.append(f"- Carried to the next step: **{chosen}** ({variants[chosen]['label']}), picked by the rule fixed before the run "
                     f"({how}{'' if result['chosen']['within_drawdown_limit'] else '; no setting stayed within the drawdown limit'}).")
    lines.append(f"- Goal 1 (match SPY's Sharpe {num(spy['sharpe'])} and Calmar {num(spy['calmar'])} with a worst fall of at most {pct(result['criteria']['max_drawdown'], 0)}): "
                 + (f"met by {', '.join(met)}." if met else f"not met yet. Closest Sharpe: {best} at {num(variants[best]['account']['sharpe'])}."))
    lines += ["", "## The benchmark", "",
              f"Holding SPY from {w['start']} to {w['end']} turned $100,000 into {money(spy['final_equity'])}: {pct(spy['cagr'])} a year, "
              f"worst fall {pct(spy['max_drawdown'])}, Sharpe {num(spy['sharpe'])}, Calmar {num(spy['calmar'])}.", "",
              "## Account results", "",
              "| Rule | $100k became | Growth a year | Worst fall | Sharpe | Calmar | Money invested | Checks passed |",
              "|---|---|---|---|---|---|---|---|"]
    explicit = [v for v in variants if variants[v].get("family") != "grid"]
    grid = sorted((v for v in variants if variants[v].get("family") == "grid"),
                  key=lambda v: -(variants[v]["monte_carlo"] or {}).get("sharpe", {}).get("median", -9))
    shown = list(dict.fromkeys(explicit + ([chosen] if chosen else []) + grid[:5]))
    for vid in shown:
        v, a = variants[vid], variants[vid]["account"]
        checks = v["verdict"]["checks"]
        mark = " (carried forward)" if vid == chosen else ""
        lines.append(f"| {vid}{mark}: {v['label']} | {money(a['final_equity'])} | {pct(a['cagr'])} | {pct(a['max_drawdown'])} | {num(a['sharpe'])} | "
                     f"{num(a['calmar'])} | {pct(a['average_exposure'], 0)} | {sum(checks.values())} of {len(checks)} |")
    if len(variants) > len(shown):
        lines.append(f"\nShowing {len(shown)} of {len(variants)} rules: the references, the one carried forward and the five best luck-check results. All are in `result.json` and the scoreboard.")
    focus = chosen or best
    lines += ["", f"## Checks for {focus}", ""]
    for key, ok in variants[focus]["verdict"]["checks"].items():
        lines.append(f"- {'✓' if ok else '✗'} {CHECK_WORDS.get(key, key)}")
    if result.get("rolling"):
        roll = result["rolling"]
        lines += ["", f"## Rolling {roll['years']}-year windows", "",
                  f"{roll['windows']} windows, starting monthly from {roll['first_window']} to {roll['last_window']}.", "",
                  "| Portfolio | Median Sharpe | Worst 5% Sharpe | Worst fall in any window | Lowest window return | Windows with a gain |",
                  "|---|---|---|---|---|---|"]
        for name, v in roll["per_portfolio"].items():
            lines.append(f"| {name} | {num(v['sharpe_median'])} | {num(v['sharpe_p5'])} | {pct(v['worst_fall'])} | {pct(v['lowest_return'])} | {pct(v['share_positive'], 0)} |")
        if roll.get("core_checks"):
            lines += ["", f"Core checks ({roll.get('core', 'core')}): " + ", ".join(f"{'✓' if ok else '✗'} {k.replace('_', ' ')}" for k, ok in roll["core_checks"].items()),
                      f"Core Sharpe at least the benchmark's in {pct(roll['core_sharpe_beats_benchmark_share'], 0)} of windows. Core confirmed: **{'yes' if roll['core_passed'] else 'no'}**."]
    if result.get("comparisons"):
        lines += ["", "## Questions fixed before the run", ""]
        lines += [f"- {'✓' if c['holds'] else '✗'} {c['question']} ({c['a']} {num(c['a_value'])} vs {c['b']} {num(c['b_value'])})" for c in result["comparisons"]]
    if result.get("chosen") and result["chosen"].get("rule", {}).get("kind") == "improve_on":
        lines += ["", f"Improvement over {result['chosen']['rule']['baseline']}: **{'yes, ' + result['chosen']['variant'] if result['chosen']['improved'] else 'no, the baseline stays'}**."]
    if result.get("excluded"):
        lines += ["", "Not tested on this window: " + "; ".join(f"{e['portfolio']} ({e['reason']})" for e in result["excluded"]) + "."]
    if result.get("next_step"):
        lines += ["", "## Next step (planned before the run)", "", result["next_step"]]
    lines += ["", "## Words used", "",
              "- **Sharpe**: return per unit of day-to-day swing; higher is smoother growth.",
              "- **Calmar**: growth per year divided by the worst fall.",
              "- **Worst fall**: the biggest drop from a previous high, in percent of the account.",
              "- **Luck check**: the same rule re-run 200 times with same-day signals in shuffled order.",
              "- **Money invested**: the average share of the account in stocks; the rest is cash."]
    return "\n".join(lines) + "\n"


def render_scoreboard(results):
    board = {"schema_version": "1.0.0", "experiments": [], "champions": {}}
    lines = ["# Research lab scoreboard", "", "Generated by `research/lab/run_queue.py` from every saved result; do not edit by hand.",
             "Trade-level tables count every signal once per rule; signals overlap, so they are diagnostics, not a portfolio.",
             "Account tables trade the approved $100k research account day by day and are the deciding test.", ""]
    for result in sorted(results, key=lambda r: (r["group"], r["completed_at"])):
        board["experiments"].append({k: result[k] for k in ("spec_id", "experiment_id", "group", "completed_at", "champion")} | {"dataset": result["dataset"]["dataset_id"]})
        if result["champion"]:
            v = result["variants"][result["champion"]]
            board["champions"][result["group"]] = {"spec_id": result["spec_id"], "variant": result["champion"], "rule": v["rule"],
                                                   "overall": v["account"] if result.get("kind") in ("account", "allocation") else v["overall"]}
        if result.get("kind") == "selection":
            r, sv = result["random"], result["sv"]
            lines += [f"## {result['spec_id']} ({result['dataset']['dataset_id']}, SV against {r['runs']} random-pick accounts)", "", result["question"], "",
                      f"SV Sharpe {sv['sharpe']} beat {r['sv_beats_share_sharpe'] * 100:.0f}% of random accounts; trade-level excess {result['trade_level']['mean_excess_vs_random'] * 100:.2f}% "
                      f"(t {result['trade_level']['t_monthly']}). Selection skill shown: **{'yes' if result['verdict']['passed'] else 'no'}**", ""]
            continue
        if result.get("kind") in ("account", "allocation"):
            w = result["window"]
            lines += [f"## {result['spec_id']} ({result['dataset']['dataset_id']}, $100k account {w['start']} to {w['end']})", "", result["question"], "",
                      *_account_table(result), "", f"Champion: **{result['champion'] or 'none passed; current rule stays'}**", ""]
            continue
        lines += [f"## {result['spec_id']} ({result['dataset']['dataset_id']})", "", result["question"], "",
                  "| Variant | Trades | Win | Mean | Median | Per day | PF | E[R] | SQN | vs SPY | Beat SPY | Splits + | Passed |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        pct = lambda x, d=2: "—" if x is None else f"{x * 100:.{d}f}%"
        for vid, v in result["variants"].items():
            o = v["overall"]
            per_day = o.get("mean_return_per_day", o["mean_return"] / o["avg_hold"] if o.get("avg_hold") else None)
            lines.append(f"| {vid} {v['label']} | {o.get('resolved', 0)} | {pct(o.get('win_rate'))} | {pct(o.get('mean_return'))} | {pct(o.get('median_return'))} | "
                         f"{pct(per_day, 3)} | {o.get('profit_factor', '—')} | {o.get('expectancy_r', '—')} | {o.get('sqn', '—')} | {pct(o.get('mean_excess'))} | "
                         f"{pct(o.get('beat_benchmark_rate'), 1)} | {'yes' if v['verdict']['checks']['every_split_positive'] else 'no'} | {'**yes**' if v['verdict']['passed'] else 'no'} |")
        lines += ["", f"Champion: **{result['champion'] or 'none passed; baseline stays'}**", ""]
    return board, "\n".join(lines) + "\n"


def write_outputs(root, result, trades_csv, event, manifests):
    out = pathlib.Path(root) / "research/lab/results" / result["spec_id"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    (out / "trades.csv.gz").write_bytes(trades_csv)
    if result.get("kind") in ("account", "allocation"):
        (out / "REPORT.md").write_text(render_report(result))
    elif result.get("kind") == "selection":
        (out / "REPORT.md").write_text(render_selection_report(result))
    for entry in manifests:
        record = pathlib.Path(root) / "research/lab/datasets" / f"{entry['dataset_id']}.json"
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(entry, indent=1) + "\n")
    events = pathlib.Path(root) / "research/experiment-events.jsonl"
    if event["details"]["spec_sha256"] not in events.read_text():
        with events.open("a") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    results = [json.loads(p.read_text()) for p in (pathlib.Path(root) / "research/lab/results").glob("*/result.json")]
    board, markdown = render_scoreboard(results)
    (pathlib.Path(root) / "research/lab/scoreboard.json").write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n")
    (pathlib.Path(root) / "research/lab/SCOREBOARD.md").write_text(markdown)


def publish(result, trades_csv, event, manifests, attempts=3):
    def git(*args, check=True):
        return subprocess.run(["git", *args], cwd=ROOT, check=check, text=True, capture_output=True)
    for _ in range(attempts):
        git("fetch", "origin", "main")
        git("switch", "--detach", "--force", "origin/main")
        write_outputs(ROOT, result, trades_csv, event, manifests)
        # Keep the published experiment catalog and summary in step with the event log.
        subprocess.run(["python3", "-m", "services.scanner.experiment_catalog"], cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["python3", "-m", "services.scanner.project_status"], cwd=ROOT, check=True, capture_output=True)
        git("add", "--", "research/lab", "research/experiment-events.jsonl", "research/generated/experiment-catalog.json",
            "docs/EXPERIMENT_SUMMARY_ZH.md", "docs/CURRENT_STATUS_ZH.md")
        if git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return
        git("-c", "user.name=sage-vista-bot", "-c", "user.email=sage-vista-bot@users.noreply.github.com",
            "commit", "-m", f"research: lab result {result['spec_id']} [skip ci]")
        if git("push", "origin", "HEAD:main", check=False).returncode == 0:
            return
    raise RuntimeError("could not publish lab result after retries")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--max-specs", type=int, default=3)
    args = parser.parse_args(argv)
    if args.publish and in_eod_window():
        print("Inside the 23:30-04:30 UTC EOD window; nothing published.")
        return
    ran = 0
    for path, spec in pending_specs()[: args.max_specs]:
        sha = spec_sha(path)
        loaded, manifests = {}, []

        def load(ds):
            # One build per dataset id per run, even when a spec names it twice.
            if ds["id"] not in loaded:
                loaded[ds["id"]] = ensure_dataset(ds, args.publish)
                if loaded[ds["id"]][2]:
                    manifests.append(loaded[ds["id"]][2])
            return loaded[ds["id"]]

        data, entry, _ = load(spec["dataset"])
        benchmark = None
        if spec.get("benchmark"):
            bench_data, bench_entry, _ = load(spec["benchmark"]["dataset"])
            symbol = spec["benchmark"]["symbol"]
            benchmark = {"symbol": symbol, "series": bench_data["prices"][symbol], "entry": bench_entry}
        run = {"account": run_account_spec, "allocation": run_allocation_spec, "selection": run_selection_spec}.get(spec.get("kind"), run_spec)
        extra = {}
        if spec.get("core"):
            extra["core_data"] = load(spec["core"]["dataset"])[0]
        if spec.get("style"):
            extra["style_data"] = load(spec["style"]["dataset"])[0]
        result, trades_csv = run(spec, data, entry, spec.get("cost_per_side", 0.001), benchmark, **extra)
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        result |= {"spec_sha256": sha, "completed_at": now, "code_commit": os.environ.get("GITHUB_SHA", "local")}
        run_url = f"{os.environ.get('GITHUB_SERVER_URL', '')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
        event = {"experiment_id": spec["experiment_id"], "event": "completed", "event_at": now,
                 "time_source": "github_actions" if os.environ.get("GITHUB_ACTIONS") else "local",
                 "source_ref": run_url if os.environ.get("GITHUB_ACTIONS") else None,
                 "details": {"lab_spec": spec["id"], "spec_sha256": sha, "result": f"research/lab/results/{spec['id']}/result.json",
                             "dataset": entry["dataset_id"], "champion": result["champion"]}}
        if args.publish:
            publish(result, trades_csv, event, manifests)
        else:
            (WORK / "preview").mkdir(parents=True, exist_ok=True)
            (WORK / "preview" / f"{spec['id']}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
        print(f"{spec['id']}: champion={result['champion']} ({entry['events']} events)")
        ran += 1
    if not ran:
        print("No pending lab specs.")


if __name__ == "__main__":
    main()
