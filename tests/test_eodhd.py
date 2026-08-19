import unittest
from unittest.mock import patch
from services.scanner.audit_eodhd import common
from services.scanner.eodhd_factor_pilot import stable_sample
from services.scanner.eodhd_factor_validation import percentile_scores,portfolio_stats,simulate_atr_trade,rolling_oos
from services.scanner.research_pipeline import factor_values
from services.scanner.market_context_factor_test import ratio_signal,bootstrap_relation,bh_adjust
from services.scanner.neutralization_test import correlation,point_in_time_exposure
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
