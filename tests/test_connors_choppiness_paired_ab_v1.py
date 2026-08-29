import unittest

from research.backtest.connors_choppiness_paired_ab_v1 import (
    A_ID,
    B_ID,
    analyze_rows,
    factor_group,
)


class ConnorsChoppinessPairedABTests(unittest.TestCase):
    def test_groups_are_mutually_exclusive(self):
        def row(a, b):
            return {"candidate_features": {A_ID: a, B_ID: b}}

        self.assertEqual(factor_group(row(80, 40)), "none")
        self.assertEqual(factor_group(row(60, 40)), "a_only")
        self.assertEqual(factor_group(row(80, 70)), "b_only")
        self.assertEqual(factor_group(row(60, 70)), "both")

    def test_analysis_preserves_no_production_change(self):
        rows = []
        group_values = {
            "none": (80, 40, -0.01),
            "a_only": (60, 40, 0.01),
            "b_only": (80, 70, 0.02),
            "both": (60, 70, 0.04),
        }
        for year in (2020, 2025, 2026):
            for group, (a_value, b_value, outcome) in group_values.items():
                for index in range(110):
                    rows.append({
                        "symbol": f"{group}-{year}-{index}",
                        "date": f"{year}-06-15",
                        "signal_index": len(rows) * 121,
                        "scores": {"current": 3},
                        "factors": [],
                        "returns": {str(horizon): outcome for horizon in (5, 10, 20, 40, 60)},
                        "candidate_features": {A_ID: a_value, B_ID: b_value},
                        "legacy_features": {
                            "momentum.return_20_pct": 0.01,
                            "location.pullback_60d_pct": -0.06,
                            "volatility.atr14_pct": 0.02,
                        },
                    })
        report, _ = analyze_rows(rows)
        self.assertFalse(report["production_scoring_changed"])
        self.assertEqual(report["coverage"]["primary_events"], 1320)
        self.assertIn("both_vs_none", report["decisions"])
        self.assertEqual(report["production_action"], "none")


if __name__ == "__main__":
    unittest.main()
