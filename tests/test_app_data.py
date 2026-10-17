import datetime as dt
import gzip
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research.lab import app_data as app, triangle_forward

FIXTURES = Path(__file__).parent / 'fixtures/app'


def prices():
    fixture = json.loads((FIXTURES / 'prices.json').read_text())
    day, end = dt.date.fromisoformat(fixture['start']), dt.date.fromisoformat(fixture['end'])
    days = []
    while day <= end:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += dt.timedelta(days=1)
    output = {}
    for symbol in app.SLEEVES + ['SHY']:
        close = [fixture['base_close']] * len(days)
        if symbol != fixture['flat_symbol']:
            close[-1] = fixture['last_close']
        output[symbol] = dict(date=days[:], close=close,
                              open=close[:], high=[x + 1 for x in close],
                              low=[x - 1 for x in close], volume=[1000] * len(days))
    return output


class AppDataTests(unittest.TestCase):
    def setUp(self):
        self.prices = prices()
        self.records = [json.loads(line) for line in (FIXTURES / 'signals.jsonl').read_text().splitlines()]
        self.outcomes = json.loads((FIXTURES / 'outcomes.json').read_text())

    def build(self):
        return app.build(sectors=self.prices, universe=self.prices, records=self.records,
                         outcomes=self.outcomes, prices_by_dataset={app.UNIVERSE: self.prices},
                         facts=[], as_of='2026-10-16', generated_at='2026-10-17T08:00:00Z')

    def test_market_reuses_frozen_function_and_restores_globals(self):
        old = triangle_forward.PX, triangle_forward.SPY, triangle_forward.BREADTH
        with patch.object(triangle_forward, 'market', wraps=triangle_forward.market) as call:
            state = app.market_state(self.prices, '2026-10-16')
        call.assert_called_once_with('2026-10-16')
        self.assertEqual(state['light'], 'green')
        self.assertEqual(old, (triangle_forward.PX, triangle_forward.SPY, triangle_forward.BREADTH))
        self.assertIsNone(app.market_state(self.prices, '2026-10-19')['light'])

    def test_light_colours_and_missing(self):
        for spy, breadth, ok, expected in [(True,.6,True,'green'),(True,.5,False,'amber'),
                                          (False,.6,False,'amber'),(False,.5,False,'red'),
                                          (False,None,False,None)]:
            self.assertEqual(app.light(dict(spy_over_200d=spy,breadth=breadth,ok=ok)),expected)

    def test_sleeve_month_end_and_no_lookahead(self):
        p = app.portfolio(self.prices, '2026-10-16')
        self.assertEqual(p['month_end_signal_as_of'], '2026-09-30')
        sleeve = p['sleeves'][0]
        self.assertEqual(sleeve['month_end']['hold'], 'SHY')
        self.assertEqual(sleeve['today']['hold'], 'XLB')
        self.assertTrue(sleeve['would_switch'])
        self.assertEqual(p['sleeves'][1]['today']['hold'], 'SHY')  # equality is not above
        self.assertEqual(sleeve['today']['sma200'], 100.1)
        before = app.portfolio(self.prices, '2026-09-30')
        self.prices['XLB']['close'][-1] = 9999
        self.assertEqual(app.portfolio(self.prices, '2026-09-30'), before)
        self.assertTrue(before['rebalance_due'])
        self.assertEqual(before['month_end_signal_as_of'], '2026-09-30')
        self.assertEqual(app.portfolio(self.prices, '2026-10-01')['month_end_signal_as_of'], '2026-09-30')

    def test_missing_spy_does_not_backdate_month_end(self):
        i = self.prices['SPY']['date'].index('2026-09-30')
        for values in self.prices['SPY'].values():
            del values[i]
        p = app.portfolio(self.prices,'2026-10-16')
        self.assertEqual(p['month_end_signal_as_of'],'2026-09-30')
        spy = p['sleeves'][-1]['month_end']
        self.assertTrue(spy['stale'])
        self.assertEqual(spy['price_as_of'],'2026-09-29')
        self.assertEqual(app.portfolio(self.prices,'2026-09-30')['month_end_signal_as_of'],'2026-09-30')

    def test_regular_calendar_month_boundary_holidays(self):
        for day, expected in [('2026-10-30','2026-11-02'),('2027-05-28','2027-06-01'),
                              ('2024-03-28','2024-04-01'),('2021-12-30','2021-12-31'),
                              ('2026-06-18','2026-06-22')]:
            self.assertEqual(app.next_session(day), expected)

    def test_bulk_and_missing_latest_price(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'work/triangle-bulk'
            folder.mkdir(parents=True)
            (folder / '2026-10-19.json.gz').write_bytes(gzip.compress((FIXTURES / 'bulk.json').read_bytes()))
            app.extend_prices(self.prices, app.bulk_files(root))
        p = app.portfolio(self.prices, '2026-10-19')
        self.assertEqual(p['sleeves'][0]['today']['close'], 121)
        self.assertFalse(p['sleeves'][0]['stale'])
        self.assertTrue(p['sleeves'][1]['stale'])
        self.assertEqual(p['sleeves'][1]['today']['close'], 100)
        self.assertEqual(p['sleeves'][1]['today']['price_as_of'], '2026-10-16')
        self.assertTrue(p['shy']['stale'])

    def test_status_order_counts_and_no_blind_fields(self):
        result = self.build()
        signals = {s['id']:s for s in result['signals.json']['signals']}
        self.assertEqual(signals['wait']['status'],'waiting')
        self.assertEqual(signals['open']['status'],'open')
        for ident in ('win','loss','time'):
            self.assertEqual(signals[ident]['status'],'closed')
        self.assertEqual(signals['win']['R'],3)  # outer 1.7 is a loss
        self.assertEqual(signals['cancel']['status'],'cancelled')
        self.assertEqual(signals['veto']['status'],'skipped')
        self.assertEqual(signals['skip']['status'],'skipped')
        self.assertEqual(signals['open']['order']['target'],140)
        self.assertEqual(signals['open']['distances']['to_stop_R'],2)
        self.assertEqual(signals['open']['distances']['to_target_R'],2)
        self.assertAlmostEqual(signals['open']['distances']['to_stop_pct'],100/6)
        self.assertNotIn('chart', signals['open'])
        self.assertNotIn('taste', signals['open'])
        self.assertEqual(signals['open']['market'],self.records[1]['market'])
        self.assertEqual(result['record.json']['forward']['counts'],
                         dict(waiting=1,open=1,closed=3,cancelled=1,skipped=2,unavailable=0))
        self.assertEqual(result['today.json']['breadth_source'],app.UNIVERSE)
        self.assertEqual([a['signal_id'] for a in result['today.json']['this_week']],['wait'])

    def test_missing_outcome_is_not_a_new_order(self):
        self.outcomes['outcomes'] = []
        result = self.build()
        self.assertEqual(result['today.json']['this_week'],[])
        self.assertEqual(result['record.json']['forward']['counts']['unavailable'],6)

    def test_version_and_factor_prefix(self):
        self.records = self.records[:1]
        self.records.append(dict(self.records[0],id='old',version='3w-1.8'))
        with patch.object(app.factor_tags,'entry_audit',wraps=app.factor_tags.entry_audit) as entry:
            result = self.build()
        self.assertEqual(len(result['signals.json']['signals']),1)
        rows,end = entry.call_args.args
        self.assertEqual(rows[end]['date'],'2026-10-16')
        self.assertTrue(result['signals.json']['signals'][0]['factor_tags']['context_only'])
        self.assertIn('rsi.bearish_divergence',result['signals.json']['signals'][0]['factor_tags']['risk_unavailable'])

    def test_size_guard_and_determinism(self):
        payload = self.build()
        one, two = app.encode(payload), app.encode(self.build())
        self.assertEqual(one,two)
        with tempfile.TemporaryDirectory() as tmp:
            app.write(one,Path(tmp))
            self.assertEqual({p.name:p.read_bytes() for p in Path(tmp).iterdir()},one)
        payload['today.json']['oversize'] = 'x' * app.MAX_BYTES
        with self.assertRaisesRegex(ValueError,'2 MB'):
            app.encode(payload)
        with patch.object(app,'validate_asset',side_effect=ValueError('hosting guard')):
            with self.assertRaisesRegex(ValueError,'hosting guard'):
                app.encode(self.build())

    def test_offline_loader_never_downloads(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(app.datasets,'download') as download:
            with self.assertRaises(FileNotFoundError):
                app.frozen_prices(app.SECTOR,Path(tmp))
            download.assert_not_called()

    def test_publish_window_guard_before_any_git_or_load(self):
        with patch.object(app,'in_eod_window',return_value=True), patch.object(app.subprocess,'run') as run:
            with self.assertRaises(RuntimeError):
                app.publish({})
            with self.assertRaises(RuntimeError):
                app.main(['--publish'])
            run.assert_not_called()

    def test_publish_only_app_paths_without_switch_or_local_index(self):
        commands = []
        def git(args, **kwargs):
            commands.append((args,kwargs))
            if args[1:3] == ['rev-parse','origin/main']:
                out = b'parent\n'
            elif args[1] == 'show':
                out = (app.ROOT / args[2].split(':',1)[1]).read_bytes()
            elif args[1] == 'write-tree':
                out = b'newtree\n'
            elif args[1] == 'rev-parse':
                out = b'oldtree\n'
            else:
                out = b'object\n'
            return SimpleNamespace(stdout=out)
        with patch.object(app,'in_eod_window',return_value=False), patch.object(app.subprocess,'run',side_effect=git):
            app.publish({name:b'{}\n' for name in app.FILES})
        paths = [a[-1].split(',',2)[-1] for a,k in commands if a[1] == 'update-index']
        self.assertEqual(paths, ['public/app/'+name for name in app.FILES])
        self.assertFalse(any('switch' in a or 'checkout' in a for a,k in commands))
        for args, kwargs in commands:
            if args[1] in ('read-tree','update-index','write-tree'):
                self.assertIn('GIT_INDEX_FILE',kwargs['env'])
        self.assertEqual(commands[-1][0],['git','push','origin','object:refs/heads/main'])

    def test_publish_rejects_changed_upstream_inputs(self):
        with patch.object(app,'in_eod_window',return_value=False), patch.object(app.subprocess,'run',return_value=SimpleNamespace(stdout=b'changed')) as run:
            with self.assertRaisesRegex(RuntimeError,'upstream input changed'):
                app.publish({name:b'{}' for name in app.FILES})
        self.assertFalse(any('push' in call.args[0] for call in run.call_args_list))

    def test_preview_load_build_bulk_and_missing_bulk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / app.FORWARD
            folder.mkdir(parents=True)
            (folder/'signals.jsonl').write_text('')
            (folder/'outcomes.json').write_text(json.dumps(dict(computed_at='2026-10-19T08:00:00Z',outcomes=[])))
            (root/'research/lab/app').mkdir()
            (root/'research/lab/app/record_facts.json').write_text('[]')
            with patch.object(app,'frozen_prices',side_effect=lambda *a,**k: prices()):
                first = app.load_build(root)
            self.assertEqual(first['portfolio.json']['as_of'],'2026-10-16')
            bulk = root/'work/triangle-bulk'
            bulk.mkdir(parents=True)
            (bulk/'2026-10-19.json.gz').write_bytes(gzip.compress((FIXTURES/'bulk.json').read_bytes()))
            with patch.object(app,'frozen_prices',side_effect=lambda *a,**k: prices()):
                updated = app.load_build(root)
            self.assertEqual(updated['portfolio.json']['as_of'],'2026-10-19')
            self.assertEqual(updated['portfolio.json']['sleeves'][0]['today']['close'],121)
            self.assertTrue(updated['portfolio.json']['sleeves'][1]['stale'])

    def test_record_facts_have_exact_ledger_headings(self):
        ledger = (app.ROOT / 'docs/CASE_REVIEW_LEDGER_ZH.md').read_text()
        section = ledger.split('## 十七、',1)[1].split('\n## ',1)[0]
        facts = json.loads((app.ROOT / 'research/lab/app/record_facts.json').read_text())
        for fact in facts:
            self.assertEqual(fact['ledger_section'],17)
            self.assertIn(fact['ledger_heading'],section)
        self.assertEqual(facts[0]['p'],.59)
        self.assertEqual(facts[0]['verdict'],'FAIL')


if __name__ == '__main__':
    unittest.main()
