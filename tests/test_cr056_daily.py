import copy
import gzip
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from services.ledger.cr056 import watch_checkpoint, validate_watch_checkpoint
from services.scanner.cr056_daily import refresh, encoded
from services.scanner.cr056_public import project_report
from services.scanner.cr056_runner import run_snapshot
import tests.test_cr056_runner as runner_tests
from tests.test_cr056_strategy import facts, states


class DailyCandidateTests(unittest.TestCase):
    def setUp(self):
        fixture=runner_tests.RunnerTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.fixture=fixture;self.root=fixture.root
        self.base=self.root/'base';self.base.mkdir()
        for path in self.root.glob('*.json'):path.rename(self.base/path.name)
        fixture.root=self.base
        self.public=self.root/'public.json';self.state=self.root/'state.json.gz'
        with self.producers('2026-09-04',False):seed=fixture.run_report()
        self.public.write_bytes(encoded(project_report(seed)))
        self.state.write_bytes(gzip.compress(encoded(watch_checkpoint(seed)),mtime=0))
        self.seed_origin=seed['reviews'][0]['origin']
        self.calls=[]

    def producers(self, day, trigger, blocked=False):
        from contextlib import ExitStack
        stack=ExitStack()
        f=facts();f['as_of']=day
        f['monthly']['completed_through']='2026-08-31';f['weekly']['completed_through']='2026-09-04'
        if blocked:f['monthly']['histogram']=[1,2,1]
        def factor_rows(*args,**kwargs):
            return [SimpleNamespace(dict=lambda x=x: x) for x in [dict(s,as_of=day) for s in states()]]
        stack.enter_context(patch('services.scanner.cr056_runner.collect_direction_facts',return_value=f))
        stack.enter_context(patch('services.scanner.cr056_runner.evaluate_all_factors',side_effect=factor_rows))
        stack.enter_context(patch('services.scanner.cr056_runner.exact_daily_macd_bull_cross',return_value=trigger))
        return stack

    def bulk(self, day, directory):
        self.assertNotEqual(day,'2026-09-07','holiday must not be requested as a session')
        self.calls.append(day)
        return [dict(json.loads(p.read_text())[-1],date=day,code=p.stem) for p in self.base.glob('*.json')]

    def reference(self, start, end):
        from datetime import date
        self.assertLessEqual((date.fromisoformat(end)-date.fromisoformat(start)).days,19)
        spy=json.loads((self.base/'SPY.json').read_text())[-1]
        return [dict(spy,date=d) for d in ['2026-09-04','2026-09-08','2026-09-09','2026-09-10'] if start<=d<=end]

    def run_daily(self, day, **overrides):
        return refresh(as_of=day,code_commit='reviewed',public_path=self.public,state_path=self.state,
            archive_dir=self.root/'archive',work_dir=self.root/'work',base_cache=self.base,
            fetch_reference=overrides.get('fetch_reference',self.reference),fetch_bulk=self.bulk)

    def checkpoint(self):return validate_watch_checkpoint(json.loads(gzip.decompress(self.state.read_bytes())))

    def test_same_day_needs_no_source_and_does_not_recreate_watches(self):
        before=self.state.read_bytes()
        result=self.run_daily('2026-09-04',fetch_reference=lambda *a:self.fail('no request'))
        self.assertEqual(result['result'],'already_current');self.assertTrue(result['changed'])
        self.assertEqual(before,self.state.read_bytes());self.assertEqual(self.calls,[])
        self.assertFalse(self.run_daily('2026-09-04')['changed'])

    def test_holiday_gap_old_watch_and_new_nomination_then_disqualification_and_restore(self):
        originals={p.name:p.read_bytes() for p in self.base.glob('*.json')}
        with self.producers('2026-09-08',True):result=self.run_daily('2026-09-08')
        self.assertEqual(result['result'],'updated',result)
        self.assertEqual(self.calls,['2026-09-04','2026-09-08'])
        public=json.loads(self.public.read_text());self.assertIn('AAA',public['continuing_ranked_symbols'])
        self.assertIn('NEW',public['new_nomination_symbols'])
        original=self.checkpoint()['reviews'][0]['watch']['origin']
        self.assertEqual(original,self.seed_origin)
        first_archive={p.name:p.read_bytes() for p in (self.root/'archive').glob('*')}
        with self.producers('2026-09-09',False,blocked=True):result=self.run_daily('2026-09-09')
        self.assertEqual(result['result'],'updated',result)
        self.assertEqual(json.loads(self.public.read_text())['ranked_symbols'],[])
        with self.producers('2026-09-10',False):result=self.run_daily('2026-09-10')
        self.assertEqual(result['result'],'updated',result)
        public=json.loads(self.public.read_text());self.assertEqual(public['new_nomination_symbols'],[])
        self.assertIn('NEW',public['continuing_ranked_symbols'])
        for r in self.checkpoint()['reviews']:
            self.assertTrue(r['watch']['restored']);self.assertFalse(r['watch']['alert_due'])
        self.assertEqual(original,self.checkpoint()['reviews'][0]['watch']['origin'])
        for name,content in first_archive.items():self.assertEqual((self.root/'archive'/name).read_bytes(),content)
        for name,content in originals.items():self.assertEqual((self.base/name).read_bytes(),content)

    def test_provider_failure_keeps_date_scores_and_checkpoint_and_retry_succeeds(self):
        before=json.loads(self.public.read_text());state=self.state.read_bytes()
        def unavailable(*a):raise RuntimeError('provider not ready')
        result=self.run_daily('2026-09-08',fetch_reference=unavailable)
        self.assertEqual(result['result'],'retained_previous')
        self.assertEqual(state,self.state.read_bytes())
        after=json.loads(self.public.read_text())
        self.assertEqual(after['as_of'],before['as_of']);self.assertEqual(after['reviews'],before['reviews'])
        self.assertEqual(after['refresh_status']['status'],'failed')
        self.assertFalse(self.run_daily('2026-09-08',fetch_reference=unavailable)['changed'])
        with self.producers('2026-09-08',False):result=self.run_daily('2026-09-08')
        self.assertEqual(result['result'],'updated',result)

    def test_missing_or_corrupt_checkpoint_never_reimports_legacy_history(self):
        self.state.write_bytes(gzip.compress(b'{}'))
        result=self.run_daily('2026-09-08',fetch_reference=lambda *a:self.fail('no request'))
        self.assertEqual(result['result'],'retained_previous')
        self.assertEqual(result['reason'],'watch_checkpoint_content_mismatch')
        self.assertEqual(self.calls,[])

    def test_old_legacy_new_rankings_do_not_silently_enter_previous_watch_pool(self):
        previous=self.checkpoint();history=copy.deepcopy(self.fixture.history)
        history['days'].append({'date':'2026-09-04','ranking':[{'symbol':'NEW'}]})
        with self.producers('2026-09-04',False):
            result=run_snapshot(self.base,as_of='2026-09-04',history=history,code_commit='test',
                                input_report=self.fixture.report,previous=previous)
        new=next(r for r in result['reviews'] if r['symbol']=='NEW')
        self.assertIsNone(new['watch']);self.assertEqual(new['status'],'not_nominated')

    def test_cache_eviction_preserves_frozen_identity_and_cooldown(self):
        import shutil
        with self.producers('2026-09-08',True):self.run_daily('2026-09-08')
        before=self.checkpoint();shutil.rmtree(self.root/'work'/'cache')
        with self.producers('2026-09-09',False):result=self.run_daily('2026-09-09')
        self.assertEqual(result['result'],'updated',result)
        after=self.checkpoint()
        for a,b in zip(before['reviews'],after['reviews']):
            for key in ('watch_id','origin','last_alert_as_of'):self.assertEqual(a['watch'][key],b['watch'][key])
            self.assertFalse(b['watch']['alert_due'])

    def test_corrupt_cache_and_incomplete_reference_cannot_advance_state(self):
        with self.producers('2026-09-08',False):self.run_daily('2026-09-08')
        state=self.state.read_bytes()
        (self.root/'work'/'cache'/'eodhd-cache'/'AAA.json').write_text('[]')
        result=self.run_daily('2026-09-09')
        self.assertEqual(result['reason'],'private_cache_hash_mismatch')
        self.assertEqual(state,self.state.read_bytes())
        result=self.run_daily('2026-09-09',fetch_reference=lambda start,end:self.reference(start,'2026-09-08'))
        self.assertEqual(result['reason'],'reference_latest_session_missing')
        self.assertEqual(state,self.state.read_bytes())
        result=self.run_daily('2026-10-01',fetch_reference=lambda *a:self.fail('long history download forbidden'))
        self.assertEqual(result['reason'],'refresh_gap_exceeds_bounded_recovery')

    def test_committed_checkpoint_matches_reviewed_view_and_has_no_raw_bars(self):
        root=Path(__file__).resolve().parents[1]
        checkpoint=validate_watch_checkpoint(json.loads(gzip.decompress((root/'automation/cr056-watch-state.json.gz').read_bytes())))
        public=json.loads((root/'public/cr056-ranking.json').read_text())
        self.assertEqual(checkpoint['as_of'],public['as_of'])
        self.assertEqual(checkpoint['snapshot_fingerprint'],public['source_snapshot'])
        def check(value):
            if isinstance(value,dict):
                self.assertFalse({'open','high','low','close','volume'}<=value.keys())
                for v in value.values():check(v)
            elif isinstance(value,list):
                for v in value:check(v)
        check(checkpoint)

    def test_partial_local_write_is_rolled_back_before_failure_view(self):
        from services.scanner.cr056_daily import replace_bytes
        before=self.state.read_bytes();failed=False
        def write(path,content):
            nonlocal failed
            if path==self.public and not failed:
                failed=True;raise OSError('write interrupted')
            replace_bytes(path,content)
        with self.producers('2026-09-08',False),patch('services.scanner.cr056_daily.replace_bytes',side_effect=write):
            result=self.run_daily('2026-09-08')
        self.assertEqual(result['result'],'retained_previous')
        self.assertEqual(before,self.state.read_bytes())
        self.assertEqual(json.loads(self.public.read_text())['as_of'],'2026-09-04')

    def test_cache_loss_cannot_bypass_adjustment_anchor_checks(self):
        import shutil
        with self.producers('2026-09-08',False):self.run_daily('2026-09-08')
        before=self.checkpoint()['reviews'][0]['watch']
        shutil.rmtree(self.root/'work'/'cache')
        original_bulk=self.bulk
        def revised(day,directory):
            rows=original_bulk(day,directory)
            if day=='2026-09-04':
                for row in rows:
                    if row['code']=='AAA':row['adjusted_close']/=2
            return rows
        self.bulk=revised
        with self.producers('2026-09-09',False):result=self.run_daily('2026-09-09')
        self.assertEqual(result['result'],'updated',result)
        aaa=next(r for r in json.loads(self.public.read_text())['reviews'] if r['symbol']=='AAA')
        self.assertIn('historical_adjustment_changed',aaa['reason_codes']);self.assertIsNone(aaa['rank'])
        after=self.checkpoint()['reviews'][0]['watch']
        self.assertEqual(before['watch_id'],after['watch_id']);self.assertEqual(before['origin'],after['origin'])
        self.assertEqual(before['last_alert_as_of'],after['last_alert_as_of'])
