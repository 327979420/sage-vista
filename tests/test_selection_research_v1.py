import copy,unittest
from research.backtest.selection_research_v1 import _return,_rs,features
class SelectionResearchTests(unittest.TestCase):
 def test_returns_are_point_in_time(self):
  rows=[{"close":100+i} for i in range(260)];before=_return(rows,200,20);rows[259]["close"]=99999;self.assertEqual(_return(rows,200,20),before)
 def test_relative_strength_is_stock_minus_spy(self):
  stock=[{"close":100+i} for i in range(30)];spy=[{"close":100+i/2} for i in range(30)];self.assertGreater(_rs(stock,29,spy,29,20),0)
 def test_selection_features_ignore_future_rows(self):
  rows=[{"open":100+i*.2,"high":102+i*.2,"low":98+i*.2,"close":101+i*.2,"volume":1000+i} for i in range(300)]
  spy=[{"open":100+i*.1,"high":102+i*.1,"low":98+i*.1,"close":101+i*.1,"volume":1000} for i in range(300)]
  before=features(rows,260,spy,260,{"support_level":150})
  changed=copy.deepcopy(rows);changed[261:]=[{**x,"close":99999,"high":99999,"volume":99999} for x in changed[261:]]
  self.assertEqual(before,features(changed,260,spy,260,{"support_level":150}))
