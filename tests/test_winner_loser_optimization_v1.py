import copy
import gzip
import json
import pathlib
import tempfile
import unittest
from datetime import date, timedelta

from research.backtest.winner_loser_optimization_v1 import (
    FEATURES,
    FeatureSeries,
    aggregate,
)


class WinnerLoserOptimizationTests(unittest.TestCase):
    def test_signal_features_ignore_future_bar_changes(self):
        start = date(2020, 1, 1)
        rows = []
        for index in range(280):
            close = 100 + index * 0.2
            rows.append({
                "date": (start + timedelta(days=index)).isoformat(),
                "open": close - 0.1,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 1_000_000 + index * 100,
            })
        signal_date = rows[250]["date"]
        baseline = FeatureSeries(copy.deepcopy(rows)).technical(signal_date)
        rows[270].update({"open": 1, "high": 5000, "low": 1, "close": 4000, "volume": 999_999_999})
        changed = FeatureSeries(rows).technical(signal_date)
        self.assertEqual(baseline, changed)
        self.assertEqual(set(baseline), set(FEATURES))

    def test_aggregate_freezes_a_non_production_challenger(self):
        split_specs = (
            ("discovery", "2018-06-01"),
            ("calibration", "2024-06-01"),
            ("validation_2025", "2025-06-01"),
            ("forward_2026", "2026-03-01"),
        )
        rows = []
        signal_index = 1000
        for split, event_date in split_specs:
            for index in range(240):
                strong = index >= 120
                result = (-0.01 if strong and index % 10 == 0 else 0.10) if strong else -0.04
                features = {name: None for name in FEATURES}
                features["trend.ema21_vs_50_pct"] = 0.20 if strong else -0.10
                rows.append({
                    "symbol": f"{split}-{index}",
                    "date": event_date,
                    "signal_index": signal_index,
                    "optimization_split": split,
                    "scores": {"current": 0},
                    "factors": [],
                    "features": features,
                    "market_features": {},
                    "returns": {"20": result},
                })
                signal_index += 200
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "source"
            source.mkdir()
            with gzip.open(source / "winner-loser-events-test.jsonl.gz", "wt", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")
            output = pathlib.Path(directory) / "result.json"
            detail = pathlib.Path(directory) / "detail.json.gz"
            report = aggregate(source, output, detail)
            self.assertFalse(report["production_scoring_changed"])
            self.assertTrue(report["selected_challenger"])
            self.assertTrue(output.exists())
            self.assertTrue(detail.exists())
            selected_ids = {item["candidate_id"] for item in report["selected_challenger"]}
            self.assertTrue(any("trend.ema21_vs_50_pct" in item for item in selected_ids))


if __name__ == "__main__":
    unittest.main()
