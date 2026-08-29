import unittest

from research.backtest.factor_family_return_combination_v1 import (
    COMBINATIONS,
    analyze_rows,
    family_flags,
    fit_thresholds,
    public_payload,
)


def row(symbol, year, kind, outcome):
    factors = ["macd.daily_bull_cross", "qualification.long_trend"]
    legacy = {
        "trend.ema200_slope_60_pct": 0.08,
        "volatility.atr14_pct": 0.02,
        "location.pullback_60d_pct": -0.10,
        "momentum.macd_histogram_change_3_pct": -0.01,
        "volume.relative_20": 0.7,
        "candle.close_location": 0.3,
    }
    candidates = {
        "location.days_since_high_60": 25,
        "risk.ulcer_index_20": 12,
        "pullback.return_balance_20": -0.5,
        "trend.directional_control_14": -10,
        "volume.chaikin_money_flow_20": -0.5,
        "volume.return_volume_corr_20": -0.5,
        "volatility.squeeze_ratio_20": 3,
    }
    if kind in {"all", "support"}:
        factors.append("support.ema_proximity")
    if kind in {"all", "pullback"}:
        factors.append("qualification.pullback_60d")
        candidates.update({
            "location.days_since_high_60": 18,
            "risk.ulcer_index_20": 3,
            "pullback.return_balance_20": 0.3,
        })
    if kind in {"all", "reacceleration"}:
        factors.append("volume.relative_expansion")
        legacy.update({
            "momentum.macd_histogram_change_3_pct": 0.03,
            "volume.relative_20": 2,
            "candle.close_location": 0.9,
        })
        candidates["trend.directional_control_14"] = 20
    if kind in {"all", "low_risk"}:
        candidates.update({
            "risk.ulcer_index_20": 2,
            "volume.chaikin_money_flow_20": 0.4,
            "volume.return_volume_corr_20": 0.4,
            "volatility.squeeze_ratio_20": 0.8,
        })
    else:
        factors.append("risk.overhead_unfilled_gap")
    return {
        "symbol": symbol,
        "date": f"{year}-06-15",
        "signal_index": year * 200,
        "factors": factors,
        "scores": {"current": 3},
        "returns": {str(horizon): outcome for horizon in (5, 10, 20, 40, 60)},
        "legacy_features": legacy,
        "candidate_features": candidates,
    }


class FactorFamilyReturnCombinationTests(unittest.TestCase):
    def test_family_state_deduplicates_support_evidence(self):
        rows = [row("BASE", 2020, "all", 0.05)]
        thresholds = fit_thresholds(rows)
        one = family_flags(rows[0], thresholds)
        duplicate = {**rows[0], "factors": rows[0]["factors"] + ["support.monthly_ema_proximity"]}
        two = family_flags(duplicate, thresholds)
        self.assertEqual(one, two)
        self.assertTrue(one["support_location"])
        self.assertTrue(one["reacceleration"])
        self.assertTrue(one["low_supply_risk"])

    def test_analysis_searches_only_fifteen_frozen_combinations(self):
        rows = []
        kinds = {
            "all": 0.08,
            "support": 0.01,
            "pullback": 0.012,
            "reacceleration": 0.015,
            "low_risk": 0.011,
            "none": -0.02,
        }
        for year in range(2009, 2027):
            for kind, outcome in kinds.items():
                for index in range(10):
                    rows.append(row(f"{kind}-{year}-{index}", year, kind, outcome + (index - 5) * 0.001))
        report = analyze_rows(rows)
        self.assertEqual(len(COMBINATIONS), 15)
        self.assertEqual(len(report["rolling_test_combination_ranking"]), 15)
        self.assertEqual(len(report["rolling_folds"]), 4)
        self.assertFalse(report["production_scoring_changed"])
        self.assertEqual(report["decision"]["production_weight"], 0)
        self.assertFalse(report["audit"]["2025_2026_used_for_selection"])
        self.assertIsNone(report["not_applicable_execution_metrics"]["mfe"])
        public = public_payload(report)
        self.assertFalse(public["production_scoring_changed"])
        self.assertEqual(public["candidate"]["production_weight"], 0)
        self.assertIn("rolling_test", public["candidate"])


if __name__ == "__main__":
    unittest.main()
