import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research.backtest.run_store import save, seal, sha256, validate_receipt


def receipt(identity='123-1', status='failed'):
    return seal({'schema_version':'legacy-research-run-v1','id':identity,
                 'result_role':'legacy/research','status':status,'reason':'cache_missing',
                 'code_commit':'a'*40,'request':{'start':'2026-01-01','end':'2026-02-01'},
                 'summary':{},'report':None})


class StoreTests(unittest.TestCase):
    def test_failure_and_retry_are_permanent_and_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); first=receipt(); save(first,root=root); save(first,root=root)
            save(receipt('123-2','unavailable'),root=root)
            index=json.loads((root/'index.json').read_bytes())
            self.assertEqual([r['id'] for r in index['runs']],['123-2','123-1'])
            self.assertEqual(index['runs'][1]['receipt_sha256'],sha256((root/'123-1/receipt.json').read_bytes()))
            changed=copy.deepcopy(first);changed['reason']='different'
            with self.assertRaises(FileExistsError): save(seal(changed),root=root)
            self.assertEqual(json.loads((root/'123-1/receipt.json').read_bytes()),first)

    def test_index_recovers_after_interrupted_publication(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); first=receipt();save(first,root=root)
            (root/'index.json').unlink();save(first,root=root)
            self.assertEqual(len(json.loads((root/'index.json').read_bytes())['runs']),1)

    def test_html_bytes_and_path_cannot_be_substituted(self):
        raw=b'<html><body>derived report</body></html>'
        value=receipt();value.update(status='completed',report={'path':'123-1/report.html','sha256':sha256(raw)})
        value=seal(value)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'report_bytes_mismatch'):save(value,b'wrong',root=d)
            save(value,raw,root=d)
            changed=copy.deepcopy(value);changed['report']['path']='../other.html'
            with self.assertRaisesRegex(ValueError,'invalid_report_reference'):seal(changed)

    def test_tampered_receipt_and_symlink_fail_closed(self):
        value=receipt();value['summary']={'total_return':1}
        with self.assertRaisesRegex(ValueError,'fingerprint'):validate_receipt(value)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'123-1').symlink_to(root/'outside')
            with self.assertRaisesRegex(ValueError,'symlink'):save(receipt(),root=root)


class DailyReturnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import pandas as pd
        except ImportError:
            raise unittest.SkipTest('requires isolated research dependencies')
        cls.pd=pd

    def test_first_day_reconciliation_and_missing_values(self):
        from research.backtest.quantstats_report import checked_daily_returns
        pd=self.pd; dates=pd.date_range('2025-01-02',periods=3,freq='B')
        equity=pd.Series([99.,100.,98.],index=dates)
        returns=pd.Series([-.01,100/99-1,-.02],index=dates)
        self.assertTrue(checked_daily_returns(equity,returns,100).equals(returns))
        for bad in ([0.,100/99-1,-.02],[.2,.1,-.3],[float('nan'),0,0]):
            with self.assertRaises(ValueError):checked_daily_returns(equity,pd.Series(bad,index=dates),100)

    def test_trade_slots_and_reordered_sessions_rejected(self):
        from research.backtest.quantstats_report import checked_daily_returns
        pd=self.pd
        for dates in (pd.date_range('2025-01-02',periods=2,freq='h'),pd.to_datetime(['2025-01-03','2025-01-02'])):
            with self.assertRaises(ValueError):checked_daily_returns(pd.Series([100.,110.],index=dates),pd.Series([0.,.1],index=dates),100)

    def test_real_quantstats_renders_only_synthetic_daily_adapter_fixture(self):
        try:
            import quantstats  # noqa: F401
        except ImportError:
            self.skipTest('requires isolated QuantStats environment')
        import math
        from research.backtest.quantstats_report import render_daily_report
        pd=self.pd; dates=pd.bdate_range('2024-01-02',periods=260)
        daily=pd.Series([math.sin(i)*.01+.0002 for i in range(260)],index=dates)
        equity=100*(1+daily).cumprod()
        with tempfile.TemporaryDirectory() as d, patch('yfinance.download',side_effect=AssertionError('no_download')), patch('socket.socket.connect',side_effect=AssertionError('no_network')):
            path=Path(d)/'synthetic.html'
            metrics=render_daily_report(equity,daily,100,path,title='Synthetic adapter test',synthetic=True)
            raw=path.read_text()
            self.assertIn('SYNTHETIC ADAPTER TEST',raw)
            self.assertGreater(raw.count('<svg '),3)
            self.assertIn('Monthly Returns',raw)
            self.assertIn('Drawdown',raw)
            self.assertNotIn('<body onload=',raw)
            self.assertAlmostEqual(metrics['total_return'],equity.iloc[-1]/100-1)


if __name__=='__main__': unittest.main()
