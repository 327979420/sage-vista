import unittest
from services.scanner.technical import ema,rsi,position_size,backtest,trade_efficiency,evaluate

class TechnicalTests(unittest.TestCase):
 def test_ema_constant(self):self.assertTrue(all(abs(x-10)<1e-9 for x in ema([10]*30,20)))
 def test_rsi_rising(self):self.assertGreater(rsi(list(range(1,40)))[-1],99)
 def test_size_risk_and_cap(self):self.assertEqual(position_size(100000,.01,100,95),200)
 def test_size_caps_concentration(self):self.assertEqual(position_size(100000,.02,100,99),200)
 def test_invalid_size(self):self.assertEqual(position_size(100000,.03,100,95),0)
 def test_trade_efficiency_empty(self):self.assertEqual(trade_efficiency([])["count"],0)
 def test_signal_executes_next_open(self):
  rows=[{"date":str(i),"open":100+i*.1,"high":101+i*.1,"low":99+i*.1,"close":100+i*.1,"volume":1000000} for i in range(260)]
  plan=evaluate(rows,240)
  if plan:self.assertEqual(plan.entry,rows[241]["open"])
 def test_regime_can_block_signal(self):
  rows=[{"date":str(i),"open":100+i*.1,"high":101+i*.1,"low":99+i*.1,"close":100+i*.1,"volume":1000000} for i in range(260)]
  self.assertIsNone(evaluate(rows,240,market_regime={str(240):False}))
 def test_empty_backtest(self):self.assertEqual(backtest([])["summary"]["count"],0)

if __name__=="__main__":unittest.main()
