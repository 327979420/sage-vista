import unittest
from services.scanner.experiment_catalog import build,render_summary

class ExperimentCatalogTests(unittest.TestCase):
 def test_all_old_experiments_are_preserved_and_ids_are_unique(self):
  catalog=build();self.assertEqual(catalog["experiment_count"],35)
  self.assertEqual(len({x["experiment_id"] for x in catalog["experiments"]}),35)
  self.assertTrue(catalog["policy"]["append_only"]);self.assertTrue(catalog["policy"]["failed_results_preserved"])
  challenger=next(x for x in catalog["experiments"] if x["experiment_id"]=="timeframe-score-v3.0.0-2026-08-28")
  self.assertEqual(challenger["status"],"pre_registered")
  exit_score=next(x for x in catalog["experiments"] if x["experiment_id"]=="exit-score-v0.1.0-2026-08-28")
  self.assertEqual(exit_score["status"],"pre_registered")
  self.assertEqual(exit_score["specification"]["score"]["bearish_body_engulfing"],2)
  factor_lab=next(x for x in catalog["experiments"] if x["experiment_id"]=="factor-strategy-lab-v2.0.0-2026-08-29")
  self.assertEqual(factor_lab["status"],"completed_research_only");self.assertEqual(factor_lab["specification"]["new_candidates"],12)
  self.assertIn("No new or existing factor",factor_lab["result"])
  paired=next(x for x in catalog["experiments"] if x["experiment_id"]=="connors-choppiness-paired-ab-v1.0.0-2026-08-29")
  self.assertEqual(paired["status"],"completed_research_only");self.assertIn("B-only",paired["result"])
  mechanism=next(x for x in catalog["experiments"] if x["experiment_id"]=="choppiness-state-mechanism-v1.0.0-2026-08-29")
  self.assertEqual(mechanism["status"],"completed_research_only");self.assertEqual(mechanism["specification"]["primary_change"],"current Choppiness14 minus five trading sessions earlier")
  self.assertIn("high-falling/release candidate failed",mechanism["result"])
  family_combo=next(x for x in catalog["experiments"] if x["experiment_id"]=="factor-family-return-combination-v1.0.0-2026-08-29")
  self.assertEqual(family_combo["status"],"completed_research_only");self.assertEqual(len(family_combo["specification"]["families"]),4)
  self.assertEqual(family_combo["specification"]["primary_objective"],"50bps net 1% trimmed mean return")
  self.assertIn("historical-return combination",family_combo["result"])
  bottom_retest=next(x for x in catalog["experiments"] if x["experiment_id"]=="triple-bottom-neckline-retest-v1.0.0-2026-08-29")
  self.assertEqual(bottom_retest["status"],"pre_registered");self.assertEqual(len(bottom_retest["specification"]["new_factors"]),2)
  favorite=next(x for x in catalog["experiments"] if x["experiment_id"]=="favorite-pattern-tracker-v1.0.0-2026-08-29")
  self.assertEqual(favorite["status"],"pre_registered_forward_only");self.assertFalse(favorite["specification"]["main_multifactor_macd_gate_changed"])
  favorite_v2=next(x for x in catalog["experiments"] if x["experiment_id"]=="favorite-pattern-sequence-v2.0.0-2026-08-30")
  self.assertEqual(favorite_v2["status"],"pre_registered_calibration_then_forward");self.assertTrue(favorite_v2["specification"]["known_cases_excluded_from_effectiveness"])
  generalization=next(x for x in catalog["experiments"] if x["experiment_id"]=="favorite-pattern-generalization-v1.0.0-2026-08-30")
  self.assertEqual(generalization["status"],"pre_registered_observation_only");self.assertFalse(generalization["specification"]["formal_signal_changed"])
  case_audit=next(x for x in catalog["experiments"] if x["experiment_id"]=="top10-winner-loser-case-audit-v1.0.0-2026-08-31")
  self.assertEqual(case_audit["status"],"pre_registered");self.assertEqual(case_audit["specification"]["case_counts"],{"winners":10,"losers":10})
  self.assertEqual(case_audit["specification"]["primary_ranking"],"realised strategy return with R multiple audit")

 def test_every_experiment_has_lifecycle_and_plain_chinese_summary(self):
  catalog=build();self.assertEqual(catalog["summary"]["completed"],26);self.assertEqual(catalog["summary"]["in_progress"],9)
  for row in catalog["experiments"]:
   self.assertTrue(row["human_summary"]["title_zh"]);self.assertTrue(row["human_summary"]["use_zh"])
   self.assertTrue(row["lifecycle"]["registered_at"]);self.assertGreaterEqual(row["lifecycle"]["event_count"],1)
   if row["status"].startswith("completed"):self.assertTrue(row["lifecycle"]["completed_at"])
  markdown=render_summary(catalog)
  self.assertIn("得到什么",markdown);self.assertIn("现在怎么用",markdown);self.assertIn("GitHub 首次记录时间",markdown)

 def test_factor_references_link_to_lossless_ledger(self):
  catalog=build();self.assertIn("macd-rollout-05-fibonacci-half-2026-08-25",catalog["factor_experiments"]["support.fibonacci_half"])
  self.assertIn("macd-pattern-v0.6.0-2026-08-24",catalog["factor_experiments"]["structure.trendline_three_push"])

if __name__=="__main__":unittest.main()
