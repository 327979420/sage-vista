import unittest
from unittest.mock import patch

from services.scanner import unified_v2_scan


class HistoricalMarketOptionalTest(unittest.TestCase):
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
