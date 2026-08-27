import unittest
from services.scanner.market_etf_watch import FUNDS,build

def rows(last="2026-08-26",future=False):
 out=[{"date":f"2026-{6+(i//28):02d}-{1+i%28:02d}","close":100+i/10} for i in range(56)];out[-1]["date"]=last
 if future:out.append({"date":"2027-01-01","close":99999})
 return out

class MarketEtfWatchTests(unittest.TestCase):
 def test_exact_date_and_future_rows_are_enforced(self):
  report=build({code:rows(future=True) for code in FUNDS},"2026-08-26")
  self.assertEqual(report["as_of"],"2026-08-26");self.assertFalse(report["future_data_used"]);self.assertEqual(report["audit"]["funds_exact_as_of"],len(FUNDS))
 def test_missing_fund_date_fails_closed(self):
  raw={code:rows() for code in FUNDS};raw["IWM"][-1]["date"]="2026-08-25"
  with self.assertRaisesRegex(RuntimeError,"IWM"):build(raw,"2026-08-26")
 def test_layers_do_not_claim_to_be_technical_score(self):
  report=build({code:rows() for code in FUNDS},"2026-08-26")
  self.assertEqual(report["mode"],"decision_context_not_technical_score");self.assertEqual(set(report["layers"]),{"trend","breadth","risk_appetite"})

if __name__=="__main__":unittest.main()
