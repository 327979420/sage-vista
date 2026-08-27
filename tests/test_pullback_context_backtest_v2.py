import unittest
from research.backtest.pullback_context_backtest_v2 import context_states

def bars(n=260,drop=0):
 rows=[]
 for i in range(n):
  close=100+i*.2-(drop if i==n-1 else 0);rows.append({"date":f"D{i}","open":close,"high":close+1,"low":close-1,"close":close,"volume":100})
 return rows

class PullbackContextTests(unittest.TestCase):
 def test_aligned_benchmarks_produce_a_context(self):
  result=context_states(bars(),bars())
  self.assertIn("D259",result);self.assertIn(result["D259"]["state"],{"Uptrend No Pullback","Pullback At Support","Pullback + MACD Repair"})

if __name__=="__main__":unittest.main()
