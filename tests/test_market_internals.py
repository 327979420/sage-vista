import copy
from datetime import date,timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from services.contracts.market_data import canonical_fingerprint
from services.scanner import market_internals as calc
from services.scanner import market_internals_daily as daily


def calendar(n=410):
    d=date(2025,1,1);out=[]
    while len(out)<n:
        if d.weekday()<5:out.append(d.isoformat())
        d+=timedelta(days=1)
    return out


def bar(day,price,volume=200000):
    return dict(date=day,open=price,high=price+1,low=price-1,close=price,adjusted_close=price,volume=volume)


class MarketFactsTests(unittest.TestCase):
    def setUp(self):
        self.days=calendar(300)
        self.rows={s:{d:{'date':d,'close':100.,'high':101.,'low':99.,'volume':100,'raw_close':100.} for d in self.days} for s in ('A','B','C','D')}
        self.etfs={s:copy.deepcopy(self.rows['A']) for s in ('SPY','RSP')}
        for s,p,v in [('A',110,200),('B',105,100),('C',90,300),('D',100,999)]:
            self.rows[s][self.days[-1]].update(close=p,high=p+1,low=p-1,volume=v)
    def calculate(self):
        return calc.facts(self.rows,self.etfs,self.days,self.days[-1],list(self.rows))
    def test_hand_calculated_breadth_volume_dispersion(self):
        r=self.calculate();v=r['values']
        self.assertEqual((r['advances'],r['declines'],r['unchanged']),(2,1,1))
        for n in (20,50,200):self.assertEqual(v[f'above{n}'],50)
        self.assertEqual(v['ad_ratio'],2)
        self.assertEqual(v['up_volume'],50) # flat volume excluded
        self.assertEqual(v['trin'],2)
        self.assertEqual(v['median_rvol'],2.5)
        self.assertEqual(v['rvol_breadth'],75)
        self.assertAlmostEqual(v['dispersion'],7.3950997289)
        self.assertEqual((r['new_highs'],r['new_lows']),(3,2)) # flat touches both
        self.assertEqual(v['new_high_low'],25)
    def test_calendar_gap_is_not_silently_compressed(self):
        del self.rows['A'][self.days[-10]]
        r=self.calculate()
        self.assertEqual(r['valid'],4)
        self.assertEqual(r['counts']['above20'],3)
        self.assertEqual(r['counts']['new_high_low'],3)
    def test_stale_current_bar_and_zero_denominators(self):
        del self.rows['A'][self.days[-1]]
        self.assertEqual(self.calculate()['valid'],3)
        for series in self.rows.values():
            if self.days[-1] in series:series[self.days[-1]]['close']=110
        r=self.calculate()
        self.assertIsNone(r['values']['ad_ratio']);self.assertIsNone(r['values']['trin'])
    def test_adjustment_and_future_rows_use_shared_contract(self):
        raw=[bar(self.days[-2],100),bar(self.days[-1],50)]
        raw[0]['adjusted_close']=50
        result=daily.prepared(raw,self.days[-1])
        self.assertEqual([r['close'] for r in result.values()],[50,50])
        self.assertEqual(result[self.days[-2]]['raw_close'],100)
        self.assertEqual(daily.prepared(raw+[{'date':'2099-01-01','close':'bad'}],self.days[-1]),result)
    def test_config_rejects_invalid_weights_and_unsorted_risk_knots(self):
        c=daily.read(daily.CONFIG_PATH);calc.validate_config(c)
        c['subscores']['extension']['weight']=.9
        with self.assertRaisesRegex(ValueError,'weights'):calc.validate_config(c)
        c=daily.read(daily.CONFIG_PATH);c['indicators']['above20']['risk_knots'].reverse()
        with self.assertRaisesRegex(ValueError,'risk_curve'):calc.validate_config(c)

    def test_indicator_interpretations_are_not_uniform(self):
        c=daily.read(daily.CONFIG_PATH)['indicators']
        self.assertGreater(calc.risk(90,c['above20']['risk_knots']),70)
        self.assertLess(calc.risk(70,c['above200']['risk_knots']),10)
        self.assertEqual(calc.band(70,c['above200']['levels'])['tone'],'green')


class MarketPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.days=calendar();self.cache=self.root/'cache';self.cache.mkdir();self.etf=self.root/'etfs';self.etf.mkdir()
        self.symbols=['A','B','C','D']
        import math
        manifest=[]
        for j,s in enumerate(self.symbols):
            rows=[bar(d,100+j*15+math.sin(i*.17+j)*5+i*.04,200000+(i%7)*20000) for i,d in enumerate(self.days)]
            p=self.cache/f'{s}.json';p.write_text(json.dumps(rows));manifest.append({'symbol':s,'repaired_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
        for s,j in [('SPY',0),('RSP',1)]:
            (self.etf/f'{s}.json').write_text(json.dumps([bar(d,100+i*(.03+j*.005)) for i,d in enumerate(self.days)]))
        self.index=self.root/'index.json';self.index.write_text(json.dumps({'as_of':self.days[-2],'repaired':manifest}))
        self.common=self.root/'common.json';self.common.write_text(json.dumps([{'Code':s,'Type':'Common Stock','Exchange':'NYSE'} for s in self.symbols]+[{'Code':'ETF','Type':'ETF','Exchange':'NYSE'}]))
        self.config=self.root/'config.json';c=daily.read(daily.CONFIG_PATH);c['quality']['minimum_members']=3;self.config.write_text(json.dumps(c))
        self.args=dict(cache_dir=self.cache,index_path=self.index,common_path=self.common,etf_dir=self.etf,as_of=self.days[-2],state_dir=self.root/'state',out=self.root/'public.json',config_path=self.config,bootstrap_sessions=70)
    def run_it(self):return daily.run(**self.args)
    def test_snapshot_is_immutable_idempotent_and_does_not_write_cache(self):
        hashes={p.name:p.read_bytes() for p in self.cache.iterdir()}
        r=self.run_it();self.assertEqual(r['history_sessions'],70)
        p=daily.read(self.args['out']);daily.validate_public(p,self.args['as_of'])
        self.assertEqual(self.run_it()['result'],'already_current')
        self.assertEqual(hashes,{p.name:p.read_bytes() for p in self.cache.iterdir()})
        self.assertEqual(p['history'][0]['observation_kind'],'reconstructed_current_membership')
        self.assertEqual(p['history'][-1]['observation_kind'],'observed_eod')
        self.assertIsNone(p['history'][0]['temperature']['score'])
        self.assertIsNotNone(p['history'][-1]['temperature']['score'])
        self.assertIsNotNone(p['history'][-1]['indicators']['above20']['percentile'])
        self.assertIsNone(p['history'][10]['indicators']['above20']['percentile'])
    def test_append_preserves_old_days_and_rejects_config_drift(self):
        self.run_it();before=daily.read(self.args['out'])['history']
        self.args['as_of']=self.days[-1];i=daily.read(self.index);i['as_of']=self.days[-1];self.index.write_text(json.dumps(i))
        self.run_it();self.assertEqual(daily.read(self.args['out'])['history'][:-1],before)
        c=daily.read(self.config);c['quality']['minimum_members']=2;self.config.write_text(json.dumps(c))
        with self.assertRaisesRegex(ValueError,'new_series'):self.run_it()
    def test_short_eod_gap_is_recovered_without_overwriting_history(self):
        self.args['as_of']=self.days[-4]
        idx=daily.read(self.index);idx['as_of']=self.args['as_of'];self.index.write_text(json.dumps(idx))
        self.run_it();old=daily.read(self.args['out'])['history']
        self.args['as_of']=self.days[-1];idx['as_of']=self.args['as_of'];self.index.write_text(json.dumps(idx))
        self.run_it();new=daily.read(self.args['out'])['history']
        self.assertEqual(new[:-3],old)
        self.assertEqual([s['observation_kind'] for s in new[-3:]],['recovered_eod','recovered_eod','observed_eod'])

    def test_missing_fixed_member_degrades_and_never_drops_denominator(self):
        self.run_it();(self.cache/'A.json').unlink()
        self.args['as_of']=self.days[-1];i=daily.read(self.index);i['as_of']=self.days[-1];self.index.write_text(json.dumps(i))
        self.run_it();last=daily.read(self.args['out'])['history'][-1]
        self.assertEqual(last['quality']['universe_size'],4);self.assertEqual(last['quality']['missing_ticker_count'],1)
        self.assertIsNone(last['temperature']['score']);self.assertEqual(last['temperature']['status']['tone'],'neutral')
    def test_hash_mismatch_and_missing_rsp(self):
        (self.etf/'RSP.json').unlink();self.run_it()
        self.assertIsNone(daily.read(self.args['out'])['history'][-1]['temperature']['score'])
        with (self.cache/'A.json').open('a') as f:f.write(' ')
        self.args['state_dir']=self.root/'fresh'
        with self.assertRaisesRegex(ValueError,'hash_mismatch'):self.run_it()
    def test_rsp_status_uses_configurable_five_day_bands(self):
        c=daily.read(self.config)
        c['indicators']['rsp_spy']['levels']=[{'maximum':1000000,'label':'configured-band','tone':'yellow'}]
        self.config.write_text(json.dumps(c));self.run_it()
        item=daily.read(self.args['out'])['history'][-1]['indicators']['rsp_spy']
        self.assertEqual(item['level'],{'label':'configured-band','tone':'yellow'})
        self.assertIsNotNone(item['change_5d'])

    def test_forged_quality_cannot_publish_score(self):
        self.run_it();p=daily.read(self.args['out']);p['history'][-1]['quality']['coverage']=0.1
        last=p['history'][-1];last['fingerprint']=canonical_fingerprint({k:v for k,v in last.items() if k!='fingerprint'})
        p['content_fingerprint']=canonical_fingerprint({k:v for k,v in p.items() if k!='content_fingerprint'})
        with self.assertRaisesRegex(ValueError,'incomplete_score'):daily.validate_public(p)

if __name__=='__main__':unittest.main()
