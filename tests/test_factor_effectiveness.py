import tempfile
import unittest
from pathlib import Path

from services.scanner.decision_summary import run as decision_summary
from services.scanner.factor_effectiveness import run as factor_effectiveness


class FactorEffectivenessTests(unittest.TestCase):
    def test_latest_audited_study_drives_all_four_quadrants(self):
        with tempfile.TemporaryDirectory() as folder:
            result = factor_effectiveness(out=Path(folder) / "factors.json")
        self.assertEqual(result["version"], "factor-effectiveness-v3.0.0")
        self.assertEqual(result["coverage"]["factors"], 37)
        self.assertEqual(result["coverage"]["audited_events"], 62170)
        self.assertEqual(result["quadrant_counts"], {"in_use": 7, "watch": 13, "paused": 9, "retire": 8})
        self.assertFalse(result["production_scoring_changed"])
        factors = {row["factor_id"]: row for row in result["factors"]}
        self.assertEqual(factors["macd.daily_bull_cross"]["production_role"], "event_gate")
        self.assertEqual(factors["volume.bottom_expansion"]["quadrant"], "in_use")
        self.assertEqual(factors["volume.bottom_expansion"]["latest_verdict"], "unstable")
        self.assertEqual(factors["volume.relative_expansion"]["quadrant"], "watch")
        self.assertEqual(factors["structure.double_bottom"]["quadrant"], "retire")
        self.assertEqual(factors["support.ema_proximity"]["quadrant"], "paused")

    def test_family_color_is_stable_across_quadrants(self):
        with tempfile.TemporaryDirectory() as folder:
            result = factor_effectiveness(out=Path(folder) / "factors.json")
        colors = {}
        for row in result["factors"]:
            colors.setdefault(row["family"], set()).add(row["family_color"])
        self.assertTrue(all(len(values) == 1 for values in colors.values()))
        self.assertEqual(len(colors), 8)

    def test_decision_summary_replaces_old_b_factor_claims(self):
        with tempfile.TemporaryDirectory() as folder:
            result = decision_summary(Path(folder) / "decision.json")
        self.assertEqual(result["version"], "production-evidence-v4.0.0")
        self.assertEqual(result["source_experiment"], "winner-loser-strategy-optimization-v1.0.0-2026-08-29")
        self.assertEqual(result["counts"]["validated_add_on_factors"], 0)
        self.assertEqual(result["usable"][0]["name"], "长期趋势＋完整日线MACD刚金叉")
        self.assertIn("把高分解释成更高胜率", {row["name"] for row in result["avoid"]})
        self.assertIn("直接采用最大赢家／输家推导的5项权重", {row["name"] for row in result["avoid"]})
        self.assertNotIn("底部放量", {row["name"] for row in result["usable"]})


if __name__ == "__main__":
    unittest.main()
