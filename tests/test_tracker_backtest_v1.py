import unittest
from research.backtest.tracker_backtest_v1 import strict_long_trend,support_level,trade_outcomes

class TrackerBacktestV1Tests(unittest.TestCase):
 def rows(self,n=300):return [{"date":f"D{i}","open":100+i*.1,"high":101+i*.1,"low":99+i*.1,"close":100+i*.1,"volume":1_000_000} for i in range(n)]
 def test_strict_trend_uses_only_signal_and_prior_curve(self):
  rows=self.rows();curve=[90+i*.05 for i in range(len(rows))];before=strict_long_trend(rows,250,curve);rows[280]["close"]=1
  self.assertTrue(before);self.assertEqual(before,strict_long_trend(rows,250,curve))
 def test_support_level_ignores_future_bar(self):
  rows=self.rows();curves={21:[x["close"]-1 for x in rows],50:[x["close"]-2 for x in rows],200:[x["close"]-3 for x in rows]};before=support_level(rows,250,curves);rows[280]["low"]=1
  self.assertEqual(before,support_level(rows,250,curves))
 def test_entry_is_next_open_and_ambiguous_bar_stops_first(self):
  rows=self.rows(80);event={"_rows":rows,"_i":20,"support_level":100,"support_source":"test"};rows[21].update(open=105,low=98,high=120);result=trade_outcomes(event)
  self.assertEqual(result["entry_open"],105);self.assertEqual(result["stop_scenarios"]["1"]["r_targets"]["1"],-1.0)

if __name__=="__main__":unittest.main()
