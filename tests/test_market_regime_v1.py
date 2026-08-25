import unittest
from research.backtest.market_regime_v1 import classify,benchmark_state,_market_arrays
class MarketRegimeV1Tests(unittest.TestCase):
 def test_fixed_thresholds(self):
  self.assertEqual(classify(65),"Risk-On");self.assertEqual(classify(40),"Neutral");self.assertEqual(classify(39.99),"Risk-Off")
 def test_future_rows_do_not_change_prior_state(self):
  rows=[{"date":f"2020-{1+i//28:02d}-{1+i%28:02d}","open":100+i,"high":101+i,"low":99+i,"close":100+i,"volume":1} for i in range(240)]
  before=benchmark_state(_market_arrays(rows),"2020-08-15");rows[-1]["close"]=99999
  self.assertEqual(benchmark_state(_market_arrays(rows),"2020-08-15"),before)
