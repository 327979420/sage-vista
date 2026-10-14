import unittest

from research.lab import answer_key, buytrain, selection, triangle, triangle_exam
from tests.test_buysystem import walk


def weekly_rows(highs, lows, closes):
    return [{"date": f"w{k:03d}", "open": c, "high": h, "low": l, "close": c} for k, (h, l, c) in enumerate(zip(highs, lows, closes))]


def triangle_weeks(last_bottom=14.05):
    """Pushes at weeks 5, 15 and 25 (20, 18.5, 17), bottoms at 10, 20 and 30, a close above the line in week 33."""
    highs, lows, closes = [15.0] * 40, [14.6] * 40, [14.8] * 40
    for k, v in ((5, 20.0), (15, 18.5), (25, 17.0)):
        highs[k] = v
    for k, v in ((10, 14.0), (20, 14.1), (30, last_bottom)):
        lows[k] = v
    highs[33], closes[33] = 17.5, 17.0
    return weekly_rows(highs, lows, closes)


class TriangleShapeTests(unittest.TestCase):
    def test_a_three_push_line_with_level_bottoms_is_a_triangle(self):
        rows = triangle_weeks()
        lines = triangle.push_lines(rows, [5, 15, 25], 33, broken=True)
        self.assertEqual([ln["pushes"] for ln in lines], [[5, 15, 25]])
        self.assertEqual(triangle.push_lines(rows, [5, 15, 25], 33, broken=False), [])
        bots = triangle.bottoms_of(rows, [5, 15, 25], 33)
        self.assertEqual([j for j, _ in bots], [10, 20, 30])
        self.assertTrue(triangle.converging(lines[0]["line"], bots, 5, 33))

    def test_a_last_bottom_more_than_one_percent_under_the_first_is_not_a_triangle(self):
        self.assertIsNotNone(triangle.bottoms_of(triangle_weeks(13.87), [5, 15, 25], 33))  # 0.93% lower: still level enough
        self.assertIsNone(triangle.bottoms_of(triangle_weeks(13.8), [5, 15, 25], 33))     # DHI 2014: 1.4% lower

    def test_a_line_already_closed_above_before_the_signal_is_stale(self):
        rows = triangle_weeks()
        rows[28]["close"] = 17.5  # above the line (16.55 at week 28) by more than 1%
        self.assertEqual(triangle.push_lines(rows, [5, 15, 25], 33, broken=True), [])

    def test_volume_ratio_and_buy_stop_orders(self):
        self.assertEqual(triangle.volume_ratio({"volume": [100] * 10 + [250]}, 10), 2.5)
        # two weeks of daily bars after signal week 0: the buy-stop at 10.5 fills on the first day that reaches it
        s = {"date": [f"d{i}" for i in range(11)], "open": [10, 10, 10.6, 10, 10, 10, 10, 10, 10, 10, 10],
             "high": [10.2, 10.3, 10.9, 10.4, 10.4, 10.4, 10.4, 10.4, 10.4, 10.4, 10.4], "low": [9.8] * 11}
        W = {"start": [0, 1, 6], "end": [0, 5, 10]}
        self.assertEqual(triangle.order(s, W, None, 0, 3, 10.5, 9.0), (2, 10.6))  # gapped above the level: filled at the open
        s["low"][1] = 8.9
        self.assertIsNone(triangle.order(s, W, None, 0, 3, 10.5, 9.0))  # the stop traded first: cancelled
        s["low"][1], s["high"][2] = 9.8, 10.4
        s["open"][2] = 10
        self.assertIsNone(triangle.order(s, W, None, 0, 3, 10.5, 9.0))  # never reached in the order's weeks

    def test_rsi_stays_in_range(self):
        r = triangle.rsi([10 + (k % 7) - (k % 3) for k in range(80)])
        self.assertTrue(all(0 <= x <= 100 for x in r))


class BuyStopEntryTests(unittest.TestCase):
    def test_a_buy_stop_entry_uses_the_order_price_and_a_stop_touched_that_day_counts(self):
        s = {"date": [f"2010-01-{d:02d}" for d in range(4, 9)], "open": [10, 9.4, 10.6, 10.8, 11], "high": [10.2, 10.6, 11, 11.2, 11.4],
             "low": [9.9, 9.3, 10.5, 10.7, 10.9], "close": [10, 10.5, 10.9, 11.1, 11.3]}
        runner = {"kind": "daily_sma", "length": 3}
        # bought at 10.5 during day 1, whose open (9.4) was under the 9.5 stop and whose low (9.3) reached it: stopped at the stop
        r = buytrain.simulate(s, 5, 1, 9.5, 12, 2 / 3, runner, 100, 0.0, entry_price=10.5)
        self.assertEqual((r["entry"], r["exit_reason"], r["fills"][0]["price"]), (10.5, "stop", 9.5))
        # bought at that day's open instead, the stop would sit above the buy
        self.assertEqual(buytrain.simulate(s, 5, 1, 9.5, 12, 2 / 3, runner, 100, 0.0)["status"], "skipped")
        r = buytrain.simulate(s, 5, 2, 10.0, 11.0, 1.0, runner, 100, 0.0, entry_price=10.6)  # the target reached on the fill day
        self.assertEqual((r["entry"], r["exit_reason"], round(r["net_return"], 6)), (10.6, "target", round(11.0 / 10.6 - 1, 6)))

    def test_the_price_floor_can_read_the_unadjusted_close(self):
        s = {"date": ["d0", "d1", "d2"], "close": [3.0, 3.0, 3.0], "raw_close": [30.0, 30.0, 30.0], "volume": [5e6] * 3}
        pool = {"min_history": 1, "min_close": 5.0, "min_dollar_volume": 1e7}
        self.assertFalse(buytrain.tradable(s, 1, pool))
        self.assertTrue(buytrain.tradable(s, 1, {**pool, "raw_close": True}))
        self.assertEqual(selection.eligible_pool({"X": s}, "d1", pool), [])
        self.assertEqual(selection.eligible_pool({"X": s}, "d1", {**pool, "raw_close": True}), ["X"])


def card(option="C", nested=False, confluence=2, volume=1.0, entry=10.0, stop=9.0):
    return {"symbol": "X", "kind": "week", "option": option, "decision_date": "2010-01-08", "fill_date": "2010-01-12", "entry": entry, "stop": stop,
            "target": 13.0, "rr": 3.0, "entry_at": "stop_order", "nested": nested, "confluence_count": confluence, "volume_ratio": volume,
            "priority": (0 if nested else 1, -confluence)}


class ExamRuleTests(unittest.TestCase):
    def test_variants_filter_or_reshape_the_cards(self):
        cards = [card("C", volume=1.3, confluence=4), card("B", nested=True, confluence=1), card("B", volume=None, confluence=3)]
        self.assertEqual([c["option"] for c in triangle_exam.apply(cards, {"options": ["B"]})], ["B", "B"])
        self.assertEqual(len(triangle_exam.apply(cards, {"min_volume_ratio": 1.25})), 1)
        self.assertEqual(len(triangle_exam.apply(cards, {"min_confluence": 4})), 1)  # nesting alone does not pass
        fixed = triangle_exam.apply(cards, {"target_r": 1.5})[0]
        self.assertEqual((fixed["target"], fixed["rr"], cards[0]["target"]), (11.5, 1.5, 13.0))
        self.assertEqual(triangle_exam.params({"max_sessions": 130})["exit"]["max_sessions"], 130)
        with self.assertRaises(KeyError):
            triangle_exam.apply(cards, {"option": ["C"]})

    def test_contradicting_option_choices_keep_the_sharper_one(self):
        variants = {"V1": {"options": ["C"]}, "V2": {"options": ["B"]}, "V6": {"market_filter": True}}
        arms = {"V1": {"sv": {"sharpe": 0.4}}, "V2": {"sv": {"sharpe": 0.6}}, "V6": {"sv": {"sharpe": 0.5}}}
        self.assertEqual(triangle_exam.combine(["V1", "V2", "V6"], variants, arms), {"options": ["B"], "market_filter": True})
        self.assertEqual(triangle_exam.combine([], variants, arms), {})

    def test_the_exam_needs_three_shards_and_pooled_trades(self):
        crit = {"min_random_share": 0.95, "min_shards": 3, "min_trade_excess_t": 2.0, "min_exam_trades": 200}
        shard = lambda beats, sharpe: {"random": {"sv_beats_share_sharpe": beats}, "sv": {"sharpe": sharpe}, "spy": {"sharpe": 0.6}, "goal_1": {"met": False}}
        good = {"signals": 400, "t_monthly": 2.4, "median_difference": 0.01, "difference_winsorized": 0.02}
        checks, passed, goal = triangle_exam.verdict([shard(0.97, 0.7), shard(0.96, 0.5), shard(0.99, 0.8), shard(0.5, 0.2)], good, crit)
        self.assertTrue(passed)
        self.assertEqual((goal["shards_sharpe_at_least_spy"], goal["met"]), (2, False))
        self.assertFalse(triangle_exam.verdict([shard(0.97, 0.7), shard(0.9, 0.5), shard(0.99, 0.8), shard(0.5, 0.2)], good, crit)[1])
        self.assertFalse(triangle_exam.verdict([shard(0.97, 0.7)] * 4, {**good, "median_difference": -0.01}, crit)[1])


class AnswerKeyTests(unittest.TestCase):
    def test_a_case_counts_when_a_fill_lands_in_a_window_with_the_right_stop(self):
        key = {"cases": [{"symbol": "AAA", "expect": "buy", "windows": [["2010-03-01", "2010-03-12"]], "stop": 10.0},
                         {"symbol": "BBB", "expect": "none", "windows": [["2011-01-03", "2011-02-25"]]},
                         {"symbol": "CCC", "expect": "buy", "windows": [["2012-05-07", "2012-05-18"]]}]}
        scans = {"AAA": [{"options": {"C": {"fill": "2010-03-15", "entry": 11.0, "stop": 10.2}}}],  # within the four-day grace, stop 2% off
                 "BBB": [{"options": {"B": {"fill": "2011-03-14", "entry": 5.0, "stop": 4.5}}}],   # outside the no-buy window
                 "CCC": [{"options": {"B": {"fill": "2012-06-11", "entry": 5.0, "stop": 4.5}}}]}   # too late
        rows, hits = answer_key.score(lambda s: scans[s], key)
        self.assertEqual([r["ok"] for r in rows], [True, True, False])
        self.assertEqual(hits, 2)


class ExamRunTests(unittest.TestCase):
    def test_a_small_run_trains_reports_the_known_stocks_later_and_examines_each_shard(self):
        prices = {f"S{k}": walk(2600, seed=40 + k, drift=0.0005) for k in range(6)}
        shards = [{f"F{k}": walk(2600, seed=70 + k, drift=0.0005) for k in range(4)}, {f"G{k}": walk(2600, seed=90 + k, drift=0.0005) for k in range(4)}]
        for shard in shards:
            for s in shard.values():
                s["raw_close"] = list(s["close"])
        spy = walk(2600, seed=99, drift=0.0003)
        entry = {"dataset_id": "x", "asset": "x", "sha256": "x", "symbols": 6}
        spec = {"id": "t", "experiment_id": "t", "group": "t", "question": "q",
                "windows": {"train": ["2001-01-01", "2005-12-31"], "holdout": ["2006-01-01", "2009-12-31"], "exam": ["2001-01-01", "2009-12-31"]},
                "pool": {"min_history": 250, "min_close": 5.0, "min_dollar_volume": 1e7, "raw_close": True},
                "account": {"risk_per_trade": 0.02, "position_cap": 0.05, "max_positions": 10, "heat_cap": 0.2},
                "random": {"runs": 2, "seed": 1, "max_draws": 10},
                "variants": {"V1_c_only": {"options": ["C"]}, "V7": {"max_sessions": 130}},
                "selection": {"min_trades": 1, "sharpe_gain": 0.05, "beat_share_gain": 0.05},
                "criteria": {"min_random_share": 0.95, "min_shards": 2, "min_trade_excess_t": 2.0, "min_exam_trades": 1},
                "exam_datasets": [{"id": "fa"}, {"id": "fb"}]}
        loads = iter(shards)
        data = {"prices": prices}
        result, rows = triangle_exam.run(spec, data, entry, 0.001, {"symbol": "SPY", "series": spy, "entry": entry},
                                         lambda ds: ({"prices": next(loads)}, {"dataset_id": ds["id"], "asset": "a", "sha256": "s", "symbols": 4}), workers=1)
        self.assertEqual(set(result["train"]), {"baseline", "V1_c_only", "V7"})
        self.assertEqual([s["dataset"]["dataset_id"] for s in result["exam"]["shards"]], ["fa", "fb"])
        self.assertTrue(all(s["raw_close"] for s in result["exam"]["shards"]))
        self.assertFalse(result["train_raw_close"])
        self.assertEqual(data["prices"], {})  # the known stocks are released before the shards load
        for r in rows:
            window = {"train": spec["windows"]["train"], "holdout_known_stocks": spec["windows"]["holdout"], "exam": spec["windows"]["exam"]}[r["window"]]
            self.assertTrue(window[0] <= r["fill_date"] <= window[1])
        self.assertTrue(triangle_exam.render(result | {"completed_at": "2026-10-14"}).startswith("# t"))
        from research.lab import run_queue
        board, markdown = run_queue.render_scoreboard([result | {"completed_at": "2026-10-14"}])
        self.assertIn("weekly triangle", markdown)


if __name__ == "__main__":
    unittest.main()
