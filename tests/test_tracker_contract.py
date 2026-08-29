import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]


class TrackerOutputContractTests(unittest.TestCase):
    def test_primary_navigation_matches_daily_research_flow(self):
        source = (ROOT / "app/zh/watch/resonance/tracker-ui.tsx").read_text()
        navigation = source.split("export const modules=[", 1)[1].split("] as const;", 1)[0]
        for label in ("今日研究总览", "多因子机会", "行业与大盘", "历史与实验"):
            self.assertIn(f'["{label}"', navigation)
        self.assertNotIn("个股研究", navigation)
        for legacy_route in ("/macd", "/confluence", "/rsi", "/volume"):
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

    def test_published_update_status_proves_freshness(self):
        tracker = json.loads((ROOT / "public/resonance-tracker.json").read_text())
        radar = json.loads((ROOT / "public/rare-opportunity-radar.json").read_text())
        status = json.loads((ROOT / "public/update-status.json").read_text())
        self.assertEqual(status["status"], "up_to_date")
        self.assertEqual(status["source_latest_complete_date"], tracker["as_of"])
        self.assertEqual(status["tracker_as_of"], tracker["as_of"])
        self.assertEqual(status["radar_as_of"], radar["as_of"])
        self.assertTrue(status["data_dates_match"])
        self.assertFalse(status["future_data_used"])

    def test_strict_bulk_day_never_accepts_an_empty_fallback(self):
        from services.scanner.resonance_tracker import bulk_day

        with tempfile.TemporaryDirectory() as folder, patch("services.scanner.resonance_tracker.get", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "not ready"):
                bulk_day("2026-08-24", cache_dir=folder, strict=True)
            self.assertFalse((Path(folder) / "2026-08-24.json").exists())

    def test_factor_registry_is_versioned_and_safe(self):
        from services.scanner.factor_registry import FACTORS, validate_registry

        self.assertTrue(validate_registry())
        self.assertGreaterEqual(len(FACTORS), 20)
        self.assertEqual(len({factor.id for factor in FACTORS}), len(FACTORS))
        self.assertFalse(any(factor.score_mode == "official" and factor.status != "validated" for factor in FACTORS))

    def test_dynamic_radar_score_is_observational_only(self):
        from services.scanner.rare_opportunity_scanner import COMPONENTS, score_observation

        result = score_observation(COMPONENTS[:5])
        self.assertEqual(result["official_score"], 0)
        self.assertEqual(result["observational_score"], 1)
        self.assertEqual(result["total_score"], 1)
        self.assertEqual(len(result["important_misses"]), len(COMPONENTS) - 5)
        self.assertNotIn("support.fibonacci_half",result["factor_ids"])
        self.assertIn("Fibonacci支撑",result["non_scoring_hits"])

    def test_rejected_and_unstable_registry_factors_cannot_score(self):
        from services.scanner.factor_registry import FACTORS, validate_registry
        from services.scanner.rare_opportunity_scanner import score_observation

        validate_registry()
        blocked={x.id for x in FACTORS if x.status in ("rejected","unstable")}
        result=score_observation(["Fibonacci支撑"])
        self.assertFalse(blocked & set(result["factor_ids"]))
        self.assertEqual(result["total_score"],0)

    def test_trendline_retest_is_registered_as_parent_bound_observation(self):
        from services.scanner.factor_registry import FACTORS

        factors = {factor.id: factor for factor in FACTORS}
        retest = factors["structure.trendline_three_push_retest"]
        parent = factors["structure.trendline_three_push"]
        self.assertEqual(retest.score_mode, "display_only")
        self.assertEqual(retest.weight, 0)
        self.assertEqual(retest.redundancy_group, parent.redundancy_group)
        self.assertEqual(retest.depends_on, (parent.id,))
        self.assertIn("10 completed sessions", retest.machine_rule)

    def test_new_bottom_factors_are_zero_weight_and_family_bound(self):
        from services.scanner.factor_registry import FACTORS

        factors = {factor.id: factor for factor in FACTORS}
        triple = factors["structure.triple_bottom_pullback"]
        w_retest = factors["structure.double_bottom_neckline_retest"]
        three_push_retest = factors["structure.trendline_three_push_retest"]
        self.assertEqual((triple.status, triple.score_mode, triple.weight, triple.experimental_weight), ("testing", "display_only", 0, 0))
        self.assertEqual(triple.redundancy_group, "pullback_location")
        self.assertEqual(triple.depends_on, ("qualification.long_trend", "qualification.pullback_60d"))
        self.assertEqual((w_retest.status, w_retest.score_mode, w_retest.weight, w_retest.experimental_weight), ("testing", "display_only", 0, 0))
        self.assertEqual(w_retest.depends_on, ("structure.double_bottom",))
        self.assertEqual(w_retest.redundancy_group, three_push_retest.redundancy_group)

    def test_runtime_enforces_dependency_and_redundancy(self):
        from services.scanner.rare_opportunity_scanner import score_observation

        missing_parent=score_observation(["三推突破后回踩确认"])
        with_parent=score_observation(["三推趋势线突破","三推突破后回踩确认"])
        deduplicated=score_observation(["EMA支撑","EMA支撑"])
        self.assertEqual(missing_parent["total_score"],0)
        self.assertEqual(with_parent["total_score"],0)
        self.assertEqual(with_parent["factor_ids"],[])
        self.assertEqual(deduplicated["total_score"],0)

    def test_daily_macd_cross_stays_fresh_for_five_completed_sessions(self):
        from services.scanner.rare_opportunity_scanner import recent_bull_cross

        line = [-2, -1, 1, 2, 3, 4, 5, 6]
        signal = [0] * len(line)
        self.assertTrue(recent_bull_cross(line, signal, 6))
        self.assertFalse(recent_bull_cross(line, signal, 7))
        lost = line.copy()
        lost[6] = -1
        self.assertFalse(recent_bull_cross(lost, signal, 6))

    def test_daily_macd_freshness_is_an_observational_factor(self):
        from services.scanner.factor_registry import FACTORS

        factor = {x.id: x for x in FACTORS}["macd.daily_bull_cross"]
        self.assertEqual(factor.score_mode, "observational")
        self.assertEqual(factor.weight, 1)
        self.assertIn("latest 5 sessions", factor.machine_rule)

    def test_support_confirmations_cannot_score_without_support(self):
        from services.scanner.macd_factor_backtest import support_bottom_volume, support_bullish_engulfing

        rows = [{"open":10,"high":20,"low":9,"close":10,"volume":100} for _ in range(20)]
        rows.append({"open":10,"high":10.2,"low":9.5,"close":9.7,"volume":100})
        rows.append({"open":9.6,"high":10.8,"low":9.5,"close":10.5,"volume":200})
        self.assertFalse(support_bottom_volume(rows,21,False))
        self.assertFalse(support_bullish_engulfing(rows,21,False))
        self.assertTrue(support_bottom_volume(rows,21,True))
        self.assertTrue(support_bullish_engulfing(rows,21,True))

    def test_support_confirmations_are_observational_factors(self):
        from services.scanner.factor_registry import FACTORS

        factors = {x.id:x for x in FACTORS}
        for factor_id in ("volume.bottom_expansion","structure.support_bullish_engulfing"):
            self.assertEqual(factors[factor_id].status,"candidate")
            self.assertEqual(factors[factor_id].score_mode,"observational")
            self.assertEqual(factors[factor_id].weight,0)
            self.assertEqual(factors[factor_id].experimental_weight,1)

    def test_early_watch_requires_pre_cross_shrinking_gap_and_two_supports(self):
        from services.scanner.resonance_tracker import early_watch_evidence

        daily={"macd_line":-.2,"signal_line":-.1,"macd_histogram":-.1,"macd_histogram_change":.03,"negative_histogram_shrinking":True,"energy_streak":3,"near_cross":True,"rsi_score":2,"rsi":"超卖修复"}
        higher={"histogram_rising":True,"macd_line":-.4,"signal_line":-.3,"negative_histogram_shrinking":True}
        item={"frames":{"日线":daily,"周线":higher,"月线":higher},"ema_layer":{"direction":"buy"},"price_structure":{"confirmed":False},"volume":{"near_bottom":False,"score":0}}
        evidence=early_watch_evidence(item)
        self.assertIn("日线负柱连续收缩3根",evidence)
        self.assertTrue(any("差距单日缩小" in x for x in evidence))
        self.assertEqual(early_watch_evidence({**item,"frames":{**item["frames"],"日线":{**daily,"macd_line":0}}}),[])


if __name__ == "__main__":
    unittest.main()
