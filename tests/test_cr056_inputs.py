import copy
import json
import tempfile
import unittest
from pathlib import Path
from services.scanner.cr056_inputs import merge_recent_history, repair_existing_cache, normalized_comparison_rows, reseed_excluded


def bar(day, adjustment=10):
    return {'date': day, 'open': 10, 'high': 11, 'low': 9, 'close': 10, 'adjusted_close': adjustment, 'volume': 100}

class InputRepairTests(unittest.TestCase):
    def test_merge_requires_every_observed_session_and_preserves_input(self):
        raw = [bar('2026-08-28')]; before = copy.deepcopy(raw)
        added = {d: bar(d) for d in ('2026-08-28', '2026-08-31', '2026-09-01', '2026-09-04')}
        result = merge_recent_history(raw, added, as_of='2026-09-04', expected_sessions=list(added))
        self.assertEqual(raw, before)
        self.assertEqual(result[-1]['date'], '2026-09-04')
        with self.assertRaisesRegex(ValueError, 'session_missing'):
            merge_recent_history(raw, added, as_of='2026-09-04', expected_sessions=[*added, '2026-09-03'])

    def test_split_ratio_revision_cannot_silently_mix_history(self):
        with self.assertRaisesRegex(ValueError, 'adjustment_changed'):
            merge_recent_history([bar('2026-08-28')], {'2026-08-28': bar('2026-08-28', 5)},
                                 as_of='2026-09-04', expected_sessions=[])

    def test_old_tail_never_revived(self):
        with self.assertRaisesRegex(ValueError, 'not_automatically_revived'):
            merge_recent_history([bar('2020-08-28')], {'2026-09-04': bar('2026-09-04')},
                                 as_of='2026-09-04', expected_sessions=[])

    def test_missing_cache_never_calls_supplier(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'no_existing_cache'):
                repair_existing_cache(Path(tmp)/'absent', Path(tmp)/'private', as_of='2026-09-04',
                    fetch_bulk=lambda d: self.fail('supplier must not be called'))

    def test_missing_same_day_anchor_rejects_even_when_all_new_sessions_present(self):
        days = ['2026-08-31', '2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04']
        with self.assertRaisesRegex(ValueError, 'adjustment_anchor_missing'):
            merge_recent_history([bar('2026-08-28')], {d: bar(d) for d in days},
                                 as_of=days[-1], expected_sessions=days)

    def test_reseed_is_bounded_busiest_first_and_failures_keep_their_reason(self):
        days = ['2026-09-01', '2026-09-02', '2026-09-03', '2026-09-04']
        fresh = [bar(d) for d in days]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            report = {'repaired': [], 'excluded': {'A': 'historical_adjustment_changed', 'B': 'recent_session_missing',
                                                   'C': 'ambiguous_bulk_symbol', 'D': 'historical_adjustment_changed',
                                                   'E': 'recent_session_missing'}}
            calls = []
            def fetch(symbol):
                calls.append(symbol)
                return fresh[:-1] if symbol == 'A' else fresh + [bar('2026-09-08')]  # A stops a day early; later rows are cut
            reseed_excluded(report, out, as_of='2026-09-04', fetch_history=fetch, budget=2,
                            traded_value={'A': 5.0, 'B': 9.0, 'C': 100.0, 'D': 1.0})  # E did not trade today
            self.assertEqual(calls, ['B', 'A'])  # busiest first, within the budget; C's reason is not curable
            self.assertEqual(report['reseed']['restored'], ['B'])
            self.assertEqual(report['reseed']['failed'], {'A': 'reseed_not_current'})
            self.assertNotIn('B', report['excluded'])
            self.assertEqual(report['excluded']['A'], 'historical_adjustment_changed')  # tried again next run
            self.assertEqual(json.loads((out/'B.json').read_text())[-1]['date'], '2026-09-04')  # nothing after as_of
            self.assertEqual((report['repaired'][0]['source'], report['repaired_count'], report['excluded_count']), ('full_history_reseed', 1, 4))

    def test_private_repair_reports_anchor_failure_and_keeps_original_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)/'original'; cache.mkdir()
            raw = json.dumps([bar('2026-08-28')]).encode()
            for symbol in ('SPY', 'AAA'): (cache/f'{symbol}.json').write_bytes(raw)
            calls = []
            def fetch(day):
                calls.append(day)
                rows = [dict(bar(day), code='SPY')]
                if day != '2026-08-28': rows.append(dict(bar(day), code='AAA'))
                return rows
            report = repair_existing_cache(cache, Path(tmp)/'private', as_of='2026-09-04', fetch_bulk=fetch)
            self.assertEqual(len(calls), 6)
            self.assertEqual(report['excluded']['AAA'], 'adjustment_anchor_missing')
            self.assertEqual(report['repaired_count'], 1)
            self.assertEqual((cache/'AAA.json').read_bytes(), raw)
            self.assertEqual((cache/'SPY.json').read_bytes(), raw)
            with self.assertRaisesRegex(ValueError, 'separate_from_original'):
                repair_existing_cache(cache, cache.parent, as_of='2026-09-04',
                                      fetch_bulk=lambda d: self.fail('must reject before supplier'))

    def test_adjustment_preserves_equal_prices_without_tolerance(self):
        raw = dict(date='2026-09-04', open=1.03, high=1.03, low=1.02,
                   close=1.03, adjusted_close=.45, volume=100)
        result = normalized_comparison_rows([raw], as_of=raw['date'])[0]
        self.assertEqual(result['high'], .45)
        self.assertEqual(result['open'], .45)
        # A genuine raw OHLC violation must fail before any equality repair.
        with self.assertRaisesRegex(ValueError, 'raw OHLC relationship'):
            normalized_comparison_rows([dict(raw, high=1.02)], as_of=raw['date'])
        with self.assertRaisesRegex(ValueError, 'future_rows'):
            normalized_comparison_rows([raw], as_of='2026-09-03')
