"""Entry-path semantics and daily/replay boundary regression tests."""
import copy
import hashlib
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from services.factors.cr056 import collect_entry_facts
from services.selectors.cr056 import assess_entry
from services.scanner.cr056_runner import run_snapshot
from services.contracts.cr056_policy import POLICY_VERSION, POLICY_FINGERPRINT
from research.backtest.cr056_history import prepare
from research.backtest.run_store import CANDIDATE_POLICY
from tests.test_cr056_strategy import facts, states


def bars():
    # Two separated, confirmed lows with a distinct bounce. A final retest
    # closes as a bullish engulf, before any new MACD cross is required.
    closes=[110.]*40
    for i,c in {10:105,11:100,12:104,13:109,14:112,
                22:104,23:101,24:105,25:109,26:112,37:105,38:102,39:105}.items():closes[i]=c
    start=date(2026,1,1)
    out=[{'date':(start+timedelta(days=i)).isoformat(),'open':c-.2,'high':c+1,'low':c-1,'close':c,'volume':1000000} for i,c in enumerate(closes)]
    out[-2].update(open=106,close=102,high=107,low=101)
    out[-1].update(open=101,close=107,high=108,low=100)
    return out


class EntryTests(unittest.TestCase):
    def test_support_reversal_can_precede_macd_and_future_pivot_confirmation(self):
        rows=bars()
        with patch('services.factors.cr056.macd',side_effect=lambda c:([-1.]*len(c),[0.]*len(c))):
            gate=assess_entry(collect_entry_facts(rows,as_of=rows[-1]['date'],complete_session=True))
        self.assertIn(('support_reversal','daily'),[(x['path'],x['timeframe']) for x in gate['paths']])
        self.assertFalse(gate['evidence']['daily']['macd_valid'])
        bad=copy.deepcopy(rows);bad[-1].update(open=106,close=100,low=99)
        f=collect_entry_facts(bad,as_of=bad[-1]['date'],complete_session=True)
        self.assertFalse(f['frames']['daily']['support_reversal'])

    def test_cross_before_second_bottom_and_older_than_display_window_is_valid(self):
        rows=bars()[:30]
        def curve(c):
            return ([-1. if i<15 else 1. for i in range(len(c))],[0.]*len(c))
        with patch('services.factors.cr056.macd',side_effect=curve):
            f=collect_entry_facts(rows,as_of=rows[-1]['date'],complete_session=True)
        daily=f['frames']['daily']
        self.assertEqual(len(daily['bottoms']),2)
        self.assertEqual(daily['cross_date'],rows[15]['date'])
        self.assertTrue(daily['macd_valid'])
        self.assertIn('bottom_macd',[p['path'] for p in assess_entry(f)['paths']])
        with patch('services.factors.cr056.macd',side_effect=lambda c:(curve(c)[0][:-1]+[-1.],[0.]*len(c))):
            bad=collect_entry_facts(rows,as_of=rows[-1]['date'],complete_session=True)
        self.assertFalse(bad['frames']['daily']['macd_valid'])

    def test_three_push_requires_a_fresh_solid_close_and_two_bottoms(self):
        anchors={0:135,5:125,10:130,15:95,20:120,25:96,30:110,35:100,38:100,39:99,40:106}
        rows=[]
        for i in range(41):
            before=max(x for x in anchors if x<=i);after=min(x for x in anchors if x>=i)
            c=anchors[before] if before==after else anchors[before]+(anchors[after]-anchors[before])*(i-before)/(after-before)
            rows.append({'date':str(date(2026,1,1)+timedelta(days=i)),'open':c-.2,'high':c+1,'low':c-1,'close':c,'volume':1000000})
        rows[-1].update(open=100,low=99,high=107)
        f=collect_entry_facts(rows,as_of=rows[-1]['date'],complete_session=True)
        self.assertTrue(f['frames']['daily']['breakout'])
        self.assertEqual(len(f['frames']['daily']['bottoms']),2)
        rows[-1]['close']=99.5
        f=collect_entry_facts(rows,as_of=rows[-1]['date'],complete_session=True)
        self.assertFalse(f['frames']['daily']['breakout'])

    def test_cross_period_parts_cannot_make_a_ticket(self):
        blank={'available':True,'completed_through':'2026-01-30','bottoms':[],
               'macd_valid':False,'breakout':False,'support_reversal':False}
        day={**blank,'bottoms':[{},{}]};week={**blank,'macd_valid':True,'breakout':True}
        self.assertFalse(assess_entry({'as_of':'2026-01-30','frames':{'daily':day,'weekly_completed':week}})['eligible'])
        day.update(breakout=True,macd_valid=True,support_reversal=True)
        result=assess_entry({'as_of':'2026-01-30','frames':{'daily':day}})
        self.assertEqual(len(result['paths']),3)

    def test_partial_week_and_month_never_count_as_confirmed(self):
        rows=bars();as_of=rows[-1]['date']
        f=collect_entry_facts(rows,as_of=as_of,complete_session=True)
        self.assertLess(f['frames']['monthly_completed']['completed_through'],as_of)
        with self.assertRaises(ValueError):collect_entry_facts(rows,as_of=rows[-2]['date'])

    def test_daily_and_historical_adapter_same_gate_score_and_monthly_veto(self):
        # Isolate I/O/cohort wiring from detectors tested above. Crucially there
        # is no daily cross, so the old MACD-only prefilter would omit this trade.
        start=date(2020,1,1)
        rows=[]
        for i in range(900):
            d=start+timedelta(days=i)
            if d.weekday()<5:rows.append({'date':str(d),'open':80.,'high':81.,'low':79.,'close':80.,'adjusted_close':80.,'volume':1000000})
        day,end=rows[-2]['date'],rows[-1]['date']
        ef={'as_of':day,'frames':{'daily':{'available':True,'completed_through':day,'bottoms':[],
            'macd_valid':False,'breakout':False,'support_reversal':True}}}
        df=facts();df['as_of']=day
        for tf in ('monthly','weekly'):df[tf]['completed_through']=day
        fs=states()
        for state in fs:state['as_of']=day
        with tempfile.TemporaryDirectory() as temp:
            cache=Path(temp)/'cache';cache.mkdir()
            for symbol in ('AAA','SPY'):(cache/f'{symbol}.json').write_text(json.dumps(rows))
            def direction(past,**kwargs):
                val=copy.deepcopy(df);val['as_of']=kwargs['as_of'];return val
            def factor(past,as_of,**kwargs):
                val=copy.deepcopy(fs)
                for v in val:v['as_of']=as_of
                return val
            def entry(past,**kwargs):
                val=copy.deepcopy(ef);val['as_of']=kwargs['as_of'];return val
            with patch('services.scanner.cr056_runner.collect_entry_facts',side_effect=entry),patch('research.backtest.cr056_history.collect_entry_facts',side_effect=entry),patch('services.scanner.cr056_runner.collect_direction_facts',side_effect=direction),patch('research.backtest.cr056_history.collect_direction_facts',side_effect=direction),patch('services.scanner.cr056_runner.evaluate_period_factors',side_effect=factor),patch('research.backtest.cr056_history.signal_support_plan',return_value={'level':70}):
                bounded=[r for r in rows if r['date']<=day]
                live=Path(temp)/'live';live.mkdir();repaired=[]
                for symbol in ('AAA','SPY'):
                    raw=json.dumps(bounded).encode();(live/f'{symbol}.json').write_bytes(raw)
                    repaired.append({'symbol':symbol,'repaired_sha256':hashlib.sha256(raw).hexdigest(),'source_sha256':'test'})
                report=run_snapshot(live,as_of=day,history={'days':[]},code_commit='a'*40,input_report={'as_of':day,'result_role':'legacy_comparison_input_repair','repaired':repaired,'repaired_count':2,'excluded_count':0})
                selected=next(r for r in report['reviews'] if r['symbol']=='AAA')
                self.assertFalse(selected['exact_daily_cross_today']);self.assertTrue(selected['new_nomination'])
                ledger,_=prepare({'strategy':CANDIDATE_POLICY,'start':day,'end':end},cache,Path(temp)/'state','a'*40)
                event=next(e for e in json.loads(ledger.read_bytes())['events'] if e['symbol']=='AAA')
                self.assertEqual(event['selection']['technical_score'],selected['score']['total_score'])
                self.assertEqual(event['selection']['entry_gate'],selected['entry_gate'])
                self.assertEqual(event['selection']['policy_fingerprint'],POLICY_FINGERPRINT)
                df['monthly']['histogram']=[1.,.5,.1]
                blocked=run_snapshot(live,as_of=day,history={'days':[]},code_commit='a'*40,input_report={'as_of':day,'result_role':'legacy_comparison_input_repair','repaired':repaired,'repaired_count':2,'excluded_count':0})
                self.assertEqual(blocked['ranked_symbols'],[])
                rejected,_=prepare({'strategy':CANDIDATE_POLICY,'start':day,'end':end},cache,Path(temp)/'blocked','a'*40)
                self.assertEqual(json.loads(rejected.read_bytes())['events'],[])


class NegativeHistogramEvidenceTests(unittest.TestCase):
    def test_strict_completed_negative_improvements(self):
        from services.factors.cr056 import negative_histogram_confirmation as check
        dates=['2026-09-07','2026-09-08','2026-09-09']
        for values, expected in [([-3,-2,-1],True),([-3,-2,-2],False),
                                 ([-3,-2,0],False),([-3,-1,-2],False),
                                 ([3,2,1],False),([-3,1,2],False)]:
            with self.subTest(values=values):
                r=check(values,[0]*3,dates)
                self.assertEqual(r['confirmed'],expected)
                self.assertEqual(r['confirmation_date'],dates[-1] if expected else None)
                self.assertEqual(r['dates'],dates)

    def test_missing_or_nonfinite_is_unavailable(self):
        from services.factors.cr056 import negative_histogram_confirmation as check
        self.assertFalse(check([-2,-1],[0,0],['a','b'])['available'])
        self.assertFalse(check([-3,float('nan'),-1],[0,0,0],['a','b','c'])['available'])
        with self.assertRaises(ValueError):check([-1],[0],[])

    def test_evidence_alone_cannot_admit_stock(self):
        frame={'available':True,'completed_through':'2026-09-09','bottoms':[],
               'macd_valid':False,'breakout':False,'support_reversal':False,
               'negative_histogram_confirmation':{'confirmed':True}}
        self.assertFalse(assess_entry({'as_of':'2026-09-09','frames':{'daily':frame}})['eligible'])

class PullbackMomentumTests(unittest.TestCase):
    def rows(self):
        anchors={0:135,5:125,10:130,15:95,20:120,25:96,30:110,35:100,38:100,39:99,40:106}
        rows=[]
        for i in range(41):
            before=max(x for x in anchors if x<=i);after=min(x for x in anchors if x>=i)
            c=anchors[before] if before==after else anchors[before]+(anchors[after]-anchors[before])*(i-before)/(after-before)
            rows.append({'date':str(date(2026,1,1)+timedelta(days=i)),'open':c-.2,'high':c+1,'low':c-1,'close':c,'volume':1000000})
        rows[-1].update(open=100,low=99,high=107)
        for c in [105.,105.]:
            rows.append({'date':str(date(2026,1,1)+timedelta(days=len(rows))),
                         'open':c+.2,'high':c+1,'low':c-2,'close':c,'volume':1000000})
        return rows

    def test_real_breakout_ema_retest_without_cross_or_bullish_candle(self):
        from services.factors.cr056 import breakout_pullback_momentum
        from services.contracts.cr056_policy import ENTRY_SETTINGS
        rows=self.rows()
        r=breakout_pullback_momentum(rows,{'confirmed':True},ENTRY_SETTINGS)
        self.assertTrue(r['confirmed'],r)
        self.assertIn('ema20',[s['kind'] for s in r['supports']])
        self.assertEqual(r['breakout_date'],rows[40]['date'])
        self.assertEqual(len(r['bottoms']),2)
        frame={'available':True,'completed_through':rows[-1]['date'],'bottoms':[],
               'macd_valid':False,'breakout':False,'support_reversal':False,'pullback_momentum':r}
        p=assess_entry({'as_of':rows[-1]['date'],'frames':{'daily':frame}})['paths']
        self.assertEqual(len(p),1)
        self.assertEqual(p[0]['confirmation_kinds'],['negative_histogram_pullback'])
        frame['support_reversal']=True
        both=assess_entry({'as_of':rows[-1]['date'],'frames':{'daily':frame}})['paths']
        self.assertEqual(len(both),1)
        self.assertEqual(len(both[0]['confirmation_kinds']),2)

    def test_large_full_body_and_wick_boundaries(self):
        from services.factors.cr056 import bearish_full_body_evidence
        rows=self.rows();rows[-1].update(open=109,close=101,high=110,low=100)
        self.assertTrue(bearish_full_body_evidence(rows)['blocked'])
        # Same body and volatility, but a longer lower rejection wick.
        rows[-1]['low']=98
        self.assertFalse(bearish_full_body_evidence(rows)['blocked'])
        rows[-1].update(open=105.8,close=105.,high=105.9,low=104.9)
        self.assertFalse(bearish_full_body_evidence(rows)['blocked'])
        rows[-1].update(open=101,close=109,high=110,low=100)
        self.assertFalse(bearish_full_body_evidence(rows)['blocked'])

    def test_bearish_guard_applies_to_all_three_confirmation_days(self):
        from services.factors.cr056 import breakout_pullback_momentum
        from services.contracts.cr056_policy import ENTRY_SETTINGS
        for offset in [-1,-2,-3]:
            rows=self.rows();rows[offset].update(open=109,close=101,high=110,low=100)
            r=breakout_pullback_momentum(rows,{'confirmed':True},ENTRY_SETTINGS)
            self.assertFalse(r['confirmed'])
            self.assertEqual(r['reason'],'large_full_body_bearish_candle')

    def test_no_breakout_or_lost_floor_cannot_be_saved_by_momentum(self):
        from services.factors.cr056 import breakout_pullback_momentum
        from services.contracts.cr056_policy import ENTRY_SETTINGS
        rows=self.rows();rows[40].update(close=99.5,open=99.2)
        self.assertFalse(breakout_pullback_momentum(rows,{'confirmed':True},ENTRY_SETTINGS)['confirmed'])
        rows=self.rows();rows[41].update(close=90,open=90,low=89,high=91)
        self.assertFalse(breakout_pullback_momentum(rows,{'confirmed':True},ENTRY_SETTINGS)['confirmed'])


class MomentumSharedEntryTests(unittest.TestCase):
    def test_daily_facts_and_history_ticket_prefilter_share_momentum_branch(self):
        from research.backtest.cr056_history import ticket_dates
        rows=PullbackMomentumTests().rows()
        lead=[{'open':140.,'close':140.,'high':141.,'low':139.,'volume':1000000} for _ in range(400)]
        rows=lead+rows
        for i,r in enumerate(rows):r['date']=str(date(2024,1,1)+timedelta(days=i))
        def curve(c):return [-4.]*(len(c)-3)+[-3.,-2.,-1.],[0.]*len(c)
        day=rows[-1]['date']
        with patch('services.factors.cr056.macd',side_effect=curve):
            evidence=collect_entry_facts(rows,as_of=day,complete_session=True)
            gate=assess_entry(evidence)
            self.assertTrue(evidence['frames']['daily']['pullback_momentum']['confirmed'])
            self.assertTrue(any('negative_histogram_pullback' in p['confirmation_kinds'] for p in gate['paths']))
            self.assertEqual(list(ticket_dates(rows,day,day)),[day])
            evidence['frames']['daily']['pullback_momentum']['confirmed']=False
            # No automatic conversion of the negative histogram itself to a ticket.
            evidence['frames']['daily'].update(macd_valid=False,breakout=False,support_reversal=False)
            self.assertFalse(any(p['timeframe']=='daily' for p in assess_entry(evidence)['paths']))
