import unittest

from services.scanner.support_risk import executable_stop, simulate_execution
from services.scanner.unified_v2_scan import _compact_day


class SupportRiskTests(unittest.TestCase):
    def test_support_stop_is_capped_at_ten_percent_of_entry(self):
        plan = executable_stop(100, {"level": 80, "source": "confirmed-swing-low"})
        self.assertTrue(plan["executable"])
        self.assertEqual(plan["stop"], 90)
        self.assertEqual(plan["stop_source"], "max-loss-10pct-cap")

    def test_near_support_uses_five_percent_buffer(self):
        plan = executable_stop(100, {"level": 98, "source": "volume-profile-poc"})
        self.assertEqual(plan["stop"], 93.1)
        self.assertEqual(plan["stop_source"], "volume-profile-poc")

    def test_same_bar_uses_stop_before_target(self):
        path = [{"date": "2026-01-02", "open": 100, "low": 90, "high": 120, "close": 110}]
        result = simulate_execution(100, {"level": 100, "source": "EMA21"}, path)
        self.assertEqual(result["exit_reason"], "stop")
        self.assertEqual(result["return"], -0.05)

    def test_public_history_keeps_audit_state_without_raw_evidence(self):
        day = {
            "date": "2026-01-01",
            "rare_opportunities": [{"symbol": "PG"}],
            "ranking": [{"symbol": "PG", "factor_summary": {"scored_hits": ["MACD"]}, "factor_ledger": [{"factor_id": "macd.daily_bull_cross", "name": "MACD", "available": True, "hit": True, "active_now": True, "bars_since_hit": 0, "points": 3, "evidence": {"raw": 1}}]}],
        }
        compact = _compact_day(day)
        self.assertEqual(compact["rare_symbols"], ["PG"])
        self.assertNotIn("factor_ledger", compact["rare_opportunities"][0])
        self.assertNotIn("factor_summary", compact["ranking"][0])
        self.assertNotIn("evidence", compact["ranking"][0]["factor_ledger"][0])


if __name__ == "__main__":
    unittest.main()
