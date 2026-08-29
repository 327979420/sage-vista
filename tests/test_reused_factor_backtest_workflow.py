import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]


class ReusedFactorBacktestWorkflowTests(unittest.TestCase):
    def test_workflow_reuses_cache_and_archived_events(self):
        text = (ROOT / ".github/workflows/reused-factor-backtest.yml").read_text()
        self.assertIn("actions/cache@v4", text)
        self.assertIn("unified-v2-research-", text)
        self.assertIn("score-timeframe-attribution-v2", text)
        self.assertNotIn("unified_v2_scan", text)
        self.assertNotIn("EODHD_API_TOKEN", text)

    def test_workflow_archives_years_before_aggregate(self):
        text = (ROOT / ".github/workflows/reused-factor-backtest.yml").read_text()
        self.assertIn("natural-week checkpoints and annual audit", text)
        self.assertIn("retention-days: 90", text)
        self.assertIn("research/backtest/output/reused-v2/annual", text)


if __name__ == "__main__":
    unittest.main()
