import unittest
from services.scanner.experiment_catalog import build

class ExperimentCatalogTests(unittest.TestCase):
 def test_all_old_experiments_are_preserved_and_ids_are_unique(self):
  catalog=build();self.assertEqual(catalog["experiment_count"],17)
  self.assertEqual(len({x["experiment_id"] for x in catalog["experiments"]}),17)
  self.assertTrue(catalog["policy"]["append_only"]);self.assertTrue(catalog["policy"]["failed_results_preserved"])

 def test_factor_references_link_to_lossless_ledger(self):
  catalog=build();self.assertIn("macd-rollout-05-fibonacci-half-2026-08-25",catalog["factor_experiments"]["support.fibonacci_half"])
  self.assertIn("macd-pattern-v0.6.0-2026-08-24",catalog["factor_experiments"]["structure.trendline_three_push"])

if __name__=="__main__":unittest.main()
