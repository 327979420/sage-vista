import unittest
from unittest.mock import patch
from services.scanner.audit_eodhd import common
from services.scanner.eodhd_factor_pilot import stable_sample
from services.scanner.eodhd_factor_validation import percentile_scores,portfolio_stats,simulate_atr_trade,rolling_oos
from services.scanner.research_pipeline import factor_values
from services.scanner.market_context_factor_test import ratio_signal,bootstrap_relation,bh_adjust
from services.scanner.neutralization_test import correlation,point_in_time_exposure
from services.scanner.resonance_tracker import aggregate,breakout_state,ema_state,macd_buy_gate,macd_sell_gate,macd_state_score,price_structure_state,ranking_evidence,rsi_layer_direction,transmission_score,volume_state
class EodhdTests(unittest.TestCase):
 def test_macd_cross_below_zero_has_more_weight(self):
  common={"bars_since_cross":0,"near_cross":False,"negative_histogram_shrinking":False,"histogram_rising":True,"macd_line":-1,"signal_line":-2}
  self.assertGreater(macd_state_score({**common,"zero_zone":"零轴下"}),macd_state_score({**common,"zero_zone":"零轴上"}))
 def test_small_to_large_transmission_gets_chain_bonus(self):
  cross={"bars_since_cross":0,"near_cross":False,"negative_histogram_shrinking":False,"zero_zone":"零轴下","macd_line":-1,"signal_line":-2}
  monthly={"bars_since_cross":None,"near_cross":False,"negative_histogram_shrinking":True,"zero_zone":"零轴下","macd_line":-2,"signal_line":-1}
  score,reason=transmission_score({"日线":cross,"周线":cross,"月线":monthly})
  self.assertEqual(score,22);self.assertIn("小带大",reason)
 def test_bottom_volume_expansion_is_separate_signal(self):
  rows=[{"open":10,"high":11,"low":9,"close":10,"volume":100} for _ in range(60)]
  rows.append({"open":9.2,"high":10,"low":9,"close":9.8,"volume":220})
  result=volume_state(rows)
  self.assertEqual(result["label"],"底部放量上涨");self.assertEqual(result["ratio"],2.2)
 def test_dead_macd_cross_cannot_enter_combined_list(self):
  dead={"bars_since_cross":None,"macd_line":-2,"signal_line":-1,"macd_histogram":-1,"zero_zone":"零轴下","near_cross":False,"negative_histogram_shrinking":False,"histogram_rising":False}
  monthly={**dead,"negative_histogram_shrinking":True,"histogram_rising":True}
  valid,_=macd_buy_gate({"日线":dead,"周线":dead,"月线":monthly})
  self.assertFalse(valid)
 def test_price_structure_reports_multiple_confirmations(self):
  rows=[]
  for i in range(90):
   close=100+i*.2;rows.append({"open":close-.1,"high":close+.2,"low":close-.2,"close":close,"volume":100})
  result=price_structure_state(rows)
  self.assertTrue(result["confirmed"])
  self.assertGreaterEqual(result["score"], 2)
 def test_ema_layer_requires_price_and_both_averages_to_align(self):
  rows=[]
  for i in range(90):
   close=100+i*.3;rows.append({"open":close,"high":close+.2,"low":close-.2,"close":close,"volume":100})
  self.assertEqual(ema_state(rows)["direction"],"buy")
 def test_breakout_uses_prior_completed_bars(self):
  rows=[{"open":10,"high":11,"low":9,"close":10,"volume":100} for _ in range(25)]
  rows.append({"open":10,"high":12.5,"low":10,"close":12,"volume":100})
  result=breakout_state(rows)
  self.assertEqual(result["direction"],"buy")
  self.assertEqual(result["level"],11)
 def test_ranking_evidence_is_deterministic_and_penalizes_conflict(self):
  frame={"macd_score":8,"bars_since_dead_cross":None,"histogram_falling":False,"rsi":"底背离"}
  frames={x:frame for x in ("日线","周线","月线")}
  ema_layer={"direction":"buy","fresh_cross":False};breakout={"direction":"buy","distance":.02}
  clean=ranking_evidence(frames,{"macd":"buy"},4,0,ema_layer,breakout,False)
  repeated=ranking_evidence(frames,{"macd":"buy"},4,0,ema_layer,breakout,False)
  conflict=ranking_evidence(frames,{"macd":"buy"},3,1,ema_layer,breakout,True)
  self.assertEqual(clean,repeated)
  self.assertGreater(clean[0],conflict[0])
 def test_bearish_macd_requires_death_cross_above_zero(self):
  base={"bars_since_dead_cross":0,"macd_line":1,"signal_line":2,"histogram_falling":True}
  above={**base,"dead_cross_zero_zone":"零轴上","zero_zone":"零轴上"}
  below={**base,"macd_line":-2,"signal_line":-1,"dead_cross_zero_zone":"零轴下","zero_zone":"零轴下"}
  fallen_below={**base,"macd_line":-.2,"signal_line":.1,"dead_cross_zero_zone":"零轴上","zero_zone":"穿越零轴"}
  self.assertTrue(macd_sell_gate({"日线":above,"周线":above,"月线":above}))
  self.assertFalse(macd_sell_gate({"日线":below,"周线":below,"月线":below}))
  self.assertFalse(macd_sell_gate({"日线":fallen_below,"周线":above,"月线":above}))
 def test_oversold_rsi_cannot_be_published_as_pure_bearish(self):
  neutral={"rsi":"中性","rsi_bearish_divergence":False,"rsi_overbought_reversal":False}
  frames={"日线":{**neutral,"rsi":"超卖"},"周线":{**neutral,"rsi":"顶背离","rsi_bearish_divergence":True},"月线":neutral}
  self.assertEqual(rsi_layer_direction(frames),"conflict")
 def test_higher_timeframe_direction_excludes_current_partial_bucket(self):
  rows=[{"date":"08/18/2026","open":1,"high":2,"low":1,"close":2,"volume":1},{"date":"08/19/2026","open":2,"high":3,"low":2,"close":3,"volume":1},{"date":"08/24/2026","open":3,"high":4,"low":3,"close":4,"volume":1}]
  self.assertEqual(len(aggregate(rows,"weekly",True)),1)
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
 def test_rolling_oos_never_trains_on_test_year(self):
  panel=[]
  for year in range(2010,2016):
   for i in range(10):panel.append({"date":f"{year}-01-31","symbol":str(i),"factors":{k:i for k in ("momentum_12_1","trend_quality","breakout_252","relative_strength_6m","volume_expansion","volatility_contraction","adx_14","low_volatility")},"forward":{10:i/100}})
  result=rolling_oos(panel,5)
  self.assertEqual(result["runs"][0]["training_window"],"2010-2014")
  self.assertEqual(result["runs"][0]["test_year"],2015)
 def test_ratio_signal_uses_trailing_observations_only(self):
  dates=[f"2020-01-{i:02d}" for i in range(1,23)]
  numerator={d:100+i for i,d in enumerate(dates)}
  denominator={d:100 for d in dates}
  self.assertIsNone(ratio_signal(numerator,denominator,dates[19]))
  self.assertAlmostEqual(ratio_signal(numerator,denominator,dates[20]),.2)
 def test_bootstrap_relation_detects_monotonic_relation(self):
  context={str(i):i for i in range(12)};returns={str(i):i*2 for i in range(12)}
  result=bootstrap_relation(context,returns,200)
  self.assertEqual(result["spearman"],1)
  self.assertGreater(result["ci_95"][0],0)
 def test_bh_adjustment_is_monotonic_and_bounded(self):
  result=bh_adjust([("a",.01),("b",.04),("c",.5)])
  self.assertLessEqual(result["a"],result["b"])
  self.assertLessEqual(result["b"],result["c"])
  self.assertLessEqual(result["c"],1)
 def test_correlation_requires_enough_history(self):
  self.assertIsNone(correlation({str(i):i for i in range(10)},{str(i):i for i in range(10)}))
 def test_point_in_time_exposure_does_not_use_future_rows(self):
  rows=[]
  for i in range(260):rows.append({"date":f"01/{i%28+1:02d}/2000","close":100+i,"open":100+i})
  # Duplicate pseudo-dates make this deliberately insufficient rather than allowing future observations.
  result=point_in_time_exposure(rows,{"SPY":rows,**{x:rows for x in ("XLB","XLC","XLE","XLF","XLI","XLK","XLP","XLRE","XLU","XLV","XLY")}},"2000-01-10")
  self.assertIsNone(result["beta"])
if __name__=="__main__":unittest.main()
