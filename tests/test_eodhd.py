import unittest
from unittest.mock import patch
from services.scanner.audit_eodhd import common
from services.scanner.eodhd_factor_pilot import stable_sample
from services.scanner.eodhd_factor_validation import percentile_scores,portfolio_stats,simulate_atr_trade
from services.scanner.research_pipeline import factor_values
class EodhdTests(unittest.TestCase):
 def test_primary_common_stock_filter(self):
  rows=[{"Code":"A","Type":"Common Stock","Exchange":"NYSE"},{"Code":"P","Type":"Common Stock","Exchange":"PINK"},{"Code":"E","Type":"ETF","Exchange":"NASDAQ"}]
  self.assertEqual([x["Code"] for x in common(rows)],["A"])
 def test_sample_is_deterministic(self):
  rows=[{"Code":x} for x in "ABCDE"]
  self.assertEqual(stable_sample(rows,3,"seed"),stable_sample(list(reversed(rows)),3,"seed"))
 def test_combination_scores_are_cross_sectional(self):
  rows=[{"symbol":str(i),"factors":{"momentum_12_1":i,"trend_quality":i}} for i in range(10)]
  scores=percentile_scores(rows,["momentum_12_1","trend_quality"])
  self.assertEqual(scores["0"],0)
  self.assertEqual(scores["9"],1)
 def test_zero_prior_volume_is_missing_not_error(self):
  rows=[{"date":"01/01/2020","open":10,"high":11,"low":9,"close":10,"volume":0} for _ in range(253)]
  self.assertIsNone(factor_values(rows,252)["volume_expansion"])
 def test_portfolio_stats_include_drawdown(self):
  result=portfolio_stats([.10,-.20,.05])
  self.assertEqual(result["periods"],3)
  self.assertAlmostEqual(result["max_drawdown"],-.2)
 def test_atr_trade_uses_next_open_and_time_exit(self):
  rows=[{"date":"01/01/2020","open":10,"high":11,"low":9,"close":10,"volume":100} for _ in range(30)]
  trade=simulate_atr_trade(rows,20,2,horizon=3,cost_bps=0)
  self.assertEqual(trade["reason"],"time")
  self.assertEqual(trade["holding_days"],3)
if __name__=="__main__":unittest.main()
