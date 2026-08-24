import unittest
from services.scanner.macd_factor_backtest import completed_groups,daily_pattern_flags,ema,features,outcome,stats,three_push_breakout

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
  rows=[{"open":10,"high":11,"low":9,"close":10}]+[{"open":20,"high":26,"low":19,"close":25} for _ in range(100)]
  forward,_,_=outcome(rows,0,"buy")
  self.assertAlmostEqual(forward[5],.25)
 def test_reports_return_above_market(self):
  rows=[{"date":"2025-01-01","open":10,"high":11,"low":9,"close":10}]+[{"date":f"2025-01-{i+2:02d}","open":20,"high":26,"low":19,"close":25} for i in range(100)]
  spy={x["date"]:{**x,"open":100,"close":110} for x in rows}
  forward,_,excess=outcome(rows,0,"buy",{"SPY":spy,"QQQ":spy})
  self.assertAlmostEqual(forward[5],.25)
  self.assertAlmostEqual(excess["SPY"][5],.15)
 def test_pattern_flags_do_not_read_future_bars(self):
  rows=[{"date":f"D{i}","open":100,"high":101,"low":99,"close":100.2,"volume":1000} for i in range(220)]
  first=daily_pattern_flags(rows,180);rows[210].update(high=999,low=1,close=500)
  self.assertEqual(first,daily_pattern_flags(rows,180))
 def test_long_term_gate_excludes_persistent_decline(self):
  up=[{"date":f"D{i}","open":100+i*.1,"high":101+i*.1,"low":99+i*.1,"close":100+i*.1,"volume":1000} for i in range(300)]
  down=[{"date":f"D{i}","open":400-i,"high":401-i,"low":399-i,"close":400-i,"volume":1000} for i in range(300)]
  self.assertTrue(daily_pattern_flags(up,280)["长期趋势合格＋日线金叉"])
  self.assertFalse(daily_pattern_flags(down,280)["长期趋势合格＋日线金叉"])
 def test_bottom_doji_uses_recent_lower_range(self):
  rows=[{"date":f"D{i}","open":100+i*.1,"high":101+i*.1,"low":99+i*.1,"close":100+i*.1,"volume":1000} for i in range(300)]
  rows[279].update(open=105,close=105.02,high=106,low=104)
  self.assertTrue(daily_pattern_flags(rows,280)["长期趋势合格＋日线金叉＋底部Doji"])
 def test_bottom_bullish_engulfing_requires_prior_bear_candle(self):
  rows=[{"date":f"D{i}","open":100+i*.1,"high":101+i*.1,"low":99+i*.1,"close":100+i*.1,"volume":1000} for i in range(300)]
  rows[278].update(open=106,close=104.8,high=106.2,low=104.5);rows[279].update(open=104.7,close=106.1,high=106.3,low=104.5)
  self.assertTrue(daily_pattern_flags(rows,280)["长期趋势合格＋日线金叉＋底部Bullish Engulfing"])
 def test_three_push_requires_breakout(self):
  rows=[{"date":f"D{i}","open":95,"high":96,"low":94,"close":95,"volume":1000} for i in range(80)]
  for i,p in ((20,110),(35,106),(50,102)):rows[i].update(high=p,close=p-2,open=p-3,low=p-4)
  rows[55].update(open=98,high=103,low=97,close=102.5)
  self.assertTrue(three_push_breakout(rows,55))

if __name__=="__main__":unittest.main()
