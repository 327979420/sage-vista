import unittest
from services.scanner.experiment_catalog import build,render_summary

class ExperimentCatalogTests(unittest.TestCase):
 def test_all_old_experiments_are_preserved_and_ids_are_unique(self):
  catalog=build();self.assertEqual(catalog["experiment_count"],27)
  self.assertEqual(len({x["experiment_id"] for x in catalog["experiments"]}),27)
  self.assertTrue(catalog["policy"]["append_only"]);self.assertTrue(catalog["policy"]["failed_results_preserved"])
  challenger=next(x for x in catalog["experiments"] if x["experiment_id"]=="timeframe-score-v3.0.0-2026-08-28")
  self.assertEqual(challenger["status"],"pre_registered")
  exit_score=next(x for x in catalog["experiments"] if x["experiment_id"]=="exit-score-v0.1.0-2026-08-28")
  self.assertEqual(exit_score["status"],"pre_registered")
  self.assertEqual(exit_score["specification"]["score"]["bearish_body_engulfing"],2)
  factor_lab=next(x for x in catalog["experiments"] if x["experiment_id"]=="factor-strategy-lab-v2.0.0-2026-08-29")
  self.assertEqual(factor_lab["status"],"completed_research_only");self.assertEqual(factor_lab["specification"]["new_candidates"],12)
  self.assertIn("No new or existing factor",factor_lab["result"])

 def test_every_experiment_has_lifecycle_and_plain_chinese_summary(self):
  catalog=build();self.assertEqual(catalog["summary"]["completed"],23);self.assertEqual(catalog["summary"]["in_progress"],4)
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
