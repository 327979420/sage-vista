import unittest

from research.backtest.score_factor_study_v1 import bh_adjust, deduplicate, metrics, percentile


class ScoreFactorStudyV1Tests(unittest.TestCase):
    def test_metrics_reports_profit_factor_and_cost(self):
        rows = [{"returns": {"20": .10}}, {"returns": {"20": -.05}}]
        self.assertEqual(metrics(rows, 20)["profit_factor"], 2.0)
        self.assertLess(metrics(rows, 20, 50)["expectancy_pct"], metrics(rows, 20)["expectancy_pct"])

    def test_deduplicate_keeps_first_ticker_event(self):
        rows = [
            {"ticker": "A", "date": "2025-01-01"},
            {"ticker": "A", "date": "2025-01-20"},
            {"ticker": "A", "date": "2025-03-01"},
            {"ticker": "B", "date": "2025-01-20"},
        ]
        self.assertEqual(len(deduplicate(rows)), 3)

    def test_bh_is_bounded_and_ordered(self):
        adjusted = bh_adjust([.01, .04, .03])
        self.assertTrue(all(0 <= value <= 1 for value in adjusted))
        self.assertLessEqual(adjusted[0], adjusted[2])

    def test_percentile(self):
        self.assertEqual(percentile([0, 10], .9), 9)


if __name__ == "__main__":
    unittest.main()
