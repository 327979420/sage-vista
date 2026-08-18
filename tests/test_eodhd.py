import unittest
from unittest.mock import patch
from services.scanner.audit_eodhd import common
from services.scanner.eodhd_factor_pilot import stable_sample
class EodhdTests(unittest.TestCase):
 def test_primary_common_stock_filter(self):
  rows=[{"Code":"A","Type":"Common Stock","Exchange":"NYSE"},{"Code":"P","Type":"Common Stock","Exchange":"PINK"},{"Code":"E","Type":"ETF","Exchange":"NASDAQ"}]
  self.assertEqual([x["Code"] for x in common(rows)],["A"])
 def test_sample_is_deterministic(self):
  rows=[{"Code":x} for x in "ABCDE"]
  self.assertEqual(stable_sample(rows,3,"seed"),stable_sample(list(reversed(rows)),3,"seed"))
if __name__=="__main__":unittest.main()
