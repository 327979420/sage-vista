import unittest
from services.scanner.technical import ema,rsi,position_size,backtest,trade_efficiency

class TechnicalTests(unittest.TestCase):
 def test_ema_constant(self):self.assertTrue(all(abs(x-10)<1e-9 for x in ema([10]*30,20)))
 def test_rsi_rising(self):self.assertGreater(rsi(list(range(1,40)))[-1],99)
 def test_size_risk_and_cap(self):self.assertEqual(position_size(100000,.01,100,95),200)
 def test_size_caps_concentration(self):self.assertEqual(position_size(100000,.02,100,99),200)
 def test_invalid_size(self):self.assertEqual(position_size(100000,.03,100,95),0)
 def test_trade_efficiency_empty(self):self.assertEqual(trade_efficiency([])["count"],0)
 def test_empty_backtest(self):self.assertEqual(backtest([])["summary"]["count"],0)

if __name__=="__main__":unittest.main()
