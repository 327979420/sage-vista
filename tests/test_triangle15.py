import json
import math
import random
import unittest

from research.lab import triangle15 as N, triangle_forward as F


def series(closes, start="2020-01-01"):
    import datetime as dt
    d0 = dt.date.fromisoformat(start)
    dates, day = [], d0
    while len(dates) < len(closes):
        if day.weekday() < 5:
            dates.append(day.isoformat())
        day += dt.timedelta(days=1)
    return {"date": dates, "open": list(closes), "high": [c * 1.01 for c in closes], "low": [c * 0.99 for c in closes],
            "close": list(closes), "volume": [1e6] * len(closes)}


class TradeTests(unittest.TestCase):
    def test_limit_fill_then_target(self):
        s = series([100] * 5 + [97, 99, 105, 112, 120] + [120] * 80)
        got = N.trade(s, 4, 98.0, 90.0, 110.0)
        self.assertEqual(got["status"], "win")
        self.assertAlmostEqual(got["R"], (112.0 - 97.0) / (97.0 - 90.0))  # gapped over the target: sold at the open

    def test_stop_after_fill(self):
        s = series([100] * 5 + [97, 92, 88, 85] + [85] * 80)
        got = N.trade(s, 4, 98.0, 90.0, 110.0)
        self.assertEqual(got["status"], "loss")
        self.assertAlmostEqual(got["R"], (88.0 - 97.0) / (97.0 - 90.0))  # gapped under the stop: sold at the open

    def test_target_before_fill_cancels(self):
        s = series([100] * 5 + [104, 108, 112] + [112] * 80)
        self.assertEqual(N.trade(s, 4, 98.0, 90.0, 110.0)["status"], "cancelled")

    def test_time_stop(self):
        s = series([100] * 5 + [97] + [100] * 120)
        got = N.trade(s, 4, 98.0, 90.0, 130.0)
        self.assertEqual(got["status"], "time")
        self.assertEqual(got["exit_day"] - got["fill_day"], N.HOLD - 1)


class ShapeTests(unittest.TestCase):
    def test_signals_and_states_run_on_a_random_walk(self):
        rng = random.Random(7)
        c, closes = 50.0, []
        for _ in range(2600):
            c *= math.exp(rng.gauss(0, 0.02)); closes.append(c)
        s = series(closes, "2005-01-03")
        sigs = N.signals(s, pool={**N.POOL, "min_history": 0, "min_dollar_volume": 0})
        self.assertIsInstance(sigs, list)
        self.assertIn(N.daily_state(s, 2000), ("about", "crossed", "neither"))
        self.assertIsInstance(N.monthly_veto(s, 2000), bool)
        for sig in sigs:
            self.assertLess(sig["stop"], sig["t1"])

    def test_plan_skips_low_reward(self):
        s = series([100.0] * 400)
        sig = {"day": 399, "stop": 90.0, "t1": 104.0}
        p = N.plan(s, sig, 1.0)
        self.assertFalse(p["go"])
        self.assertEqual(p["why"], "R:R under 1.5")

    def test_taste_is_a_probability(self):
        n = 200
        W = {"close": [100 + math.sin(i / 7) * 10 for i in range(n)], "volume": [1e6] * n}
        W.update(high=[c * 1.02 for c in W["close"]], low=[c * 0.98 for c in W["close"]], open=list(W["close"]), atr=[2.0] * n,
                 dif=[math.sin(i / 9) for i in range(n)], dea=[math.sin((i - 3) / 9) for i in range(n)], ema20=list(W["close"]), ema200=[100.0] * n)
        model = json.loads((N.ROOT / "research/lab/cases/taste-model-v1.json").read_text())
        p = N.taste(W, {"t": 150, "pushes": [60, 90, 120], "bottoms": [100, 135]}, model)
        self.assertTrue(0 < p < 1)


class ForwardTests(unittest.TestCase):
    def test_extend_appends_and_stops_on_jumps(self):
        prices = {"A": series([10.0] * 3), "B": series([20.0] * 3), "OLD": series([5.0] * 2)}
        last = prices["A"]["date"][-1]
        bars = {"2030-01-02": {"A": [10, 11, 9.5, 10.5, 1000], "B": [45, 46, 44, 45, 1000], "OLD": [5, 5, 5, 5, 10]}}
        stopped = F.extend(prices, [last, "2030-01-02"], lambda d: bars[d])
        self.assertEqual(prices["A"]["date"][-1], "2030-01-02")
        self.assertEqual(prices["A"]["close"][-1], 10.5)
        self.assertEqual(stopped, {"B"})
        self.assertEqual(len(prices["OLD"]["date"]), 2)

    def test_summary_groups_by_the_users_answers(self):
        recs = [{"id": "a", "market": {"ok": True}}, {"id": "b", "market": {"ok": False}}, {"id": "c"}]
        outs = [{"id": "a", "status": "win", "R": 2.0, "random_R": 0.1}, {"id": "b", "status": "loss", "R": -1.0, "random_R": 0.0},
                {"id": "c", "status": "waiting"}]
        s = F.summary(recs, outs, {"a": "do", "b": "no"})
        self.assertEqual(s["user_do"]["trades"], 1)
        self.assertEqual(s["user_no"]["mean_R"], -1.0)
        self.assertEqual(s["open"], 1)
        self.assertEqual(s["rule18_all"]["trades"], 1)
        self.assertEqual(s["rule18_user_do"]["mean_R"], 2.0)


if __name__ == "__main__":
    unittest.main()
