"""Independent arithmetic and causality checks for the registered portfolios."""
import datetime as dt
import math
import statistics
import unittest

from research.lab.combine import (combine, equal_weights, inverse_volatility,
                                  portfolios, volatility_target)


def calendar(n):
    days, day = [], dt.date(2005, 1, 3)
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += dt.timedelta(days=1)
    return days


def series(n):
    return {name: [amplitude * math.sin(i * frequency) for i in range(n)]
            for name, amplitude, frequency in
            (("TREND", .01, .7), ("MOMLV", .02, .4), ("3W", .03, .3))}


class CombineTests(unittest.TestCase):
    def test_no_lookahead_next_session_for_all_portfolios(self):
        dates = calendar(340)
        data = series(len(dates))
        i = next(i for i in range(260, 320) if dates[i][:7] != dates[i + 1][:7])
        changed = {k: list(v) for k, v in data.items()}
        changed["TREND"][i + 1] = .8
        original = portfolios(dates, data)
        future = portfolios(dates, changed)
        for name in original:
            a, b = original[name], future[name]
            self.assertEqual(a["equity"][:i + 1], b["equity"][:i + 1])
            self.assertEqual(a["start_weights"][i + 1], b["start_weights"][i + 1])
            self.assertEqual([d for d in a["decisions"] if d["decision_date"] <= dates[i]],
                             [d for d in b["decisions"] if d["decision_date"] <= dates[i]])
            self.assertNotEqual(a["equity"][i + 1], b["equity"][i + 1])

    def test_drift_without_rebalancing(self):
        result = combine(["2020-01-02", "2020-01-03", "2020-01-06"],
                         {"a": [.1, .1, 0], "b": [0, 0, 0]}, equal_weights, 0)
        self.assertAlmostEqual(result["equity"][1], 110500)
        self.assertAlmostEqual(result["weights"][0]["a"], 55 / 105)
        self.assertAlmostEqual(result["weights"][1]["a"], 60.5 / 110.5)
        self.assertEqual(result["fees"], [0, 0, 0])

    def test_fee_once_and_next_session_return_uses_target(self):
        result = combine(["2020-01-30", "2020-01-31", "2020-02-03", "2020-02-04"],
                         {"a": [0, .2, .1, 0], "b": [0, 0, 0, 0]}, equal_weights, .001)
        turnover = abs(.5 - 6 / 11) + abs(.5 - 5 / 11)
        fee = 110000 * .001 * turnover
        self.assertAlmostEqual(result["fees"][2], fee)
        self.assertAlmostEqual(result["equity"][2], (110000 - fee) * 1.05)
        self.assertEqual([result["fees"][i] for i in (0, 1, 3)], [0, 0, 0])
        self.assertEqual(len(result["decisions"]), 1)
        self.assertEqual(result["decisions"][0]["execution_date"], "2020-02-03")

    def test_unchanged_weights_have_no_fee(self):
        result = combine(["2020-01-31", "2020-02-03"], {"a": [0, 0], "b": [0, 0]}, equal_weights)
        self.assertEqual(result["fees"], [0, 0])

    def test_equal_weights_before_252_and_exact_window(self):
        data = series(300)
        for n in (1, 63, 251):
            h = {k: v[:n] for k, v in data.items()}
            self.assertEqual(inverse_volatility(h), equal_weights(h))
        for n in (252, 300):
            h = {k: v[:n] for k, v in data.items()}
            inv = {k: 1 / statistics.stdev(v[-252:]) for k, v in h.items()}
            for k, w in inverse_volatility(h).items():
                self.assertAlmostEqual(w, inv[k] / sum(inv.values()))
        p2 = portfolios(calendar(300), data)["P2"]
        for decision in p2["decisions"]:
            if calendar(300).index(decision["decision_date"]) < 251:
                self.assertEqual(decision["target"], equal_weights(data))

    def test_p3_window_scale_cash_and_no_leverage(self):
        data = series(300)
        low = [.0001 * (-1) ** i for i in range(300)]
        high = [.1 * (-1) ** i for i in range(300)]
        self.assertEqual(volatility_target(data, low), inverse_volatility(data))
        scaled = volatility_target(data, high)
        scale = .1 / (statistics.stdev(high[-63:]) * math.sqrt(252))
        self.assertAlmostEqual(sum(scaled.values()), scale)
        # Older P2 returns do not enter the 63-session window.
        self.assertEqual(scaled, volatility_target(data, [5.] * 237 + high[-63:]))
        h = {k: v[:62] for k, v in data.items()}
        self.assertEqual(volatility_target(h, high[:62]), equal_weights(h))
        p3 = portfolios(calendar(300), data)["P3"]
        for weights in p3["weights"] + p3["start_weights"]:
            self.assertLessEqual(sum(weights.values()), 1 + 1e-12)
            self.assertGreaterEqual(min(weights.values()), 0)
        for weights, cash in zip(p3["weights"], p3["cash_weight"]):
            self.assertAlmostEqual(sum(weights.values()) + cash, 1)
        self.assertTrue(any(c > 0 for c in p3["cash_weight"]))

    def test_cash_cost_is_not_double_counted(self):
        result = combine(["2020-01-31", "2020-02-03", "2020-02-04"],
                         {"a": [0, 0, 0]}, lambda h: {"a": .5})
        self.assertEqual(result["fees"], [0, 50, 0])
        self.assertEqual(result["equity"], [100000, 99950, 99950])

    def test_reject_bad_input_and_leverage(self):
        with self.assertRaises(ValueError):
            combine(["2020-01-31", "2020-02-03"], {"a": [0, 0]}, lambda h: {"a": 1.1})
        with self.assertRaises(ValueError):
            combine(["2020-01-31"], {"a": [float("nan")]}, equal_weights)
        with self.assertRaises(ValueError):
            volatility_target({"a": [0]}, [0, 0])


if __name__ == "__main__":
    unittest.main()
