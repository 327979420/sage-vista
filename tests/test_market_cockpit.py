import copy
from datetime import date, datetime, timedelta
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from services.scanner import market_cockpit as m

ROOT=Path(__file__).resolve().parents[1]
from tests.public_fixture import changed, local_public, reseal

DAY='2026-09-18'
FROZEN=ROOT/'tests/fixtures/market-2026-09-18/market-cockpit.json.gz'

def frozen_payload():return json.loads(gzip.decompress(FROZEN.read_bytes()))


def options(day=DAY,customer=60):
    day=date.fromisoformat(day).strftime('%m-%d-%Y')
    return (f'From {day} To {day}\nGroup\tSymbol\tEx.\tCustomer\tFirm\tCustomer/Firm Totals\tMkt Maker\tTotal\n'
            f'A\tA\tC\t{customer}\t10\t{customer+10}\t30\t{customer+40}\n'
            f'Symbol\tTotal\t\t{customer}\t10\t{customer+10}\t30\t{customer+40}\n'
            f'Group\tTotal\t\t{customer}\t10\t{customer+10}\t30\t{customer+40}\n').encode()


def source():return {'provider':'OCC','url':m.OCC,'fetched_at':'2026-09-21T00:00:00+00:00','sha256':'a'*64}


class CockpitTests(unittest.TestCase):
    def test_finra_selects_debit_column_units_and_month_end(self):
        html=b"millions<table><tr><th>Month</th><th>Free Credit</th><th>Debit Balances in Customers' Securities Margin Accounts</th></tr><tr><td>Jul-26</td><td>999</td><td>1,000,000</td></tr><tr><td>Aug-26</td><td>999</td><td>1,100,000</td></tr><tr><td>Sep-26</td><td>999</td><td>1,500,000</td></tr></table>"
        p=m.parse_margin(html,DAY)
        self.assertEqual(p['value'],1100);self.assertEqual(p['observation_date'],'2026-08-31');self.assertAlmostEqual(p['change_pct'],10)
        with self.assertRaises(ValueError):m.parse_margin(html.replace(b'millions',b'thousands'),DAY)
        gap=m.parse_margin(html.replace(b'Jul-26',b'Jun-26'),DAY);self.assertIsNone(gap['change_pct'])

    def test_flows_only_domestic_and_contiguous_weeks(self):
        html=b'Combined Estimated Millions of dollars<table><tr><th></th><th>9/9/2026</th><th>9/2/2026</th><th>8/26/2026</th><th>8/19/2026</th></tr><tr><td>Equity</td><td>999</td><td>999</td><td>999</td><td>999</td></tr><tr><td>Domestic</td><td>-1000</td><td>2000</td><td>-3000</td><td>4000</td></tr></table>'
        p=m.parse_flows(html,DAY);self.assertEqual(p['value'],-1);self.assertEqual(p['sum_4w'],2)
        self.assertIsNone(m.parse_flows(html.replace(b'8/19/2026',b'8/12/2026'),DAY)['sum_4w'])
        with self.assertRaises(ValueError):m.parse_flows(html.replace(b'Domestic',b'World'),DAY)

    def test_cftc_net_over_oi_and_previous_only_percentile(self):
        raw=[]
        for code in m.CODES:
            for i in range(54):
                raw.append({'cftc_contract_market_code':code,'report_date_as_yyyy_mm_dd':(date(2025,9,9)+timedelta(weeks=i)).isoformat(),'open_interest_all':1000,'asset_mgr_positions_long':300+i,'asset_mgr_positions_short':100,'lev_money_positions_long':100,'lev_money_positions_short':300-i})
        p=m.parse_positions(json.dumps(raw).encode(),DAY);c=p['contracts'][0]
        self.assertEqual(c['percentiles']['leveraged'],100);self.assertEqual(c['percentile_weeks'],53)
        self.assertAlmostEqual(c['history'][-1]['leveraged'],-14.7)
        with self.assertRaises(ValueError):m.parse_positions(json.dumps(raw+[raw[-1]]).encode(),DAY)
        short=m.parse_positions(json.dumps([r for r in raw if r['report_date_as_yyyy_mm_dd']>'2026-08-01']).encode(),DAY)
        self.assertIsNone(short['contracts'][0]['percentiles']['asset'])

    def test_occ_excludes_subtotals_and_checks_complete_download(self):
        p=m.parse_options(options(),DAY);self.assertEqual(p['value'],60);self.assertEqual(p['history'][0]['total'],100)
        with self.assertRaises(ValueError):m.parse_options(options().split(b'Group\tTotal')[0],DAY)
        with self.assertRaises(ValueError):m.parse_options(options().replace(b'60\t10\t70',b'60\t10\t71'),DAY)
        with self.assertRaises(ValueError):m.parse_options(options(), '2026-09-17')

    def test_quote_sessions_must_match_benchmark(self):
        rows=[{'date':(date(2026,8,29)+timedelta(days=i)).isoformat(),'value':100+i} for i in range(21)]
        histories={s:copy.deepcopy(rows) for s in m.SYMBOLS}
        p=m.quote_metrics(histories,DAY);self.assertAlmostEqual(p['funds'][0]['returns']['20'],20)
        histories['XLK'].pop(3)
        with self.assertRaisesRegex(ValueError,'missing_session'):m.quote_metrics(histories,DAY)

    def test_actual_frozen_sources_roundtrip(self):
        payload=frozen_payload();m.validate(payload,DAY)
        for key,parser in [('margin',m.parse_margin),('positions',m.parse_positions),('options',m.parse_options)]:
            panel=payload['panels'][key];s=panel['sources'][-1]
            raw=gzip.decompress((ROOT/'data/market/cockpit-v1/raw'/f"{s['sha256']}.gz").read_bytes())
            self.assertEqual(m.hashlib.sha256(raw).hexdigest(),s['sha256'])
            parsed=parser(raw,DAY)
            self.assertEqual(parsed['observation_date'],panel['observation_date'])
            if 'value' in parsed:self.assertEqual(parsed['value'],panel['value'])

    def test_validator_rejects_future_mixed_quotes_and_false_shares(self):
        original=frozen_payload()
        for mutate in [lambda p:p['panels']['margin'].update(observation_date='2099-01-01'),lambda p:p['panels']['quotes']['sources'][0].update(provider='Other'),lambda p:p['panels']['options']['history'][-1].update(customer=1),lambda p:p['panels']['positions']['contracts'][0]['percentiles'].update(asset=999)]:
            p=copy.deepcopy(original);mutate(p);p['content_fingerprint']=m.canonical_fingerprint({k:v for k,v in p.items() if k!='content_fingerprint'})
            with self.assertRaises(ValueError):m.validate(p)

    def test_next_day_with_unavailable_options_remains_valid_but_old_target_is_rejected(self):
        payload=frozen_payload()
        target='2026-09-21'
        payload['as_of']=target
        payload['panels']['options']={'id':'options','frequency':'daily','status':'unavailable','sources':[], 'observation_date':None,'error_type':'OSError'}
        histories={f['ticker']:f['history']+[dict(f['history'][-1],date=target)] for f in payload['panels']['quotes']['funds']}
        payload['panels']['quotes'].update(m.quote_metrics(histories,target))
        payload['content_fingerprint']=m.canonical_fingerprint({k:v for k,v in payload.items() if k!='content_fingerprint'})
        m.validate(payload,target)
        from services.scanner.verify_live_deployment import verify_cockpit_asset
        with patch.object(Path,'read_bytes',return_value=json.dumps(payload).encode()),patch('services.scanner.verify_live_deployment.fetch',return_value=payload):
            self.assertEqual(verify_cockpit_asset('https://example.com',target,'abc')['as_of'],target)
        with self.assertRaisesRegex(ValueError,'cockpit_target_date'):m.validate(payload,DAY)
        broken=copy.deepcopy(payload);broken['panels']['options']['value']=0
        broken['content_fingerprint']=m.canonical_fingerprint({k:v for k,v in broken.items() if k!='content_fingerprint'})
        with self.assertRaisesRegex(ValueError,'unavailable_with_data'):m.validate(broken,target)

    def test_daily_reuse_failure_isolation_and_recovery_preserves_history(self):
        calls=[];fail=[False]
        def collect(key,as_of,now,state):
            calls.append(key)
            if key!='options' or fail[0]:raise OSError('simulated transport failure')
            return {'id':key,'frequency':'daily','status':'available','sources':[source()],**m.parse_options(options(as_of),as_of)}
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'public.json';state=Path(directory)/'state'
            m.run('2026-09-16',out=out,state=state,collector=collect)
            m.run('2026-09-16',out=out,state=state,collector=collect)
            self.assertEqual(len(calls),9)
            self.assertEqual(calls.count('options'),1)
            fail[0]=True;m.run('2026-09-17',out=out,state=state,collector=collect)
            self.assertEqual(json.loads(out.read_text())['panels']['options']['status'],'unavailable')
            fail[0]=False;m.run(DAY,out=out,state=state,collector=collect)
            p=json.loads(out.read_text());self.assertEqual([r['date'] for r in p['panels']['options']['history']],['2026-09-16',DAY])
            self.assertEqual(len(list(state.glob('*.json'))),3)
            self.assertEqual(p['panels']['margin']['status'],'unavailable')

    def test_public_response_size_is_bounded(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,n):return b'x'*n
        with patch.object(m,'urlopen',return_value=Response()),self.assertRaisesRegex(ValueError,'too_large'):m.fetch('https://example.com',10)

    def test_workflow_and_release_guard_use_cockpit_contract(self):
        workflow=(ROOT/'.github/workflows/daily-eod.yml').read_text()
        self.assertEqual(workflow.count('python3 -m services.scanner.market_cockpit --as-of'),2)
        self.assertIn("or cockpit['changed']",workflow)
        from services.scanner.verify_live_deployment import verify_cockpit_asset
        # Frozen reviewed payload; the live generated asset is checked by the release contract.
        payload=frozen_payload();target=payload['as_of']
        with local_public({'market-cockpit.json':payload}):
            with patch('services.scanner.verify_live_deployment.fetch',return_value=payload):self.assertEqual(verify_cockpit_asset('https://example.com',target,'abc')['as_of'],target)
            broken=reseal(changed(payload,lambda p:p.update(checked_at=(datetime.fromisoformat(payload['checked_at'])+timedelta(seconds=1)).isoformat())))
            with patch('services.scanner.verify_live_deployment.fetch',return_value=broken),self.assertRaisesRegex(RuntimeError,'differs'):verify_cockpit_asset('https://example.com',target,'abc')

if __name__=='__main__':unittest.main()
