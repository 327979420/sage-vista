import copy
import json
from pathlib import Path
import importlib.util
import unittest
import tempfile
import sys
from unittest.mock import patch
from research.lab import calendars as c, weekly_report as w
from tests.test_app_data import prices

# QuantStats needs pandas; CI has neither, the weekly routine runs these locally in work/vectorbt-env.
NEEDS_PANDAS = unittest.skipUnless(importlib.util.find_spec("pandas") and importlib.util.find_spec("quantstats"), "needs pandas + QuantStats")

FIXTURE = Path(__file__).parent / 'fixtures/weekly/cockpit.json'


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.export = json.loads(FIXTURE.read_text())
        self.outcomes = {'computed_at': '2026-10-17', 'outcomes': []}

    def test_value_and_sleeves(self):
        result = w.valuation(self.export, '2026-10-16')
        self.assertEqual(result['equity'], 10200)
        self.assertEqual(result['sleeves']['trend']['unrealized'], 100)
        self.assertEqual(result['sleeves']['3W']['realized'], 100)

    def test_missing_stale_future_and_other_account(self):
        self.export['positions'].append(dict(self.export['positions'][0], account='live', qty=10000))
        self.assertEqual(w.valuation(self.export, '2026-10-16')['equity'], 10200)
        for day in ('2026-10-15', '2026-10-19'):
            self.export['prices']['SPY']['date'] = day
            self.assertIsNone(w.valuation(self.export, '2026-10-16')['equity'])

    @NEEDS_PANDAS

    def test_short_report_escape_and_signals(self):
        signals = [{'symbol':'SPY', 'version':'3w-1.9', 'signal_day':'2026-10-15'},
                   {'symbol':'FUTURE', 'version':'3w-1.9', 'signal_day':'2026-10-19'}]
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            html = w.render(self.export, self.outcomes, prices(), '2026-10-17', signals=signals)
        self.assertIn('本周 1 个记录', html)
        self.assertNotIn('FUTURE', html)
        self.assertIn('历史不足 20', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>', html)
        self.assertNotIn('src="http', html)
        self.assertIn('2026-10-19', html)

    def histories(self):
        days = [d for d in c._load('XNYS')['sessions'] if '2026-09-18' <= d <= '2026-10-16']
        exports = []
        for i, day in enumerate(days):
            exports.append(dict(as_of=day, accounts={'paper':dict(start_cash=10000,cash=9000)},
                                positions=[dict(account='paper',symbol='SPY',source='trend',qty=10,entry=100,opened=days[0],status='open')],
                                prices={'SPY':dict(close=100+i*.5,date=day)},journal=[]))
        sectors = prices()
        sectors['SPY'] = dict(date=days, close=[100+i*.25 for i in range(len(days))])
        return exports, sectors

    @NEEDS_PANDAS

    def test_real_quantstats(self):
        history, sectors = self.histories()
        self.assertEqual(len(history), 21)
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            metrics, reason = w.history_metrics(history, sectors, '2026-10-16')
            html = w.render(history[-1], self.outcomes, sectors, '2026-10-17', history=history, signals=[])
        self.assertEqual(reason, '')
        self.assertAlmostEqual(metrics['total'], .01)
        self.assertAlmostEqual(metrics['benchmark'], .05)
        self.assertEqual(min(metrics['drawdown']), 0)
        self.assertIn('<svg', html)
        self.assertIn('月度收益', html)

    @NEEDS_PANDAS

    def test_history_gaps_cashflows_missing_spy_and_duplicates(self):
        history, sectors = self.histories()
        self.assertIsNone(w.history_metrics(history[:-1], sectors, '2026-10-16')[0])
        duplicate = history + [history[-1]]
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            w.history_metrics(duplicate, sectors, '2026-10-16')
        extra = copy.deepcopy(history[0]); extra['as_of'] = '2026-09-16'
        self.assertIn('不连续', w.history_metrics([extra]+history, sectors, '2026-10-16')[1])
        history[0]['accounts']['paper']['cash'] += 100
        self.assertIn('不一致', w.history_metrics(history, sectors, '2026-10-16')[1])
        history[0]['accounts']['paper']['cash'] -= 100
        sectors['SPY']['date'].pop()
        self.assertIn('SPY', w.history_metrics(history, sectors, '2026-10-16')[1])

    @NEEDS_PANDAS

    def test_first_loss_drawdown_and_conflicting_history(self):
        history, sectors = self.histories()
        history[1]['prices']['SPY']['close'] = 90
        metrics, _ = w.history_metrics(history, sectors, '2026-10-16')
        self.assertAlmostEqual(min(metrics['drawdown']), -.01)
        conflicting = copy.deepcopy(history[-1])
        conflicting['accounts']['paper']['cash'] += 10
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            w.render(conflicting, self.outcomes, sectors, '2026-10-17', history=history)

    @NEEDS_PANDAS

    def test_future_outcomes_and_wrong_export_date(self):
        self.outcomes['computed_at'] = '2026-10-19'
        html = w.render(self.export, self.outcomes, prices(), '2026-10-17')
        self.assertIn('晚于报告日', html)
        self.export['as_of'] = '2026-10-15'
        with self.assertRaises(ValueError):
            w.render(self.export, self.outcomes, prices(), '2026-10-17')


class PublishedWeeklyTests(unittest.TestCase):
    setUp = WeeklyTests.setUp
    histories = WeeklyTests.histories
    def portfolio(self):
        return dict(w.app_data.portfolio(prices(), '2026-10-16'), as_of='2026-10-16',
                    generated_at='2026-10-18T12:00:00Z')

    def test_published_fresh_and_future_portfolio(self):
        portfolio = self.portfolio()
        # The published flags are authoritative, not a recomputation from frozen prices.
        for sleeve in portfolio['sleeves']:
            sleeve['stale'] = sleeve['month_end']['stale'] = False
            sleeve['today']['hold'] = sleeve['symbol']
        html = w.render(self.export, self.outcomes, None, '2026-10-17', portfolio=portfolio)
        self.assertIn('行情不足或过期：无', html)
        self.assertIn('2026-10-18T12:00:00Z', html)
        for field in ('as_of', 'price_as_of'):
            future = copy.deepcopy(portfolio)
            if field == 'as_of':
                future[field] = '2026-10-19'
            else:
                future['sleeves'][0]['today'][field] = '2026-10-19'
            html = w.render(self.export, self.outcomes, None, '2026-10-17', portfolio=future)
            self.assertIn('晚于估值日，拒用', html)
            self.assertNotIn('与月底相比的候选变化', html)

    def test_forward_grace_and_utc_conversion(self):
        for stamp, accepted in (('2026-10-18T23:59:59Z', True),
                                ('2026-10-19T00:00:00Z', False),
                                ('2026-10-19T00:30:00+11:00', True),
                                ('2026-10-18T23:30:00-04:00', False), ('bad', False), (None, False)):
            with self.subTest(stamp=stamp):
                html = w.render(self.export, dict(computed_at=stamp, outcomes=[]), None, '2026-10-17')
                self.assertIn(stamp or "未提供", html)
                self.assertEqual('尚不能据此证明策略有效' in html, accepted)
                self.assertEqual('前向记录日期缺失或晚于报告日，不能用于本期报告。' in html, not accepted)

    def test_published_benchmark_sources_and_future_records(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'work') as folder:
            root = Path(folder)
            (root / 'public/app').mkdir(parents=True)
            (root / 'research/lab/paper').mkdir(parents=True)
            (root / 'public/app/portfolio.json').write_text(json.dumps(self.portfolio()))
            portfolio, benchmark = w.published_inputs(root, '2026-10-16')
            html = w.render(self.export, self.outcomes, None, '2026-10-17', portfolio=portfolio, benchmark=benchmark)
            self.assertIn('不可用：缺少完整同期每日历史', html)
            path = root / 'research/lab/paper/history.jsonl'
            history, _ = self.histories()
            records = [dict(as_of=x['as_of'], recorded_at='2026-10-18T00:00:00Z',
                            values=dict(date=x['as_of'], spy=100000+i*250)) for i,x in enumerate(history)]
            records += [dict(as_of='2026-10-19', values=dict(date='2026-10-19', spy=1))]
            path.write_text('\n'.join(json.dumps(x) for x in records))
            _, benchmark = w.published_inputs(root, '2026-10-16')
            self.assertEqual(benchmark['label'], w.SPY_NAV_LABEL)
            self.assertEqual(len(benchmark['SPY']['date']), 21)
            self.assertNotIn('2026-10-19', benchmark['SPY']['date'])
            self.assertIn('拒用', ''.join(benchmark['notes']))
            if importlib.util.find_spec('quantstats'):
                metrics, reason = w.history_metrics(history, benchmark, '2026-10-16')
                self.assertEqual(reason, '')
                self.assertEqual(metrics['spy'][0], 1)
                self.assertAlmostEqual(metrics['benchmark'], .05)
                html = w.render(history[-1], self.outcomes, None, '2026-10-17', history=history, benchmark=benchmark)
                self.assertIn(w.SPY_NAV_LABEL, html)
            # No paper: public closes may supply dates, never fill intervening sessions.
            path.unlink()
            (root / 'public/app/today.json').write_text(json.dumps(dict(as_of='2026-10-16',
                generated_at='2026-10-19', market=dict(price_as_of='2026-10-16', close=123))))
            (root / 'public/app/portfolio.json').unlink()
            _, benchmark = w.published_inputs(root, '2026-10-16')
            self.assertEqual(benchmark['SPY'], dict(date=['2026-10-16'], close=[123]))
            self.assertIn('不可用', w.history_metrics(history, benchmark, '2026-10-16')[1])
            _, benchmark = w.published_inputs(root, '2026-10-15')
            self.assertEqual(benchmark['SPY']['date'], [])

    def test_cli_default_and_explicit_frozen(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'work') as folder:
            args = ['weekly_report', '--cockpit', str(FIXTURE), '--date', '2026-10-17',
                    '--outcomes', str(FIXTURE.with_name('outcomes.json')), '--output-dir', folder]
            with patch('socket.socket', side_effect=AssertionError('network forbidden')), patch.object(sys, 'argv', args), patch.object(w.app_data, 'frozen_prices', side_effect=AssertionError('implicit frozen')):
                w.main()
            with patch('socket.socket', side_effect=AssertionError('network forbidden')), patch.object(sys, 'argv', args + ['--sectors-frozen']), patch.object(w.app_data, 'frozen_prices', return_value=prices()) as frozen:
                w.main()
                frozen.assert_called_once_with(w.app_data.SECTOR)
            html = (Path(folder) / '2026-10-17.html').read_text()
            self.assertIn('离线冻结回退', html)

    def test_missing_inputs_and_partial_nav_do_not_invent_history(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'work') as folder:
            portfolio, benchmark = w.published_inputs(Path(folder), '2026-10-16')
            html = w.render(self.export, self.outcomes, None, '2026-10-17', portfolio=portfolio, benchmark=benchmark)
            self.assertIn('portfolio.json 未提供；不可用', html)
            self.assertIn('paper history.jsonl 未提供或为空', html)
        history, _ = self.histories()
        partial = dict(SPY=dict(date=['2026-10-16'], close=[100000]), label=w.SPY_NAV_LABEL)
        html = w.render(history[-1], self.outcomes, None, '2026-10-17', history=history, benchmark=partial)
        self.assertIn('不可用', html)
        self.assertNotIn('<svg', html)
