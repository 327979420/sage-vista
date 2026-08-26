import unittest
from research.backtest.ranking_research_v1 import order_day
class RankingResearchTests(unittest.TestCase):
 def setUp(self):self.rows=[{"ticker":"A","date":"2020-01-01","macd":1,"factor":3},{"ticker":"B","date":"2020-01-01","macd":3,"factor":1},{"ticker":"C","date":"2020-01-01","macd":2,"factor":2}]
 def test_fixed_rankers(self):
  self.assertEqual(order_day(self.rows,"A")[0]["ticker"],"B");self.assertEqual(order_day(self.rows,"B")[0]["ticker"],"A")
 def test_random_is_reproducible(self):self.assertEqual(order_day(self.rows,"D"),order_day(self.rows,"D"))
 def test_hybrid_is_fixed_equal_percentiles(self):self.assertEqual({x["ticker"] for x in order_day(self.rows,"C")}, {"A","B","C"})
