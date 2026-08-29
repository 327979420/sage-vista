import unittest
from copy import deepcopy
from services.scanner.detectors import detect_bos,detect_retest,detect_triple_bottom,detect_w_bottom,evaluate_gap,pivots,relative_volume,count_level_tests,load_config

def bars(n=50,price=100,volume=1000):return [{"date":f"D{i}","open":price,"high":price+1,"low":price-1,"close":price+.2,"volume":volume} for i in range(n)]

class DetectorTests(unittest.TestCase):
 def setUp(self):self.cfg=load_config()
 def test_swing_confirmation_and_no_lookahead(self):
  x=bars(9);x[2]["low"]=90
  self.assertEqual(len(pivots(x,3,self.cfg)["lows"]),0)
  self.assertEqual(pivots(x,4,self.cfg)["lows"][0]["index"],2)
 def test_swing_high(self):
  x=bars(9);x[3]["high"]=110;self.assertEqual(pivots(x,5,self.cfg)["highs"][0]["index"],3)
 def test_valid_w_bottom(self):
  x=bars(20);x[4]["low"]=90;x[5]["high"]=103;x[9]["low"]=91
  d=detect_w_bottom(x,11,self.cfg);self.assertTrue(d.detected);self.assertEqual(d.classification,"w_bottom")
 def test_high_second_low_is_not_w(self):
  x=bars(20);x[4]["low"]=85;x[9]["low"]=95
  d=detect_w_bottom(x,11,self.cfg);self.assertFalse(d.detected);self.assertEqual(d.classification,"ordinary_higher_low")
 def test_triple_bottom_requires_three_confirmed_separated_lows(self):
  x=bars(40);x[5]["low"]=90;x[15]["low"]=91;x[25]["low"]=90.5
  d=detect_triple_bottom(x,27,self.cfg);self.assertTrue(d.detected);self.assertEqual(d.classification,"triple_bottom");self.assertEqual(d.measurements["separation_bars"],[10,10])
  self.assertFalse(detect_triple_bottom(x,26,self.cfg).detected)
 def test_triple_bottom_is_point_in_time_safe(self):
  x=bars(40);x[5]["low"]=90;x[15]["low"]=91;x[25]["low"]=90.5
  before=detect_triple_bottom(x,27,self.cfg).dict();x[35].update(low=1,high=999,close=500);self.assertEqual(before,detect_triple_bottom(x,27,self.cfg).dict())
 def test_bos_vs_wick_swipe(self):
  x=bars(30);x[25].update(open=99,high=105,low=98,close=104,volume=2000);self.assertTrue(detect_bos(x,25,102,self.cfg).detected)
  x[26].update(open=101,high=105,low=99,close=101,volume=2000);self.assertEqual(detect_bos(x,26,102,self.cfg).classification,"liquidity_swipe")
 def test_level_tests_clustered(self):
  x=bars(40);[x[i].update(high=105.1) for i in (20,21,25,30)]
  d=count_level_tests(x,35,105,self.cfg);self.assertTrue(d.detected);self.assertEqual(d.measurements["separate_tests"],3)
 def test_relative_volume_tiers_previous_bars_only(self):
  x=bars(25);x[20]["volume"]=2000;self.assertEqual(relative_volume(x,20,self.cfg).classification,"exceptional")
  x[20]["volume"]=1490;self.assertEqual(relative_volume(x,20,self.cfg).classification,"normal")
 def test_valid_and_failed_retest(self):
  x=bars(35);x[22].update(open=101,low=99.9,high=104,close=103.8)
  self.assertTrue(detect_retest(x,20,25,100,98,104,self.cfg).detected)
  y=deepcopy(x);y[21].update(open=100,high=100.2,low=96,close=97)
  self.assertTrue(detect_retest(y,20,25,100,98,104,self.cfg).invalidated)
 def test_breakout_without_retest(self):
  x=bars(35,105);d=detect_retest(x,20,26,100,98,104,self.cfg);self.assertEqual(d.classification,"breakout_without_entry")
 def test_gap_rejection(self):
  self.assertFalse(evaluate_gap(100,101,101.4,2,self.cfg)["reject"])
  self.assertTrue(evaluate_gap(100,101,103,2,self.cfg)["reject"])
 def test_future_mutation_does_not_change_detection(self):
  x=bars(20);x[4]["low"]=90;x[9]["low"]=91;a=detect_w_bottom(x,11,self.cfg).dict();x[15].update(low=1,high=999,close=500,volume=999999);b=detect_w_bottom(x,11,self.cfg).dict();self.assertEqual(a,b)

if __name__=="__main__":unittest.main()
