import unittest
from datetime import date,timedelta
from research.backtest.selection_observation import target_day,observe,choose,summarize
from research.backtest.run_store import seal,sha256,encode,trade_csv

class ObservationTests(unittest.TestCase):
    def test_calendar_month_and_leap(self):
        self.assertEqual(target_day('2024-01-31',1,'m',['2024-01-31','2024-02-29','2024-03-01']),'2024-02-29')
        self.assertIsNone(target_day('2024-01-31',12,'m',['2024-01-31','2024-02-29']))
    def test_only_ticket_frames_can_dominate(self):
        gate={'paths':[{'timeframe':'daily','structure_floor':90}]}
        self.assertEqual(choose(gate,{'daily':30,'monthly_completed':99}),('daily',90))
    def test_equal_score_prefers_month(self):
        gate={'paths':[{'timeframe':'daily','structure_floor':90},{'timeframe':'monthly_completed','structure_floor':80}]}
        self.assertEqual(choose(gate,{'daily':50,'monthly_completed':50}),('monthly_completed',80))
    def test_forward_windows_missing_and_no_trading(self):
        ds=[(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(30)]
        rows=[{'date':d,'close':100+i,'high':102+i,'low':50 if i==1 else 99+i} for i,d in enumerate(ds)]
        e={'signal_date':ds[0]};spy={d:{'close':100} for d in ds}
        r=observe(e,rows,spy)['outcomes'];self.assertAlmostEqual(r['5d']['return'],.05)
        self.assertEqual(r['5d']['mae'],-.5) # no implicit stop
        self.assertEqual(r['3m']['status'],'immature')
        self.assertEqual(observe(e,rows[:2]+rows[3:],spy)['outcomes']['5d']['status'],'missing_prices')
    def test_observation_receipt_not_account(self):
        r={'schema_version':'legacy-research-run-v1','id':'123-1','result_role':'legacy/research','status':'completed','request':{'strategy':'cr056-selection-observation-v1','start':'2020-09-14','end':'2025-09-11'},'summary':{'opportunities':0,'symbols':1},'code_commit':'a'*40,'events':[],'observation':{},'report':{'path':'123-1/report.html','sha256':sha256(b'ok')}}
        r=seal(r);r['downloads']={'trades_csv':{'path':'123-1/trades.csv','sha256':sha256(trade_csv(r))}};seal(r)
        self.assertIn(b'window',trade_csv(r))
        r['summary']['opportunities']=1
        with self.assertRaises(ValueError):seal(r)

    def test_replay_prefix_dedup_and_checkpoint_reuse(self):
        import tempfile,json,os,gzip
        from pathlib import Path
        from unittest.mock import patch
        from research.backtest import selection_observation as m
        days=['2005-09-12','2005-09-13','2005-09-14','2025-09-11','2026-09-11']
        rows=[{'date':d,'open':100,'close':100,'low':99,'high':101,'volume':10000} for d in days]
        calls=[]
        def scan(stage,as_of,**kwargs):
            for f in stage.glob('*.json'):
                self.assertLessEqual(max(r['date'] for r in json.loads(f.read_bytes())),as_of)
            calls.append(as_of)
            gate={'eligible':True,'paths':[{'timeframe':'daily','path':'bottom_macd','structure_key':'constant','structure_floor':90}]}
            return {'reviews':[{'symbol':s,'status':'allowed','rank':1,'entry_gate':gate,'score':{'total_score':40,'timeframes':{'daily':{'normalized':.4}}},'reason_codes':[]} for s in ('AAA','SPY')]}
        with tempfile.TemporaryDirectory() as td,patch.object(m,'ROOT',Path(td)),patch.dict(os.environ,{'GITHUB_SHA':'a'*40}),patch.object(m,'normalized_comparison_rows',side_effect=lambda r,**k:r),patch.object(m,'ticket_dates',side_effect=lambda rows,start,end:[start]),patch.object(m,'run_snapshot',side_effect=scan):
            cache=Path(td)/'work/eodhd-cache';cache.mkdir(parents=True)
            for s in ('AAA','SPY'):(cache/(s+'.json')).write_text(json.dumps(rows))
            m.shard(0,1)
            data=json.loads(gzip.decompress((Path(td)/'work/observation/AAA.json.gz').read_bytes()))
            self.assertEqual(len(data['events']),1)
            self.assertEqual(len(calls),2)
            m.shard(0,1)
            self.assertEqual(len(calls),2)
