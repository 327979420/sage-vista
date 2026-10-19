"""Task043 synthetic-only contracts; no provider or price cache access."""
import datetime
import json
import pathlib
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

from research.lab import screen
from services.scanner import eodhd


def stock(code, name='Company', kind='Common Stock'):
    return dict(Code=code, Name=name, Type=kind, Exchange='NYSE')


def bars(n=60, close=1000, volume=13_000_000):
    return [dict(date=(datetime.date(2010, 1, 1)+datetime.timedelta(days=i)).isoformat(),
                 open=close, high=close, low=close, close=close, adjusted_close=close, volume=volume) for i in range(n)]


class KoreaScreenTests(unittest.TestCase):
    def spec(self):
        s = json.loads(pathlib.Path('research/lab/queue/data-kr-universe-v1.json').read_text())
        s.update(workers=1, shard_dir='u', shard_size=2)
        s['criteria'] = dict(max_error_share=.02, min_kept=1)
        return s

    def run_screen(self, listed, histories, delisted=None, spec=None):
        with tempfile.TemporaryDirectory() as root:
            result, stats, failed = screen.run(spec or self.spec(), {'prices': {'000010.KO': {}}},
                dict(dataset_id='synthetic', asset='none', sha256='none', symbols=1), root,
                listed, delisted or dict(KO=[], KQ=[]), lambda c: histories[c])
            kept = [c for f in result['shards'] for c in pathlib.Path(root, f['file']).read_text().split()]
        return result, stats, failed, kept

    def test_registration_verbatim_and_spec(self):
        card = pathlib.Path('tasks/043-korea-exam.md').read_text()
        fixed = card.split('2. Fixed values (do not change):\n')[1].split('3. `research/')[0]
        for file in ['docs/rules/08_BACKTEST_AND_EXPERIMENTS.md', 'docs/CASE_REVIEW_LEDGER_ZH.md']:
            text = pathlib.Path(file).read_text()
            self.assertIn(fixed, text)
            self.assertIn('Task037 已关闭', text)
        s = json.loads(pathlib.Path('research/lab/queue/data-kr-universe-v1.json').read_text())
        self.assertEqual(s['exchanges'], ['KO', 'KQ'])
        self.assertNotIn('exchange', s)
        self.assertEqual(s['pool'], dict(min_close=1000, min_dollar_volume=13e9))
        self.assertEqual(s['criteria'], dict(max_error_share=.02, min_kept=300))
        self.assertEqual(s['window'], ['2005-01-01', '2025-06-30'])
        self.assertEqual(s['fetch_start'], '2004-01-01')
        self.assertEqual(s['min_sessions'], 60)
        self.assertEqual(s['shard_prefix'], 'kr-2005-2025-v1')

    def test_types_exact_and_same_exchange_reuse(self):
        kept, counts, _ = screen.kr_candidates(dict(KO=[stock('000010'), stock('000020', kind='common stock')], KQ=[stock('000010')]),
            dict(KO=[stock('000010', kind='ETF'), stock('000030')], KQ=[]))
        self.assertEqual(kept, ['000010.KQ', '000030.KO'])
        self.assertEqual(counts['reused'], 1)
        self.assertEqual(counts['non_common_type'], 2)

    def test_code_class_sixth_character_and_preserved_zeros(self):
        rows = [stock('00001'+c) for c in '0123456789K'] + [stock('000020.KO')]
        kept, counts, _ = screen.kr_candidates(dict(KO=rows, KQ=[]), dict(KO=[], KQ=[]))
        self.assertEqual(kept, ['000010.KO', '000020.KO'])
        self.assertEqual(counts['非普通股代码'], 10)
        self.assertEqual(screen.kr_company_key('000010.KQ'), '000010')

    def test_malformed_code_excluded_and_counted(self):
        # Amendment 2026-10-19: a code that is not six characters is excluded and counted, the screen keeps going.
        kept, counts, _ = screen.kr_candidates(dict(KO=[stock('123'), stock('000020')], KQ=[]), dict(KO=[], KQ=[]))
        self.assertEqual(kept, ['000020.KO'])
        self.assertEqual(counts['代码格式异常'], 1)

    def test_every_name_exclusion_case_insensitive_counts_overlap(self):
        rows = [stock(f'{i:05d}0', 'prefix '+term.lower()) for i, term in enumerate(screen.KR_NAME_EXCLUSIONS)]
        rows += [stock('001000', 'ETF Fund'), stock('001010', 'Trust Bank')]
        kept, counts, _ = screen.kr_candidates(dict(KO=rows, KQ=[]), dict(KO=[], KQ=[]))
        self.assertEqual(kept, ['001010.KO'])
        self.assertEqual(counts['excluded_name'], 12)
        for term in screen.KR_NAME_EXCLUSIONS:
            self.assertEqual(counts['name_matches'][term], 2 if term in ('ETF', 'FUND') else 1)

    def test_proxy_never_candidate_even_with_wrong_metadata(self):
        kept, counts, _ = screen.kr_candidates(dict(KO=[stock('069500')], KQ=[stock('069500')]), dict(KO=[], KQ=[]))
        self.assertEqual(kept, [])
        self.assertEqual(counts['market_proxy'], 2)

    def test_cross_board_most_bars_and_tie_ko(self):
        winners, removed, unresolved = screen.kr_dedupe({'000010.KO': dict(window_bars=60), '000010.KQ': dict(window_bars=61),
            '000020.KO': dict(window_bars=60), '000020.KQ': dict(window_bars=60)}, [])
        self.assertEqual(winners, ['000010.KQ', '000020.KO'])
        self.assertEqual(removed, ['000010.KO', '000020.KQ'])
        self.assertEqual(unresolved, [])

    def test_dedupe_before_liquidity_no_fallback(self):
        r, _, _, kept = self.run_screen(dict(KO=[stock('000010')], KQ=[stock('000010')]),
            {'000010.KO': bars(), '000010.KQ': bars(61, close=999)})
        self.assertEqual(kept, [])
        self.assertEqual(r['company_duplicates'], ['000010.KO'])
        self.assertEqual(r['provider_counts']['below_liquidity'], 1)

    def test_valid_window_bars_only(self):
        rows = bars(1)
        rows += [dict(rows[0], date=d) for d in ['2004-12-31', '2005-01-01', '2025-06-30', '2025-07-01']]
        rows += [dict(rows[0]), dict(rows[0], date='2011-01-01', close=float('nan')),
                 dict(rows[0], date='bad'), dict(rows[0], date='2012-01-01', volume=-1),
                 dict(rows[0], date='2013-01-01', adjusted_close=0)]
        _, stats, _, _ = self.run_screen(dict(KO=[stock('000010')], KQ=[]), {'000010.KO': rows})
        self.assertEqual(stats['000010.KO']['window_bars'], 3)
        self.assertEqual(stats['000010.KO']['bars'], 5)

    def test_failed_alias_unresolved_after_retry(self):
        r, _, failed, kept = self.run_screen(dict(KO=[stock('000010')], KQ=[stock('000010')]), {'000010.KO': bars()})
        self.assertEqual(kept, [])
        self.assertEqual(failed, ['000010.KQ'])
        self.assertEqual(r['unresolved_company'], ['000010.KO'])
        self.assertFalse(r['passed'])

    def test_review_terms_flag_only_kept_names(self):
        rows = [stock(f'{i:05d}0', term.lower()) for i, term in enumerate(screen.KR_REVIEW_TERMS)]
        rows += [stock('000050', 'PREF fund'), stock('000060', 'Holdings')]
        r, _, _, kept = self.run_screen(dict(KO=rows, KQ=[]), {f'{i:05d}0.KO': bars() for i in range(4)} | {'000060.KO': bars(59)})
        self.assertEqual(len(kept), 4)
        self.assertEqual([x['code'] for x in r['review_flags']], kept)
        report = screen.render(r)
        self.assertIn('KRW', report)
        self.assertNotIn('$', report)
        self.assertIn('STOP 2', report)
        for x in r['review_flags']:
            self.assertIn(x['name'], report)

    def test_raw_price_turnover_and_session_boundaries(self):
        rows = bars()
        for row in rows:
            row.update(adjusted_close=500, volume=26_000_000)
        for n, close, volume, expected in [(60,1000,26_000_000,1), (59,1000,26_000_000,0),
                (60,999,26_000_000,0), (60,1000,25_999_999,0)]:
            with self.subTest(n=n, close=close, volume=volume):
                _, _, _, kept = self.run_screen(dict(KO=[stock('000010')], KQ=[]),
                    {'000010.KO': [dict(r, close=close, volume=volume) for r in rows[:n]]})
                self.assertEqual(len(kept), expected)

    def test_mock_adapter_both_boards_suffix_and_end_date(self):
        with tempfile.TemporaryDirectory() as root, patch.object(eodhd, 'symbols', side_effect=lambda gone, board: [] if gone else [stock('000010.'+board)]) as symbols, patch.object(eodhd, 'get', return_value=bars()) as get:
            r, _, _ = screen.run(self.spec(), {'prices': {}}, dict(dataset_id='d', asset='a', sha256='x', symbols=0), root)
        self.assertEqual(sorted(c.args for c in symbols.call_args_list), [(False,'KO'), (False,'KQ'), (True,'KO'), (True,'KQ')])
        self.assertEqual(sorted(c.args[0] for c in get.call_args_list), ['eod/000010.KO', 'eod/000010.KQ'])
        for c in get.call_args_list:
            self.assertEqual(c.kwargs['from'], '2004-01-01')
            self.assertEqual(c.kwargs['to'], '2025-06-30')
        self.assertEqual(r['company_duplicates'], ['000010.KQ'])

    def test_retry_before_dedupe_and_empty_separate(self):
        attempts = {}
        def fetch(code):
            attempts[code] = attempts.get(code, 0)+1
            if code == '000010.KQ' and attempts[code] == 1:
                raise RuntimeError('transient')
            if code == '000020.KO':
                return []
            return bars(61 if code.endswith('KQ') else 60)
        with tempfile.TemporaryDirectory() as root:
            r, _, _ = screen.run(self.spec(), {'prices': {}}, dict(dataset_id='d',asset='a',sha256='x',symbols=0),root,
                dict(KO=[stock('000010'),stock('000020')],KQ=[stock('000010')]),dict(KO=[],KQ=[]),fetch)
        self.assertEqual(attempts['000010.KQ'], 2)
        self.assertEqual(r['company_duplicates'], ['000010.KO'])
        self.assertEqual(r['failed_empty'], 1)
        self.assertEqual(r['failed_errors'], 0)
        self.assertTrue(r['passed'])

    def test_unregistered_exchange_list_rejected(self):
        s = self.spec(); s['exchanges'] = ['KO']
        with self.assertRaises(ValueError):
            self.run_screen({}, {}, spec=s)

    def test_us_hk_tse_byte_identical_to_b849055(self):
        old = types.ModuleType('baseline_screen')
        source = subprocess.check_output(['git', 'show', 'b849055:research/lab/screen.py'], text=True)
        exec(compile(source, 'b849055:screen.py', 'exec'), old.__dict__)
        for exchange in ['US', 'HK', 'TSE']:
            for retry in [False, True]:
                with self.subTest(exchange=exchange, retry=retry):
                    s = self.spec(); s.pop('exchanges'); s.update(exchange=exchange,retry_failed=retry,min_sessions=1)
                    listed = [stock(c, name) for c,name in [('1300','Holdings'),('01300','ETF'),('3000','Trust'),('4000','Empty'),('5000','Error'),('6000','Retry'),('7000','Reused'),('8000','Known'),('9000','Low')]]
                    outputs = []
                    for module in [old, screen]:
                        attempts = {}
                        def fetch(c):
                            attempts[c] = attempts.get(c,0)+1
                            if c == '5000' or (c == '6000' and attempts[c] == 1):
                                raise RuntimeError('synthetic failure')
                            return [] if c == '4000' else bars(2, close=999 if c=='9000' else 1000)
                        with tempfile.TemporaryDirectory() as root:
                            r, stats, failed = module.run(s, {'prices': {'8000': {}}}, dict(dataset_id='d',asset='a',sha256='x',symbols=1),root,listed,[stock('7000'),stock('03000')],fetch)
                            outputs.append((json.dumps([r,stats,failed],ensure_ascii=False).encode(), module.render(r).encode(),
                                [(f['file'],pathlib.Path(root,f['file']).read_bytes()) for f in r['shards']]))
                    self.assertEqual(outputs[0], outputs[1])


if __name__ == '__main__':
    unittest.main()
