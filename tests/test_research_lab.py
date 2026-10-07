import datetime as dt
import json
import pathlib
import random
import tempfile
import unittest

from research.lab import datasets, run_queue
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


class QueueAndDatasetTests(unittest.TestCase):
    def test_eod_window_blocks_publishing(self):
        for hhmm, blocked in [("23:29", False), ("23:30", True), ("02:00", True), ("04:29", True), ("04:30", False), ("12:00", False)]:
            h, m = map(int, hhmm.split(":"))
            self.assertEqual(run_queue.in_eod_window(dt.datetime(2026, 10, 7, h, m, tzinfo=dt.timezone.utc)), blocked, hhmm)

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

    def test_every_queued_spec_is_complete_and_linked_to_a_registered_experiment(self):
        registered = {json.loads(line)["experiment_id"] for line in (ROOT / "research/experiments.jsonl").read_text().splitlines() if line.strip()}
        for path in (ROOT / "research/lab/queue").glob("*.json"):
            spec = json.loads(path.read_text())
            self.assertIn(spec["experiment_id"], registered, path.name)
            ids = {v["id"] for v in spec["variants"]}
            self.assertIn(spec["baseline"], ids)
            for vid, neighbours in spec.get("neighbours", {}).items():
                self.assertTrue({vid, *neighbours} <= ids, path.name)
            for key in ("min_expectancy_r", "min_profit_factor", "min_sqn", "min_split_trades", "min_trades"):
                self.assertIn(key, spec["criteria"])


if __name__ == "__main__":
    unittest.main()
