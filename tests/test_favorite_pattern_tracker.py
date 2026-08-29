import json
import unittest
from pathlib import Path

from services.scanner.favorite_pattern_tracker import (
    GENERALIZATION_VERSION,
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


def known_case(symbol):
    payload = json.loads((Path(__file__).parent / "fixtures/favorite-pattern-v2-known-cases.json").read_text())
    columns = payload["columns"]
    return [dict(zip(columns, values)) for values in payload["symbols"][symbol]["rows"]]


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
        result = evaluate(rows(119))
        self.assertFalse(result["available"])
        self.assertEqual(result["stage"], "unavailable")

    def test_adbe_known_case_reaches_two_stage_confirmation_on_macd_day(self):
        case_rows = known_case("ADBE")
        before = evaluate([row for row in case_rows if row["date"] <= "2023-05-17"])
        signal_day = evaluate([row for row in case_rows if row["date"] <= "2023-05-18"])
        result = evaluate(case_rows)
        self.assertEqual(PATTERN_VERSION, "favorite-pattern-v2.0.0")
        self.assertEqual(before["match_count"], 6)
        self.assertNotEqual(before["stage"], "entry_ready")
        self.assertEqual(signal_day["stage"], "entry_ready")
        self.assertEqual(signal_day["sequence"]["completion_date"], "2023-05-18")
        self.assertEqual(result["stage"], "entry_ready")
        self.assertEqual(result["match_count"], 7)
        self.assertEqual(result["sequence"]["first_bottom"]["first_date"], "2023-02-24")
        self.assertEqual(result["sequence"]["first_bottom"]["second_date"], "2023-03-13")
        self.assertEqual(result["sequence"]["first_confirmation_date"], "2023-03-30")
        self.assertEqual(result["sequence"]["second_bottom"]["first_date"], "2023-05-04")
        self.assertEqual(result["sequence"]["second_bottom"]["second_date"], "2023-05-12")
        self.assertEqual(result["sequence"]["second_breakout_date"], "2023-05-17")
        self.assertEqual(result["sequence"]["second_macd_date"], "2023-05-18")
        self.assertEqual(result["sequence"]["completion_date"], "2023-05-18")
        self.assertEqual(result["sequence"]["full_alignment_date"], "2023-05-25")
        self.assertFalse(result["risk_gate"]["blocked"])

    def test_ttd_known_case_keeps_unresolved_bearish_pressure_visible(self):
        result = evaluate(known_case("TTD"))
        self.assertNotEqual(result["stage"], "entry_ready")
        self.assertTrue(result["risk_gate"]["blocked"])
        self.assertGreaterEqual(result["risk_gate"]["unresolved_pressure_rounds"], 2)

    def test_aeva_known_case_is_vetoed_by_top_supply_and_exhaustion(self):
        result = evaluate(known_case("AEVA"))
        self.assertEqual(result["stage"], "risk_blocked")
        self.assertTrue(result["risk_gate"]["blocked"])
        self.assertIsNotNone(result["risk_gate"]["multi_top"])
        self.assertTrue(result["risk_gate"]["top_exhaustion"])

    def test_report_keeps_reference_cases_without_promoting_them(self):
        conditions = [
            {"id": f"step_{index}", "label": f"机制{index}", "hit": index <= 6}
            for index in range(1, 8)
        ]
        base = {"available": True, "pattern_version": PATTERN_VERSION, "match_count": 4, "total_conditions": 7, "stage": "waiting_breakout", "stage_zh": "等待突破", "conditions": conditions}
        candidates = [
            {"symbol": "XYZ", "price": 10, "dollar_volume": 20_000_000, "favorite_pattern": {**base, "match_count": 6, "stage": "breakout_incomplete", "stage_zh": "已突破但条件不完整"}},
            {"symbol": "READY", "price": 20, "dollar_volume": 30_000_000, "favorite_pattern": {**base, "match_count": 7, "stage": "entry_ready", "stage_zh": "入场就绪", "conditions": [{**item, "hit": True} for item in conditions]}},
            {"symbol": "BABA", "price": 120, "dollar_volume": 200_000_000, "favorite_pattern": {**base, "match_count": 2, "stage": "discovery", "stage_zh": "早期发现"}},
        ]
        report = build_report(candidates, "2026-08-28")
        self.assertEqual(report["candidates"][0]["symbol"], "READY")
        self.assertEqual(report["summary"]["entry_ready"], 1)
        self.assertEqual(report["summary"]["breakout_incomplete"], 1)
        self.assertEqual(report["generalization_version"], GENERALIZATION_VERSION)
        self.assertEqual([row["symbol"] for row in report["entry_ready_candidates"]], ["READY"])
        self.assertEqual([row["symbol"] for row in report["near_matches"]], ["XYZ"])
        self.assertEqual(report["near_matches"][0]["mechanism_profile"]["status"], "near_match")
        self.assertEqual(report["near_matches"][0]["mechanism_profile"]["missing"][0]["label"], "机制7")
        self.assertFalse(report["generalization_policy"]["examples_are_templates"])
        self.assertEqual(report["generalization_policy"]["legacy_only_cases"], ["PG"])
        references = {row["symbol"]: row for row in report["reference_cases"]}
        self.assertIn("BABA", references)
        self.assertNotIn("PG", references)
        self.assertFalse(report["production_scoring_changed"])


if __name__ == "__main__":
    unittest.main()
