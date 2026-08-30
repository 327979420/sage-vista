import json,tempfile,unittest
from pathlib import Path

from services.scanner.unified_v2_scan import _candidate,_rank_day,_write_report,write_latest


def state(factor_id, hit=False, recent=False):
 return {"factor_id":factor_id,"available":True,"hit":hit,"recent_hit":recent,"bars_since_hit":0 if hit else None,"latest_hit_date":"2026-08-27" if hit or recent else None,"evidence":{}}


class UnifiedV2ScanTests(unittest.TestCase):
 def test_candidate_keeps_a_complete_score_ledger(self):
  row={"symbol":"MARA","price":12.5,"trigger":{"factor_id":"macd.daily_bull_cross","exact_completed_cross":True},"factors":[state("qualification.long_trend",True),state("macd.daily_bull_cross",True,True),state("support.ema_proximity",True),state("qualification.pullback_60d",True),state("structure.bullish_fvg_support",False),state("structure.support_bullish_engulfing",True,True),state("volume.bottom_expansion",True,True),state("risk.overhead_unfilled_gap",True),state("rsi.oversold_repair",True)],"scoring":{"experimental_observational_score":7}}
  market={"market_temperature":{"score":4}}
  industry={"historical_membership_safe":True,"ticker_context":{"MARA":[{"state":"Leadership"}]}}
  result=_candidate(row,market,industry)
  self.assertEqual(result["technical_score"],10)
  self.assertEqual(result["technical_resonance"]["positive_hit_count"],5)
  self.assertEqual(result["technical_resonance"]["family_count"],5)
  self.assertEqual(result["technical_resonance"]["risk_hit_count"],1)
  self.assertEqual(result["b_shadow_score"],2)
  self.assertEqual(result["final_priority"],12)
  self.assertEqual(sum(x["points"] for x in result["factor_ledger"]),result["technical_resonance"]["positive_hit_count"])
  self.assertEqual(sum(x["shadow_points"] for x in result["factor_ledger"]),result["b_shadow_score"])
  self.assertIn("rsi.oversold_repair",[x["factor_id"] for x in result["factor_ledger"] if x["counted_in_resonance"]])
  self.assertIn("5颗 + 5家族",result["score_equation"])
  self.assertEqual(result["timeframe_profile"]["status"],"count_based_research_priority")

 def test_weekly_profile_counts_all_evidence_and_adds_same_family_resonance(self):
  row={"symbol":"WEEK","price":20,"trigger":{"factor_id":"macd.daily_bull_cross","exact_completed_cross":True},"factors":[state("qualification.long_trend",True),state("qualification.pullback_60d",True),state("macd.daily_bull_cross",True,True),state("support.ema_proximity",True),state("macd.weekly_histogram_improving",True),state("support.weekly_ema_proximity",True),state("structure.weekly_bullish_engulfing",True)],"scoring":{"experimental_observational_score":10}}
  result=_candidate(row,{"market_temperature":{"score":3}},{"historical_membership_safe":False})
  self.assertEqual(result["technical_score"],11)
  self.assertEqual(result["b_shadow_score"],1)
  self.assertEqual(result["technical_resonance"]["timeframe_resonance_bonus"],2)
  self.assertEqual(result["timeframe_profile"]["label"],"周线主导")
  self.assertEqual(result["timeframe_profile"]["independent_groups"]["weekly"],3)

 def test_rare_opportunities_are_an_ordered_subset_of_published_ranking(self):
  rows=[]
  for symbol in ("AAA","BBB","CCC","DDD","EEE","FFF"):
   rows.append({"symbol":symbol,"price":10,"trigger":{"factor_id":"macd.daily_bull_cross","exact_completed_cross":True},"factors":[state("qualification.long_trend",True),state("macd.daily_bull_cross",True,True),state("support.ema_proximity",True),state("qualification.pullback_60d",True),state("structure.bullish_fvg_support",True),state("structure.support_bullish_engulfing",True,True),state("volume.bottom_expansion",True,True),state("risk.overhead_unfilled_gap",False)],"scoring":{"experimental_observational_score":5}})
  snapshot={"as_of":"2026-08-27","eligible_count":len(rows),"symbols":rows};market={"as_of":"2026-08-27","market_temperature":{"state":"normal","score":3}};industry={"as_of":"2026-08-27","status":"available","historical_membership_safe":False,"ticker_context":{}}
  day=_rank_day(snapshot,market,industry)
  self.assertEqual([x["symbol"] for x in day["rare_opportunities"]],[x["symbol"] for x in day["ranking"][:5]])
  self.assertLessEqual(len(day["rare_opportunities"]),5)

 def test_non_triggered_row_cannot_enter_ranking(self):
  row={"symbol":"OLD","price":10,"factors":[state("qualification.long_trend",True),state("macd.daily_bull_cross",False,True),state("support.ema_proximity",True)],"scoring":{"experimental_observational_score":9}}
  self.assertIsNone(_candidate(row,{"market_temperature":{"score":5}},{"historical_membership_safe":False}))

 def test_latest_view_keeps_only_the_newest_day(self):
  report={"coverage":{"start":"2026-08-26","end":"2026-08-27","sessions":2},"days":[{"date":"2026-08-26"},{"date":"2026-08-27"}]}
  with tempfile.TemporaryDirectory() as folder:
   out=Path(folder)/"latest.json";latest=write_latest(report,out)
   self.assertEqual(latest["days"],[{"date":"2026-08-27"}])
   self.assertEqual(json.loads(out.read_text())["coverage"]["sessions"],2)

 def test_new_model_can_refresh_latest_without_rewriting_same_day_history(self):
  with tempfile.TemporaryDirectory() as folder:
   archive=Path(folder)/"archive.json";latest_path=Path(folder)/"latest.json"
   archive.write_text(json.dumps({"version":"old-v1","model":{"factor_registry_version":"old-registry"},"days":[{"date":"2026-08-28","model_version":"old-v1","ranking":[{"symbol":"OLD"}]}]}))
   fresh={"date":"2026-08-28","model_version":"new-v2","factor_registry_version":"new-registry","ranking":[{"symbol":"NEW","factor_ledger":[]}]}
   report=_write_report([fresh],archive,True)
   latest=write_latest(report,latest_path,day=fresh)
   self.assertEqual(report["days"][0]["ranking"][0]["symbol"],"OLD")
   self.assertEqual(latest["days"][0]["ranking"][0]["symbol"],"NEW")


if __name__=="__main__":unittest.main()
