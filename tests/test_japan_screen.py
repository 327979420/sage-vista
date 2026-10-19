"""Synthetic-only Step 1 checks: no provider, datasets or locked prices accessed."""
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from research.lab import screen, run_queue, datasets
from services.scanner import eodhd


def bars(days, close=200, volume=10_000_000):
    return [dict(date=d, open=close, high=close, low=close, close=close,
                 adjusted_close=close, volume=volume) for d in days]


def stock(code, name='Company', kind='Common Stock'):
    return dict(Code=code, Name=name, Type=kind, Exchange='TSE')


class JapanScreenTests(unittest.TestCase):
    def spec(self):
        spec = json.loads(pathlib.Path('research/lab/queue-parked/data-jp-universe-v1.json').read_text())
        spec.update(min_sessions=1, workers=1, shard_dir='u')
        spec['criteria'] = dict(max_error_share=.02, min_kept=1)
        return spec

    def run_screen(self, listed, histories, delisted=None):
        entry = dict(dataset_id='synthetic', asset='none', sha256='none', symbols=1)
        with tempfile.TemporaryDirectory() as root:
            result, stats, failed = screen.run(self.spec(), {'prices': {'1301': {}}}, entry,
                root, listed, delisted or [], fetch=lambda s: histories[s])
            kept = [s for f in result['shards'] for s in pathlib.Path(root, f['file']).read_text().split()]
        return result, stats, failed, kept

    def test_suffix_request_preserves_code_and_zeros(self):
        for code, expected in [('01301', '01301.TSE'), ('1301.TSE', '1301.TSE'),
                               ('1301-A', '1301-A.TSE'), ('1301-A.TSE', '1301-A.TSE'), (1301, '1301.TSE')]:
            with self.subTest(code=code), patch.object(eodhd, 'get', return_value=[]) as get:
                eodhd.prices(code, start='2004-01-01', end='2025-06-30', exchange='TSE')
                get.assert_called_once_with('eod/' + expected, **{'from': '2004-01-01', 'to': '2025-06-30', 'period': 'd'})

    def test_us_hk_request_defaults_unchanged(self):
        for code, exchange in [('BRK-B', 'US'), ('0700', 'HK'), ('0700.HK', 'HK')]:
            with patch.object(eodhd, 'get', return_value=[]) as get:
                eodhd.prices(code, exchange=exchange)
                self.assertEqual(get.call_args.args[0], f'eod/{code}.{exchange}')
        with patch.object(eodhd, 'get') as get:
            eodhd.symbols(True, 'TSE')
            get.assert_called_once_with('exchange-symbol-list/TSE', delisted=1)

    def test_company_key(self):
        for code in ['001301', '1301.TSE', '01301-A.TSE', '1301.TSE-A']:
            self.assertEqual(screen.company_key(code), '1301')
        self.assertEqual(screen.company_key('001A.TSE'), '1A')

    def test_all_name_terms_case_insensitive_and_overlaps_counted(self):
        listed = [stock(str(3000+i), 'prefix ' + term.lower() + ' suffix') for i, term in enumerate(screen.NAME_EXCLUSIONS)]
        listed += [stock('4000', 'ETF Fund'), stock('4001'), stock('4002', kind='ETF')]
        kept, counts, _ = screen.jp_candidates(listed, [])
        self.assertEqual(kept, ['4001'])
        self.assertEqual(counts['non_common_type'], 1)
        self.assertEqual(counts['excluded_name'], len(screen.NAME_EXCLUSIONS) + 1)
        self.assertEqual(counts['name_matches']['ETF'], 2)
        self.assertEqual(counts['name_matches']['FUND'], 2)
        self.assertEqual(counts['excluded_metadata_union'], len(screen.NAME_EXCLUSIONS) + 2)

    def test_trust_bank_is_kept(self):
        # Amendment 2026-10-19: "TRUST" is not an exclusion term, so trust banks stay.
        kept, counts, _ = screen.jp_candidates([stock('8309', 'Sumitomo Mitsui Trust Holdings Inc')], [])
        self.assertEqual(kept, ['8309'])
        self.assertEqual(counts['excluded_name'], 0)

    def test_reused_code_excluded_even_if_delisted_type_differs(self):
        kept, counts, _ = screen.jp_candidates([stock('1301'), stock('3000')], [stock('1301', kind='ETF'), stock('4000')])
        self.assertEqual(kept, ['3000', '4000'])
        self.assertEqual(counts['reused'], 1)

    def test_valid_daily_bars_are_finite_unique_and_window_bounded(self):
        raw = bars(['2004-12-31', '2005-01-01', '2025-06-30', '2025-07-01'])
        raw += [dict(raw[1]), dict(raw[1], date='2010-01-01', close=float('nan')),
                dict(raw[1], date='2010-01-02', volume=-1), dict(raw[1], date='bad'),
                dict(raw[1], date='2010-01-03', open=None)]
        _, stats, _ = screen.screen(['X'], lambda s: raw, ('2005-01-01', '2025-06-30'),
            self.spec()['pool'], 1, japan=True)
        self.assertEqual(stats['X']['window_bars'], 2)
        self.assertEqual(stats['X']['bars'], 4)

    def test_dedupe_uses_window_bars_then_lexical_tie(self):
        stats = {'01301-A': {'window_bars': 2, 'bars': 2}, '1301': {'window_bars': 1, 'bars': 100},
                 '3000': {'window_bars': 2}, '03000': {'window_bars': 2}}
        winners, duplicates, unresolved = screen.jp_dedupe(stats, [])
        self.assertEqual(winners, ['01301-A', '03000'])
        self.assertEqual(duplicates, ['1301', '3000'])
        self.assertEqual(unresolved, [])

    def test_dedupe_precedes_liquidity_no_shorter_alias_fallback(self):
        result, stats, failed, kept = self.run_screen([stock('1301'), stock('01301-A'), stock('3000')],
            {'1301': bars(['2010-01-01']), '01301-A': bars(['2010-01-01', '2010-01-02'], close=99),
             '3000': bars(['2010-01-01'])})
        self.assertEqual(kept, ['3000'])
        self.assertEqual(result['provider_counts']['company_duplicates'], 1)
        self.assertEqual(result['provider_counts']['below_liquidity'], 1)
        self.assertEqual(result['company_duplicates'], ['1301'])

    def test_failed_alias_cannot_silently_select_shorter_alias(self):
        winners, duplicates, unresolved = screen.jp_dedupe({'1301': {'window_bars': 3}}, ['01301-A'])
        self.assertEqual(winners, [])
        self.assertEqual(unresolved, ['1301'])

    def test_review_flags_are_inclusive_and_do_not_exclude(self):
        codes = ['1299', '1300', '1699', '1700', '2499', '2500', '2599', '2600', '8949', '8950', '8999', '9000']
        result, _, _, kept = self.run_screen([stock(c, 'Name '+c) for c in codes], {c: bars(['2010-01-01']) for c in codes})
        self.assertEqual(kept, sorted(codes))
        self.assertEqual([x['code'] for x in result['review_flags']], ['1300', '1699', '2500', '2599', '8950', '8999'])
        report = screen.render(result)
        self.assertIn('| 1300 | Name 1300 |', report)
        self.assertIn('JPY', report)
        self.assertIn('STOP 2', report)

    def test_tse_does_not_exclude_same_code_in_us_reference(self):
        _, _, _, kept = self.run_screen([stock('1301')], {'1301': bars(['2010-01-01'])})
        self.assertEqual(kept, ['1301'])

    def test_raw_floor_and_turnover_boundaries(self):
        row = bars(['2010-01-01'], close=100, volume=30_000_000)[0]
        row['adjusted_close'] = 50
        self.assertEqual(screen.qualifies([dict(row, close=50)], ('2005-01-01','2025-06-30'), self.spec()['pool'], [row]), 1)
        row['close'] = 99
        self.assertEqual(screen.qualifies([dict(row, close=50)], ('2005-01-01','2025-06-30'), self.spec()['pool'], [row]), 0)

    def test_screen_network_adapter_is_mocked_and_suffix_safe(self):
        spec = self.spec()
        with tempfile.TemporaryDirectory() as root, patch.object(eodhd, 'symbols', side_effect=[[stock('1301.TSE')], []]), patch.object(eodhd, 'get', return_value=bars(['2010-01-01'])) as get:
            screen.run(spec, {'prices': {}}, dict(dataset_id='d', asset='a', sha256='x', symbols=0), root)
            self.assertEqual(get.call_args.args[0], 'eod/1301.TSE')
            self.assertEqual(get.call_args.kwargs['to'], '2025-06-30')

    def test_retry_finishes_before_company_selection_and_counts_errors(self):
        attempts = {}
        def fetch(code):
            attempts[code] = attempts.get(code, 0) + 1
            if code == '01301' and attempts[code] == 1:
                raise RuntimeError('transient')
            if code == '4000':
                raise RuntimeError('permanent')
            if code == '5000':
                return []
            return bars(['2010-01-01', '2010-01-02'] if code == '01301' else ['2010-01-01'])
        with tempfile.TemporaryDirectory() as root:
            result, _, failed = screen.run(self.spec(), {'prices': {}},
                dict(dataset_id='d', asset='a', sha256='x', symbols=0), root,
                [stock(c) for c in ['1301', '01301', '4000', '5000']], [], fetch)
        self.assertEqual(attempts['01301'], 2)
        self.assertEqual(result['company_duplicates'], ['1301'])
        self.assertEqual(result['failed_errors'], 1)
        self.assertEqual(result['failed_empty'], 1)
        self.assertEqual(result['error_share'], .25)
        self.assertFalse(result['passed'])
        self.assertEqual(failed, ['4000', '5000'])

    def test_dataset_builder_tse_path_raw_and_numeric_symbols(self):
        with tempfile.TemporaryDirectory() as root:
            root = pathlib.Path(root)
            listing = root / 'symbols.txt'
            listing.write_text('01301-A\n1301.TSE\n')
            ds = dict(id='synthetic-jp-test', builder='universe', symbols_file=str(listing), extra_symbols=['1306'], start='1995-01-01', exchange='TSE', keep_raw=True)
            with patch.object(datasets, 'manifest', return_value=None), patch.object(run_queue, 'WORK', root), patch.object(eodhd, 'get', return_value=bars(['2005-01-01'])) as get:
                data, entry, built = run_queue.ensure_dataset(ds, publish=False)
            self.assertEqual([c.args[0] for c in get.call_args_list], ['eod/01301-A.TSE', 'eod/1301.TSE', 'eod/1306.TSE'])
            self.assertEqual(data['prices']['1306']['raw_close'], [200.0])
            self.assertEqual(entry['symbols'], 3)

    def test_registration_copies_fixed_values_and_answers_verbatim(self):
        card = pathlib.Path('tasks/037-japan-exam.md').read_text()
        fixed = card.split('2. Fixed values (do not change):\n')[1].split('3. Write ')[0]
        answers = card.split('## Claude answers')[1].split('**STOP 1**')[0]
        for path in ['docs/rules/08_BACKTEST_AND_EXPERIMENTS.md', 'docs/CASE_REVIEW_LEDGER_ZH.md']:
            text = pathlib.Path(path).read_text()
            self.assertIn(fixed, text)
            self.assertIn(answers, text)
        spec = self.spec()
        self.assertEqual(spec['exchange'], 'TSE')
        self.assertEqual(spec['pool'], {'min_close': 100, 'min_dollar_volume': 1.5e9})


if __name__ == '__main__':
    unittest.main()
