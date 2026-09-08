import copy
import json
from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services.scanner.industry_radar import refresh_display_context

ROOT = Path(__file__).resolve().parents[1]
AS_OF = '2026-09-04'


def raw_rows():
    end = date.fromisoformat(AS_OF)
    return [dict(date=(end-timedelta(days=299-i)).isoformat(), open=100+i/10,
                 high=102+i/10, low=99+i/10, close=101+i/10,
                 adjusted_close=101+i/10, volume=100000) for i in range(300)]


class IndustryDisplayContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'industry.json'
        self.original = json.loads((ROOT/'public/industry-radar.json').read_text())
        self.original.pop('display_context', None)
        self.path.write_text(json.dumps(self.original))

    def refresh(self, loader):
        return refresh_display_context(self.path, AS_OF, fetch_prices=loader)

    def test_all_registered_themes_are_visible_without_revising_legacy_inputs(self):
        calls = []
        def load(fund, **kwargs):
            calls.append((fund, kwargs))
            return raw_rows()
        result = self.refresh(load)
        report = json.loads(self.path.read_text())
        display = report.pop('display_context')
        self.assertEqual(report, self.original)
        self.assertEqual(len(calls), 21)
        self.assertEqual(display['coverage']['themes'], 26)
        self.assertEqual(display['coverage']['available_etfs'], 21)
        self.assertEqual(sum(t['manual'] for t in display['themes']), 5)
        self.assertTrue(all(not t['members'] and t['reference_etf'] is None for t in display['themes'] if t['manual']))
        igv = next(t for t in display['themes'] if t['reference_etf']=='IGV')
        self.assertEqual(igv['members'], [])
        self.assertIsNone(igv['membership_as_of'])
        self.assertTrue(result['changed'])
        self.assertTrue(all(k == {'start':'2025-07-31','end':AS_OF} for _,k in calls))
        before = self.path.read_bytes()
        self.assertFalse(self.refresh(lambda *a, **k: self.fail('same-day successful ETF refetched'))['changed'])
        self.assertEqual(before, self.path.read_bytes())

    def test_failed_fund_retries_alone_and_does_not_erase_mapping(self):
        def fail_one(fund, **kwargs):
            if fund == 'SOXX': raise RuntimeError('secret-token-should-not-leak')
            return raw_rows()
        self.refresh(fail_one)
        payload=json.loads(self.path.read_text())['display_context']
        self.assertEqual(payload['coverage']['available_etfs'],20)
        self.assertFalse(payload['funds']['SOXX']['available'])
        self.assertIn('semiconductors',payload['ticker_themes']['NVDA'])
        self.assertNotIn('secret-token',self.path.read_text())
        calls=[]
        self.refresh(lambda fund, **kw: calls.append(fund) or raw_rows())
        self.assertEqual(calls,['SOXX'])

    def test_old_future_and_invalid_prices_fail_closed(self):
        for kind in ('old','future','invalid'):
            with self.subTest(kind=kind):
                self.path.write_text(json.dumps(self.original))
                rows=raw_rows()
                if kind=='old':rows=rows[:-1]
                if kind=='future':rows[-1]['date']='2026-09-05'
                if kind=='invalid':rows[-1]['high']=1
                self.refresh(lambda *a, **kw: copy.deepcopy(rows))
                display=json.loads(self.path.read_text())['display_context']
                self.assertEqual(display['coverage']['available_etfs'],0)
                self.assertEqual(len(display['themes']),26)

    def test_missing_membership_and_taxonomy_never_invent_relationships(self):
        with patch('services.scanner.industry_radar.select_snapshot',return_value=None), patch('services.scanner.industry_radar.select_finance_database_snapshot',return_value=None):
            self.refresh(lambda *a, **kw: raw_rows())
        display=json.loads(self.path.read_text())['display_context']
        self.assertEqual(display['ticker_themes'],{})
        self.assertEqual(display['classifications'],{})
        self.assertEqual(display['coverage']['dated_membership_themes'],0)
        self.assertEqual(display['coverage']['available_etfs'],21)

    def test_next_day_rebuilds_facts_without_changing_frozen_legacy_payload(self):
        self.refresh(lambda *a, **kw: raw_rows())
        original=json.loads(self.path.read_text())
        original['as_of']='2026-09-08'
        self.path.write_text(json.dumps(original))
        calls=[]
        refresh_display_context(self.path,'2026-09-08',fetch_prices=lambda f, **kw: calls.append(f) or raw_rows())
        result=json.loads(self.path.read_text())
        self.assertEqual(len(calls),21)
        self.assertEqual(result['display_context']['coverage']['available_etfs'],0)
        self.assertEqual(result['themes'],self.original['themes'])

    def test_bundle_mismatch_stops_before_supplier_request(self):
        before=self.path.read_bytes()
        with self.assertRaisesRegex(ValueError,'date_mismatch'):
            refresh_display_context(self.path,'2026-09-08',fetch_prices=lambda *a, **k: self.fail('request'))
        self.assertEqual(before,self.path.read_bytes())


class DailyBackgroundOrderTests(unittest.TestCase):
    def setUp(self):
        import os
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        previous=os.getcwd();os.chdir(self.tmp.name)
        self.addCleanup(os.chdir,previous)

    def market(self,path,as_of,**kwargs):
        self.calls.append('market')
        result={'as_of':as_of,'funds':[]}
        Path(path).write_text(json.dumps(result))
        return result

    def etf(self,*args,**kwargs):
        self.calls.append('industry_etf')
        return raw_rows()

    def test_actual_preflight_runs_before_stock_scan_and_same_day_reuses(self):
        from services.scanner import daily_tracker_update as daily
        self.calls=[]
        def first_stock(*args,**kwargs):
            self.calls.append('stock')
            raise RuntimeError('stop_at_stock_boundary')
        with patch.object(daily,'read_json',side_effect=lambda p: json.loads(Path(p).read_text()) if Path(p).exists() else {}), patch.object(daily,'run_market_context',side_effect=self.market), patch('services.scanner.eodhd.prices',side_effect=self.etf), patch.object(daily,'expand_universe',side_effect=first_stock):
            with self.assertRaisesRegex(RuntimeError,'stock_boundary'):daily.run(as_of=AS_OF)
            self.assertEqual(self.calls,['market']+['industry_etf']*21+['stock'])
            self.calls=[]
            with self.assertRaisesRegex(RuntimeError,'stock_boundary'):daily.run(as_of=AS_OF)
            self.assertEqual(self.calls,['stock'])

    def test_same_day_background_publication_does_not_rerun_stocks(self):
        from services.scanner import daily_tracker_update as daily
        public=Path('public');public.mkdir()
        names=('resonance-tracker.json','favorite-pattern.json','signal-history-summary.json','rare-opportunity-radar.json','daily-factor-snapshot.json','industry-radar.json','market-etf-watch.json','signal-history.json')
        for name in names:
            payload={'as_of':AS_OF,'pattern_version':daily.PATTERN_VERSION,'generalization_version':daily.GENERALIZATION_VERSION,
                     'registry_version':daily.REGISTRY_VERSION,'snapshot_mode_version':daily.SNAPSHOT_MODE_VERSION,
                     'signal_schema_version':daily.SIGNAL_HISTORY_SCHEMA_VERSION,
                     'favorite_pattern_tracker':{'pattern_version':daily.PATTERN_VERSION,'generalization_version':daily.GENERALIZATION_VERSION}}
            (public/name).write_text(json.dumps(payload))
        before={name:(public/name).read_bytes() for name in names}
        with patch.object(daily,'prepare_background',return_value=({'as_of':AS_OF}, {'as_of':AS_OF})), patch.object(daily,'expand_universe') as scan:
            result=daily.run(as_of=AS_OF)
            self.assertTrue(result['background_changed'])
            self.assertEqual(result['result'],'already_current')
            scan.assert_not_called()
            self.assertFalse(daily.run(as_of=AS_OF)['background_changed'])
        for name in names:
            if name!='industry-radar.json':self.assertEqual(before[name],(public/name).read_bytes())

    def test_market_failure_stops_before_stocks_or_industry(self):
        from services.scanner import daily_tracker_update as daily
        with patch.object(daily,'read_json',return_value={}), patch.object(daily,'run_market_context',side_effect=RuntimeError('market unavailable')), patch.object(daily,'expand_universe') as scan, patch.object(daily,'refresh_display_context') as industry:
            with self.assertRaisesRegex(RuntimeError,'market unavailable'):daily.run(as_of=AS_OF)
            scan.assert_not_called();industry.assert_not_called()

    def test_market_cache_is_staged_until_original_post_stock_boundary(self):
        from services.scanner.market_etf_watch import refreshed_rows
        from services.scanner.daily_tracker_update import publish_market_cache
        target=Path('work/eodhd-cache');target.mkdir(parents=True)
        old=raw_rows()[:-1];original=json.dumps(old);(target/'SPY.json').write_text(original)
        staged=Path('work/daily-background')/AS_OF/'market-cache'
        with patch('services.scanner.market_etf_watch.prices',return_value=raw_rows()):
            refreshed_rows('SPY',persist=False,staged_cache_dir=staged)
        self.assertEqual((target/'SPY.json').read_text(),original)
        publish_market_cache(AS_OF)
        self.assertEqual(json.loads((target/'SPY.json').read_text())[-1]['date'],AS_OF)

if __name__ == '__main__': unittest.main()
