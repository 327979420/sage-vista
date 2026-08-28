import unittest

from services.scanner.opportunity_ledger import build, preserve_mature_evaluations, validate


ROWS = [
    {"date": "2026-08-25", "open": 9, "high": 10.5, "low": 8.5, "close": 10},
    {"date": "2026-08-26", "open": 11, "high": 12, "low": 10, "close": 11.5},
    {"date": "2026-08-27", "open": 12, "high": 13, "low": 11, "close": 12.5},
]


def unified():
    profile = {"version": "timeframe-profile-v0.1.0", "label": "周线主导", "dominant_timeframe": "weekly"}
    return {"version": "model-test-v2", "coverage": {"end": "2026-08-27"}, "days": [{"date": "2026-08-25", "model_version":"frozen-v1","factor_registry_version":"factors-7","ruleset_id":"frozen-v1+factors-7","market": {"state": "Risk-On", "score": 4}, "ranking": [{"rank": 1, "symbol": "PG", "price": 10, "technical_score": 7, "industry_adjustment": 1, "market_adjustment": 1, "final_priority": 9, "score_equation": "7 + 1 + 1 = 9", "reasons": ["长期趋势"], "industry_states": ["Leadership"], "timeframe_profile": profile, "factor_ledger": [{"factor_id": "qualification.long_trend", "hit": True, "points": 2}, {"factor_id": "structure.test", "hit": True, "points": 0}]}]}]}


class OpportunityLedgerTests(unittest.TestCase):
    def test_v2_signal_is_immutable_selection_with_next_open_outcomes(self):
        report = build(unified(), {"as_of": "2026-08-27", "cases": []}, lambda _: ROWS)
        event = report["events"][0]
        self.assertEqual(event["selection"]["rank"], 1)
        self.assertEqual(event["selection"]["model_version"], "frozen-v1")
        self.assertEqual(event["selection"]["factor_registry_version"], "factors-7")
        self.assertTrue(event["selection"]["rare_selected"])
        self.assertEqual(event["evaluation"]["entry_date"], "2026-08-26")
        self.assertAlmostEqual(event["evaluation"]["returns"]["1"], 11.5 / 11 - 1)
        self.assertEqual(event["selection"]["observed_factor_ids"], ["structure.test"])
        self.assertEqual(event["selection"]["timeframe_profile"]["label"], "周线主导")
        self.assertEqual(report["summary"]["by_horizon"]["1"]["samples"], 1)

    def test_same_symbol_and_date_merges_production_origin_without_duplication(self):
        case = {"signal_id": "SVP1-PG-2026-08-25", "symbol": "PG", "first_seen_date": "2026-08-25", "last_seen_date": "2026-08-27", "source_systems": ["technical_tracker"], "lifecycle": "ACTIVE", "latest_current_status": "current", "product_version": "SV-PRODUCT-V1", "entry": {"date": "2026-08-26", "price": 11}, "signal_time_snapshot": {"technical": {"tracker_rank": 2, "technical_score": 70}, "multi_factor": {"experimental_observational_score": 5, "score_contributions": [], "risks": [], "non_scoring_evidence": []}, "industry": {"themes": []}, "market": {}}, "forward": {"elapsed_sessions": 2, "returns": {"1": .045, "5": None}, "mfe": .18, "mae": -.09, "status": "observing"}}
        report = build(unified(), {"as_of": "2026-08-27", "cases": [case]}, lambda _: ROWS)
        self.assertEqual(len(report["events"]), 1)
        self.assertEqual(report["events"][0]["origins"], ["historical_replay", "production_forward"])
        self.assertIn("unified_v2", report["events"][0]["source_systems"])
        self.assertEqual(report["events"][0]["production_forward"]["current_status"], "current")

    def test_missing_prices_keep_signal_instead_of_dropping_it(self):
        report = build(unified(), {"as_of": "2026-08-27", "cases": []}, lambda _: [])
        self.assertEqual(len(report["events"]), 1)
        self.assertEqual(report["events"][0]["evaluation"]["status"], "data_unavailable")
        self.assertTrue(validate(report))

    def test_partial_cache_does_not_erase_saved_outcomes(self):
        previous = build(unified(), {"as_of": "2026-08-27", "cases": []}, lambda _: ROWS)
        partial = build(unified(), {"as_of": "2026-08-27", "cases": []}, lambda _: [])
        restored = preserve_mature_evaluations(partial, previous)
        event = restored["events"][0]
        self.assertEqual(event["evaluation"]["entry_date"], "2026-08-26")
        self.assertEqual(restored["summary"]["by_horizon"]["1"]["samples"], 1)


if __name__ == "__main__":
    unittest.main()
