import unittest

from research.backtest.context_comparison_v1 import compare

def row(day,industry,market,value,identifier):
 return {"signal_id":identifier,"signal_date":day,"context_as_of":day,"industry_confirmed":industry,"market_supportive":market,
  "forward_returns":{"5":value,"20":value,"60":None,"100":None},"excess_returns":{"5":value-.01,"20":value-.01},"mfe":max(value,0),"mae":min(value,0)}

class ContextComparisonTests(unittest.TestCase):
 def test_four_arms_share_one_baseline_without_changing_production(self):
  report=compare([row("2025-01-01",True,True,.1,"A"),row("2025-02-01",False,True,-.1,"B"),row("2026-01-01",True,False,.05,"C")])
  arms=report["arms"]
  self.assertEqual(arms["technical_baseline"]["selection_count"],3)
  self.assertEqual(arms["technical_plus_industry"]["selection_count"],2)
  self.assertEqual(arms["technical_plus_market"]["selection_count"],2)
  self.assertEqual(arms["technical_plus_industry_and_market"]["selection_count"],1)
  self.assertFalse(report["production_score_changed"])

 def test_missing_context_is_not_silently_treated_as_confirmation(self):
  report=compare([row("2025-01-01",None,None,.1,"A")])
  self.assertEqual(report["arms"]["technical_baseline"]["selection_count"],1)
  self.assertEqual(report["arms"]["technical_plus_industry"]["selection_count"],0)

 def test_context_date_mismatch_fails_closed(self):
  item=row("2025-01-01",True,True,.1,"A");item["context_as_of"]="2025-01-02"
  with self.assertRaisesRegex(ValueError,"point-in-time"):compare([item])

if __name__=="__main__":unittest.main()
