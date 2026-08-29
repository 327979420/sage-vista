import unittest
from dataclasses import replace
from unittest.mock import patch

from services.scanner.factor_registry import FACTORS_BY_ID
from services.scanner.factor_scoring import experimental_score

def state(factor_id,hit=True,recent=True,available=True,evidence=None):
 return {"factor_id":factor_id,"hit":hit,"recent_hit":recent,"available":available,"evidence":evidence or {}}

class FactorScoringTests(unittest.TestCase):
 def test_core_auxiliary_and_official_scores_are_separate(self):
  result=experimental_score([state("macd.weekly_histogram_improving"),state("qualification.long_trend")])
  self.assertEqual(result["official_score"],0)
  self.assertEqual(result["experimental_core_score"],1)
  self.assertEqual(result["experimental_auxiliary_score"],1)
  self.assertEqual(result["experimental_observational_score"],2)

 def test_rejected_and_unstable_are_zero_score_but_remain_observations(self):
  result=experimental_score([state("support.fibonacci_half"),state("rsi.bullish_divergence")])
  self.assertEqual(result["experimental_observational_score"],0)
  self.assertEqual({item["reason"] for item in result["non_scoring_observations"]},{"rejected","unstable"})

 def test_dependency_and_support_context_are_enforced(self):
  missing=experimental_score([state("structure.trendline_three_push_retest"),state("structure.trendline_three_push",False,False)])
  support_missing=experimental_score([state("volume.bottom_expansion",evidence={"support_context":False})])
  self.assertEqual(missing["experimental_observational_score"],0)
  self.assertEqual(support_missing["experimental_observational_score"],0)

 def test_engulfing_follow_through_cannot_score_without_parent(self):
  missing=experimental_score([state("structure.engulfing_bullish_follow_through")])
  present=experimental_score([state("structure.support_bullish_engulfing",evidence={"support_context":True}),state("structure.engulfing_bullish_follow_through")])
  self.assertEqual(missing["experimental_observational_score"],0)
  self.assertEqual(present["experimental_observational_score"],1)
  self.assertIn("display_only",{x["reason"] for x in present["non_scoring_observations"]})

 def test_redundancy_group_takes_one_max_contribution(self):
  fib=replace(FACTORS_BY_ID["support.fibonacci_618"],score_tier="auxiliary",experimental_weight=1)
  golden=replace(FACTORS_BY_ID["support.golden_pocket"],score_tier="auxiliary",experimental_weight=1)
  with patch.dict("services.scanner.factor_scoring.FACTORS_BY_ID",{"support.fibonacci_618":fib,"support.golden_pocket":golden}):
   result=experimental_score([state("support.fibonacci_618"),state("support.golden_pocket")])
  self.assertEqual(result["experimental_observational_score"],1)
  self.assertEqual(len(result["score_contributions"]),1)
  self.assertIn("redundancy_capped",{item["reason"] for item in result["non_scoring_observations"]})

 def test_c_and_d_engulfing_variants_are_zero_weight(self):
  result=experimental_score([
   state("structure.weekly_bullish_engulfing"),state("structure.weekly_double_bullish_engulfing"),
   state("structure.monthly_bullish_engulfing"),state("structure.monthly_double_bullish_engulfing"),
  ])
  self.assertEqual(result["experimental_auxiliary_score"],0)
  self.assertEqual(result["score_contributions"],[])
  self.assertEqual({item["reason"] for item in result["non_scoring_observations"]},{"rejected","display_only"})

if __name__=="__main__":unittest.main()
