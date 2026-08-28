import json
import unittest
from datetime import date,timedelta

from services.scanner.detectors import load_config,pivots
from services.scanner.factor_detectors import (MONITORED_FACTOR_IDS,evaluate_initial_factors,
 higher_timeframe_bullish_engulfing,higher_timeframe_double_engulfing,
 higher_timeframe_ema_support,recent_bull_cross)
from services.scanner.factor_registry import FACTORS_BY_ID,REGISTRY_VERSION
from services.scanner.factor_snapshot import SNAPSHOT_MODE_VERSION,build_snapshot,exact_daily_macd_bull_cross
from services.scanner.macd_factor_backtest import (available,bullish_fvg_support,completed_groups,ema,
 fibonacci_support_levels,kline_congestion_support,macd_state,overhead_unfilled_gap,
 recent_three_push_breakout,support_bottom_volume,support_bullish_engulfing,
 three_push_retest,volume_profile_support)
from services.scanner.technical import macd


def sample_rows(count=500):
 rows=[];start=date(2024,1,1)
 for i in range(count):
  day=start+timedelta(days=i);close=80+i*.08+(2 if i%17==0 else 0)
  rows.append({"date":day.isoformat(),"open":close-.2,"high":close+1,"low":close-1,"close":close,"volume":1_000_000+i*100})
 return rows

def trigger_rows():
 rows=sample_rows();base=rows[-31]["close"]
 for offset in range(30):
  close=base-.5*(offset+1)
  rows[-30+offset].update(open=close-.2,high=close+1,low=close-1,close=close)
 prior=rows[-2]["close"];rows[-1].update(open=prior,high=prior+11,low=prior-1,close=prior+10)
 return rows


class FactorSnapshotTests(unittest.TestCase):
 def test_snapshot_contains_hits_and_misses_with_versions(self):
  rows=trigger_rows();as_of=rows[-1]["date"];report=build_snapshot({"XYZ":rows},as_of)
  self.assertEqual(report["registry_version"],REGISTRY_VERSION)
  self.assertFalse(report["future_data_used"])
  self.assertEqual(report["eligible_count"],1)
  self.assertEqual(report["triggered_count"],1)
  self.assertEqual(report["snapshot_mode_version"],SNAPSHOT_MODE_VERSION)
  self.assertTrue(report["symbols"][0]["trigger"]["exact_completed_cross"])
  states=report["symbols"][0]["factors"]
  self.assertEqual([state["factor_id"] for state in states],list(MONITORED_FACTOR_IDS))
  self.assertEqual(len(states),len(MONITORED_FACTOR_IDS))
  self.assertTrue(any(not state["hit"] for state in states))
  for state in states:
   self.assertEqual(state["factor_version"],FACTORS_BY_ID[state["factor_id"]].version)
   self.assertEqual(state["as_of"],as_of)
   self.assertFalse(state["lookahead_audit"]["future_data_used"])
  unavailable={state["factor_id"] for state in states if not state["available"]}
  definition_required={"structure.breakout_retest","volume.pullback_contraction","trend.dual_ma_alignment","trend.dual_ma_fresh_cross","structure.dual_ma_pullback_hold"}
  self.assertEqual(unavailable,definition_required|{"support.monthly_ema_proximity"})
  self.assertTrue(all(next(state for state in states if state["factor_id"]==factor_id)["runtime_status"]=="definition_required" for factor_id in definition_required))
  self.assertEqual(next(state for state in states if state["factor_id"]=="support.monthly_ema_proximity")["runtime_status"],"insufficient_history")

 def test_recent_event_memory_records_actual_date_and_age(self):
  rows=sample_rows();as_of=rows[-1]["date"]
  baseline=sum(row["volume"] for row in rows[-22:-2])/20
  rows[-2]["volume"]=baseline*2;rows[-1]["volume"]=baseline
  states={state.factor_id:state for state in evaluate_initial_factors(rows,as_of)}
  from services.scanner.factor_detectors import evaluate_all_factors
  volume={state.factor_id:state for state in evaluate_all_factors(rows,as_of)}["volume.relative_expansion"]
  self.assertFalse(volume.hit)
  self.assertTrue(volume.recent_hit)
  self.assertEqual(volume.latest_hit_date,rows[-2]["date"])
  self.assertEqual(volume.bars_since_hit,1)

 def test_snapshot_is_deterministic_and_symbol_sorted(self):
  rows=trigger_rows();as_of=rows[-1]["date"]
  first=build_snapshot({"ZZZ":rows,"AAA":rows},as_of);second=build_snapshot({"AAA":rows,"ZZZ":rows},as_of)
  self.assertEqual(json.dumps(first,sort_keys=True),json.dumps(second,sort_keys=True))
  self.assertEqual([row["symbol"] for row in first["symbols"]],["AAA","ZZZ"])

 def test_non_triggered_symbol_skips_full_factor_evaluation(self):
  rows=sample_rows();as_of=rows[-1]["date"];report=build_snapshot({"XYZ":rows},as_of)
  self.assertFalse(exact_daily_macd_bull_cross(rows))
  self.assertEqual(report["eligible_count"],1)
  self.assertEqual(report["triggered_count"],0)
  self.assertEqual(report["symbols"],[])

 def test_as_of_trimming_ignores_future_mutation(self):
  rows=sample_rows();as_of=rows[450]["date"]
  first=[state.dict() for state in evaluate_initial_factors(rows,as_of)]
  rows[480].update(open=1,high=9999,low=1,close=9999,volume=999999999)
  self.assertEqual(first,[state.dict() for state in evaluate_initial_factors(rows,as_of)])

 def test_canonical_results_match_legacy_flags(self):
  rows=sample_rows();i=len(rows)-1;as_of=rows[i]["date"]
  day=date.fromisoformat(as_of);weekly=completed_groups(rows,"weekly");wr=available(weekly,(day.isocalendar().year,day.isocalendar().week))
  weekly_state=macd_state(wr[-160:]);curves={period:ema([row["close"] for row in rows],period) for period in (21,50,200)}
  states={state.factor_id:state.hit for state in evaluate_initial_factors(rows,as_of)}
  closes=[row["close"] for row in rows];line,signal=macd(closes);current=closes[i]
  ema_hit=any(abs(current/curves[period][i]-1)<=.02 for period in (21,50,200));fvg=bullish_fvg_support(rows,i)
  parent=recent_three_push_breakout(rows,i);retest=parent and three_push_retest(rows,i);fib=fibonacci_support_levels(rows,i)
  support=bool(fib[.5] or fib[.618] or ema_hit or fvg or retest or volume_profile_support(rows,i) or kline_congestion_support(rows,i))
  expected={
   "macd.daily_bull_cross":recent_bull_cross(line,signal,i),
   "macd.weekly_histogram_improving":weekly_state["histogram_rising"],
   "support.ema_proximity":ema_hit,
   "structure.trendline_three_push_retest":retest,
   "structure.bullish_fvg_support":fvg,
   "risk.overhead_unfilled_gap":overhead_unfilled_gap(rows,i),
   "volume.bottom_expansion":support_bottom_volume(rows,i,support),
   "structure.support_bullish_engulfing":support_bullish_engulfing(rows,i,support),
   "structure.engulfing_bullish_follow_through":False,
  }
  self.assertEqual(states,expected)

 def test_bullish_follow_through_requires_immediately_prior_support_engulfing(self):
  rows=sample_rows();rows[-3].update(open=121,close=119,high=122,low=118);rows[-2].update(open=118.5,close=121.5,high=122,low=118);rows[-1].update(open=121,close=122,high=123,low=120)
  from services.scanner.factor_detectors import evaluate_all_factors
  states={state.factor_id:state for state in evaluate_all_factors(rows,rows[-1]["date"])}
  follow=states["structure.engulfing_bullish_follow_through"]
  self.assertTrue(follow.hit)
  self.assertEqual(follow.evidence["dependency_hits"],["structure.support_bullish_engulfing"])
  rows[-1].update(open=122,close=121)
  states={state.factor_id:state for state in evaluate_all_factors(rows,rows[-1]["date"])}
  self.assertFalse(states["structure.engulfing_bullish_follow_through"].hit)

 def test_weekly_state_uses_only_prior_completed_week(self):
  rows=sample_rows();as_of=rows[-1]["date"]
  weekly=next(state for state in evaluate_initial_factors(rows,as_of) if state.factor_id=="macd.weekly_histogram_improving")
  self.assertLess(weekly.evidence["completed_week_end"],as_of)

 def test_higher_timeframe_ema_support_names_period_and_completed_bar(self):
  bars=[{"date":f"W{i:03d}","open":100,"high":101,"low":99,"close":100,"volume":1} for i in range(210)]
  weekly,evidence=higher_timeframe_ema_support({"close":102},bars,"weekly_completed",.03)
  monthly,monthly_evidence=higher_timeframe_ema_support({"close":104},bars,"monthly_completed",.05)
  self.assertTrue(weekly);self.assertTrue(monthly)
  self.assertEqual(evidence["available_periods"],[20,50,200])
  self.assertEqual(evidence["completed_period_end"],"W209")
  self.assertEqual(monthly_evidence["timeframe"],"monthly_completed")

 def test_higher_timeframe_double_engulfing_requires_two_similar_lows(self):
  bars=[
   {"date":"1","open":100,"close":90,"high":101,"low":85},
   {"date":"2","open":89,"close":101,"high":102,"low":86},
   {"date":"3","open":102,"close":91,"high":103,"low":87},
   {"date":"4","open":90,"close":103,"high":104,"low":86.5},
  ]
  single,_=higher_timeframe_bullish_engulfing(bars,"weekly_completed")
  double,evidence=higher_timeframe_double_engulfing(bars,"weekly_completed",26)
  self.assertTrue(single);self.assertTrue(double)
  self.assertEqual(evidence["engulfing_dates"],["2","4"])
  far_apart=[*bars[:3],{**bars[3],"low":60}]
  self.assertFalse(higher_timeframe_double_engulfing(far_apart,"weekly_completed",26)[0])

 def test_pivot_requires_configured_right_bars(self):
  rows=sample_rows(40);cfg=load_config();right=cfg["pivot"]["right_bars"]
  pivot_index=25;rows[pivot_index].update(low=1)
  before=pivots(rows,pivot_index+right-1,cfg)["lows"]
  after=pivots(rows,pivot_index+right,cfg)["lows"]
  self.assertFalse(any(point["index"]==pivot_index for point in before))
  self.assertTrue(any(point["index"]==pivot_index and point["confirmed_index"]==pivot_index+right for point in after))


if __name__=="__main__":unittest.main()
