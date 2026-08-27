import unittest
from research.backtest.full_line_backtest_v1 import assign_heat_buckets,market_state,relative_volume

def rows(n=240,step=.1,volume=100):
 return [{"date":f"D{i}","open":100+i*step,"high":101+i*step,"low":99+i*step,"close":100+i*step,"volume":volume} for i in range(n)]

class FullLineBacktestTests(unittest.TestCase):
 def test_relative_volume_uses_prior_twenty_sessions(self):
  data=rows(22);data[20]["volume"]=200
  self.assertEqual(relative_volume(data,20),2)
 def test_heat_rank_is_cross_sectional_per_date(self):
  data=[{"date":"D1","dollar_volume":x} for x in (10,30,20)]
  assign_heat_buckets(data)
  self.assertEqual(next(x for x in data if x["dollar_volume"]==30)["daily_volume_rank"],1)
 def test_market_state_is_unavailable_without_real_aligned_dates(self):
  data=rows()
  self.assertEqual(market_state(data,data,"missing"),"Unavailable")

if __name__=="__main__":unittest.main()
