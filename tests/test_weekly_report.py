import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from research.lab import calendars as c, weekly_report as w
from tests.test_app_data import prices

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

    def test_first_loss_drawdown_and_conflicting_history(self):
        history, sectors = self.histories()
        history[1]['prices']['SPY']['close'] = 90
        metrics, _ = w.history_metrics(history, sectors, '2026-10-16')
        self.assertAlmostEqual(min(metrics['drawdown']), -.01)
        conflicting = copy.deepcopy(history[-1])
        conflicting['accounts']['paper']['cash'] += 10
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            w.render(conflicting, self.outcomes, sectors, '2026-10-17', history=history)

    def test_future_outcomes_and_wrong_export_date(self):
        self.outcomes['computed_at'] = '2026-10-19'
        html = w.render(self.export, self.outcomes, prices(), '2026-10-17')
        self.assertIn('晚于报告日', html)
        self.export['as_of'] = '2026-10-15'
        with self.assertRaises(ValueError):
            w.render(self.export, self.outcomes, prices(), '2026-10-17')
