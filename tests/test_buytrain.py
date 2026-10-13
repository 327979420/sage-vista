import random
import unittest
from collections import Counter

from research.lab import account, buysystem as B, buytrain as T, datasets
from research.lab.exit_rules import simulate as reference
from tests.test_buysystem import walk


def cut(series, limit):
    return {k: v[:limit] for k, v in series.items()}


class SimulatorTests(unittest.TestCase):
    def test_the_fast_simulator_matches_the_shared_one_for_both_runners(self):
        rng = random.Random(5)
        s = walk(2600, seed=21, drift=0.0005)
        checked, reasons = {"resolved": 0, "observing": 0}, set()
        for kind in ("month", "week"):
            runner = B.PARAMS["kinds"][kind]["runner"]
            for _ in range(400):
                limit = rng.randrange(400, len(s["date"]) + 1)
                i = rng.randrange(1, limit)
                entry = s["open"][i]
                stop = entry * (1 - rng.uniform(0.02, 0.3))
                target = entry + rng.uniform(0.5, 4) * (entry - stop)
                variant = {"stop": {"kind": "level", "price": stop}, "targets": [{"price": target, "fraction": 2 / 3}],
                           "breakeven_after_target": True, "trend_after_target": True, "trend_exit": dict(runner), "max_hold": 5040}
                want = reference(datasets.BarsView(cut(s, limit)), i, variant, cost_per_side=0.001)
                got = T.simulate(s, limit, i, stop, target, 2 / 3, runner, 5040, 0.001)
                self.assertEqual(got, want)
                checked[got["status"]] += 1
                reasons.add(got.get("exit_reason"))
                if got["status"] in ("resolved", "observing"):
                    self.assertEqual(T.candidate(s, limit, i, got, "e", "X", "d", 0, "2099-01-01"),
                                     account.candidate({"event_id": "e", "symbol": "X", "signal_date": "d"}, datasets.BarsView(cut(s, limit)), i, got, 0,
                                                       "2099-01-01"))
        self.assertGreater(checked["resolved"], 100)
        self.assertGreater(checked["observing"], 10)
        self.assertTrue({"stop", "trend_exit"} <= reasons)


class SettingsTests(unittest.TestCase):
    def test_overrides_change_only_the_named_parameter_and_reject_unknown_ones(self):
        p = T.override(B.PARAMS, {"kinds.week.a.min_pullback": 0.08, "daily.window": 5})
        self.assertEqual(p["kinds"]["week"]["a"]["min_pullback"], 0.08)
        self.assertEqual(p["daily"]["window"], 5)
        self.assertEqual(B.PARAMS["kinds"]["week"]["a"]["min_pullback"], 0.15)
        self.assertEqual(p["kinds"]["month"]["a"]["min_pullback"], 0.15)
        with self.assertRaises(KeyError):
            T.override(B.PARAMS, {"daily.windw": 5})
        self.assertEqual(T.engine_changes({"account.rank": "rs_6m", "veto.place_macd": False}), {"veto.place_macd": False})

    def test_a_change_is_adopted_only_when_it_clears_both_margins_with_enough_trades(self):
        sel = {"min_trades": 60, "sharpe_gain": 0.05, "beat_share_gain": 0.05}
        arm = lambda sharpe, beats, trades=100: {"sv": {"sharpe": sharpe, "trades_taken": trades}, "random": {"sv_beats_share_sharpe": beats}}
        base = arm(0.50, 0.60)
        self.assertTrue(T.adopt(base, arm(0.55, 0.65), sel))
        self.assertFalse(T.adopt(base, arm(0.60, 0.62), sel))
        self.assertFalse(T.adopt(base, arm(0.52, 0.90), sel))
        self.assertFalse(T.adopt(base, arm(0.90, 0.90, trades=59), sel))

    def test_the_market_filter_uses_the_close_against_its_200_day_average(self):
        spy = {"date": [f"d{i:04d}" for i in range(260)], "close": [100.0] * 199 + [101.0] + [90.0] * 60}
        ok = T.market_filter_days(spy)
        self.assertIn("d0199", ok)
        self.assertNotIn("d0198", ok)
        self.assertNotIn("d0259", ok)


class RunTests(unittest.TestCase):
    def test_a_small_run_keeps_every_training_trade_inside_the_training_window(self):
        prices = {f"S{k}": walk(2600, seed=30 + k, drift=0.0006) for k in (1, 2, 3, 4, 8)}
        spy = walk(2600, seed=99, drift=0.0003)
        spec = {"id": "t", "experiment_id": "t", "group": "t", "question": "q",
                "windows": {"train": ["2001-01-01", "2005-12-31"], "test": ["2006-01-01", "2009-12-31"]},
                "pool": {"min_history": 250, "min_close": 5.0, "min_dollar_volume": 1e7},
                "account": {"risk_per_trade": 0.02, "position_cap": 0.05, "max_positions": 10, "heat_cap": 0.2},
                "random": {"runs": 2, "seed": 1, "max_draws": 10},
                "variants": {"V7": {"account.market_filter": True}},
                "selection": {"min_trades": 1, "sharpe_gain": 0.05, "beat_share_gain": 0.05},
                "criteria": {"min_random_share": 0.95, "min_trade_excess_t": 2.0, "min_test_signals": 1}}
        entry = {"dataset_id": "x", "asset": "x", "sha256": "x", "symbols": 5}
        result, rows = T.run(spec, {"prices": prices}, entry, 0.001, {"symbol": "SPY", "series": spy, "entry": entry}, workers=1)
        self.assertEqual(set(result["train"]), {"baseline", "V7"})
        self.assertIn("passed", result["test"])
        self.assertEqual(Counter(r["window"] for r in rows if r["arm"] in ("baseline", "final")), {"train": 2, "test": 2})
        self.assertTrue(all(r["net"] is not None or r["exit"] is None for r in rows))
        for r in rows:
            window = spec["windows"][r["window"]]
            self.assertTrue(window[0] <= r["fill_date"] <= window[1])
        self.assertTrue(T.render(result).startswith("# t"))


if __name__ == "__main__":
    unittest.main()
