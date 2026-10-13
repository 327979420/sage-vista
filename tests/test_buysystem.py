import datetime as dt
import random
import unittest

from research.lab import buysystem as B


def bars(opens, highs, lows, closes):
    """Bars in the engine's form from plain lists (one bar per list item)."""
    n = len(closes)
    b = {"date": [f"2000-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(n)], "open": list(opens), "high": list(highs),
         "low": list(lows), "close": list(closes), "volume": [1e6] * n}
    b = B._indicators(b)
    b["start"] = b["end"] = list(range(n))
    return b


def walk(days=2600, seed=7, drift=0.0004):
    rng, price, out = random.Random(seed), 20.0, {"date": [], "open": [], "high": [], "low": [], "close": [], "volume": []}
    day = dt.date(2000, 1, 3)
    for _ in range(days):
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        o = price
        price = max(1.0, price * (1 + drift + rng.gauss(0, 0.02)))
        out["date"].append(day.isoformat())
        out["open"].append(round(o, 4))
        out["high"].append(round(max(o, price) * (1 + abs(rng.gauss(0, 0.006))), 4))
        out["low"].append(round(min(o, price) * (1 - abs(rng.gauss(0, 0.006))), 4))
        out["close"].append(round(price, 4))
        out["volume"].append(1e6)
        day += dt.timedelta(days=1)
    return out


class SwingAndBarTests(unittest.TestCase):
    def test_a_swing_low_is_known_one_bar_later(self):
        values = [5, 4, 3, 4, 5, 2, 6]
        self.assertEqual(B.pivots(values, "low", 2, 1), [2, 5])
        self.assertEqual(B._known([2, 5], 5, 1), [2])
        self.assertEqual(B._known([2, 5], 6, 1), [2, 5])

    def test_the_open_week_at_the_end_of_the_data_is_not_complete_but_the_last_day_is(self):
        s = walk(30)
        n = len(s["close"])
        W, Dd = B.periods(s, "week"), B.daily_bars(s)
        self.assertEqual(B.completed(Dd, n - 1, n), n - 1)
        self.assertEqual(B.completed(W, n - 1, n), len(W["close"]) - 2)


class BackgroundTests(unittest.TestCase):
    CFG = {"lookback": 36, "tol_pct": 0.03, "tol_atr": 0.5, "min_gap": 3, "follow_bars": 3, "follow_body_atr": 0.5}

    def base(self, second_low, follow_close=33.0):
        # decline from 60 to a first bottom of 20 (bar 4), rebound to 40 (bar 7), second bottom (bar 10), follow-through (bar 11)
        closes = [58, 50, 40, 30, 22, 26, 34, 38, 32, 26, second_low + 2, follow_close, follow_close]
        lows = [56, 48, 38, 28, 20, 24, 30, 35, 30, 24, second_low, 26, 30]
        highs = [60, 59, 50, 40, 31, 30, 36, 40, 39, 33, 28, follow_close + 1, follow_close + 1]
        opens = [59, 58, 50, 40, 30, 22, 26, 34, 38, 32, 27, 24, follow_close]
        return bars(opens, highs, lows, closes)

    def test_a_higher_second_bottom_counts_when_it_retraces_at_least_half_of_the_rebound(self):
        X = self.base(23.0)
        b = B.second_bottom(X, 12, self.CFG, B.pivots(X["low"], "low", 2, 1))
        self.assertIsNotNone(b)
        self.assertEqual(b["_first"], 4)
        self.assertEqual(b["_second"], 10)
        self.assertEqual(b["neckline"], 40)

    def test_a_second_bottom_above_half_of_the_rebound_is_not_a_bottom(self):
        # first bottom 20, rebound to 40, the only later low is 33: above 30 (halfway), so not a second bottom
        closes = [58, 50, 40, 30, 22, 26, 34, 38, 37, 36, 35, 39, 39]
        lows = [56, 48, 38, 28, 20, 24, 30, 35, 34, 34, 33, 34, 36]
        highs = [60, 59, 50, 40, 31, 30, 36, 40, 39, 38, 37, 40, 40]
        opens = [59, 58, 50, 40, 30, 22, 26, 34, 38, 37, 36, 34, 39]
        X = bars(opens, highs, lows, closes)
        self.assertIn(10, B.pivots(X["low"], "low", 2, 1))
        self.assertIsNone(B.second_bottom(X, 12, self.CFG, B.pivots(X["low"], "low", 2, 1)))

    def test_a_second_bottom_far_below_the_first_is_not_a_bottom(self):
        X = self.base(12.0)
        self.assertIsNone(B.second_bottom(X, 12, self.CFG, B.pivots(X["low"], "low", 2, 1)))

    def test_a_pullback_must_come_after_the_high_bar_and_stay_within_half(self):
        cfg = {"a": {"rise": 6, "min_bars_ema200": 999, "high_lookback": 24, "leg_lookback": 60, "min_pullback": 0.15, "max_pullback": 0.5,
                     "touch_pct": 0.02, "touch_atr": 0.5, "gp": [0.5, 0.7]}, "b": self.CFG}
        rising = [10 + i for i in range(40)]
        X = bars(rising, [c + 1 for c in rising], [c - 1 for c in rising], rising)
        bg, _ = B.background(X, 39, cfg, [], None, None)
        self.assertIsNone(bg)  # the high is the latest bar: no pullback has happened yet
        closes = rising + [44, 40]  # 50 high -> 40: a 20% pullback after the high
        X = bars(closes, [c + 1 for c in closes], [c - 1 for c in closes], closes)
        bg, _ = B.background(X, 41, cfg, [], None, None)
        self.assertEqual(bg["kind"], "A")
        closes = rising + [30, 20]  # 50 -> 19: a collapse, not a pullback
        X = bars(closes, [c + 1 for c in closes], [c - 1 for c in closes], closes)
        bg, _ = B.background(X, 41, cfg, [], None, None)
        self.assertIsNone(bg)


class TimingTests(unittest.TestCase):
    def test_the_daily_layer_needs_a_close_above_yesterdays_high_and_a_rising_histogram_and_skips_gap_downs(self):
        s = walk(300, seed=3)
        Dd = B.daily_bars(s)
        found = B.daily_entry(s, Dd, 50, B.PARAMS)
        if found:
            i, fill, entry = found
            self.assertGreater(s["close"][i], s["high"][i - 1])
            self.assertGreater(Dd["hist"][i], Dd["hist"][i - 1])
            self.assertEqual((fill, entry), (i + 1, s["open"][i + 1]))
            # make that next open a gap down of more than one ATR: the day is skipped, the search goes on
            s2 = {k: list(v) for k, v in s.items()}
            s2["open"][i + 1] = s["close"][i] - 2 * Dd["atr"][i]
            again = B.daily_entry(s2, Dd, 50, B.PARAMS)
            self.assertTrue(again is None or again[0] > i)


class ResistanceTests(unittest.TestCase):
    def test_a_fibonacci_line_needs_two_bar_highs_within_three_percent(self):
        # decline 100 -> 50 on daily data; weekly-like bars T carry the highs that confirm (or not) each line
        D = {"date": [f"d{i}" for i in range(6)], "high": [100, 90, 80, 70, 60, 55], "low": [95, 85, 75, 65, 50, 52],
             "open": [0] * 6, "close": [0] * 6, "volume": [0] * 6}
        T = {"date": [f"t{i}" for i in range(6)], "start": list(range(6)), "end": list(range(6)), "high": [100, 69.5, 69.0, 75.5, 60, 55]}
        above, leg = B.confluence(D, T, 5, 0, 5, 56.0, None, B.PARAMS["risk"])
        sources = [x["source"] for x in above]
        self.assertIn("fib_0.382", sources)      # 69.1 confirmed by 69.5 and 69.0
        self.assertNotIn("fib_0.5", sources)     # 75 has only one high (75.5) nearby
        self.assertEqual(sources[-1], "prior_high")
        self.assertEqual(above[0]["price"], 50 + 0.382 * 50)
        _, leg = B.confluence(D, T, 5, 0, 5, 68.0, None, B.PARAMS["risk"])
        self.assertTrue(any(x["source"] == "fib_0.382" for x in leg["inside"]))  # 68 is within 3% under 69.1


class EngineTests(unittest.TestCase):
    def test_both_kinds_share_one_parameter_shape(self):
        month, week = B.PARAMS["kinds"]["month"], B.PARAMS["kinds"]["week"]
        self.assertEqual(set(month), set(week))
        self.assertEqual(set(month["a"]), set(week["a"]))
        self.assertEqual(set(month["b"]), set(week["b"]))
        self.assertEqual((month["direction"], month["place"], month["filter"]), ("month", "week", None))
        self.assertEqual((week["direction"], week["place"], week["filter"]), ("week", "day", "month"))

    def test_scans_are_deterministic_and_never_fill_before_their_confirmation(self):
        s = walk(2600, seed=11, drift=0.0006)
        for kind in ("month", "week"):
            first, second = B.scan(s, kind), B.scan(s, kind)
            self.assertEqual(first, second)
            for card in first["signals"] + first["near_misses"]:
                self.assertGreater(card["fill_date"], card["confirmation"]["valid"])
                self.assertGreaterEqual(card["fill_date"], card["timing"])
            for card in first["signals"]:
                self.assertTrue(card["passed"])
                self.assertGreaterEqual(card["rr"], B.PARAMS["risk"]["min_rr"])
                self.assertLess(card["stop"], card["entry"])
                self.assertGreater(card["target"], card["entry"])
                t = B.trade(s, card)
                self.assertIn(t["status"], ("resolved", "observing"))


if __name__ == "__main__":
    unittest.main()
