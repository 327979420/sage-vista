import unittest
from research.backtest.factor_attribution_v1 import compare
class FactorAttributionTests(unittest.TestCase):
 def test_with_without_partition(self):
  rows=[{"flag":True,"date":"2020-01-01","return":.1,"r":1,"reason":"target","bars":1,"mfe":.1,"mae":0,"risk_pct":.1},{"flag":False,"date":"2020-01-02","return":-.1,"r":-1,"reason":"stop","bars":1,"mfe":0,"mae":-.1,"risk_pct":.1}]
  result=compare(rows,lambda x:x["flag"]);self.assertEqual(result["with"]["samples"]+result["without"]["samples"],2);self.assertGreater(result["delta"]["expectancy_pct"],0)
