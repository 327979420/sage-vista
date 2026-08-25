import unittest
from research.backtest.tracker_backtest_v2 import simulate,stop_price,STOPS,TARGETS
from services.scanner.technical import atr
class BacktestV2Tests(unittest.TestCase):
 def test_matrix_is_six_by_four(self):self.assertEqual((len(STOPS),TARGETS),(6,(1.,1.5,2.,3.)))
 def test_same_bar_ambiguity_is_stop_first(self):self.assertEqual(simulate(100,90,110,[{"open":100,"high":112,"low":88,"close":105}])[:3],(90,1,"stop"))
 def test_gap_rules(self):
  self.assertEqual(simulate(100,90,110,[{"open":85,"high":90,"low":80,"close":88}])[:3],(85,1,"stop"))
  self.assertEqual(simulate(100,90,110,[{"open":115,"high":120,"low":114,"close":118}])[:3],(110,1,"target"))
 def test_stop_definitions(self):self.assertEqual(stop_price(100,4,"pct",.01),99);self.assertEqual(stop_price(100,4,"atr",.5),98)
 def test_atr_at_signal_is_unchanged_by_future_bars(self):
  rows=[{"high":101+i,"low":99+i,"close":100+i} for i in range(20)];before=atr(rows)[10];rows[19]={"high":9999,"low":1,"close":5000};self.assertEqual(atr(rows)[10],before)
