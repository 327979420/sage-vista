import copy
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from services.contracts.market_data import canonical_fingerprint
from services.ledger.cr056 import review_watch
from services.scanner.cr056_runner import run_snapshot, save_report
from tests.test_cr056_strategy import facts, states


class WatchTests(unittest.TestCase):
    def test_restore_cooldown_and_same_day_idempotence(self):
        dates = ['2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04', '2026-09-08', '2026-09-09']
        origin = {'date': dates[0]}
        good = {'total_score': 80, 'permission': 'allowed', 'high_score_eligible': True,
                'score_fingerprint': 'one', 'reason_codes': []}
        def run(i, score, previous):
            return review_watch(symbol='AAA', as_of=dates[i], origin=origin, score=score,
                                previous=previous, reference_sessions=dates[:i+1])
        first = run(0, good, None)
        self.assertTrue(first['alert_due'])
        self.assertEqual(first, run(0, good, first))
        with self.assertRaisesRegex(ValueError, 'same-day'):
            run(0, dict(good, total_score=79), first)
        blocked = run(1, dict(good, total_score=None, permission='blocked', high_score_eligible=False), first)
        restored = run(2, good, blocked)
        self.assertTrue(restored['restored']); self.assertFalse(restored['alert_due'])
        self.assertEqual(restored['watch_id'], first['watch_id'])
        self.assertEqual(restored['consecutive_high_sessions'], 1)
        current = run(3, good, restored)
        current = run(4, good, current)
        current = run(5, good, current)
        self.assertTrue(current['alert_due'])
        self.assertEqual(current['consecutive_high_sessions'], 4)
        with self.assertRaisesRegex(ValueError, 'frozen'):
            review_watch(symbol='AAA', as_of=dates[-1], origin={'date': dates[1]}, score=good,
                         previous=current, reference_sessions=dates)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        bars = []
        day = date(2018, 1, 1)
        while day <= date(2026, 9, 4):
            if day.weekday() < 5:
                c = 60 + len(bars)*.01 + 5*math.sin(len(bars)/30)
                bars.append(dict(date=day.isoformat(), open=c, high=c+1, low=c-1,
                                 close=c, adjusted_close=c, volume=10_000_000))
            day += timedelta(days=1)
        payload = json.dumps(bars).encode()
        self.report = dict(as_of='2026-09-04', result_role='legacy_comparison_input_repair',
                           repaired=[], excluded={'BAD': 'adjustment_anchor_missing'},
                           repaired_count=3, excluded_count=1)
        for symbol in ('AAA', 'NEW', 'SPY'):
            (self.root/f'{symbol}.json').write_bytes(payload)
            self.report['repaired'].append(dict(symbol=symbol, source_sha256='original',
                                                repaired_sha256=hashlib.sha256(payload).hexdigest()))
        self.history = {'days': [{'date': '2026-08-28', 'ranking': [{'symbol': 'AAA', 'score': 7}]}]}

    def run_report(self, **kw):
        return run_snapshot(self.root, as_of='2026-09-04', history=self.history,
                            code_commit='test', input_report=self.report, **kw)

    def test_real_producers_run_on_long_synthetic_history(self):
        result = self.run_report()
        by = {r['symbol']: r for r in result['reviews']}
        self.assertIn('permission', by['AAA'])
        self.assertIn('score', by['AAA'])
        self.assertEqual(by['AAA']['periods'], {'monthly': '2026-08-31', 'weekly': '2026-09-04'})
        self.assertEqual(by['BAD']['reason_codes'], ['adjustment_anchor_missing'])
        self.assertIsNotNone(by['AAA']['watch'])
        self.assertEqual(sum(result['counts'].values()), 4)
        saved = save_report(result, self.root/'results')
        self.assertEqual(saved, save_report(result, self.root/'results'))
        self.assertEqual(json.loads(saved.read_text()), result)

    def test_old_watch_runs_without_new_cross_and_new_nomination_uses_same_score(self):
        f = facts()
        f['monthly']['completed_through'] = '2026-08-31'
        f['weekly']['completed_through'] = '2026-09-04'
        objects = states()
        with patch('services.scanner.cr056_runner.exact_daily_macd_bull_cross', side_effect=[False, True, False]), \
             patch('services.scanner.cr056_runner.assess_entry', side_effect=[{'eligible':v,'paths':[],'reason_codes':[]} for v in (False,True,False)]), \
             patch('services.scanner.cr056_runner.collect_direction_facts', return_value=f), \
             patch('services.scanner.cr056_runner.evaluate_period_factors', return_value=objects):
            result = self.run_report()
        self.assertEqual(result['continuing_ranked_symbols'], ['AAA'])
        self.assertEqual(result['new_nomination_symbols'], ['NEW'])
        self.assertEqual(self.history['days'][0]['ranking'][0]['score'], 7)
        by = {r['symbol']: r for r in result['reviews']}
        self.assertEqual(by['AAA']['score']['total_score'], by['NEW']['score']['total_score'])
        self.assertFalse(by['AAA']['exact_daily_cross_today'])

    def test_corrupt_stock_excluded_and_corrupt_reference_aborts(self):
        (self.root/'AAA.json').write_text('[]')
        result = self.run_report()
        aaa = next(r for r in result['reviews'] if r['symbol'] == 'AAA')
        self.assertEqual(aaa['reason_codes'], ['repaired_source_hash_mismatch'])
        self.assertEqual(aaa['watch']['state'], 'data_unavailable')
        self.assertNotIn('AAA', result['ranked_symbols'])
        (self.root/'SPY.json').write_text('[]')
        with self.assertRaisesRegex(ValueError, 'reference input hash'):
            self.run_report()
