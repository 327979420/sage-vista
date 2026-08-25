import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class TrackerOutputContractTests(unittest.TestCase):
    def test_primary_navigation_has_only_four_product_entries(self):
        source = (ROOT / "app/zh/watch/resonance/tracker-ui.tsx").read_text()
        navigation = source.split("export const modules=[", 1)[1].split("] as const;", 1)[0]
        for label in ("总览", "MACD", "多因子雷达", "MACD研究"):
            self.assertIn(f'["{label}"', navigation)
        for legacy_route in ("/confluence", "/rsi", "/volume"):
            self.assertNotIn(legacy_route, navigation)

    def test_legacy_factor_views_remain_available_during_migration(self):
        report = json.loads((ROOT / "public/resonance-tracker.json").read_text())
        for key in ("macd_buy_top10", "macd_sell_top10", "combined_top10", "rsi_top10", "volume_top10"):
            self.assertIn(key, report)
            self.assertIsInstance(report[key], list)

    def test_tracker_audit_is_safe(self):
        report = json.loads((ROOT / "public/resonance-tracker.json").read_text())
        audit = report["consistency_audit"]
        self.assertTrue(audit["details_cover_all_published"])
        self.assertFalse(audit["duplicate_symbols"])
        self.assertTrue(audit["completed_higher_timeframes_only"])

    def test_tracker_and_radar_dates_match(self):
        tracker = json.loads((ROOT / "public/resonance-tracker.json").read_text())
        radar = json.loads((ROOT / "public/rare-opportunity-radar.json").read_text())
        self.assertEqual(tracker["as_of"], radar["as_of"])
        self.assertFalse(radar["scan"]["future_data_used"])

    def test_factor_registry_is_versioned_and_safe(self):
        from services.scanner.factor_registry import FACTORS, validate_registry

        self.assertTrue(validate_registry())
        self.assertGreaterEqual(len(FACTORS), 20)
        self.assertEqual(len({factor.id for factor in FACTORS}), len(FACTORS))
        self.assertFalse(any(factor.score_mode == "official" and factor.status != "validated" for factor in FACTORS))

    def test_transitional_radar_score_is_observational_only(self):
        from services.scanner.rare_opportunity_scanner import COMPONENTS, score_observation

        result = score_observation(COMPONENTS[:5])
        self.assertEqual(result["official_score"], 0)
        self.assertEqual(result["observational_score"], 5)
        self.assertEqual(result["total_score"], 5)
        self.assertEqual(len(result["important_misses"]), 1)
        self.assertEqual(len(result["factor_ids"]), 5)


if __name__ == "__main__":
    unittest.main()
