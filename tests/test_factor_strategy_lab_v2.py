import copy
import gzip
import json
import pathlib
import tempfile
import unittest
from datetime import date, timedelta

from research.backtest.factor_strategy_lab_v2 import (
    CANDIDATES,
    CandidateSeries,
    aggregate,
    load_catalog,
)


class FactorStrategyLabV2Tests(unittest.TestCase):
    def test_catalog_and_point_in_time_feature_contract(self):
        start = date(2018, 1, 1)
        rows = []
        for index in range(380):
            close = 80 + index * 0.15 + (index % 9 - 4) * 0.08
            rows.append({
                "date": (start + timedelta(days=index)).isoformat(),
                "open": close - 0.2,
                "high": close + 0.9,
                "low": close - 1.0,
                "close": close,
                "volume": 900_000 + (index % 17) * 15_000,
            })
        signal_date = rows[280]["date"]
        baseline, _, auxiliary = CandidateSeries(copy.deepcopy(rows)).technical(signal_date)
        rows[330].update({"open": 1, "high": 9000, "low": 0.5, "close": 8000, "volume": 999_999_999})
        changed, _, changed_auxiliary = CandidateSeries(rows).technical(signal_date)
        self.assertEqual(baseline, changed)
        self.assertEqual(auxiliary, changed_auxiliary)
        self.assertEqual(set(baseline), set(CANDIDATES))
        self.assertEqual(len(load_catalog()["candidates"]), 12)

    def test_aggregate_builds_matched_controls_and_action_groups(self):
        split_dates = (
            "2012-06-15",
            "2014-06-15",
            "2017-06-15",
            "2020-06-15",
            "2023-06-15",
            "2025-06-15",
            "2026-06-15",
        )
        rows = []
        signal_index = 500
        candidate_ids = list(CANDIDATES)
        for event_date in split_dates:
            for index in range(260):
                strong = index >= 130
                candidate_value = 0.8 if strong else 0.2
                outcome = 0.03 + (index - 130) / 10_000 if strong else -0.04 - index / 100_000
                rows.append({
                    "symbol": f"S{event_date[:4]}-{index}",
                    "date": event_date,
                    "signal_index": signal_index,
                    "scores": {"current": 3 if strong else 2},
                    "factors": ["support.ema_proximity"] if strong else [],
                    "returns": {"20": outcome},
                    "candidate_features": {candidate_id: candidate_value for candidate_id in candidate_ids},
                    "legacy_features": {
                        "momentum.return_20_pct": 0.02 if strong else 0.01,
                        "location.pullback_60d_pct": -0.06 if strong else -0.07,
                        "volatility.atr14_pct": 0.025 if strong else 0.027,
                    },
                    "auxiliary_features": {"trend.adx_14": 25},
                    "separate_market_context": {},
                })
                signal_index += 121
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "source"
            source.mkdir()
            with gzip.open(source / "factor-lab-events-test.jsonl.gz", "wt", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")
            output = pathlib.Path(directory) / "result.json"
            detail = pathlib.Path(directory) / "pairs.json.gz"
            report = aggregate(source, output, detail)
            self.assertFalse(report["production_scoring_changed"])
            self.assertEqual(len(report["new_candidate_results"]), 12)
            self.assertGreater(report["coverage"]["matched_winner_loser_pairs"], 0)
            self.assertIn("new_candidates", report["actions"])
            self.assertTrue(report["case_cards"]["top_winners"])
            self.assertTrue(output.exists())
            self.assertTrue(detail.exists())


class FactorStrategyLabWorkflowTests(unittest.TestCase):
    def test_workflow_reuses_existing_events_and_price_cache(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        text = (root / ".github/workflows/factor-strategy-lab-v2.yml").read_text()
        self.assertIn("score-timeframe-attribution-v2-", text)
        self.assertIn("eodhd-history-v1-", text)
        self.assertIn("factor_strategy_lab_v2", text)
        self.assertNotIn("EODHD_API_TOKEN", text)
        self.assertIn("matched-pairs-detail.json.gz", text)


if __name__ == "__main__":
    unittest.main()
