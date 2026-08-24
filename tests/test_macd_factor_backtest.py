import unittest
from services.scanner.macd_factor_backtest import completed_groups,ema,features,outcome,stats

class MacdFactorBacktestTests(unittest.TestCase):
 def test_completed_period_excludes_current_bucket(self):
  rows=[{"date":"2025-01-02","open":1,"high":2,"low":1,"close":2,"volume":10},{"date":"2025-01-03","open":2,"high":3,"low":2,"close":3,"volume":20},{"date":"2025-01-06","open":3,"high":4,"low":3,"close":4,"volume":30}]
  groups=completed_groups(rows,"weekly")
  self.assertEqual(len(groups),2)
  self.assertEqual(groups[0][1]["close"],3)
 def test_bullish_full_combo_requires_all_three_period_conditions(self):
  daily={"macd_line":-1,"signal_line":-2,"zero_zone":"零轴下","cross_zero_zone":"零轴下","dead_cross_zero_zone":None,"histogram_rising":True,"histogram_falling":False,"negative_histogram_shrinking":False,"near_cross":False}
  weekly={**daily,"cross_zero_zone":None}
  monthly={**daily,"macd_line":-2,"signal_line":-1,"cross_zero_zone":None,"negative_histogram_shrinking":True}
  result=features("buy",daily,weekly,monthly)
  self.assertTrue(result["日周月完整组合"])
  self.assertTrue(result["基准＋周线能量改善"])
  self.assertFalse(result["基准＋月线已经多头"])
 def test_stats_reports_robust_mean(self):
  events=[{"forward":{5:x},"mae":{5:-.01}} for x in (.01,.02,.03,5.0)]
  self.assertIn("trimmed_mean_return",stats(events,5))
 def test_market_ema_uses_only_prior_and_current_values(self):
  first=ema([1]*200+[2]);second=ema([1]*200+[2,999])
  self.assertEqual(first[-1],second[-2])
 def test_signal_executes_at_next_open(self):
  rows=[{"open":10,"high":11,"low":9,"close":10}]+[{"open":20,"high":26,"low":19,"close":25} for _ in range(20)]
  forward,_=outcome(rows,0,"buy")
  self.assertAlmostEqual(forward[5],.25)

if __name__=="__main__":unittest.main()
