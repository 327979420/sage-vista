import copy
import unittest
from research.backtest.observation_horizons import summarize, quantile
from research.backtest.selection_observation import target_day

class HorizonTests(unittest.TestCase):
    def event(self,symbol,value,missing=False):
        o={'status':'complete','return':value,'spy_return':.01,'excess':value-.01,'mae':-.2}
        return {'symbol':symbol,'timeframe':'monthly_completed','outcomes':{k:copy.deepcopy(o) for k in ('3m','6m','9m')}|{'12m':{'status':'missing_prices'} if missing else copy.deepcopy(o)}}

    def test_common_cohort_excludes_missing_without_zero_fill(self):
        rows=summarize([self.event('A',.1),self.event('B',-.3,True)])
        row=lambda c,w:next(r for r in rows if r['timeframe']=='monthly_completed' and r['cohort']==c and r['window']==w)
        self.assertAlmostEqual(row('per_window','3m')['mean_return'],-.1)
        self.assertAlmostEqual(row('per_window','12m')['mean_return'],.1)
        self.assertEqual(row('common_planned','3m')['events'],1)
        self.assertEqual(row('common_planned','3m')['symbols'],1)
        self.assertAlmostEqual(row('common_planned','3m')['median_excess'],.09)
        self.assertEqual(row('per_window','12m')['statuses'],{'complete':1,'missing_prices':1})

    def test_unavailable_is_not_a_negative_return(self):
        e={'symbol':'A','timeframe':'daily','outcomes':{k:{'status':'complete','return':.1,'spy_return':.02,'excess':.08,'mae':.01} for k in ('5d','10d','20d')}}
        rows=summarize([e]);r=next(r for r in rows if r['timeframe']=='daily' and r['cohort']=='common_available' and r['window']=='5d')
        self.assertEqual(r['median_downside'],0)
        self.assertEqual(r['required_windows'],['5d','10d','20d'])
        r=next(r for r in rows if r['timeframe']=='daily' and r['cohort']=='common_planned' and r['window']=='5d')
        self.assertEqual(r['events'],0);self.assertIsNone(r['mean_return'])

    def test_calendar_month_roll_and_trading_session_offset(self):
        self.assertEqual(target_day('2024-01-31',1,'m',['2024-01-31','2024-02-29','2024-03-01']),'2024-02-29')
        self.assertEqual(target_day('2024-01-05',1,'d',['2024-01-05','2024-01-08']),'2024-01-08')
        self.assertAlmostEqual(quantile([-1,0,1],.1),-.8)

    def test_exact_price_identity_parity_and_resume(self):
        import tempfile
        from pathlib import Path
        from datetime import date,timedelta
        from unittest.mock import patch
        from research.backtest import observation_horizons as h
        from research.backtest.run_store import encode,sha256
        days=[(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(400)]
        raw=[{'date':d,'open':100+i,'close':100+i,'adjusted_close':100+i,'high':102+i,'low':99+i,'volume':10000} for i,d in enumerate(days)]
        rows=h.normalized_comparison_rows(raw,as_of=h.original.ASOF)
        event=h.original.observe({'symbol':'A','episode_id':'a'*64,'timeframe':'daily','signal_date':days[0]},rows,{r['date']:r for r in rows})
        parent={'events':[event],'observation':{'sources':[{'identity':{'symbol':'A','source':sha256(encode(raw)),'spy':sha256(encode(raw))}}]}}
        with tempfile.TemporaryDirectory() as d:
            cache=Path(d)/'prices';cache.mkdir();cp=Path(d)/'checkpoints'
            for s in ('A','SPY'):(cache/(s+'.json')).write_bytes(encode(raw))
            result,audit=h.supplement(parent,cache,cp)
            self.assertAlmostEqual(result[0]['horizon_outcomes']['15d']['return'],.15)
            self.assertEqual(audit['events_exact_parity'],1)
            with patch.object(h.original,'observe',side_effect=AssertionError('must resume')):
                resumed,audit=h.supplement(parent,cache,cp)
            self.assertEqual(result,resumed);self.assertEqual(audit['resumed_symbols'],1)
            (cache/'A.json').write_bytes(encode(raw)+b' ')
            result,audit=h.supplement(parent,cache,cp)
            self.assertEqual(result[0]['horizon_outcomes']['15d']['status'],'unavailable')
            self.assertIn('original_price_hash_mismatch',audit)
