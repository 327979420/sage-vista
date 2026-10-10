import csv
import datetime as dt
import gzip
import importlib.util
import io
import json
import math
import pathlib
import random
import tempfile
import unittest
from unittest import mock

from research.lab import account, allocation, datasets, levels, run_queue, selection, structure, timeframe
from research.lab.exit_rules import simulate
from research.lab.metrics import evaluate, summarise
from services.scanner.support_risk import simulate_execution

ROOT = pathlib.Path(__file__).resolve().parents[1]
A0 = {"stop": {"kind": "support_cap", "buffer": 0.05, "cap": 0.10}, "targets": [{"r": 2.0, "fraction": 1.0}], "max_hold": 40}


def walk(seed, n=160, start=100.0, drift=0.0005, vol=0.02):
    rng, price, bars = random.Random(seed), start, []
    day = dt.date(2020, 1, 1)
    for _ in range(n):
        o = price * (1 + rng.gauss(0, vol / 2))
        c = o * (1 + rng.gauss(drift, vol))
        h, l = max(o, c) * (1 + abs(rng.gauss(0, vol / 2))), min(o, c) * (1 - abs(rng.gauss(0, vol / 2)))
        bars.append({"date": day.isoformat(), "open": o, "high": h, "low": l, "close": c, "volume": 1000})
        price, day = c, day + dt.timedelta(days=1)
    return bars


def flat(prices):
    return [{"date": f"2020-01-{i + 1:02d}", "open": o, "high": h, "low": l, "close": c, "volume": 1} for i, (o, h, l, c) in enumerate(prices)]


class ExitRuleTests(unittest.TestCase):
    def test_baseline_reproduces_the_production_rule_exactly(self):
        checked = 0
        for seed in range(400):
            bars = walk(seed)
            entry_index = 60
            plan = {"level": bars[entry_index - 1]["close"] * random.Random(seed).uniform(0.8, 0.99)} if seed % 4 else {}
            lab = simulate(bars, entry_index, A0, plan, cost_per_side=0)
            prod = simulate_execution(bars[entry_index]["open"], plan, bars[entry_index:])
            if prod["status"] != "resolved":
                self.assertNotEqual(lab["status"], "resolved")
                continue
            checked += 1
            self.assertAlmostEqual(lab["gross_return"], prod["return"], places=6)
            self.assertEqual(lab["held"], prod["holding_sessions"])
            self.assertEqual(lab["exit_reason"], {"time_40d": "time"}.get(prod["exit_reason"], prod["exit_reason"]))
        self.assertGreater(checked, 300)

    def test_gap_below_stop_fills_at_the_open_and_costs_are_charged_twice(self):
        bars = flat([(100, 101, 99, 100)] * 30 + [(100, 101, 99, 100), (80, 81, 79, 80)])
        variant = {"stop": {"kind": "pct", "pct": 0.10}, "targets": [], "max_hold": 40}
        result = simulate(bars, 30, variant, cost_per_side=0.001)
        self.assertEqual(result["exit_reason"], "stop_gap")
        self.assertAlmostEqual(result["gross_return"], -0.2)
        self.assertAlmostEqual(result["net_return"], -0.202)
        self.assertAlmostEqual(result["r_multiple"], -2.02)

    def test_trailing_stop_only_rises_and_uses_completed_bars(self):
        rising = [(100 + i, 101 + i, 99 + i, 100 + i) for i in range(40)]
        bars = flat([(100, 101, 99, 100)] * 25 + rising + [(130, 131, 100, 101)])
        variant = {"stop": {"kind": "pct", "pct": 0.20}, "targets": [], "trail": {"kind": "pct_close", "pct": 0.08}, "max_hold": 100}
        result = simulate(bars, 25, variant, cost_per_side=0)
        self.assertEqual(result["exit_reason"], "trail")
        highest_close = 139
        self.assertAlmostEqual(result["fills"][-1]["price"], round(highest_close * 0.92, 6))

    def test_partial_target_then_trail_and_time_exit(self):
        bars = flat([(100, 101, 99, 100)] * 25 + [(100, 101, 99, 100)] + [(100 + 3 * i, 102 + 3 * i, 99 + 3 * i, 101 + 3 * i) for i in range(1, 15)])
        variant = {"stop": {"kind": "pct", "pct": 0.05}, "targets": [{"r": 2.0, "fraction": 0.5}],
                   "trail": {"kind": "pct_close", "pct": 0.5}, "trail_after_target": True, "max_hold": 10}
        result = simulate(bars, 25, variant, cost_per_side=0)
        self.assertEqual([f["reason"] for f in result["fills"]], ["target", "time"])
        self.assertAlmostEqual(sum(f["fraction"] for f in result["fills"]), 1.0)

    def test_moving_average_exit_happens_at_the_next_open(self):
        bars = flat([(100, 101, 99, 100)] * 60 + [(100, 101, 90, 91), (92, 93, 91, 92)])
        variant = {"stop": {"kind": "pct", "pct": 0.30}, "targets": [], "trail": {"kind": "ma_close", "period": 50}, "max_hold": 100}
        result = simulate(bars, 59, variant, cost_per_side=0)
        self.assertEqual(result["exit_reason"], "trend_exit")
        self.assertEqual(result["fills"][-1]["price"], 92)

    def test_unfinished_trades_are_observing_not_counted(self):
        bars = flat([(100, 101, 99, 100)] * 30)
        self.assertEqual(simulate(bars, 25, {"stop": {"kind": "pct", "pct": 0.5}, "targets": [], "max_hold": 40})["status"], "observing")


class MetricsTests(unittest.TestCase):
    def test_summary_and_pass_checks(self):
        trades = [{"status": "resolved", "net_return": r, "r_multiple": r / 0.05, "held": 10, "exit_reason": e}
                  for r, e in [(0.10, "target"), (-0.05, "stop"), (0.10, "target"), (-0.05, "stop"), (0.02, "time")]]
        s = summarise(trades)
        self.assertEqual(s["resolved"], 5)
        self.assertAlmostEqual(s["profit_factor"], round(0.22 / 0.10, 4))
        self.assertAlmostEqual(s["expectancy_r"], round((2 - 1 + 2 - 1 + 0.4) / 5, 4))
        self.assertEqual(s["stop_rate"], 0.4)
        criteria = {"min_expectancy_r": 0.2, "min_profit_factor": 1.3, "min_sqn": 0.5, "min_split_trades": 3, "min_trades": 5}
        verdict = evaluate(s, {"a": s, "tiny": {"resolved": 1, "mean_return": -1}}, [s], criteria)
        self.assertTrue(verdict["passed"])
        failing = evaluate(s, {"a": {**s, "mean_return": -0.01}}, [], criteria)
        self.assertFalse(failing["passed"])
        self.assertFalse(failing["checks"]["every_split_positive"])

    def test_excess_over_the_benchmark_is_clustered_by_month_and_checked_per_split(self):
        trades = [{"status": "resolved", "net_return": 0.05, "r_multiple": 0.5, "held": 20, "exit_reason": "time",
                   "excess_return": x, "cluster": month} for month, x in [("2020-01", 0.02), ("2020-01", 0.04), ("2020-02", 0.01), ("2020-03", -0.01)]]
        s = summarise(trades)
        self.assertEqual(s["mean_return_per_day"], 0.0025)
        self.assertEqual((s["benchmark_trades"], s["excess_months"]), (4, 3))
        self.assertAlmostEqual(s["mean_excess"], 0.015)
        self.assertEqual(s["beat_benchmark_rate"], 0.75)
        # Monthly means 0.03, 0.01, -0.01: mean 0.01, sample sd 0.02, t = 0.01 / (0.02 / sqrt(3)).
        self.assertAlmostEqual(s["excess_t_monthly"], round(0.01 / (0.02 / 3 ** 0.5), 3))
        criteria = {"min_expectancy_r": 0, "min_profit_factor": 0, "min_sqn": -9, "min_split_trades": 1, "min_trades": 1,
                    "min_excess_t": 0.5, "every_split_beats_benchmark": True}
        self.assertTrue(evaluate(s, {"a": s}, [], criteria)["passed"])
        lagging = evaluate(s, {"a": s, "b": {**s, "mean_excess": -0.001}}, [], criteria)
        self.assertFalse(lagging["checks"]["every_split_beats_benchmark"])
        self.assertNotIn("excess_t", evaluate(s, {}, [], {k: v for k, v in criteria.items() if k != "min_excess_t"})["checks"])


class BenchmarkTests(unittest.TestCase):
    SERIES = {"date": ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-06"],
              "open": [100.0, 102.0, 104.0, 110.0], "close": [101.0, 103.0, 105.0, 111.0]}

    def test_benchmark_is_held_over_the_same_days_and_fractions(self):
        fills = [{"date": "2020-01-03", "fraction": 0.5, "reason": "target"}, {"date": "2020-01-06", "fraction": 0.5, "reason": "stop_gap"}]
        # Buy at the 01-02 open (102); half sold at the 01-03 close (105), half at the 01-06 open (110).
        expected = 0.5 * (105 / 102 - 1) + 0.5 * (110 / 102 - 1)
        self.assertAlmostEqual(run_queue.benchmark_gross(self.SERIES, "2020-01-02", fills), expected)

    def test_a_day_the_benchmark_did_not_trade_uses_its_last_close(self):
        fills = [{"date": "2020-01-05", "fraction": 1.0, "reason": "stop_gap"}]
        self.assertAlmostEqual(run_queue.benchmark_gross(self.SERIES, "2020-01-01", fills), 105 / 100 - 1)
        self.assertIsNone(run_queue.benchmark_gross(self.SERIES, "2019-12-31", fills))


def dated(prices, start="2025-01-01"):
    day = dt.date.fromisoformat(start)
    out = []
    for o, h, l, c in prices:
        out.append({"date": day.isoformat(), "open": o, "high": h, "low": l, "close": c, "volume": 1})
        day += dt.timedelta(days=1)
    return out


def trade(symbol, entry_date, price, fills, closes, priority=0, event_id=None, stop=None):
    return {"event_id": event_id or f"{symbol}-{entry_date}", "symbol": symbol, "signal_date": entry_date, "priority": priority,
            "entry_date": entry_date, "entry_price": price, "stop": price * 0.9 if stop is None else stop, "fills": fills, "closes": closes}


class AccountTests(unittest.TestCase):
    CAL = [f"2025-01-0{i}" for i in range(1, 7)]
    SCENARIO = {"initial_cash": 1000.0, "allocation_fraction": 0.5, "max_positions": 1, "cost_rate": 0.01, "fractional_shares": False}

    def test_entries_before_exits_slots_same_stock_whole_shares_and_fees(self):
        c = self.CAL
        trades = [
            trade("A", c[1], 100.0, [(c[3], 110.0, 1.0)], [(c[1], 101.0), (c[2], 104.0), (c[3], 109.0)], priority=1),
            trade("B", c[1], 50.0, [(c[2], 55.0, 1.0)], [(c[1], 50.0), (c[2], 55.0)], priority=2),   # slot taken by A
            trade("A", c[2], 104.0, [(c[4], 100.0, 1.0)], [(c[2], 104.0), (c[3], 100.0), (c[4], 100.0)], event_id="A-again"),  # A still held
            trade("C", c[3], 20.0, [(c[4], 21.0, 1.0)], [(c[3], 20.0), (c[4], 21.0)]),  # A exits the same day, after entries
            trade("A", c[4], 120.0, [], [(c[4], 121.0)]),  # open at the end, valued at the last close
        ]
        aligned, notes = account.align(trades, c)
        path = account.run_account(aligned, len(c), self.SCENARIO)
        cash_after_a = 1000 - 5 * 100 * 1.01 + 5 * 110 * 0.99
        cash_after_last = cash_after_a - 4 * 120 * 1.01
        self.assertEqual(path["skipped"], {"position_limit": 2, "same_stock_held": 1})
        self.assertEqual([round(v, 6) for v in path["equity"]],
                         [1000.0, round(495 + 5 * 101, 6), round(495 + 5 * 104, 6), round(cash_after_a, 6),
                          round(cash_after_last + 4 * 121, 6), round(cash_after_last + 4 * 121, 6)])
        self.assertEqual(path["open_at_end"], 1)
        self.assertEqual(len(path["trades"]), 1)
        self.assertAlmostEqual(path["trades"][0]["pnl"], 5 * 110 * 0.99 - 505, places=4)
        self.assertEqual(notes["stale_valuations"], 1)  # the open trade has no bar on the last calendar day

    def test_a_stock_whose_prices_stop_is_sold_at_its_last_close(self):
        bars = dated([(100, 101, 99, 100)] * 5 + [(100, 102, 99, 101), (101, 103, 100, 102)])
        variant = {"stop": {"kind": "pct", "pct": 0.5}, "targets": [], "max_hold": 60}
        result = simulate(bars, 5, variant, cost_per_side=0)
        self.assertEqual(result["status"], "observing")
        event = {"event_id": "X", "symbol": "X", "signal_date": bars[4]["date"]}
        delisted = account.candidate(event, bars, 5, result, 0, "2025-03-01")
        self.assertTrue(delisted["data_ended"])
        self.assertEqual(delisted["fills"], [(bars[6]["date"], 102.0, 1.0)])
        still_open = account.candidate(event, bars, 5, result, 0, bars[6]["date"])
        self.assertEqual((still_open["data_ended"], still_open["fills"]), (False, []))

    def test_cash_shortfall_and_partial_fills(self):
        c = self.CAL
        tight = {**self.SCENARIO, "allocation_fraction": 0.995, "max_positions": 2}
        trades = [trade("A", c[1], 10.0, [(c[2], 12.0, 0.5), (c[3], 13.0, 0.5)], [(c[1], 10.0), (c[2], 12.0), (c[3], 13.0)], priority=1),
                  trade("B", c[1], 10.0, [(c[2], 11.0, 1.0)], [(c[1], 10.0), (c[2], 11.0)], priority=2)]
        path = account.run_account(account.align(trades, c)[0], len(c), tight)
        self.assertEqual(path["skipped"], {"cash_or_whole_share_insufficient": 1})
        shares = math.floor(995 / 10)
        expected = 1000 - shares * 10 * 1.01 + math.floor(shares * 0.5) * 12 * 0.99 + (shares - math.floor(shares * 0.5)) * 13 * 0.99
        self.assertAlmostEqual(path["equity"][-1], expected)

    def test_risk_sizing_uses_the_previous_close_value_with_caps_and_an_open_risk_limit(self):
        c = self.CAL
        scenario = {**self.SCENARIO, "cost_rate": 0.0}
        rules = {"risk_per_trade": 0.01, "position_cap": 0.25, "max_positions": 5, "heat_cap": 0.015}
        trades = [trade("A", c[1], 100.0, [(c[4], 100.0, 1.0)], [(c[i], 100.0) for i in range(1, 5)], priority=1, stop=95.0),   # risk $5 a share
                  trade("B", c[1], 50.0, [(c[4], 50.0, 1.0)], [(c[i], 50.0) for i in range(1, 5)], priority=2, stop=40.0),     # risk $10 a share
                  trade("C", c[2], 10.0, [(c[4], 10.0, 1.0)], [(c[i], 10.0) for i in range(2, 5)], priority=1, stop=5.0)]
        path = account.run_account(account.align(trades, c)[0], len(c), scenario, rules=rules)
        # A: min(25% x 1000 / 100 = 2.5, 1% x 1000 / 5 = 2) -> 2 shares, $10 at risk.
        # B: min(25% x 1000 / 50 = 5, 1% x 1000 / 10 = 1) -> 1 share; open risk 10 + 10 = 20 > 15 -> skipped.
        # C: min(25 shares, 10 / 5 = 2) -> 2 shares; open risk 10 + 10 = 20 > 15 -> skipped.
        self.assertEqual(path["skipped"], {"open_risk_limit": 2})
        self.assertEqual(path["trades"][0]["shares"], 2)
        loose = account.run_account(account.align(trades, c)[0], len(c), scenario, rules={**rules, "heat_cap": 0.05})
        self.assertEqual(sorted(t["shares"] for t in loose["trades"]), [1, 2, 2])

    def test_core_funds_purchases_takes_proceeds_and_keeps_the_cash_reserve(self):
        c = self.CAL
        scenario = {**self.SCENARIO, "cost_rate": 0.0}
        rules = {"risk_per_trade": 1.0, "position_cap": 0.10, "max_positions": 2}
        core = {"returns": [0.0, 0.01, 0.0, 0.0, 0.0, 0.0], "cash_returns": [0.0] * 6, "cash_buffer": 0.05, "cost": 0.01, "month_ends": {3}}
        trades = [trade("A", c[1], 10.0, [(c[2], 12.0, 1.0)], [(c[1], 10.0), (c[2], 12.0)], stop=5.0)]
        path = account.run_account(account.align(trades, c)[0], len(c), scenario, rules=rules, core=core)
        cash, core_value = 50.0, 950.0
        self.assertAlmostEqual(path["equity"][0], 1000.0)
        # Day 1: 10 shares (10% of 1000) paid by selling 100 / 0.99 of the core, then the core gains 1%.
        core_value = (core_value - 100 / 0.99) * 1.01
        self.assertAlmostEqual(path["equity"][1], cash + core_value + 10 * 10.0)
        # Day 2: sold for 120; 120 x 0.99 goes back into the core.
        core_value += 120 * 0.99
        self.assertAlmostEqual(path["equity"][2], cash + core_value)
        # Day 3 is a month end: the reserve is reset to 5% and the move costs 1%.
        nav = cash + core_value
        move = 0.05 * nav - cash
        self.assertAlmostEqual(path["equity"][3], nav - abs(move) * 0.01)
        no_stocks = account.run_account(account.align(trades, c)[0], len(c), scenario, rules={**rules, "max_positions": 0}, core=core)
        self.assertEqual(no_stocks["skipped"], {"position_limit": 1})
        self.assertAlmostEqual(no_stocks["equity"][1], 50 + 950 * 1.01)

    def test_signals_before_the_window_are_not_traded(self):
        c = self.CAL
        early = trade("A", "2024-12-31", 10.0, [(c[1], 11.0, 1.0)], [("2024-12-31", 10.0), (c[0], 10.5), (c[1], 11.0)])
        self.assertEqual(account.align([early], c)[0], [])

    def test_satellite_is_added_only_when_it_beats_the_same_core_without_sv(self):
        variants = {f"C{core}-M{m}": {"account": {"core": core, "max_positions": m}, "rule": {"account": {"core": core, "max_positions": m}}}
                    for core in ("PERM", "AW") for m in (0, 4, 7)}
        stats = {"CPERM-M0": (1.00, 0.40, 0.18), "CPERM-M4": (1.05, 0.41, 0.19), "CPERM-M7": (1.055, 0.42, 0.21),
                 "CAW-M0": (0.84, 0.29, 0.23), "CAW-M4": (0.80, 0.30, 0.24), "CAW-M7": (0.86, 0.31, 0.24)}
        summary = {k: {"account": {"sharpe": a, "calmar": b, "max_drawdown": d}, "rule": variants[k]["rule"]} for k, (a, b, d) in stats.items()}
        chosen = run_queue.choose_satellite(summary, variants, {"core": "PERM", "max_drawdown": 0.25, "tie_tolerance": 0.01})
        self.assertEqual(chosen["variant"], "CPERM-M4")  # M7 is better by less than the tolerance, so the smaller satellite wins
        self.assertTrue(chosen["sv_added"])
        self.assertEqual(chosen["also_better_on"], {"AW": False})
        summary["CPERM-M4"]["account"]["calmar"] = 0.39
        summary["CPERM-M7"]["account"]["max_drawdown"] = 0.30
        self.assertFalse(run_queue.choose_satellite(summary, variants, {"core": "PERM", "max_drawdown": 0.25, "tie_tolerance": 0.01})["sv_added"])

    def test_grid_variants_neighbours_and_plateau_choice(self):
        spec = {"variants": [{"id": "A0"}], "grid": {"exit": {"stop": {"kind": "pct", "pct": 0.1}, "targets": [], "max_hold": 40},
                                                   "settings": {"risk_per_trade": [0.005, 0.01], "max_positions": [10, 20]}}}
        variants, neighbours = run_queue.expand_variants(spec)
        self.assertEqual(sorted(neighbours), ["R0.5-M10", "R0.5-M20", "R1-M10", "R1-M20"])
        self.assertEqual(sorted(neighbours["R0.5-M10"]), ["R0.5-M20", "R1-M10"])
        self.assertEqual(variants["R1-M20"]["account"], {"risk_per_trade": 0.01, "max_positions": 20})
        self.assertEqual(variants["R1-M20"]["label"], "Risk 1%, up to 20 stocks")
        sharpe = {"R0.5-M10": 0.50, "R0.5-M20": 0.52, "R1-M10": 0.70, "R1-M20": 0.51}
        dd = {"R0.5-M10": 0.20, "R0.5-M20": 0.22, "R1-M10": 0.30, "R1-M20": 0.24}
        summary = {v: {"monte_carlo": {"sharpe": {"median": sharpe[v]}}, "account": {"max_drawdown": dd[v]}, "rule": variants[v]} for v in sharpe}
        chosen = run_queue.choose_plateau(summary, neighbours, {"max_drawdown": 0.25, "tie_tolerance": 0.01})
        # R1-M10 is the single peak but falls 30%; among the rest the best neighbourhood average wins.
        self.assertEqual(chosen["variant"], "R0.5-M10")
        self.assertTrue(chosen["within_drawdown_limit"])

    def test_curve_statistics_benchmark_and_deflated_sharpe(self):
        dates = ["2020-01-01", "2020-07-01", "2021-01-01"]
        stats = account.curve_stats([1100.0, 990.0, 1188.0], dates, 1000.0)
        self.assertAlmostEqual(stats["max_drawdown"], 0.1)
        self.assertAlmostEqual(stats["total_return"], 0.188)
        self.assertAlmostEqual(stats["cagr"], round(1.188 ** (365.25 / 366) - 1, 6))
        rets = [0.1, -0.1, 0.2]
        mean, sd = sum(rets) / 3, (sum((r - 0.0666666667) ** 2 for r in rets) / 2) ** 0.5
        self.assertAlmostEqual(stats["sharpe"], round(mean / sd * 252 ** 0.5, 4), places=3)
        series = {"date": dates, "open": [100.0, 0, 0], "close": [102.0, 51.0, 102.0]}
        self.assertEqual([round(r, 6) for r in account.benchmark_returns(series, dates)], [0.02, -0.5, 1.0])
        one = account.deflated_sharpe(0.05, 1000, 0.0, 3.0, 1, 0.0)
        self.assertAlmostEqual(one, round(statistics_cdf(0.05 * math.sqrt(999) / math.sqrt(1 + 2 / 4 * 0.0025)), 4))
        self.assertLess(account.deflated_sharpe(0.05, 1000, 0.0, 3.0, 24, 0.0004), one)
        v = account.versus([0.02, -0.01, 0.03], [0.01, -0.005, 0.015])
        self.assertAlmostEqual(v["beta"], 2.0)
        self.assertAlmostEqual(v["alpha_annual"], 0.0)

    def test_account_checks(self):
        base = {"account": {"trades_taken": 500, "max_drawdown": 0.2, "sharpe": 0.5, "calmar": 0.3}, "monte_carlo": {"sharpe": {"median": 0.5}, "cagr": {"p5": 0.01}}}
        good = {"account": {"trades_taken": 500, "max_drawdown": 0.2, "sharpe": 0.8, "calmar": 0.5}, "monte_carlo": {"sharpe": {"median": 0.7}, "cagr": {"p5": 0.02}},
                "splits": {"a": 0.1, "b": 0.05}, "deflated_sharpe": 0.97}
        spy = {"sharpe": 0.6, "calmar": 0.2}
        criteria = {"min_trades": 200, "max_drawdown": 0.25, "beat_baseline": ["sharpe", "calmar"], "beat_benchmark": ["sharpe", "calmar"],
                    "mc_runs": 5, "mc_p5_cagr_min": 0.0, "every_split_positive": True, "min_deflated_sharpe": 0.95}
        self.assertTrue(account.evaluate(good, base, spy, criteria)["passed"])
        deep = {**good, "account": {**good["account"], "max_drawdown": 0.3}}
        self.assertFalse(account.evaluate(deep, base, spy, criteria)["checks"]["max_drawdown"])
        weak_period = {**good, "splits": {"a": 0.1, "b": -0.01}}
        self.assertFalse(account.evaluate(weak_period, base, spy, criteria)["checks"]["every_period_positive"])
        lucky = {**good, "deflated_sharpe": 0.9}
        self.assertFalse(account.evaluate(lucky, base, spy, criteria)["passed"])

    def test_account_spec_end_to_end_is_deterministic(self):
        prices, events = {}, []
        for k in range(16):
            bars = walk(3000 + k, n=320)
            prices[f"S{k}"] = {"date": [b["date"] for b in bars], **{f: [b[f] for b in bars] for f in datasets.FIELDS}}
            for at in (60, 110, 160):
                events.append({"event_id": f"S{k}-{at}", "symbol": f"S{k}", "signal_date": bars[at]["date"], "score": (k * 7 + at) % 50})
        spec = json.loads((ROOT / "research/lab/queue/a2-account-20y-v1.json").read_text())
        spec["splits"] = [{"id": "all", "from": "2000-01-01", "to": "2100-01-01"}]
        spec["criteria"] = {**spec["criteria"], "mc_runs": 4, "min_trades": 1}
        entry = {"dataset_id": "synthetic", "asset": "-", "sha256": "-", "events": len(events), "symbols": 16}
        bench = {"symbol": "SPY", "series": prices["S0"], "entry": entry}
        first, csv_one = run_queue.run_account_spec(spec, {"events": events, "prices": prices}, entry, 0.001, bench)
        second, csv_two = run_queue.run_account_spec(spec, {"events": events, "prices": prices}, entry, 0.001, bench)
        self.assertEqual(first, second)
        self.assertEqual(csv_one, csv_two)
        self.assertEqual(first["kind"], "account")
        self.assertEqual(first["n_trials"], 15 + len(spec["variants"]))
        self.assertIn(first["champion"], [None, *first["variants"]])
        for v in first["variants"].values():
            a = v["account"]
            self.assertLessEqual(a["trades_taken"] + a["open_at_end"] + sum(a["skipped"].values()), len(events))
            self.assertEqual(v["monte_carlo"]["runs"], 4)
            self.assertIn("luck_check_median_sharpe_beats_current_rule", v["verdict"]["checks"])
        self.assertEqual(len(first["curves"]["dates"]), len(first["curves"]["SPY"]))
        board, markdown = run_queue.render_scoreboard([{**first, "completed_at": "2026-10-08T00:00:00+00:00"}])
        self.assertIn("SPY buy and hold", markdown)

    def test_sizing_grid_spec_runs_and_writes_a_plain_language_report(self):
        prices, events = {}, []
        for k in range(12):
            bars = walk(4000 + k, n=300)
            prices[f"S{k}"] = {"date": [b["date"] for b in bars], **{f: [b[f] for b in bars] for f in datasets.FIELDS}}
            for at in (60, 120, 180):
                events.append({"event_id": f"S{k}-{at}", "symbol": f"S{k}", "signal_date": bars[at]["date"], "score": (k * 5 + at) % 40})
        spec = json.loads((ROOT / "research/lab/queue/p1-size-risk-20y-v1.json").read_text())
        spec["splits"] = [{"id": "all", "from": "2000-01-01", "to": "2100-01-01"}]
        spec["criteria"] = {**spec["criteria"], "mc_runs": 3, "min_trades": 1}
        spec.pop("window")
        entry = {"dataset_id": "synthetic", "asset": "-", "sha256": "-", "events": len(events), "symbols": 12}
        result, _ = run_queue.run_account_spec(spec, {"events": events, "prices": prices}, entry, 0.001, {"symbol": "SPY", "series": prices["S0"], "entry": entry})
        self.assertEqual(len(result["variants"]), 38)
        self.assertIn(result["chosen"]["variant"], result["variants"])
        self.assertEqual(result["variants"][result["chosen"]["variant"]]["family"], "grid")
        for v in result["variants"].values():
            self.assertIn("met", v["goal_1"])
        with self.assertRaisesRegex(ValueError, "window_ends_before_last_trade"):
            short = {**spec, "window": {"start": "2000-01-01", "end": "2020-01-02"}, "grid": {**spec["grid"], "settings": {"risk_per_trade": [0.01]}}}
            run_queue.run_account_spec(short, {"events": events, "prices": prices}, entry, 0.001, {"symbol": "SPY", "series": prices["S0"], "entry": entry})
        report = run_queue.render_report({**result, "completed_at": "2026-10-09T00:00:00+00:00"})
        for heading in ("## The short answer", "## The benchmark", "## Account results", "## Next step (planned before the run)", "carried forward"):
            self.assertIn(heading, report)

    @unittest.skipUnless(importlib.util.find_spec("vectorbt"), "VectorBT is installed only in the isolated account environment")
    def test_lab_account_matches_the_approved_vectorbt_account(self):
        from research.backtest.account_runner import account as legacy_account
        from research.backtest.run_store import POLICY
        days = [d.isoformat() for d in (dt.date(2025, 1, 2) + dt.timedelta(days=i) for i in range(200)) if d.weekday() < 5][:120]
        rows = {}
        for k, symbol in enumerate("ABCD"):
            rng, price, series = random.Random(k), 100.0, []
            for d in days:
                o = price * (1 + rng.gauss(0, 0.01))
                c = o * (1 + rng.gauss(0.001, 0.02))
                series.append({"date": d, "open": o, "high": max(o, c) * 1.01, "low": min(o, c) * 0.99, "close": c, "adjusted_close": c, "volume": 1})
                price = c
            rows[symbol] = series
        events = [{"event_id": f"{s}-{i}", "symbol": s, "signal_date": days[i],
                   "selection": {"rank": r, "execution_policy_version": POLICY, "support_plan": {"level": rows[s][i]["close"] * 0.95}}}
                  for i in (5, 20, 35, 50, 70, 90) for r, s in enumerate("ABCD", 1)]
        config = {"initial_cash": 1000.0, "allocation_fraction": 0.3, "max_positions": 2, "cost_rate": 0.001, "fractional_shares": False}
        equity, _, _ = legacy_account(events, rows, days, config)
        candidates = []
        for e in events:
            bars = rows[e["symbol"]]
            entry_index = days.index(e["signal_date"]) + 1
            result = simulate(bars, entry_index, A0, e["selection"]["support_plan"], cost_per_side=0.001)
            if result["status"] in ("resolved", "observing"):
                candidates.append(account.candidate(e, bars, entry_index, result, e["selection"]["rank"], days[-1]))
        path = account.run_account(account.align(candidates, days)[0], len(days), config)
        self.assertEqual(len(path["equity"]), len(equity))
        self.assertGreater(len(path["trades"]), 5)
        self.assertGreater(sum(path["skipped"].values()), 5)
        # Lab fills are stored to 6 decimals, so values agree to a hundredth of a cent.
        for ours, theirs in zip(path["equity"], equity.tolist()):
            self.assertAlmostEqual(ours, theirs, places=4)


def monthly_series(closes, start="2020-01-31"):
    """One session per month end, plus a mid-month session, with given month-end closes."""
    dates, opens, out = [], [], []
    day = dt.date.fromisoformat(start)
    for c in closes:
        mid = day.replace(day=15)
        dates += [mid.isoformat(), day.isoformat()]
        opens += [c, c]
        out += [c, c]
        day = (day + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
        day = (day.replace(day=28) + dt.timedelta(days=4))
        day = day - dt.timedelta(days=day.day)
    return {"date": dates, "open": opens, "close": out}


class AllocationTests(unittest.TestCase):
    def test_static_weights_drift_between_rebalances_and_costs_come_out_of_the_account(self):
        prices = allocation.Prices({"A": {"date": ["2020-01-01", "2020-01-02", "2020-01-03"], "open": [10.0, 10.0, 20.0], "close": [10.0, 20.0, 20.0]},
                                    "B": {"date": ["2020-01-01", "2020-01-02", "2020-01-03"], "open": [10.0, 10.0, 10.0], "close": [10.0, 10.0, 10.0]}})
        run = allocation.simulate({"rule": "static", "rebalance": "annual", "weights": {"A": 0.5, "B": 0.5}}, prices, ["2020-01-02", "2020-01-03"], 0.01, 1000.0, "2020-01-01")
        invest = 1000 - 1000 * 0.01  # the cost estimate on 1000 of buying comes out of the value first
        left = 1000 - invest * 1.01  # actual cost is on the 990 bought, so 0.10 stays in cash
        self.assertAlmostEqual(run["equity"][0], left + invest / 2 / 10 * 20 + invest / 2)  # A doubled, no rebalance until December
        self.assertGreaterEqual(left, 0)
        self.assertAlmostEqual(run["equity"][1], run["equity"][0])

    def test_faber_timing_moves_a_slice_to_cash_below_its_ten_month_average(self):
        rising = monthly_series([10 + i for i in range(12)])
        falling = monthly_series([30 - i for i in range(12)])
        cash = monthly_series([1.0] * 12)
        prices = allocation.Prices({"UP": rising, "DOWN": falling, "CASH": cash})
        day = rising["date"][-1]
        w = allocation.target_weights({"rule": "timing", "weights": {"UP": 0.5, "DOWN": 0.5}, "months": 10, "cash": "CASH"}, prices, day)
        self.assertEqual(w, {"UP": 0.5, "CASH": 0.5})

    def test_dual_momentum_picks_the_stronger_stock_fund_or_bonds(self):
        n = 14
        prices = allocation.Prices({"US": monthly_series([100 + 2 * i for i in range(n)]), "INTL": monthly_series([100 + 3 * i for i in range(n)]),
                                    "BOND": monthly_series([100.0] * n), "CASH": monthly_series([100 + 0.1 * i for i in range(n)])})
        rule = {"rule": "dual_momentum", "risky": ["US", "INTL"], "safe": "BOND", "cash": "CASH", "months": 12}
        day = prices.series["US"]["date"][-1]
        self.assertEqual(allocation.target_weights(rule, prices, day), {"INTL": 1.0})
        weak = allocation.Prices({**prices.series, "US": monthly_series([100 - i for i in range(n)])})
        self.assertEqual(allocation.target_weights(rule, weak, day), {"BOND": 1.0})

    def test_core_satellite_spec_runs_end_to_end(self):
        spec = json.loads((ROOT / "research/lab/queue/b1-core-satellite-v1.json").read_text())
        etf, prices, events = {}, {}, []
        day, dates = dt.date(2005, 1, 3), []
        while len(dates) < 900:
            if day.weekday() < 5:
                dates.append(day.isoformat())
            day += dt.timedelta(days=1)
        for k, symbol in enumerate(spec["core"]["dataset"]["symbols"]):
            bars = walk(6000 + k, n=900, drift=0.0003, vol=0.01)
            etf[symbol] = {"date": dates, **{f: [b[f] for b in bars] for f in datasets.FIELDS}}
        for k in range(10):
            bars = walk(7000 + k, n=900)
            prices[f"S{k}"] = {"date": dates, **{f: [b[f] for b in bars] for f in datasets.FIELDS}}
            for at in range(420, 860, 45):
                events.append({"event_id": f"S{k}-{at}", "symbol": f"S{k}", "signal_date": dates[at], "score": (k * 3 + at) % 17})
        spec["window"] = {"start": dates[400], "end": dates[-1]}
        spec["splits"] = [{"id": "all", "from": "2000-01-01", "to": "2100-01-01"}]
        spec["criteria"] = {**spec["criteria"], "mc_runs": 2, "min_trades": 1}
        entry = {"dataset_id": "synthetic", "asset": "-", "sha256": "-", "events": len(events), "symbols": 10}
        bench = {"symbol": "SPY", "series": etf["SPY"], "entry": entry}
        result, _ = run_queue.run_account_spec(spec, {"events": events, "prices": prices}, entry, 0.001, bench, core_data={"prices": etf})
        self.assertEqual(len(result["variants"]), 9)
        self.assertEqual(result["variants"]["CPERM-M0"]["account"]["trades_taken"], 0)
        self.assertGreater(result["variants"]["CPERM-M10"]["account"]["trades_taken"], 0)
        self.assertIn(result["chosen"]["variant"], ("CPERM-M0", "CPERM-M4", "CPERM-M7", "CPERM-M10"))
        report = run_queue.render_report({**result, "completed_at": "2026-10-09T00:00:00+00:00"})
        self.assertIn("## Account results", report)

    def test_proven_portfolio_spec_runs_end_to_end(self):
        spec = json.loads((ROOT / "research/lab/queue/c1-proven-portfolios-v1.json").read_text())
        symbols = spec["dataset"]["symbols"]
        prices = {}
        for k, symbol in enumerate(symbols):
            bars = walk(5000 + k, n=900, drift=0.0003, vol=0.01)
            day = dt.date(2005, 1, 3)
            dates = []
            while len(dates) < 900:
                if day.weekday() < 5:
                    dates.append(day.isoformat())
                day += dt.timedelta(days=1)
            prices[symbol] = {"date": dates, **{f: [b[f] for b in bars] for f in datasets.FIELDS}}
        spec["window"] = {"start": "2006-06-01", "end": "2008-06-30"}
        spec["splits"] = [{"id": "all", "from": "2000-01-01", "to": "2100-01-01"}]
        entry = {"dataset_id": "synthetic", "asset": "-", "sha256": "-", "events": 0, "symbols": len(symbols)}
        result, rebalances = run_queue.run_allocation_spec(spec, {"events": [], "prices": prices}, entry, 0.001)
        self.assertEqual(set(result["variants"]), {p["id"] for p in spec["portfolios"]})
        self.assertEqual(result["kind"], "allocation")
        self.assertIn(result["chosen"] and result["chosen"]["variant"], [None, *result["variants"]])
        self.assertAlmostEqual(result["variants"]["SPY"]["versus_spy"]["beta"], 1.0, places=6)
        report = run_queue.render_report({**result, "completed_at": "2026-10-09T00:00:00+00:00"})
        self.assertIn("## Account results", report)
        self.assertTrue(gzip.decompress(rebalances).startswith(b"portfolio,date,weights"))


def trading_days(n, start=dt.date(2000, 1, 3)):
    days, day = [], start
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += dt.timedelta(days=1)
    return days


class LongHistoryTests(unittest.TestCase):
    def test_splice_follows_the_proxy_before_the_fund_existed_and_records_missing_tickers(self):
        proxy = [{"date": d, "open": 0, "high": 0, "low": 0, "close": c, "adjusted_close": c, "volume": 0}
                 for d, c in [("2000-01-03", 50.0), ("2000-01-04", 55.0), ("2000-01-05", 60.0)]]
        fund = [{"date": d, "open": c, "high": c, "low": c, "close": c, "adjusted_close": c, "volume": 1}
                for d, c in [("2000-01-05", 120.0), ("2000-01-06", 126.0)]]
        feeds = {"FUND.US": fund, "OLD.US": proxy}
        def fetch(t):
            if t not in feeds:
                raise RuntimeError("unknown ticker")
            return feeds[t]
        data = datasets.build_from_chains({"X": ["FUND.US", "GONE.US", "OLD.US"], "Y": ["NOPE.US"]}, "t", fetch)
        x = data["prices"]["X"]
        self.assertEqual(x["date"], ["2000-01-03", "2000-01-04", "2000-01-05", "2000-01-06"])
        self.assertAlmostEqual(x["close"][1] / x["close"][0], 55 / 50)  # proxy's move, scaled
        self.assertAlmostEqual(x["close"][2], 120.0)  # meets the fund on its first day
        self.assertEqual(x["open"][0], x["close"][0])  # a close-only proxy uses its close as the open
        self.assertEqual([n["available"] for n in data["chains"]["X"]], [True, False, True])
        self.assertEqual(data["missing_symbols"], ["Y"])

    def test_auto_window_drops_optional_portfolios_and_checks_rolling_windows(self):
        days = trading_days(2600)
        def series(seed, start=0, vol=0.01):
            bars = walk(seed, n=len(days) - start, drift=0.0004, vol=vol)
            return {"date": days[start:], **{f: [b[f] for b in bars] for f in ("open", "high", "low", "close")}}
        prices = {"STOCKS": series(1), "CASH": series(2, vol=0.0005), "LATE": series(3, start=1500)}
        spec = {"id": "t", "experiment_id": "t", "group": "t", "question": "q", "benchmark_symbol": "STOCKS", "benchmark_portfolio": "SPY",
                "splits": [{"id": "all", "from": "1990-01-01", "to": "2100-01-01"}], "window": {"start": "auto", "warmup_months": 13, "end": days[-1]},
                "criteria": {"min_trades": 0, "max_drawdown": 0.25, "beat_benchmark": ["sharpe"]}, "selection": {"tie_tolerance": 0.02},
                "rolling": {"years": 5, "step_sessions": 21, "core": "MIX", "max_window_drawdown": 0.25, "min_share_sharpe_vs_benchmark": 0.6},
                "portfolios": [{"id": "SPY", "label": "s", "rule": "static", "rebalance": "annual", "weights": {"STOCKS": 1.0}},
                               {"id": "MIX", "label": "m", "rule": "static", "rebalance": "annual", "weights": {"STOCKS": 0.5, "CASH": 0.5}},
                               {"id": "OPT", "label": "o", "rule": "static", "rebalance": "annual", "optional": True, "weights": {"LATE": 1.0}}]}
        entry = {"dataset_id": "t", "asset": "-", "sha256": "-", "events": 0, "symbols": 3}
        result, _ = run_queue.run_allocation_spec(spec, {"events": [], "prices": prices}, entry, 0.0)
        self.assertEqual(result["window"]["start"][:7], "2001-02")  # data from Jan 2000 plus 13 months
        self.assertEqual([e["portfolio"] for e in result["excluded"]], ["OPT"])
        roll = result["rolling"]
        self.assertGreater(roll["windows"], 10)
        self.assertGreaterEqual(roll["per_portfolio"]["MIX"]["share_positive"], 0.0)
        self.assertEqual(set(roll["per_portfolio"]), {"SPY", "MIX"})
        self.assertIn("core_passed", roll)
        self.assertIn("## Rolling 5-year windows", run_queue.render_report({**result, "completed_at": "2026-10-10T00:00:00+00:00"}))


class DynamicAndSectorTests(unittest.TestCase):
    def test_overlay_steps_a_slice_down_by_trend_and_volatility(self):
        n = 14
        up = monthly_series([100 + 5 * i for i in range(n)])
        flat_cash = monthly_series([100 + 0.1 * i for i in range(n)])
        mixed = monthly_series([100 + 5 * i for i in range(n - 2)] + [120, 110])  # 12-month up, 1- and 3-month down
        prices = allocation.Prices({"UP": up, "MIX": mixed, "CASH": flat_cash})
        day = up["date"][-1]
        rule = {"rule": "overlay", "weights": {"UP": 0.5, "MIX": 0.5}, "cash": "CASH",
                "overlay": {"UP": {"trend": {"kind": "tsmom", "lookbacks_months": [1, 3, 12]}}, "MIX": {"trend": {"kind": "tsmom", "lookbacks_months": [1, 3, 12]}}}}
        w = allocation.target_weights(rule, prices, day)
        self.assertAlmostEqual(w["UP"], 0.5)
        self.assertAlmostEqual(w["MIX"], 0.5 / 3)  # only the 12-month return beats cash
        self.assertAlmostEqual(w["CASH"], 0.5 * 2 / 3)
        days = trading_days(80)
        calm = {"date": days, "close": [100 * 1.0002 ** i for i in range(80)]}
        vol_prices = allocation.Prices({"X": calm})
        scale = allocation.vol_scale(vol_prices, "X", days[-1], {"target": 0.15, "days": 63, "cap": 1.0})
        self.assertEqual(scale, 1.0)  # quiet market: never above full size
        wild_closes = [100.0]
        for i in range(1, 80):
            wild_closes.append(wild_closes[-1] * (1.05 if i % 2 else 0.95))
        wild = {"date": days, "close": wild_closes}
        self.assertLess(allocation.vol_scale(allocation.Prices({"X": wild}), "X", days[-1], {"target": 0.15, "days": 63, "cap": 1.0}), 0.3)

    def test_rotation_holds_the_strongest_funds_and_cash_when_none_beats_it(self):
        n = 14
        prices = allocation.Prices({"A": monthly_series([100 + 1 * i for i in range(n)]), "B": monthly_series([100 + 3 * i for i in range(n)]),
                                    "C": monthly_series([100 + 2 * i for i in range(n)]), "CASH": monthly_series([100 + 0.5 * i for i in range(n)]),
                                    "T": monthly_series([100.0] * n)})
        day = prices.series["A"]["date"][-1]
        rule = {"rule": "rotation", "universe": ["A", "B", "C"], "top": 2, "lookbacks_months": [3, 6, 12], "sleeve": 0.5, "cash": "CASH", "weights": {"T": 0.5}}
        self.assertEqual(allocation.target_weights(rule, prices, day), {"T": 0.5, "B": 0.25, "C": 0.25})
        weak = allocation.Prices({**prices.series, "CASH": monthly_series([100 + 5 * i for i in range(n)])})
        self.assertEqual(allocation.target_weights({**rule, "absolute": True}, weak, day), {"T": 0.5, "CASH": 0.5})
        self.assertEqual(allocation.roles(rule), {"A", "B", "C", "CASH", "T"})

    def test_improve_on_keeps_the_baseline_unless_a_candidate_is_better_without_lower_sharpe(self):
        days = trading_days(900)
        def series(seed, vol):
            bars = walk(seed, n=900, drift=0.0004, vol=vol)
            return {"date": days, **{f: [b[f] for b in bars] for f in ("open", "high", "low", "close")}}
        prices = {"STOCKS": series(1, 0.012), "CASH": series(2, 0.0004)}
        spec = {"id": "t", "experiment_id": "t", "group": "t", "question": "q", "benchmark_symbol": "STOCKS", "benchmark_portfolio": "SPY",
                "splits": [], "window": {"start": days[300], "end": days[-1]}, "criteria": {"min_trades": 0, "max_drawdown": 0.9},
                "selection": {"kind": "improve_on", "baseline": "BASE", "metric": "calmar", "candidates": ["SAME"]},
                "comparisons": [{"question": "same beats base", "a": "SAME", "b": "BASE", "metric": "sharpe"}],
                "portfolios": [{"id": "SPY", "label": "s", "rule": "static", "rebalance": "annual", "weights": {"STOCKS": 1.0}},
                               {"id": "BASE", "label": "b", "rule": "static", "rebalance": "annual", "weights": {"STOCKS": 0.5, "CASH": 0.5}},
                               {"id": "SAME", "label": "same as base", "rule": "static", "rebalance": "annual", "weights": {"STOCKS": 0.5, "CASH": 0.5}}]}
        entry = {"dataset_id": "t", "asset": "-", "sha256": "-", "events": 0, "symbols": 2}
        result, _ = run_queue.run_allocation_spec(spec, {"events": [], "prices": prices}, entry, 0.001)
        self.assertEqual(result["chosen"]["variant"], "BASE")  # an identical candidate is not "better"
        self.assertFalse(result["chosen"]["improved"])
        self.assertFalse(result["comparisons"][0]["holds"])
        self.assertIn("Improvement over BASE", run_queue.render_report({**result, "completed_at": "2026-10-10T00:00:00+00:00"}))


class SelectionTests(unittest.TestCase):
    def test_tradable_pool_and_price_error_screen(self):
        days = trading_days(500)
        good = {"date": days, "close": [10.0] * 500, "volume": [2_000_000] * 500}
        cheap = {"date": days, "close": [3.0] * 500, "volume": [9_000_000] * 500}
        thin = {"date": days, "close": [10.0] * 500, "volume": [500_000] * 500}
        broken = {"date": days, "close": [10.0] * 250 + [80.0] * 250, "volume": [2_000_000] * 500}
        prices = {"GOOD": good, "CHEAP": cheap, "THIN": thin, "BROKEN": broken}
        self.assertEqual(selection.impossible_jumps(prices), {"BROKEN"})
        rules = {"min_history": 420, "min_close": 5.0, "min_dollar_volume": 10_000_000.0, "exclude": {"BROKEN"}}
        self.assertEqual(selection.eligible_pool(prices, days[450], rules), ["GOOD"])
        self.assertEqual(selection.eligible_pool(prices, days[400], rules), [])  # not yet 420 sessions of history
        self.assertEqual(selection.winsorize([1.0] * 98 + [1000.0, -1000.0]), [1.0] * 100)

    def test_random_draws_are_reproducible_and_only_from_stocks_that_traded_that_day(self):
        days = trading_days(400)
        prices = {"A": {"date": days, "close": [1.0] * 400}, "B": {"date": days[100:], "close": [1.0] * 300}, "C": {"date": days[:300], "close": [1.0] * 300}}
        self.assertEqual(sorted(selection.eligible_pool(prices, days[299])), ["A"])  # B lacks a year of history, C has no next bar
        self.assertEqual(sorted(selection.eligible_pool(prices, days[380])), ["A", "B"])
        events = [{"signal_date": days[380]}, {"signal_date": days[299]}]
        self.assertEqual(selection.draws(events, prices, 3, 7), selection.draws(events, prices, 3, 7))
        self.assertTrue(all(run[1] == "A" for run in selection.draws(events, prices, 5, 7)))

    def test_random_trade_matches_the_account_candidate_for_the_same_stock(self):
        bars = walk(11, n=420)
        series = {"date": [b["date"] for b in bars], **{f: [b[f] for b in bars] for f in datasets.FIELDS}}
        variant = {"stop": {"kind": "support_cap", "buffer": 0.05, "cap": 0.1}, "targets": [], "max_hold": 40}
        day = series["date"][300]
        o = selection.outcomes({("S", day)}, {"S": series}, variant, 0.001, series["date"][-1])[("S", day)]
        expanded = datasets.expand(series)
        from services.scanner.support_risk import signal_support_plan
        result = simulate(expanded, 301, variant, support_plan=signal_support_plan(expanded, end=300), cost_per_side=0.001)
        c = account.candidate({"event_id": "S", "symbol": "S", "signal_date": day}, expanded, 301, result, 0, series["date"][-1])
        self.assertEqual((o["entry_date"], o["entry_price"], o["stop"], o["fills"]), (c["entry_date"], c["entry_price"], c["stop"], c["fills"]))
        self.assertEqual([o["closes"][j] for j in range(len(o["closes"]))], c["closes"])

    def test_least_squares_and_clustered_t(self):
        x = [float(i % 7) for i in range(60)]
        y = [0.5 + 2.0 * v + (0.01 if i % 2 else -0.01) for i, v in enumerate(x)]
        beta, t = selection.ols(y, [x])
        self.assertAlmostEqual(beta[0], 0.5, places=2)
        self.assertAlmostEqual(beta[1], 2.0, places=3)
        mean, tval = selection.clustered_t([1.0, 3.0, 2.0, 2.0], ["a", "a", "b", "c"])
        self.assertAlmostEqual(mean, 2.0)
        self.assertEqual(tval, 0.0)  # every month averages 2, so no spread: reported as 0, not infinite

    def test_selection_spec_runs_end_to_end(self):
        days = trading_days(900, dt.date(2005, 1, 3))
        prices, events = {}, []
        for k in range(14):
            bars = walk(8000 + k, n=900)
            prices[f"S{k}"] = {"date": days, **{f: [b[f] for b in bars] for f in datasets.FIELDS}}
            if k < 6:
                for at in range(300, 860, 37):
                    events.append({"event_id": f"S{k}-{at}", "symbol": f"S{k}", "signal_date": days[at], "score": (k + at) % 11})
        style = {s: {"date": days, **{f: [b[f] for b in walk(9000 + i, n=900)] for f in datasets.FIELDS}} for i, s in enumerate(("SPY", "QQQ", "IWM", "RSP"))}
        spec = json.loads((ROOT / "research/lab/queue/e1-selection-vs-random-v1.json").read_text())
        spec["window"] = {"start": days[250], "end": days[-1]}
        spec["random_runs"] = 6
        entry = {"dataset_id": "synthetic", "asset": "-", "sha256": "-", "events": len(events), "symbols": 14}
        bench = {"symbol": "SPY", "series": style["SPY"], "entry": entry}
        first, rows = run_queue.run_selection_spec(spec, {"events": events, "prices": prices}, entry, 0.001, bench, style_data={"prices": style})
        second, _ = run_queue.run_selection_spec(spec, {"events": events, "prices": prices}, entry, 0.001, bench, style_data={"prices": style})
        self.assertEqual(first, second)
        self.assertEqual(first["random"]["runs"], 6)
        self.assertIn("passed", first["verdict"])
        self.assertEqual(set(first["style"]["same_exposure"]), {"SPY", "QQQ", "IWM", "RSP"})
        self.assertEqual(set(first["style"]["regression"]["betas"]), {"SPY", "QQQ-SPY", "IWM-SPY"})
        report = run_queue.render_selection_report({**first, "completed_at": "2026-10-10T00:00:00+00:00"})
        self.assertIn("## Trade by trade", report)
        board, markdown = run_queue.render_scoreboard([{**first, "completed_at": "2026-10-10T00:00:00+00:00"}])
        self.assertIn("random-pick accounts", markdown)


class TimeframeTests(unittest.TestCase):
    def test_structure_floor_only_counts_on_closes_of_the_opportunitys_timeframe(self):
        days = trading_days(80, dt.date(2024, 1, 1))
        prices = [(100, 101, 99, 100)] * 30 + [(100, 101, 89, 90)] * 2 + [(95, 96, 94, 95)] * 48  # dips below 92 mid-month, recovers before month end
        bars = [{"date": d, "open": o, "high": h, "low": l, "close": c, "volume": 1} for d, (o, h, l, c) in zip(days, prices)]
        monthly = {"stop": {"kind": "structure", "floor": 92.0, "period": "month", "disaster": 0.25}, "targets": [], "max_hold": 40}
        daily = {**monthly, "stop": {**monthly["stop"], "period": "day"}}
        self.assertEqual(simulate(bars, 25, monthly, cost_per_side=0)["exit_reason"], "time")
        r = simulate(bars, 25, daily, cost_per_side=0)
        self.assertEqual((r["exit_reason"], r["fills"][-1]["date"]), ("structure_exit", days[31]))  # next open after the first daily close below 92
        crash = bars[:30] + [{"date": days[30], "open": 70, "high": 71, "low": 69, "close": 70, "volume": 1}] + bars[31:]
        self.assertEqual(simulate(crash, 25, monthly, cost_per_side=0)["exit_reason"], "stop_gap")  # the 25% disaster stop still guards gaps

    def test_published_trend_exits(self):
        days = trading_days(400, dt.date(2020, 1, 1))
        up = [100 * 1.002 ** i for i in range(300)]
        down = [up[-1] * 0.99 ** (i + 1) for i in range(100)]
        closes = up + down
        bars = [{"date": d, "open": c, "high": c * 1.001, "low": c * 0.999, "close": c, "volume": 1} for d, c in zip(days, closes)]
        base = {"stop": {"kind": "pct", "pct": 0.9}, "targets": [], "max_hold": 300}
        for trend, latest in ([{"kind": "daily_sma", "length": 50}, 310], [{"kind": "prior_low", "length": 20}, 305],
                              [{"kind": "period_sma", "period": "week", "length": 10}, 330], [{"kind": "period_momentum", "period": "month", "length": 3}, 380]):
            r = simulate(bars, 250, {**base, "trend_exit": trend}, cost_per_side=0)
            self.assertEqual(r["exit_reason"], "trend_exit", trend)
            exit_day = days.index(r["fills"][-1]["date"])
            self.assertTrue(300 < exit_day <= latest, (trend, exit_day))  # only after the uptrend ends, and soon after

    def test_timeframe_spec_runs_end_to_end_with_segments(self):
        import csv as _csv
        days = trading_days(900, dt.date(2005, 1, 3))
        prices, events = {}, []
        rows = []
        for k in range(10):
            bars = walk(9500 + k, n=900, drift=0.0004, vol=0.015)
            prices[f"S{k}"] = {"date": days, **{f: [b[f] * 10 for b in bars] for f in ("open", "high", "low", "close")}, "volume": [5_000_000] * 900}
            for at, tf in ((480, "daily"), (560, "weekly_completed"), (640, "monthly_completed")):
                eid = f"S{k}-{days[at]}-{at}"
                events.append({"event_id": eid, "symbol": f"S{k}", "signal_date": days[at], "timeframe": tf, "score": 40})
                close = prices[f"S{k}"]["close"][at]
                rows.append({"symbol": f"S{k}", "signal_date": days[at], "episode_id": str(at), "structure_floor": close * 0.85, "signal_close": close})
        spy_bars = walk(9900, n=900)
        spy = {"date": days, **{f: [b[f] for b in spy_bars] for f in ("open", "high", "low", "close")}}
        spec = json.loads((ROOT / "research/lab/queue/e7-timeframe-holding-v1.json").read_text())
        spec["runs"] = {k: 2 for k in spec["runs"]}
        spec["window"] = {"start": days[300], "end": days[-1]}
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder) / "trades.csv"
            with path.open("w", newline="") as handle:
                w = _csv.DictWriter(handle, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
            spec["structure_csv"] = str(path)
            entry = {"dataset_id": "synthetic", "asset": "-", "sha256": "-", "events": len(events), "symbols": 10}
            result, _ = run_queue.run_timeframe_spec(spec, {"events": events, "prices": prices}, entry, 0.001, {"symbol": "SPY", "series": spy, "entry": entry})
        self.assertEqual(set(result["families"]), set(spec["families"]))
        self.assertEqual(result["signals"], 30)
        seg = result["families"]["short"]["segments"]
        self.assertEqual(set(seg["timeframe"]), {"daily", "weekly", "monthly"})
        self.assertTrue(set(seg["market_trend"]) <= {"SPY above 200-day", "SPY below 200-day", "unknown"})
        self.assertIn("## short: by segment (exploratory)", timeframe.render({**result, "completed_at": "2026-10-10T00:00:00+00:00"}))


class ForwardTests(unittest.TestCase):
    def test_forward_accounts_start_on_the_registered_date_and_log_each_day_once(self):
        from research.lab import forward
        days = trading_days(600, dt.date(2025, 1, 2))
        prices = {}
        for k, s in enumerate(("SPY", "TLT", "GLD", "SHY", "AGG")):
            bars = walk(9100 + k, n=600, drift=0.0002, vol=0.008)
            prices[s] = {"date": days, **{f: [b[f] for b in bars] for f in ("open", "high", "low", "close")}}
        config = json.loads((ROOT / "research/lab/forward/config.json").read_text())
        config = {**config, "start": days[500]}
        self.assertIsNone(forward.compute(config, prices, as_of_limit=days[499]))
        snap = forward.compute(config, prices)
        self.assertEqual((snap["as_of"], snap["sessions"]), (days[-1], 100))
        self.assertEqual(set(snap["portfolios"]), {p["id"] for p in config["portfolios"]})
        with tempfile.TemporaryDirectory() as folder:
            forward.write(folder, config, snap, "t1")
            forward.write(folder, config, snap, "t2")  # same day again: logged once
            later = forward.compute(config, {k: {f: v[:-1] if isinstance(v, list) else v for f, v in s.items()} for k, s in prices.items()})
            forward.write(folder, config, later, "t3")
            lines = (pathlib.Path(folder) / "research/lab/forward/history.jsonl").read_text().splitlines()
            self.assertEqual([json.loads(l)["as_of"] for l in lines], [days[-1], days[-2]])
            self.assertEqual(json.loads((pathlib.Path(folder) / "research/lab/forward/latest.json").read_text())["computed_at"], "t3")


def ohlcv(rows, start=dt.date(2020, 1, 1)):
    """Column series from (open, high, low, close, volume) rows on consecutive trading days."""
    days = trading_days(len(rows), start)
    return {"date": days, **{k: [float(r[j]) for r in rows] for j, k in enumerate(("open", "high", "low", "close", "volume"))}}


def closes_only(closes, volume=1000.0, start=dt.date(2020, 1, 1)):
    return ohlcv([(c, c + 0.5, c - 0.5, c, volume) for c in closes], start)


def ramp(a, b, n):
    return [a + (b - a) * (k + 1) / n for k in range(n)]


class StructureTests(unittest.TestCase):
    def test_value_area_holds_seventy_percent_around_the_busiest_prices(self):
        s = ohlcv([(51, 52, 50, 51, 1000)] * 100 + [(61, 62, 60, 61, 10)] * 20)
        va = structure.value_area(s, 119, lookback=120, bins=50)
        self.assertTrue(va["available"])
        self.assertTrue(50 <= va["val"] < va["poc"] < va["vah"] <= 52.5, va)  # the quiet 60-62 zone stays outside
        self.assertGreaterEqual(va["share"], 0.7)
        self.assertEqual(structure.value_area(s, 50, lookback=120)["reason"], "insufficient_history")
        self.assertEqual(structure.value_area(ohlcv([(51, 52, 50, 51, 0)] * 120), 119)["reason"], "volume_unavailable")

    def test_deep_drawdown_rejects_until_the_fall_is_repaired_or_based(self):
        fall = [100.0] * 50 + ramp(100, 20, 80)
        hit = structure.deep_drawdown(closes_only(fall + [20.0] * 10 + [30.0] * 5), 144)
        self.assertTrue(hit["reject"] and not hit["repaired"] and not hit["based"])
        self.assertFalse(structure.deep_drawdown(closes_only(fall + [25.0] * 300), 429)["reject"])  # a year-long base since the low
        self.assertFalse(structure.deep_drawdown(closes_only(fall + ramp(20, 75, 40)), 169)["reject"])  # reclaimed 0.618 of the fall
        self.assertFalse(structure.deep_drawdown(closes_only([100.0] * 50 + ramp(100, 40, 80)), 129)["reject"])  # fell only 60%

    def test_wide_box_needs_a_wide_range_crossed_twice_and_a_signal_well_below_the_top(self):
        box = [10.0] * 5 + ramp(10, 30, 40) + ramp(30, 10, 40) + ramp(10, 30, 40) + ramp(30, 15, 30)
        self.assertTrue(structure.wide_box(closes_only(box), len(box) - 1)["reject"])
        trend = [10.0] * 5 + ramp(10, 30, 120) + ramp(30, 20, 30)
        self.assertEqual(structure.wide_box(closes_only(trend), len(trend) - 1)["traversals"], 1)
        self.assertFalse(structure.wide_box(closes_only(trend), len(trend) - 1)["reject"])
        near_top = box[:-30] + ramp(30, 28, 30)
        self.assertFalse(structure.wide_box(closes_only(near_top), len(near_top) - 1)["reject"])  # within 25% of the top

    def test_bearish_pressure_needs_two_unrepaired_rounds(self):
        rows = [(100, 101, 99, 100, 1)] * 80
        rows += [(100, 100.5, 94.5, 95, 1), (95, 95.5, 93.5, 94, 1)] + [(94, 95, 93, 94, 1)] * 10
        rows += [(94, 94.5, 88.5, 89, 1), (89, 89.5, 87.5, 88, 1)] + [(88, 89, 87, 88, 1)] * 20
        weak = ohlcv(rows)
        result = structure.bearish_pressure(weak, len(rows) - 1)
        self.assertTrue(result["flag"], result)
        self.assertEqual(len(result["rounds"]), 2)
        repaired = ohlcv(rows + [(110, 111, 109, 110, 1)] * 30)
        self.assertFalse(structure.bearish_pressure(repaired, len(rows) + 29)["flag"])

    def test_multiple_tops_need_separate_tests_and_recent_exhaustion(self):
        def path(dip):
            closes = [80.0] * 10 + ramp(80, 100, 15) + ramp(100, dip, 10) + ramp(dip, 99, 10) + ramp(99, dip, 10) + ramp(dip, 99.5, 10) + ramp(99.5, 96, 8)
            rows = [(c, c + 0.5, c - 0.5, c, 1) for c in closes] + [(96, 99.5, 95.5, 95.8, 1)]  # a shooting star back near the tops
            return ohlcv(rows)
        tops = path(90)
        self.assertTrue(structure.multiple_tops(tops, len(tops["date"]) - 1)["flag"])
        shallow = path(97)  # dips under 8% do not separate the tests
        self.assertFalse(structure.multiple_tops(shallow, len(shallow["date"]) - 1)["flag"])

    def test_gap_supply_needs_a_chain_with_the_latest_gap_unfilled(self):
        def chain(fill):
            closes = [100.0] * 100 + [95.0] * 200 + [90.0] * 200 + [85.0] * 60 + ([95.0] * 10 if fill else [85.0] * 10)
            rows = []
            for k, c in enumerate(closes):
                gap = k and c < closes[k - 1] - 2
                rows.append((c, c + 0.4, c - 0.4, c, 1) if gap else (c, c + 0.5, c - 0.5, c, 1))
            return ohlcv(rows)
        self.assertTrue(structure.gap_supply(chain(False), 569)["flag"])
        self.assertFalse(structure.gap_supply(chain(True), 569)["flag"])

    def test_assess_reports_the_first_rejection_and_every_flag(self):
        fall = closes_only([100.0] * 50 + ramp(100, 20, 80) + [20.0] * 10 + [30.0] * 5)
        verdict = structure.assess(fall, 144)
        self.assertEqual(verdict["reject"], "deep_drawdown")
        self.assertEqual(structure.rejection(fall, 144), "deep_drawdown")
        self.assertEqual(set(verdict["details"]), {"deep_drawdown", "wide_box", "bearish_pressure", "multiple_tops", "gap_supply"})


def level_bars(closes, start=dt.date(2024, 1, 2)):
    days = trading_days(len(closes), start)
    return [{"date": d, "open": c, "high": c * 1.001, "low": c * 0.999, "close": c, "volume": 1} for d, c in zip(days, closes)]


class LevelExitTests(unittest.TestCase):
    def test_a_level_stop_sells_intraday_even_inside_the_minimum_hold(self):
        bars = level_bars([100.0] * 12 + [95.0, 96.0] + [100.0] * 30)
        bars[13] = {**bars[13], "low": 89.0}  # dips through the stop during the session
        rule = {"stop": {"kind": "level", "price": 90.0}, "targets": [], "max_hold": 30, "min_hold": 15, "trend_exit": {"kind": "daily_sma", "length": 5, "arm": True}}
        r = simulate(bars, 10, rule, cost_per_side=0)
        self.assertEqual((r["exit_reason"], r["fills"][-1]["price"]), ("stop", 90.0))
        self.assertIsNone(simulate(bars, 10, {**rule, "stop": {"kind": "level", "price": 120.0}}, cost_per_side=0).get("exit_reason"))

    def test_trend_exits_wait_for_the_minimum_and_arm_only_above_their_line(self):
        down = [100 - k for k in range(30)]
        bars = level_bars([100.0] * 10 + down + [70.0] * 30)
        rule = {"stop": {"kind": "level", "price": 1.0}, "targets": [], "max_hold": 50, "trend_exit": {"kind": "daily_sma", "length": 5}}
        # Bought during the decline, already below the 5-day average.
        self.assertEqual(simulate(bars, 13, rule, cost_per_side=0)["held"], 2)  # unarmed: below the line at the first close, sold at the next open
        armed = simulate(bars, 13, {**rule, "trend_exit": {**rule["trend_exit"], "arm": True}}, cost_per_side=0)
        self.assertEqual(armed["exit_reason"], "time")  # it never closed back above the line after a close below it
        later = simulate(bars, 13, {**rule, "min_hold": 15}, cost_per_side=0)
        self.assertEqual((later["exit_reason"], later["held"]), ("trend_exit", 16))  # judged from session 15, sold at the next open

    def test_monthly_minimum_and_maximum_count_full_months_after_the_entry_month(self):
        bars = level_bars([100 - 0.05 * k for k in range(200)], start=dt.date(2024, 1, 2))
        entry = next(i for i, b in enumerate(bars) if b["date"] >= "2024-01-16")
        rule = {"stop": {"kind": "level", "price": 1.0}, "targets": [], "max_hold": 199,
                "min_periods": {"period": "month", "count": 3}, "max_periods": {"period": "month", "count": 5}}
        timed = simulate(bars, entry, rule, cost_per_side=0)
        self.assertEqual((timed["exit_reason"], timed["fills"][-1]["date"][:7]), ("time", "2024-06"))  # Feb-Jun are the five full months
        trend = simulate(bars, entry, {**rule, "trend_exit": {"kind": "daily_sma", "length": 5}}, cost_per_side=0)
        self.assertEqual((trend["exit_reason"], trend["fills"][-1]["date"][:7]), ("trend_exit", "2024-05"))  # first chance after April closes

    def test_no_progress_sells_after_twenty_sessions_without_a_five_percent_close(self):
        flat = level_bars([100.0] * 50)
        rule = {"stop": {"kind": "level", "price": 80.0}, "targets": [], "max_hold": 40, "no_progress": {"sessions": 20, "gain": 0.05}}
        r = simulate(flat, 5, rule, cost_per_side=0)
        self.assertEqual((r["exit_reason"], r["held"]), ("no_progress", 21))
        moved = level_bars([100.0] * 12 + [106.0] + [100.0] * 37)
        self.assertEqual(simulate(moved, 5, rule, cost_per_side=0)["exit_reason"], "time")


def level_stock(n=700, seed=1, start=dt.date(2005, 1, 3), scale=10.0, volume=5_000_000):
    days = trading_days(n, start)
    bars = walk(seed, n=n, drift=0.0004, vol=0.015)
    return {"date": days, **{f: [b[f] * scale for b in bars] for f in ("open", "high", "low", "close")}, "volume": [float(volume)] * n}


class LevelsTests(unittest.TestCase):
    def test_win_loss_reports_win_rate_payoff_profit_factor_and_r(self):
        stats = levels.win_loss([(0.10, 0.05), (-0.05, 0.05), (0.04, 0.10), (-0.02, 0.10)])
        self.assertEqual((stats["trades"], stats["win_rate"]), (4, 0.5))
        self.assertAlmostEqual(stats["payoff_ratio"], 0.07 / 0.035, places=3)
        self.assertAlmostEqual(stats["profit_factor"], 0.14 / 0.07, places=3)
        self.assertAlmostEqual(stats["expectancy_r"], (2 - 1 + 0.4 - 0.2) / 4, places=4)
        self.assertEqual(levels.win_loss([]), {"trades": 0})

    RULES = levels._rules({"rules": json.loads((ROOT / "research/lab/queue/e7b-level-rules-20y-v1.json").read_text())["rules"]})

    def test_plan_skips_rejections_missing_support_wide_stops_and_unreclaimed_gaps(self):
        s = level_stock(seed=11)
        day = s["date"][500]
        p = levels.plan(s, day, self.RULES)
        if "skip" not in p:
            self.assertGreater(p["entry_index"], 500)
            self.assertLess(p["stop"], s["open"][p["entry_index"]])
        self.assertEqual(levels.plan(s, day, {**self.RULES, "max_stop_distance": 0.0})["skip"], "stop_too_wide")
        fall = closes_only([100.0] * 400 + ramp(100, 20, 80) + [20.0] * 10 + [30.0] * 5 + [30.0] * 10, volume=5e6, start=dt.date(2005, 1, 3))
        self.assertEqual(levels.plan(fall, fall["date"][494], self.RULES)["skip"], "veto_deep_drawdown")
        below = closes_only([50.0] * 300 + ramp(50, 30, 30) + [30.0] * 10, volume=5e6, start=dt.date(2005, 1, 3))
        self.assertEqual(levels.plan(below, below["date"][334], self.RULES, vetoes=False)["skip"], "no_support")
        self.assertEqual(levels.plan(s, "1999-01-01", self.RULES)["skip"], "no_signal_bar")

    def test_an_open_below_the_stop_waits_for_a_close_back_above_it(self):
        base = [(50, 50.5, 49.5, 50, 1e6)] * 200
        rules = {**self.RULES, "max_stop_distance": 0.5}
        signal = 199
        va = structure.value_area(ohlcv(base), signal, **rules["value_area"])
        stop = va["val"] * (1 - rules["buffer"])
        gap = [(stop - 2, stop - 1, stop - 3, stop - 2, 1e6), (stop - 2, stop + 2, stop - 3, stop + 1, 1e6), (stop + 0.5, stop + 1, stop, stop + 0.5, 1e6)]
        p = levels.plan(ohlcv(base + gap + [(50, 50.5, 49.5, 50, 1e6)] * 5), ohlcv(base)["date"][signal], rules, vetoes=False)
        self.assertEqual((p["entry_index"], p["waited"]), (signal + 3, 2))
        never = [(stop - 2, stop - 1, stop - 3, stop - 2, 1e6)] * 5
        self.assertEqual(levels.plan(ohlcv(base + never), ohlcv(base)["date"][signal], rules, vetoes=False)["skip"], "opened_below_stop")

    def test_family_exits_by_level_and_the_uncapped_family(self):
        spec = json.loads((ROOT / "research/lab/queue/e7b-level-rules-20y-v1.json").read_text())
        hold, fam = spec["hold"], spec["families"]
        self.assertEqual(levels.variant("daily", fam["T0"], hold, 9.0), {"stop": {"kind": "level", "price": 9.0}, "targets": [], "max_hold": 20})
        self.assertNotIn("no_progress", levels.variant("monthly", fam["T1"], hold, 9.0))  # the user kept the 20-day exit off monthly opportunities
        self.assertEqual(levels.variant("weekly", fam["T1"], hold, 9.0)["no_progress"], {"sessions": 20, "gain": 0.05})
        self.assertTrue(levels.variant("weekly", fam["T3"], hold, 9.0)["trend_exit"]["arm"])
        uncapped = levels.variant("monthly", fam["T4"], hold, 9.0)
        self.assertEqual((uncapped["max_hold"], "max_periods" in uncapped, uncapped["min_periods"]["count"]), (504, False, 3))

    def test_levels_spec_runs_end_to_end_with_extra_checks_periods_and_segments(self):
        days = trading_days(900, dt.date(2005, 1, 3))
        prices, events = {}, []
        for k in range(10):
            prices[f"S{k}"] = {**level_stock(900, 9500 + k), "date": days}
            for at, tf in ((480, "daily"), (560, "weekly_completed"), (640, "monthly_completed")):
                events.append({"event_id": f"S{k}-{days[at]}-{at}", "symbol": f"S{k}", "signal_date": days[at], "timeframe": tf, "score": 40})
        spy_bars = walk(9900, n=900)
        spy = {"date": days, **{f: [b[f] for b in spy_bars] for f in ("open", "high", "low", "close")}}
        spec = json.loads((ROOT / "research/lab/queue/e7b-level-rules-20y-v1.json").read_text())
        spec["runs"] = {k: 2 for k in spec["runs"]}
        spec["window"] = {"start": days[300], "end": days[-1]}
        entry = {"dataset_id": "synthetic", "asset": "-", "sha256": "-", "events": len(events), "symbols": 10}
        result, csv_gz = run_queue.run_levels_spec(spec, {"events": events, "prices": prices}, entry, 0.001, {"symbol": "SPY", "series": spy, "entry": entry})
        self.assertEqual(set(result["arms"]), {"main", "veto_off", "stop_va60", "risk_0.5pct", "market_filter"})
        skipped = result["arms"]["market_filter"]["skipped_by_level"]
        self.assertEqual(sum(c.get("market_filter", 0) for c in skipped.values()) + result["arms"]["market_filter"]["traded"]
                         + sum(v for c in skipped.values() for k, v in c.items() if k not in ("market_filter", "traded")), 30)
        self.assertIn("score_group", result["arms"]["main"]["families"]["T0"]["segments"])
        self.assertIn("met", result["arms"]["main"]["families"]["T0"]["goal_1"])
        self.assertEqual(result["arms"]["risk_0.5pct"]["account"]["risk_per_trade"], 0.005)  # an extra check can change the risk budget
        self.assertEqual(result["arms"]["main"]["account"]["risk_per_trade"], spec["account"]["risk_per_trade"])
        self.assertEqual(set(result["arms"]["main"]["families"]), set(spec["families"]))
        self.assertEqual(set(result["arms"]["veto_off"]["families"]), {"T0"})
        main = result["arms"]["main"]["families"]["T0"]
        self.assertTrue(set(main["segments"]) >= {"timeframe", "market_trend", "market_volatility", "sector", "supply_flag"})
        self.assertIn("goal_2_some_period_beats_spy", main)
        self.assertTrue({"win_rate", "payoff_ratio", "profit_factor", "expectancy_r"} <= set(main["win_loss"]["sv"]))
        self.assertIsNotNone(result["vetoes_help"])
        self.assertEqual(result["signals"], 30)
        again, _ = run_queue.run_levels_spec(spec, {"events": events, "prices": prices}, entry, 0.001, {"symbol": "SPY", "series": spy, "entry": entry})
        self.assertEqual(json.dumps(again, sort_keys=True), json.dumps(result, sort_keys=True))  # deterministic from the seed
        report = levels.render({**result, "completed_at": "2026-10-11T05:00:00+00:00"})
        self.assertIn("## main: account and trades against random picks", report)
        self.assertIn("five-year periods against SPY", report)
        self.assertTrue(gzip.decompress(csv_gz).decode().startswith("arm,family,segment"))

    def test_case_acceptance_reports_each_expected_verdict(self):
        spec = json.loads((ROOT / "research/lab/queue/e7b-case-acceptance-v1.json").read_text())
        fall = closes_only([100.0] * 400 + ramp(100, 20, 80) + [20.0] * 10 + [30.0] * 5, volume=5e6, start=dt.date(2020, 1, 1))
        calm = level_stock(495, seed=3, start=dt.date(2020, 1, 1))
        spec["cases"] = [{"symbol": "FALL", "signal_date": fall["date"][-1], "expect": "reject"},
                         {"symbol": "CALM", "signal_date": calm["date"][-1], "expect": "accept"},
                         {"symbol": "GONE", "signal_date": "2024-01-02", "expect": "accept"}]
        entry = {"dataset_id": "synthetic", "asset": "-", "sha256": "-", "events": 0, "symbols": 2}
        result, _ = run_queue.run_cases_spec(spec, {"events": [], "prices": {"FALL": fall, "CALM": calm}}, entry, 0.001, None)
        got = {r["symbol"]: (r["got"], r["passed"]) for r in result["cases"]}
        self.assertEqual(got["FALL"], ("reject", True))
        self.assertTrue(got["CALM"][1])
        self.assertEqual(got["GONE"], (None, False))
        self.assertFalse(result["passed"])
        self.assertIn("As expected", levels.render_cases({**result, "completed_at": "2026-10-10T05:00:00+00:00"}))


def statistics_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


class QueueAndDatasetTests(unittest.TestCase):
    def test_eod_window_blocks_publishing(self):
        for hhmm, blocked in [("23:29", False), ("23:30", True), ("02:00", True), ("04:29", True), ("04:30", False), ("12:00", False)]:
            h, m = map(int, hhmm.split(":"))
            self.assertEqual(run_queue.in_eod_window(dt.datetime(2026, 10, 7, h, m, tzinfo=dt.timezone.utc)), blocked, hhmm)

    def test_publishing_refuses_inside_the_eod_window(self):
        with mock.patch.object(run_queue, "in_eod_window", return_value=True), mock.patch.object(run_queue.subprocess, "run") as git:
            with self.assertRaisesRegex(RuntimeError, "EOD window"):
                run_queue.publish({"spec_id": "x"}, b"", {"details": {"spec_sha256": "-"}}, [])
            git.assert_not_called()

    def test_dataset_round_trip_rejects_tampering(self):
        data = {"dataset_id": "t", "source": "s", "price_basis": "p", "events": [], "prices": {}}
        with tempfile.TemporaryDirectory() as folder:
            path, entry = datasets.save(data, folder)
            self.assertEqual(datasets.load(path, entry["sha256"]), data)
            path.write_bytes(path.read_bytes() + b"x")
            with self.assertRaises(ValueError):
                datasets.load(path, entry["sha256"])

    def test_spec_runs_end_to_end_on_a_synthetic_dataset(self):
        prices, events = {}, []
        for k in range(30):
            bars = walk(1000 + k, n=260)
            prices[f"S{k}"] = {"date": [b["date"] for b in bars], **{f: [b[f] for b in bars] for f in datasets.FIELDS}}
            events.append({"event_id": f"S{k}", "symbol": f"S{k}", "signal_date": bars[100]["date"]})
        spec = json.loads((ROOT / "research/lab/queue/a-exits-ledger-1y-v1.json").read_text())
        spec["splits"] = [{"id": "all", "from": "2000-01-01", "to": "2100-01-01"}]
        result, trades_csv = run_queue.run_spec(spec, {"events": events, "prices": prices}, {"dataset_id": "synthetic", "asset": "-", "sha256": "-", "events": 30, "symbols": 30}, 0.001)
        self.assertEqual(set(result["variants"]), {v["id"] for v in spec["variants"]})
        self.assertIn(result["champion"], [None, *result["variants"]])
        self.assertTrue(trades_csv)

    def test_spec_with_a_benchmark_reports_excess_for_every_trade(self):
        prices, events = {}, []
        for k in range(12):
            bars = walk(2000 + k, n=260)
            prices[f"S{k}"] = {"date": [b["date"] for b in bars], **{f: [b[f] for b in bars] for f in datasets.FIELDS}}
            events.append({"event_id": f"S{k}", "symbol": f"S{k}", "signal_date": bars[100]["date"]})
        spy = prices["S0"]
        spec = json.loads((ROOT / "research/lab/queue/a-exits-20y-v1.json").read_text())
        spec["splits"] = [{"id": "all", "from": "2000-01-01", "to": "2100-01-01"}]
        spec["criteria"] = {**spec["criteria"], "min_excess_t": 3.0, "every_split_beats_benchmark": True}
        spec["champion_metric"] = "mean_return_per_day"
        entry = {"dataset_id": "synthetic", "asset": "-", "sha256": "-", "events": 12, "symbols": 12}
        result, trades_csv = run_queue.run_spec(spec, {"events": events, "prices": prices}, entry, 0.001,
                                                {"symbol": "SPY", "series": spy, "entry": entry})
        self.assertEqual(result["benchmark"]["symbol"], "SPY")
        self.assertEqual(result["selection_rule"], "highest overall mean_return_per_day among variants passing every pre-registered check")
        for v in result["variants"].values():
            self.assertEqual(v["overall"]["benchmark_trades"], v["overall"]["resolved"])
            self.assertIn("excess_t", v["verdict"]["checks"])
        rows = list(csv.DictReader(io.StringIO(gzip.decompress(trades_csv).decode())))
        # A trade in the benchmark itself has zero excess when both fill at the same open or close
        # (an intraday stop fills at the stop price, the benchmark at that close).
        same_price = [r for r in rows if r["symbol"] == "S0" and r["exit_reason"] in ("time", "stop_gap")]
        self.assertTrue(same_price and all(abs(float(r["excess_return"])) < 1e-7 for r in same_price))

    def test_a_forward_spec_waits_for_its_date(self):
        with tempfile.TemporaryDirectory() as folder:
            queue = pathlib.Path(folder) / "queue"
            queue.mkdir()
            (queue / "later.json").write_text(json.dumps({"id": "later", "not_before": "2027-04-15"}))
            (queue / "now.json").write_text(json.dumps({"id": "now"}))
            with mock.patch.object(run_queue, "QUEUE", queue), mock.patch.object(run_queue, "RESULTS", pathlib.Path(folder) / "results"):
                self.assertEqual([s["id"] for _, s in run_queue.pending_specs("2027-04-14")], ["now"])
                self.assertEqual([s["id"] for _, s in run_queue.pending_specs("2027-04-15")], ["later", "now"])

    def test_every_queued_spec_is_complete_and_linked_to_a_registered_experiment(self):
        registered = {json.loads(line)["experiment_id"] for line in (ROOT / "research/experiments.jsonl").read_text().splitlines() if line.strip()}
        for path in (ROOT / "research/lab/queue").glob("*.json"):
            spec = json.loads(path.read_text())
            self.assertIn(spec["experiment_id"], registered, path.name)
            if spec.get("kind") == "timeframe":
                self.assertEqual(set(spec["families"]), set(spec["runs"]), path.name)
                self.assertTrue((ROOT / spec["structure_csv"]).exists(), path.name)
                for family in spec["families"].values():
                    self.assertEqual(set(family["hold"]), {"daily", "weekly", "monthly"})
                for key in ("min_random_percentile", "min_trade_excess_t", "lead_t", "min_lead_signals"):
                    self.assertIn(key, spec["criteria"], path.name)
                continue
            if spec.get("kind") == "levels":
                self.assertEqual(set(spec["families"]), set(spec["runs"]), path.name)
                self.assertEqual(set(spec["hold"]), {"daily", "weekly", "monthly"})
                self.assertTrue(all(c["family"] in spec["families"] for c in spec.get("extra_checks", [])), path.name)
                for key in ("min_random_percentile", "min_trade_excess_t", "lead_t", "min_lead_signals"):
                    self.assertIn(key, spec["criteria"], path.name)
                cases = [json.loads(p.read_text()) for p in (ROOT / "research/lab/queue").glob("*.json") if json.loads(p.read_text()).get("kind") == "cases"]
                # The acceptance check must test exactly the rules the experiment trades.
                self.assertTrue(any(c["rules"] == spec["rules"] for c in cases), path.name)
                continue
            if spec.get("kind") == "cases":
                self.assertTrue(all(c["expect"] in ("reject", "flag", "accept") for c in spec["cases"]), path.name)
                continue
            if spec.get("kind") == "selection":
                for key in ("min_random_percentile", "min_trade_excess_t"):
                    self.assertIn(key, spec["criteria"], path.name)
                self.assertGreaterEqual(spec["random_runs"], 100)
                continue
            if spec.get("kind") == "allocation":
                ids = {p["id"] for p in spec["portfolios"]}
                self.assertIn(spec["benchmark_portfolio"], ids, path.name)
                series = set(spec["dataset"].get("symbols") or spec["dataset"].get("chains"))
                self.assertTrue(all(allocation.roles(p) <= series for p in spec["portfolios"]), path.name)
                for p in spec["portfolios"]:
                    if p.get("weights"):
                        # A rotation sleeve fills whatever the fixed weights leave.
                        self.assertAlmostEqual(sum(p["weights"].values()) + p.get("sleeve", 0.0), 1.0, msg=p["id"])
                continue
            ids = set(run_queue.expand_variants(spec)[0])
            self.assertIn(spec["baseline"], ids)
            for vid, neighbours in spec.get("neighbours", {}).items():
                self.assertTrue({vid, *neighbours} <= ids, path.name)
            if spec.get("kind") == "account":
                self.assertIn("benchmark", spec, path.name)
                for key in ("min_trades", "max_drawdown", "beat_baseline", "beat_benchmark"):
                    self.assertIn(key, spec["criteria"], path.name)
            else:
                for key in ("min_expectancy_r", "min_profit_factor", "min_sqn", "min_split_trades", "min_trades"):
                    self.assertIn(key, spec["criteria"], path.name)
            if "benchmark" in spec:
                self.assertTrue(spec["benchmark"]["symbol"] in spec["benchmark"]["dataset"]["symbols"], path.name)
            if "not_before" in spec:
                dt.date.fromisoformat(spec["not_before"])


if __name__ == "__main__":
    unittest.main()
