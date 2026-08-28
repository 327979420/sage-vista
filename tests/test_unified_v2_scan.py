import unittest

from services.scanner.unified_v2_scan import _candidate,_rank_day


def state(factor_id, hit=False, recent=False):
 return {"factor_id":factor_id,"available":True,"hit":hit,"recent_hit":recent,"bars_since_hit":0 if hit else None,"latest_hit_date":"2026-08-27" if hit or recent else None,"evidence":{}}


class UnifiedV2ScanTests(unittest.TestCase):
 def test_candidate_keeps_a_complete_score_ledger(self):
  row={"symbol":"MARA","price":12.5,"trigger":{"factor_id":"macd.daily_bull_cross","exact_completed_cross":True},"factors":[state("qualification.long_trend",True),state("macd.daily_bull_cross",True,True),state("support.ema_proximity",True),state("qualification.pullback_60d",True),state("structure.bullish_fvg_support",False),state("structure.support_bullish_engulfing",True,True),state("volume.bottom_expansion",True,True),state("risk.overhead_unfilled_gap",True),state("rsi.oversold_repair",True)],"scoring":{"experimental_observational_score":7}}
  market={"market_temperature":{"score":4}}
  industry={"historical_membership_safe":True,"ticker_context":{"MARA":[{"state":"Leadership"}]}}
  result=_candidate(row,market,industry)
  self.assertEqual(result["technical_score"],8)
  self.assertEqual(result["final_priority"],10)
  self.assertEqual(sum(x["points"] for x in result["factor_ledger"]),result["technical_score"])
  self.assertIn("rsi.oversold_repair",[x["factor_id"] for x in result["factor_ledger"] if x["hit"] and x["points"]==0])
  self.assertEqual(result["score_equation"],"8 技术 +1 大盘 +1 行业 = 10")

 def test_rare_opportunities_are_an_ordered_subset_of_published_ranking(self):
  rows=[]
  for symbol in ("AAA","BBB","CCC","DDD","EEE","FFF"):
   rows.append({"symbol":symbol,"price":10,"trigger":{"factor_id":"macd.daily_bull_cross","exact_completed_cross":True},"factors":[state("qualification.long_trend",True),state("macd.daily_bull_cross",True,True),state("support.ema_proximity",True),state("qualification.pullback_60d",True),state("structure.bullish_fvg_support",True),state("structure.support_bullish_engulfing",True,True),state("volume.bottom_expansion",False),state("risk.overhead_unfilled_gap",False)],"scoring":{"experimental_observational_score":5}})
  snapshot={"as_of":"2026-08-27","eligible_count":len(rows),"symbols":rows};market={"as_of":"2026-08-27","market_temperature":{"state":"normal","score":3}};industry={"as_of":"2026-08-27","status":"available","historical_membership_safe":False,"ticker_context":{}}
  day=_rank_day(snapshot,market,industry)
  self.assertEqual([x["symbol"] for x in day["rare_opportunities"]],[x["symbol"] for x in day["ranking"][:5]])
  self.assertLessEqual(len(day["rare_opportunities"]),5)

 def test_non_triggered_row_cannot_enter_ranking(self):
  row={"symbol":"OLD","price":10,"factors":[state("qualification.long_trend",True),state("macd.daily_bull_cross",False,True),state("support.ema_proximity",True)],"scoring":{"experimental_observational_score":9}}
  self.assertIsNone(_candidate(row,{"market_temperature":{"score":5}},{"historical_membership_safe":False}))


if __name__=="__main__":unittest.main()
