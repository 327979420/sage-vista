import gzip
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from research.backtest.reused_event_study_v2 import (
    PriceSeries,
    _dependency_safe_factors,
    _midrank_quintiles,
    aggregate,
    deduplicate,
    matrix,
)


ROOT = Path(__file__).parents[1]


def raw_rows(count=180, start=date(2025, 1, 1)):
    rows = []
    current = start
    price = 20.0
    while len(rows) < count:
        if current.weekday() < 5:
            price *= 1.002 if len(rows) > 50 else 0.999
            rows.append({
                "date": current.isoformat(),
                "open": price * 0.995,
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price,
                "adjusted_close": price,
                "volume": 1_000_000,
            })
        current += timedelta(days=1)
    return rows


class ReusedEventStudyV2Tests(unittest.TestCase):
    def test_committed_result_matches_the_audited_completion_record(self):
        result = json.loads((ROOT / "research/backtest/output/score-timeframe-attribution-v2.json").read_text())
        self.assertFalse(result["production_scoring_changed"])
        self.assertTrue(result["technical_only_primary_test"])
        self.assertEqual(result["coverage"]["all_events"], 62_170)
        self.assertEqual(result["coverage"]["primary_120_session_deduplicated_events"], 13_296)
        self.assertEqual(result["coverage"]["natural_week_checkpoints"], 1_414)
        annual = result["annual_coverage"]
        self.assertEqual(sum(item["coverage"]["source_candidates"] for item in annual), 63_817)
        self.assertEqual(sum(item["coverage"]["missing_price_events"] for item in annual), 1_615)
        self.assertEqual(sum(item["audits"]["daily_gate_mismatches"] for item in annual), 32)
        factors = result["primary_deduplicated"]["single_factors"]
        self.assertEqual(len(factors), 31)
        self.assertFalse(any(item["verdict"] == "validated" for item in factors))
        self.assertFalse(any(item["verdict"] == "validated" for item in result["primary_deduplicated"]["frozen_pairs"]))

    def test_outcomes_enter_at_next_open_and_use_requested_session(self):
        rows = raw_rows()
        series = PriceSeries(rows)
        signal = rows[20]["date"]
        index, returns = series.returns(signal)
        self.assertEqual(index, 20)
        expected = rows[25]["adjusted_close"] / rows[21]["open"] - 1
        self.assertAlmostEqual(returns["5"], expected)

    def test_current_partial_week_is_not_a_completed_week(self):
        keys = [(2026, 30), (2026, 31), (2026, 32)]
        self.assertEqual(PriceSeries._latest_completed(keys, (2026, 32)), (2026, 31))
        self.assertIsNone(PriceSeries._latest_completed(keys, (2026, 30)))

    def test_factor_parent_dependency_is_enforced(self):
        factors = _dependency_safe_factors(["structure.engulfing_bullish_follow_through"])
        self.assertNotIn("structure.engulfing_bullish_follow_through", factors)
        factors = _dependency_safe_factors([
            "structure.support_bullish_engulfing",
            "structure.engulfing_bullish_follow_through",
        ])
        self.assertIn("structure.engulfing_bullish_follow_through", factors)

    def test_deduplication_uses_trading_session_indices(self):
        rows = [
            {"symbol": "AAA", "date": "2025-01-01", "signal_index": 100},
            {"symbol": "AAA", "date": "2025-06-01", "signal_index": 220},
            {"symbol": "AAA", "date": "2025-06-02", "signal_index": 221},
            {"symbol": "BBB", "date": "2025-01-02", "signal_index": 101},
        ]
        kept = deduplicate(rows, 120)
        self.assertEqual([(row["symbol"], row["signal_index"]) for row in kept], [("AAA", 100), ("BBB", 101), ("AAA", 221)])

    def test_midrank_keeps_tied_daily_scores_together(self):
        rows = [
            {"date": "2025-01-02", "scores": {"current": score}, "returns": {"5": 0.01}}
            for score in (5, 5, 5, 10)
        ]
        groups = _midrank_quintiles(rows, "current")
        tied_groups = [group for group, values in groups.items() if sum(row["scores"]["current"] == 5 for row in values)]
        self.assertEqual(len(tied_groups), 1)
        self.assertEqual(len(groups[tied_groups[0]]), 3)

    def test_matrix_is_inclusive(self):
        self.assertEqual(matrix(2024, 2026), [{"year": 2024}, {"year": 2025}, {"year": 2026}])

    def test_matrix_command_prints_and_writes_github_output(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "github-output.txt"
            result = subprocess.run([
                sys.executable,
                "-m",
                "research.backtest.reused_event_study_v2",
                "matrix",
                "--start-year",
                "2025",
                "--end-year",
                "2026",
                "--github-output",
                str(output),
            ], check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout), [{"year": 2025}, {"year": 2026}])
            self.assertIn('matrix=[{"year":2025},{"year":2026}]', output.read_text())

    def test_aggregate_reads_weekly_gzip_and_keeps_period_split(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events-2025-W01.jsonl.gz"
            event = {
                "symbol": "AAA",
                "date": "2025-01-02",
                "period": "validation_2025",
                "signal_index": 100,
                "scores": {"current": 5.0, "timeframe_equal": 5.0, "timeframe_v3": 5.0},
                "factors": ["qualification.long_trend", "volume.bottom_expansion"],
                "returns": {str(horizon): 0.02 for horizon in (5, 10, 15, 20, 40, 60, 100, 120)},
            }
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                handle.write(json.dumps(event) + "\n")
            out = Path(folder) / "result.json"
            annual_dir = Path(folder) / "annual"
            result = aggregate(folder, out, annual_dir)
            self.assertEqual(result["coverage"]["all_events"], 1)
            self.assertEqual(result["coverage"]["period_events"]["validation_2025"], 1)
            self.assertEqual(result["primary_deduplicated"]["baseline_fixed_horizon"]["validation_2025"]["20"]["samples"], 1)
            self.assertEqual(result["coverage"]["natural_week_checkpoints"], 0)
            self.assertEqual(result["coverage"]["natural_weeks_with_events"], 1)
            self.assertTrue(out.exists())
            self.assertTrue(annual_dir.exists())
            factors = result["primary_deduplicated"]["single_factors"]
            self.assertNotIn("qualification.long_trend", {item["factor_id"] for item in factors})


if __name__ == "__main__":
    unittest.main()
