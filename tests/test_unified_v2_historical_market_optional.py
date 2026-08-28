import unittest
from unittest.mock import patch
import json
import tempfile
from pathlib import Path

from services.scanner import unified_v2_scan


class HistoricalMarketOptionalTest(unittest.TestCase):
    def test_non_trading_calendar_partition_is_valid_empty_checkpoint(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(unified_v2_scan, "_load_cache", return_value={"SPY": []}):
            out = Path(folder) / "empty.json"
            report = unified_v2_scan.run("2000-01-01", "2000-01-02", out, merge_existing=False)
            self.assertEqual(report["coverage"]["sessions"], 0)
            self.assertEqual(json.loads(out.read_text())["days"], [])

    def test_rank_day_records_unavailable_market_without_adjustment(self):
        snapshot = {"as_of":"2000-01-03","eligible_count":0,"triggered_count":0,"symbols":[]}
        industry = {"as_of":"2000-01-03","historical_membership_safe":False,"status":"unavailable"}
        day = unified_v2_scan._rank_day(snapshot, None, industry)
        self.assertEqual(day["market"], {"state":"unavailable","score":None})
        self.assertEqual(day["candidate_count"], 0)

    def test_missing_market_layer_does_not_remove_technical_day(self):
        data = {"SPY": [{"date": "2000-01-03"}]}
        with patch.object(unified_v2_scan, "_load_cache", return_value=data), \
             patch.object(unified_v2_scan, "build_snapshot", return_value={}), \
             patch.object(unified_v2_scan, "_market", return_value=None), \
             patch.object(unified_v2_scan, "_industry", return_value={}), \
             patch.object(unified_v2_scan, "_rank_day", return_value={"date":"2000-01-03","candidate_count":0,"ranking":[]}):
            report = unified_v2_scan.run("2000-01-03", "2000-01-03", "/tmp/v2-market-optional.json", merge_existing=False)
        self.assertEqual(report["coverage"]["sessions"], 1)
        self.assertEqual(report["days"][0]["candidate_count"], 0)


if __name__ == "__main__":
    unittest.main()
