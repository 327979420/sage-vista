import copy
import unittest
from datetime import date, timedelta

from research.backtest.choppiness_state_mechanism_v1 import (
    analyze_rows,
    classify_state,
)
from research.factor_lab.features import CandidateSeries


class ChoppinessStateMechanismTests(unittest.TestCase):
    def test_primary_states_are_mutually_exclusive(self):
        self.assertEqual(classify_state(50, -8), "low_mid")
        self.assertEqual(classify_state(60, 3), "high_rising")
        self.assertEqual(classify_state(60, 0), "high_flat")
        self.assertEqual(classify_state(60, -3), "high_falling")
        self.assertIsNone(classify_state(None, 0))

    def test_choppiness_change_uses_no_future_rows(self):
        start = date(2019, 1, 1)
        rows = []
        for index in range(320):
            close = 100 + index * 0.08 + (index % 11 - 5) * 0.4
            rows.append({
                "date": (start + timedelta(days=index)).isoformat(),
                "open": close - 0.2,
                "high": close + 1.1,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000_000,
            })
        signal_date = rows[250]["date"]
        baseline = CandidateSeries(copy.deepcopy(rows)).choppiness_change(signal_date, 5)
        rows[290].update({"high": 9_000, "low": 0.1, "close": 8_000})
        changed = CandidateSeries(rows).choppiness_change(signal_date, 5)
        self.assertEqual(baseline, changed)

    def test_analysis_never_changes_production(self):
        rows = []
        states = {
            "low_mid": (50.0, 0.0, -0.01),
            "high_rising": (62.0, 4.0, 0.005),
            "high_flat": (62.0, 0.0, 0.01),
            "high_falling": (62.0, -4.0, 0.03),
        }
        signal_index = 0
        for year in (2020, 2025, 2026):
            for state, (current, change, outcome) in states.items():
                for index in range(310):
                    realized = (
                        outcome
                        + (0.04 if index % 2 else -0.04)
                        + ((index % 7) - 3) * (0.002 if state == "high_falling" else 0.001)
                    )
                    rows.append({
                        "symbol": f"{state}-{year}-{index}",
                        "date": f"{year}-06-15",
                        "signal_index": signal_index,
                        "scores": {"current": 3},
                        "factors": [],
                        "returns": {str(horizon): realized for horizon in (5, 10, 20, 40, 60)},
                        "legacy_features": {
                            "momentum.return_20_pct": 0.01,
                            "location.pullback_60d_pct": -0.06,
                            "volatility.atr14_pct": 0.02,
                        },
                        "choppiness_state": {
                            "current": current,
                            "change_3": change,
                            "change_5": change,
                        },
                    })
                    signal_index += 121
        report, _ = analyze_rows(rows)
        self.assertFalse(report["production_scoring_changed"])
        self.assertEqual(report["coverage"]["primary_events"], len(rows))
        self.assertEqual(
            report["candidate_decision"]["verdict"],
            "add_zero_weight_research_candidate",
        )
        self.assertEqual(report["candidate_decision"]["production_weight"], 0)


if __name__ == "__main__":
    unittest.main()
