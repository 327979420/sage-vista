import datetime as dt
import json
import pathlib
import tempfile
import unittest

from services.scanner import stock_lookup as lookup
from services.scanner.release_contract import has_raw_bars

AS_OF = '2026-11-23'


def sessions(count, end=AS_OF):
    day, out = dt.date.fromisoformat(end), []
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day -= dt.timedelta(days=1)
    return out[::-1]


def raw(closes, volume=1_000_000, end=AS_OF):
    return [{'date': d, 'open': c, 'high': c * 1.01, 'low': c * .99, 'close': c, 'adjusted_close': c, 'volume': volume}
            for d, c in zip(sessions(len(closes), end), closes)]


def rows(closes, **kw):
    from services.scanner.macd_factor_backtest import adjusted_rows
    return adjusted_rows(raw(closes, **kw))


class Fixture:
    def __init__(self, folder):
        self.root = pathlib.Path(folder)
        (self.root / 'app').mkdir(parents=True, exist_ok=True)
        self.cache = {
            'AAA': rows([10 + i * .01 for i in range(500)]),            # tracked, triggered and ranked first
            'BBB': rows([50.0] * 500, volume=3_000_000),                # tracked, biggest dollar volume, calm
            'CCC': rows([20 - i * .01 for i in range(500)]),            # tracked, triggered but not ranked
            'LOW': rows([4.0] * 500, volume=50_000_000),                # under $5
            'THIN': rows([30.0] * 500, volume=100_000),                 # under $10M a day
            'NEW': rows([30.0] * 300),                                  # not 420 sessions yet
            'OLD': rows([30.0] * 500, end='2026-11-20'),                # no bar on the as-of day
        }
        self.write('daily-factor-snapshot.json', {'as_of': AS_OF, 'eligible_count': 3, 'symbols': [{'symbol': 'AAA', 'price': 14.99}, {'symbol': 'CCC', 'price': 15.01}]})
        self.write('unified-v2-latest.json', {'days': [{'date': AS_OF, 'ranking': [{'symbol': 'AAA', 'price': 14.99, 'rank': 1, 'technical_resonance': {'positive_hit_count': 9, 'families': ['macd', 'support']}}]}]})
        self.write('daily-shape-picker.json', {'as_of': AS_OF, 'universe': {'selected_activity_count': 100}, 'state_counts': {'waiting': 1, 'unconfirmed': 1},
                                               'rows': [{'symbol': 'BBB', 'state': 'waiting', 'price': 50.0, 'activity_rank': 3}, {'symbol': 'ZZZ', 'state': 'broken_out', 'price': 80.0, 'activity_rank': 9}]})
        self.write('app/signals.json', {'signals': [{'id': 'a1', 'symbol': 'SIG', 'week': '2026-11-06', 'status': 'skipped', 'quote': {'close': 10.08}},
                                                    {'id': 'a0', 'symbol': 'AAA', 'week': '2026-10-16', 'status': 'skipped', 'quote': {'close': 12.0}}]})
        self.write('app/today.json', {'as_of': '2026-11-20', 'signal_week': '2026-11-20', 'new_signals_this_week': 0, 'market': {'light': 'red'}})
        self.write('app/record.json', {'forward': {'counts': {'closed': 0}}})

    def write(self, name, payload):
        (self.root / name).write_text(json.dumps(payload))


class StockLookupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Fixture(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_tracked_uses_the_snapshot_gate_and_plain_price_facts(self):
        facts = lookup.tracked(self.f.cache, AS_OF)
        self.assertEqual(sorted(facts), ['AAA', 'BBB', 'CCC'])
        aaa = facts['AAA']
        self.assertEqual(aaa['c'], 14.99)
        self.assertAlmostEqual(aaa['m6'], (14.99 / (10 + 373 * .01) - 1) * 100, places=1)
        self.assertEqual(aaa['hi'], 0.0)
        self.assertTrue(aaa['ma'])
        self.assertFalse(facts['CCC']['ma'])

    def test_build_joins_every_view_without_price_history(self):
        index = lookup.build(self.f.cache, AS_OF, self.f.root, generated_at='t')
        s = index['stocks']
        self.assertEqual(index['count'], 3)
        self.assertEqual((s['AAA']['mf'], s['AAA']['h'], s['AAA']['f']), (1, 9, ['macd', 'support']))
        self.assertEqual(s['CCC']['mf'], 0)
        self.assertNotIn('mf', s['BBB'])
        self.assertEqual((s['BBB']['sh'], s['BBB']['a']), ('waiting', 3))
        self.assertEqual(s['AAA']['w3'], {'id': 'a0', 'week': '2026-10-16', 'status': 'skipped'})
        # Results for stocks outside the tracked gate are kept and marked, and never counted.
        self.assertEqual(s['ZZZ'], {'c': 80.0, 'x': True, 'sh': 'broken_out', 'a': 9})
        self.assertEqual(s['SIG']['w3']['id'], 'a1')
        self.assertEqual(index['big'], ['BBB', 'CCC', 'AAA'])  # by today's dollar volume
        self.assertEqual(index['w3'], {'as_of': '2026-11-20', 'week': '2026-11-20', 'new': 0, 'light': 'red', 'latest_week': '2026-11-06', 'latest': ['SIG'], 'since_lock': 2})
        self.assertFalse(any('dv' in e for e in s.values()))
        self.assertFalse(has_raw_bars(index))

    def test_build_refuses_mismatched_inputs(self):
        self.f.write('daily-factor-snapshot.json', {'as_of': AS_OF, 'eligible_count': 4, 'symbols': []})
        with self.assertRaisesRegex(ValueError, 'factor snapshot counted 4'):
            lookup.build(self.f.cache, AS_OF, self.f.root)
        self.f.write('daily-factor-snapshot.json', {'as_of': '2026-11-20', 'eligible_count': 3, 'symbols': []})
        with self.assertRaisesRegex(ValueError, 'daily-factor-snapshot is for 2026-11-20'):
            lookup.build(self.f.cache, AS_OF, self.f.root)

    def test_new_since_the_previous_index(self):
        previous = {'as_of': '2026-11-20', 'stocks': {'AAA': {'c': 14, 'w3': {'id': 'a0'}}, 'BBB': {'c': 50, 'sh': 'broken_out'}}}
        index = lookup.build(self.f.cache, AS_OF, self.f.root, previous)
        self.assertEqual(index['new'], {'mf': ['AAA'], 'sh': ['BBB', 'ZZZ'], 'w3': ['SIG']})
        self.assertEqual(index['new_since'], '2026-11-20')
        # A rerun on the same day keeps the comparison with the earlier day.
        again = lookup.build(self.f.cache, AS_OF, self.f.root, index)
        self.assertEqual((again['new'], again['new_since']), (index['new'], '2026-11-20'))
        first = lookup.build(self.f.cache, AS_OF, self.f.root, None)
        self.assertEqual((first['new'], first['new_since']), ({'mf': [], 'sh': [], 'w3': []}, None))

    def test_run_writes_once_per_change(self):
        cache = pathlib.Path(self.tmp.name) / 'cache'
        cache.mkdir()
        for symbol, closes in (('AAA', [10 + i * .01 for i in range(500)]), ('BBB', [50.0] * 500), ('CCC', [20 - i * .01 for i in range(500)])):
            (cache / f'{symbol}.json').write_text(json.dumps(raw(closes, volume=3_000_000 if symbol == 'BBB' else 1_000_000)))
        # ETFs and benchmarks share the cache; only the active common-stock list counts.
        (cache / 'SPY.json').write_text(json.dumps(raw([600.0] * 500, volume=50_000_000)))
        active = pathlib.Path(self.tmp.name) / 'active.json'
        active.write_text(json.dumps([{'Code': s} for s in ('AAA', 'BBB', 'CCC', 'GONE')]))
        first = lookup.run(AS_OF, cache, self.f.root, active)
        second = lookup.run(AS_OF, cache, self.f.root, active)
        self.assertEqual((first['result'], second['result']), ('updated', 'already_current'))
        self.assertEqual(json.loads((self.f.root / 'stock-index.json').read_text())['count'], 3)


    def test_release_contract_only_warns_about_the_index(self):
        from services.scanner.release_contract import check_stock_index
        warnings = []
        check_stock_index(self.f.root, AS_OF, warnings)
        self.assertEqual(warnings, ['stock-index: missing; /stock pages show no lookup data'])
        self.f.write('stock-index.json', {'as_of': '2026-11-20', 'stocks': {}})
        warnings = []
        check_stock_index(self.f.root, AS_OF, warnings)
        self.assertIn('still 2026-11-20', warnings[0])
        self.f.write('stock-index.json', {'as_of': AS_OF, 'stocks': {'X': {'open': 1, 'high': 1, 'low': 1, 'close': 1, 'volume': 1}}})
        with self.assertRaisesRegex(ValueError, 'raw OHLCV'):
            check_stock_index(self.f.root, AS_OF, [])

if __name__ == '__main__':
    unittest.main()
