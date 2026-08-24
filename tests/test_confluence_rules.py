import unittest
from services.scanner.confluence_rules import RULESET,combine,macd_layer,rsi_layer

def macd_frame(line,signal,**extra):
 base={"macd_line":line,"signal_line":signal,"bars_since_cross":None,"cross_zero_zone":None,"bars_since_dead_cross":None,"dead_cross_zero_zone":None,"zero_zone":"零轴上" if line>0 else "零轴下","histogram_rising":False,"histogram_falling":False,"negative_histogram_shrinking":False,"near_cross":False}
 return {**base,**extra}

def rsi_frame(value,label="中性"):
 return {"rsi_value":value,"rsi":label}

class ConfluenceRulesTests(unittest.TestCase):
 def test_ruleset_version_and_weights_are_fixed(self):
  self.assertEqual(RULESET["version"],"2.1.0")
  self.assertEqual(sum(RULESET["weights"].values()),25)
 def test_macd_large_timeframes_confirm_daily_timing(self):
  daily=macd_frame(-1,-2,bars_since_cross=0,cross_zero_zone="零轴下")
  result=macd_layer({"日线":daily,"周线":macd_frame(2,1),"月线":macd_frame(3,2)})
  self.assertEqual((result["direction"],result["stage"]),("buy","大周期→小周期"))
  self.assertGreaterEqual(result["rank_score"],44)
 def test_below_zero_cross_outranks_above_zero_cross(self):
  higher={"周线":macd_frame(2,1),"月线":macd_frame(3,2)}
  below=macd_layer({"日线":macd_frame(-1,-2,bars_since_cross=0,cross_zero_zone="零轴下"),**higher})
  above=macd_layer({"日线":macd_frame(2,1,bars_since_cross=0,cross_zero_zone="零轴上"),**higher})
  self.assertGreater(below["rank_score"],above["rank_score"])
 def test_monthly_below_zero_shrinking_supports_small_to_large(self):
  result=macd_layer({"日线":macd_frame(-1,-2,bars_since_cross=0,cross_zero_zone="零轴下"),"周线":macd_frame(-1,-2,bars_since_cross=1,cross_zero_zone="零轴下"),"月线":macd_frame(-2,-1,negative_histogram_shrinking=True,histogram_rising=True)})
  self.assertEqual((result["direction"],result["stage"]),("buy","小周期→大周期"))
 def test_above_zero_death_cross_is_sell_but_below_zero_is_not(self):
  above=macd_layer({"日线":macd_frame(1,2,bars_since_dead_cross=0,dead_cross_zero_zone="零轴上"),"周线":macd_frame(2,3,bars_since_dead_cross=1,dead_cross_zero_zone="零轴上"),"月线":macd_frame(3,4,histogram_falling=True)})
  below=macd_layer({"日线":macd_frame(-2,-1,bars_since_dead_cross=0,dead_cross_zero_zone="零轴下"),"周线":macd_frame(-2,-1),"月线":macd_frame(-3,-2)})
  self.assertEqual(above["direction"],"sell")
  self.assertNotEqual(below["direction"],"sell")
 def test_macd_direction_without_daily_trigger_is_not_a_signal(self):
  result=macd_layer({"日线":macd_frame(2,1),"周线":macd_frame(2,1),"月线":macd_frame(3,2)})
  self.assertEqual(result["direction"],"neutral")
 def test_rsi_oversold_without_reversal_is_not_a_buy_signal(self):
  frames={"日线":rsi_frame(25,"超卖"),"周线":rsi_frame(55),"月线":rsi_frame(60)}
  self.assertEqual(rsi_layer(frames)["direction"],"neutral")
 def test_combine_never_nets_conflicting_layers(self):
  layers={"macd":{"direction":"buy","score":25},"rsi":{"direction":"sell","score":25},"ema":{"direction":"neutral","score":0},"breakout":{"direction":"neutral","score":0}}
  self.assertEqual(combine(layers)["direction"],"conflict")

if __name__=="__main__":unittest.main()
