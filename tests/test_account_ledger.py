import copy
import unittest
from research.backtest.account_ledger import cost_assumptions
from tests.test_parameterized_account import AccountTests,CONFIG

class LedgerTests(AccountTests):
    def test_daily_book_reconciles_and_records_rejections(self):
        from research.backtest.account_runner import account
        days,rows,events=self.fixture()
        eq,ret,trades,book=account(events,{s:rows for s in 'ABC'},days,CONFIG,with_ledger=True)
        self.assertEqual(len(book['days']),len(days))
        first=book['days'][1]
        self.assertAlmostEqual(first['ending_cash'],199.2)
        self.assertEqual(first['skipped_signals'][0]['reason'],'position_limit')
        self.assertEqual(first['decisions'][2]['positions_at_decision'],2)
        self.assertAlmostEqual(first['decisions'][2]['cash_at_decision'],199.2)
        self.assertEqual(book['days'][11]['decisions'][0]['reason'],'same_stock_held')
        for d in book['days']:
            self.assertAlmostEqual(d['ending_cash']+d['market_value'],d['ending_portfolio_value'])
            self.assertAlmostEqual(d['realised_pnl']+d['unrealised_pnl'],d['cumulative_pnl'])
            self.assertNotIn('exit_date',str(d['eligible_signals']))
        self.assertEqual(book['metrics']['closed_trades'],sum(t['status']=='closed' for t in trades))

    def test_metrics_match_independent_arithmetic_and_resealed_bad_book_rejected(self):
        import math
        from statistics import mean,stdev
        from research.backtest.account_runner import account
        from research.backtest.account_ledger import validate_ledger_receipt
        days,rows,events=self.fixture()
        eq,ret,trades,book=account(events,{s:rows for s in 'ABC'},days,CONFIG,with_ledger=True)
        m=book['metrics'];values=list(ret)
        self.assertAlmostEqual(m['cagr'],(eq.iloc[-1]/CONFIG['initial_cash'])**(252/len(values))-1)
        self.assertAlmostEqual(m['annualised_volatility'],stdev(values)*math.sqrt(252))
        self.assertAlmostEqual(m['sharpe'],mean(values)/stdev(values)*math.sqrt(252))
        self.assertAlmostEqual(m['sortino'],mean(values)/math.sqrt(sum(min(v,0)**2 for v in values)/len(values))*math.sqrt(252))
        r={'portfolio_ledger':book,'scenario':CONFIG,'daily_account':[{'date':d,'equity':float(v)} for d,v in zip(days,eq)]}
        validate_ledger_receipt(r)
        bad=copy.deepcopy(r);bad['portfolio_ledger']['days'][1]['ending_cash']+=1
        with self.assertRaisesRegex(ValueError,'ledger_reconciliation_failed'):validate_ledger_receipt(bad)

    def test_future_change_cannot_change_past_snapshots(self):
        from research.backtest.account_runner import account
        days,rows,events=self.fixture()
        config={**CONFIG,'initial_cash':100000}
        a=account(events,{s:rows for s in 'ABC'},days,config,with_ledger=True)[3]
        altered=copy.deepcopy(rows)
        for r in altered[50:]:
            for k in ('open','close','high','low'):r[k]*=1.4
        b=account(events,{s:altered for s in 'ABC'},days,config,with_ledger=True)[3]
        self.assertEqual(a['days'][:50],b['days'][:50])

    def test_fees_and_open_pnl_are_counted_once(self):
        from research.backtest.account_runner import account
        days,rows,events=self.fixture();rows=copy.deepcopy(rows[:3])
        rows[1].update(open=100,close=103,high=104,low=99)
        rows[2].update(open=103,close=105,high=106,low=102)
        book=account(events[:1],{'A':rows},days[:3],CONFIG,with_ledger=True)[3]
        self.assertAlmostEqual(book['days'][-1]['unrealised_pnl'],19.6)
        self.assertEqual(book['days'][-1]['realised_pnl'],0)
        self.assertEqual(book['metrics']['closed_trades'],0)
        self.assertIsNone(book['metrics']['profit_factor'])

    def test_empty_book_and_pending_signal(self):
        from research.backtest.account_runner import account
        days,rows,events=self.fixture()
        empty=account([],{},days[:3],CONFIG,with_ledger=True)[3]
        self.assertEqual(empty['days'][-1]['ending_cash'],1000)
        self.assertEqual(empty['metrics']['total_return'],0)
        self.assertIsNone(empty['metrics']['sharpe'])
        e=copy.deepcopy(events[0]);e['signal_date']=days[2]
        pending=account([e],{'A':rows[:3]},days[:3],CONFIG,with_ledger=True)[3]
        self.assertEqual(len(pending['pending_signals']),1)
        self.assertEqual(len(pending['days'][-1]['eligible_signals']),1)
        self.assertEqual(pending['days'][-1]['decisions'],[])

class CostTests(unittest.TestCase):
    def test_explicit_costs_sum_and_legacy_is_not_fabricated(self):
        self.assertIsNone(cost_assumptions(CONFIG)['slippage_rate'])
        self.assertEqual(cost_assumptions({**CONFIG,'commission_rate':.0002,'fee_rate':.0003,'slippage_rate':.0005})['total_rate'],.001)
        with self.assertRaises(ValueError):cost_assumptions({**CONFIG,'commission_rate':0})
        with self.assertRaises(ValueError):cost_assumptions({**CONFIG,'commission_rate':0,'fee_rate':0,'slippage_rate':0})

if __name__=='__main__':unittest.main()
