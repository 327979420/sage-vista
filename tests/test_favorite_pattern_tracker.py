import unittest

from services.scanner.favorite_pattern_tracker import (
    PATTERN_VERSION,
    _atr,
    _confirmed_pivots,
    _find_double_bottom,
    _find_three_push,
    build_report,
    evaluate,
)


def rows(count=180, price=100.0):
    return [
        {
            "date": f"D{index:03d}",
            "open": price,
            "high": price + 1,
            "low": price - 1,
            "close": price,
            "volume": 1_000_000,
        }
        for index in range(count)
    ]


class FavoritePatternTrackerTests(unittest.TestCase):
    def test_pivots_require_two_completed_right_bars(self):
        data = rows(20)
        data[10]["low"] = 80
        data[19]["low"] = 70
        pivots = _confirmed_pivots(data, "low", "low")
        self.assertIn(10, pivots)
        self.assertNotIn(19, pivots)

    def test_wide_double_bottom_accepts_a_multi_month_structure(self):
        data = rows(170)
        data[40]["low"] = 90
        data[100]["low"] = 93
        data[70]["high"] = 112
        result = _find_double_bottom(data, _atr(data), [40, 100])
        self.assertIsNotNone(result)
        self.assertEqual(result["separation_sessions"], 60)
        self.assertLess(result["spread_pct"], 8)

    def test_three_push_needs_completed_close_breakout(self):
        data = rows(150)
        for index, high in ((20, 130), (60, 120), (100, 110)):
            data[index]["high"] = high
        data[109]["close"] = 105
        data[110]["close"] = 112
        result = _find_three_push(data, [20, 60, 100])
        self.assertIsNotNone(result)
        self.assertEqual(result["breakout_index"], 110)
        self.assertEqual(result["breakout_date"], "D110")

    def test_insufficient_history_fails_closed(self):
        result = evaluate(rows(259))
        self.assertFalse(result["available"])
        self.assertEqual(result["stage"], "unavailable")

    def test_report_keeps_reference_cases_without_promoting_them(self):
        base = {"available": True, "pattern_version": PATTERN_VERSION, "match_count": 4, "total_conditions": 7, "stage": "waiting_breakout", "stage_zh": "等待突破"}
        candidates = [
            {"symbol": "XYZ", "price": 10, "dollar_volume": 20_000_000, "favorite_pattern": {**base, "match_count": 6, "stage": "entry_ready", "stage_zh": "入场就绪"}},
            {"symbol": "BABA", "price": 120, "dollar_volume": 200_000_000, "favorite_pattern": {**base, "match_count": 2, "stage": "discovery", "stage_zh": "早期发现"}},
        ]
        report = build_report(candidates, "2026-08-28")
        self.assertEqual(report["candidates"][0]["symbol"], "XYZ")
        self.assertEqual(report["summary"]["entry_ready"], 1)
        references = {row["symbol"]: row for row in report["reference_cases"]}
        self.assertIn("BABA", references)
        self.assertIn("PG", references)
        self.assertFalse(report["production_scoring_changed"])


if __name__ == "__main__":
    unittest.main()
