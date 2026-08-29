import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class WinnerLoserOptimizationWorkflowTests(unittest.TestCase):
    def test_workflow_reuses_cache_and_v2_events(self):
        text = (ROOT / ".github/workflows/winner-loser-strategy-optimization.yml").read_text()
        self.assertIn("score-timeframe-attribution-v2-", text)
        self.assertIn("eodhd-history-v1-", text)
        self.assertIn("winner_loser_optimization_v1", text)
        self.assertNotIn("EODHD_API_TOKEN", text)
        self.assertIn("top-bottom-100-detail.json.gz", text)


if __name__ == "__main__":
    unittest.main()
