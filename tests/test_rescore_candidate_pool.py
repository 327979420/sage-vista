import unittest
from services.scanner.rescore_candidate_pool import rescore_day


class RescoreCandidatePoolTests(unittest.TestCase):
 def test_auxiliary_factor_reorders_saved_pool_without_new_candidates(self):
  day={"candidate_pool":[
   {"symbol":"AAA","base_priority":8,"technical_score":7,"experimental_score":4,"hit_factor_ids":[]},
   {"symbol":"BBB","base_priority":7.5,"technical_score":7,"experimental_score":3,"hit_factor_ids":["structure.engulfing_bullish_follow_through"]},
  ]}
  rows=rescore_day(day,{"structure.engulfing_bullish_follow_through":1})
  self.assertEqual([x["symbol"] for x in rows],["BBB","AAA"])
  self.assertEqual(rows[0]["overlay_points"],1)
  self.assertEqual(len(rows),2)

 def test_missing_candidate_pool_never_fabricates_symbols(self):
  self.assertEqual(rescore_day({}, {"anything":99}),[])


if __name__=="__main__":unittest.main()
