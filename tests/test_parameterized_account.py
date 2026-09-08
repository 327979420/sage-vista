import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research.backtest.run_store import POLICY, save

CONFIG={'initial_cash':1000.,'allocation_fraction':.4,'max_positions':2,'cost_rate':.001,'fractional_shares':True}


class AccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import vectorbt  # noqa: F401
            import quantstats  # noqa: F401
            import pandas as pd
        except ImportError:
            raise unittest.SkipTest('isolated account dependencies required')
        cls.pd=pd

    def fixture(self):
        days=self.pd.bdate_range('2025-01-02',periods=160).strftime('%Y-%m-%d').tolist()
        rows=[]
        for i,d in enumerate(days):
            price=100+math.sin(i)*2
            rows.append({'date':d,'open':price,'high':max(price+2,125 if i in (12,85) else 0),'low':price-2,'close':price,'adjusted_close':price,'volume':1000})
        def event(symbol,i,rank):
            return {'event_id':f'{symbol}-{i}','symbol':symbol,'signal_date':days[i],'selection':{'rank':rank,'model_version':'unified-v2-macd-trigger-1.3.0','execution_policy_version':POLICY,'support_plan':{'level':90,'source':'synthetic'}}}
        events=[event('A',0,1),event('B',0,2),event('C',0,3),event('A',10,1),event('A',60,1),event('B',90,2)]
        return days,rows,events

    def write_scans(self,root,days,events):
        path=root/'rankings.json'
        path.write_text(json.dumps({'future_data_used':False,'days':[{'date':d,'model_version':'unified-v2-macd-trigger-1.3.0','candidate_count':sum(e['signal_date']==d for e in events),'ranking':[{'symbol':e['symbol'],'rank':e['selection']['rank'],'execution_policy_version':POLICY} for e in events if e['signal_date']==d]} for d in days]}))
        return path

    def test_approved_whole_share_preset_and_scan_coverage_boundaries(self):
        from research.backtest.account_runner import approved_scenario,account,validate_scan_coverage
        config=approved_scenario()
        self.assertEqual({k:config[k] for k in CONFIG},{'initial_cash':100000,'allocation_fraction':.1,'max_positions':10,'cost_rate':.001,'fractional_shares':False})
        self.assertIn('01a074f9-098a-7b82-b486-3185683290fe',config['approval_ref'])
        days,rows,events=self.fixture()
        _,_,trades=account(events,{s:rows for s in 'ABC'},days,config)
        self.assertTrue(all(t['quantity'].is_integer() for t in trades if 'quantity' in t))
        with tempfile.TemporaryDirectory() as d:
            scans=json.loads(self.write_scans(Path(d),days,events).read_bytes())
        validate_scan_coverage(scans,events,days)
        for mutation,reason in [('missing','historical_scan_day_missing'),('other_policy','historical_scan_policy_unsupported'),('lost_signal','ledger_does_not_match_historical_scan')]:
            bad=copy.deepcopy(scans); actual=events
            if mutation=='missing':bad['days'].pop(3)
            elif mutation=='other_policy':bad['days'][3]['model_version']='unified-v2-macd-trigger-1.1.0'
            else:actual=events[1:]
            with self.assertRaisesRegex(ValueError,reason):validate_scan_coverage(bad,actual,days)

    def test_vectorbt_cash_rank_same_stock_and_daily_values(self):
        from research.backtest.account_runner import account
        from research.backtest.quantstats_report import checked_daily_returns
        days,rows,events=self.fixture()
        eq,r,trades=account(list(reversed(events)),{s:rows for s in 'ABC'},days,CONFIG)
        checked_daily_returns(eq,r,CONFIG['initial_cash'])
        by_id={t['event_id']:t for t in trades}
        self.assertEqual(by_id['C-0']['reason'],'position_limit')
        self.assertEqual(by_id['A-10']['reason'],'same_stock_held')
        self.assertEqual(by_id['A-0']['execution']['exit_reason'],'target')
        self.assertGreater(by_id['A-0']['entry_fees'],0)
        self.assertEqual(len(eq),len(days))
        self.assertEqual(eq.iloc[0],1000)
        self.assertEqual(by_id['A-0']['entry_date'],days[1])
        self.assertAlmostEqual(eq.iloc[1],999.2)  # Two 400 notional entries, 0.4 cost each.
        self.assertAlmostEqual(r.iloc[1],-.0008)
        self.assertEqual([t['symbol'] for t in trades[:3]],['A','B','C'])
        _,_,cash_limited=account(events,{s:rows for s in 'ABC'},days,{**CONFIG,'allocation_fraction':.6})
        self.assertEqual(next(t for t in cash_limited if t['event_id']=='B-0')['reason'],'cash_or_whole_share_insufficient')
        self.assertNotIn('quantity',next(t for t in cash_limited if t['event_id']=='B-0'))
        _,_,fee_limited=account(events,{s:rows for s in 'ABC'},days,{**CONFIG,'allocation_fraction':.5})
        self.assertEqual(next(t for t in fee_limited if t['event_id']=='B-0')['reason'],'cash_or_whole_share_insufficient')

    def test_same_day_entry_exit_and_window_end_mark_without_future_exit(self):
        from research.backtest.account_runner import account
        days,rows,events=self.fixture()
        small=copy.deepcopy(rows[:4])
        small[1].update(open=100.,close=100.,high=101.,low=89.)
        eq,r,trades=account(events[:1],{'A':small},days[:4],CONFIG)
        self.assertEqual(trades[0]['status'],'closed')
        self.assertEqual(trades[0]['execution']['exit_date'],days[1])
        self.assertAlmostEqual(eq.iloc[1],959.24)  # 40 loss + 0.4 entry fee + 0.36 exit fee.
        self.assertAlmostEqual(r.iloc[1],-.04076)
        # No price after closure is needed to value an all-cash account.
        after_exit,_r,_t=account(events[:1],{'A':small[:2]},days[:4],CONFIG)
        self.assertAlmostEqual(after_exit.iloc[-1],959.24)
        open_rows=copy.deepcopy(rows[:4]); open_rows[1].update(open=100.,close=103.,high=104.,low=99.)
        open_rows[2].update(open=103.,close=105.,high=106.,low=102.)
        first,_,open_trades=account(events[:1],{'A':open_rows},days[:3],CONFIG)
        self.assertEqual(open_trades[0]['status'],'open')
        self.assertAlmostEqual(first.iloc[-1],1019.6)
        # Future exits and ledger final returns cannot affect the selected window.
        events[0]['evaluation']={'strategy_test':{'return':999,'exit_price':99999}}
        open_rows[3].update(open=1.,close=1.,low=.5,high=2.)
        second,_,_=account(events[:1],{'A':open_rows},days[:3],CONFIG)
        self.assertTrue(first.equals(second))

    def test_missing_held_session_fails_and_absent_approval_stays_closed(self):
        from research.backtest.account_runner import account,approved_scenario
        days,rows,events=self.fixture()
        with self.assertRaisesRegex(ValueError,'held_asset_session_missing'):
            account(events,{'A':[r for r in rows if r['date']!=days[3]],'B':rows,'C':rows},days,CONFIG)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'not_approved'):approved_scenario(Path(d)/'missing.json')

    def test_valid_empty_or_only_pending_windows_complete_cash_reports(self):
        from research.backtest.account_runner import execute
        days,rows,events=self.fixture()
        pending=copy.deepcopy(events[0]);pending['signal_date']=days[64]
        with tempfile.TemporaryDirectory() as d, patch('yfinance.download',side_effect=AssertionError('no_download')):
            root=Path(d);cache=root/'cache';cache.mkdir()
            for symbol in ('SPY','A'):(cache/(symbol+'.json')).write_text(json.dumps(rows))
            ledger=root/'ledger.json'
            for n,signals in enumerate(([],[pending]),1):
                with self.subTest(signals=signals):
                    ledger.write_text(json.dumps({'coverage':{'first':days[0],'last':days[-1]},'events':signals}))
                    scans=self.write_scans(root,days,signals)
                    result=execute({'strategy':POLICY,'start':days[0],'end':days[64]},CONFIG,cache,ledger,rankings_path=scans,out=root/str(n),run_id='901',attempt=str(n),code_commit='a'*40,cache_key='synthetic',synthetic=True)
                    self.assertEqual(result['status'],'completed')
                    self.assertEqual(result['summary']['total_return'],0)
                    self.assertEqual(result['summary']['max_drawdown'],0)
                    self.assertIsNone(result['summary']['win_rate'])
                    self.assertEqual(result['selection']['entered_trades'],0)
                    self.assertTrue(all(row['equity']==1000 and row['return']==0 for row in result['daily_account']))
                    self.assertEqual(result['trades'],[] if not signals else [{'event_id':pending['event_id'],'symbol':'A','signal_date':days[64],'status':'pending_next_session'}])
                    self.assertIn('0.00%',(root/str(n)/'report.html').read_text())
            # Empty signals do not waive reference or ledger coverage requirements.
            ledger.write_text(json.dumps({'coverage':{'first':days[0],'last':days[-1]},'events':[]}))
            args=dict(out=root/'missing',run_id='902',attempt='1',code_commit='a'*40,cache_key='synthetic',synthetic=True)
            with self.assertRaisesRegex(ValueError,'requested_signal_history_not_covered'):
                execute({'strategy':POLICY,'start':'2024-01-01','end':days[64]},CONFIG,cache,ledger,**args)
            (cache/'SPY.json').unlink()
            with self.assertRaises(FileNotFoundError):
                execute({'strategy':POLICY,'start':days[0],'end':days[64]},CONFIG,cache,ledger,**args)

    def test_all_rejected_orders_leave_cash_unchanged(self):
        from research.backtest.account_runner import account
        days,rows,events=self.fixture()
        eq,daily,trades=account(events,{s:rows for s in 'ABC'},days,{**CONFIG,'allocation_fraction':1.})
        self.assertTrue((eq==CONFIG['initial_cash']).all())
        self.assertTrue((daily==0).all())
        self.assertTrue(all(t['status']=='skipped' for t in trades))
        self.assertTrue(all(t['reason']=='cash_or_whole_share_insufficient' for t in trades))
        self.assertTrue(all('quantity' not in t for t in trades))

    def test_two_synthetic_windows_reconcile_and_render_but_cannot_publish(self):
        from research.backtest.account_runner import execute
        days,rows,events=self.fixture()
        with tempfile.TemporaryDirectory() as d, patch('yfinance.download',side_effect=AssertionError('no_download')):
            root=Path(d);cache=root/'cache';cache.mkdir()
            for symbol in ('SPY','A','B','C'):(cache/(symbol+'.json')).write_text(json.dumps(rows))
            ledger=root/'ledger.json';ledger.write_text(json.dumps({'coverage':{'first':days[0],'last':days[-1]},'events':events}))
            scans=self.write_scans(root,days,events)
            results=[]
            for n,end in enumerate((days[64],days[130]),1):
                result=execute({'strategy':POLICY,'start':days[0],'end':end},CONFIG,cache,ledger,rankings_path=scans,out=root/str(n),run_id='900',attempt=str(n),code_commit='a'*40,cache_key='synthetic',synthetic=True)
                results.append(result)
                self.assertEqual(result['status'],'completed')
                self.assertAlmostEqual(result['summary']['total_return'],result['daily_account'][-1]['equity']/1000-1)
                self.assertIn('SYNTHETIC ADAPTER TEST',(root/str(n)/'report.html').read_text())
                self.assertIn('Trades',(root/str(n)/'report.html').read_text())
                with self.assertRaisesRegex(ValueError,'synthetic_result'):save(result,(root/str(n)/'report.html').read_bytes(),root=root/'publish')
            self.assertEqual(next(t for t in results[0]['trades'] if t['event_id']=='A-60')['status'],'open')
            self.assertEqual(next(t for t in results[1]['trades'] if t['event_id']=='A-60')['status'],'closed')
            self.assertNotEqual(results[0]['summary']['daily_sessions'],results[1]['summary']['daily_sessions'])
            self.assertNotEqual(results[0]['content_sha256'],results[1]['content_sha256'])

if __name__=='__main__':unittest.main()
