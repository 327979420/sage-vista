import json
import tempfile
import unittest
from pathlib import Path

from research.backtest.long_history_summary_v1 import run


class LongHistorySummaryTest(unittest.TestCase):
    def test_complete_period_and_separate_technical_attribution(self):
        with tempfile.TemporaryDirectory() as folder:
            result = run(Path(folder) / "long.json", Path(folder) / "public.json")
            self.assertEqual(result["coverage"]["historical_sessions"], 6539)
            self.assertEqual(result["coverage"]["weekly_checkpoints"], 1379)
            self.assertEqual(result["coverage"]["historical_candidates"], 57271)
            self.assertTrue(result["technical_only_primary_test"])
            self.assertEqual(result["conclusion"]["tier_a"], [])
            self.assertIn("volume.bottom_expansion", result["conclusion"]["tier_b"])
            self.assertIn("structure.double_bottom", result["conclusion"]["tier_d"])
            public = json.loads((Path(folder) / "public.json").read_text())
            self.assertEqual(public["coverage"]["development"], "2001—2024")
            self.assertEqual(public["coverage"]["validation"], 2025)
            self.assertEqual(public["coverage"]["forward"], 2026)


if __name__ == "__main__":
    unittest.main()
