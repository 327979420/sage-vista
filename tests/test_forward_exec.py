"""Task048 timing, frozen engine reuse, cache boundary and publication checks."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from research.lab import forward_exec as E, app_data


def series(n=170):
    dates = []
    day = dt.date(2024, 1, 5)
    while len(dates) < n:
        if day.weekday() < 5:
            dates.append(day.isoformat())
        day += dt.timedelta(days=1)
    return dict(date=dates, open=[105.] * n, high=[106.] * n, low=[101.] * n, close=[105.] * n)


class ExecutableTests(unittest.TestCase):
    def setUp(self):
        self.s = series()
        self.p = dict(go=True, level=100., stop=90.)
        self.live = E.live_day(self.s['date'], 0)

    def test_normal_week(self):
        self.assertEqual(self.s['date'][self.live], '2024-01-16')

    def test_monday_holiday(self):
        dates = [d for d in self.s['date'] if d != '2024-01-15']
        self.assertEqual(dates[E.live_day(dates, 0)], '2024-01-17')

    def test_late_recorded_and_exact_open(self):
        dates = self.s['date']
        self.assertEqual(E.live_day(dates, 0, '2024-01-16T14:30:00Z'), self.live)
        self.assertEqual(dates[E.live_day(dates, 0, '2024-01-16T14:30:01Z')], '2024-01-17')
        self.assertEqual(dates[E.live_day(dates, 0, '2024-01-19T22:00:00Z')], '2024-01-22')
        with self.assertRaises(ValueError): E.live_day(dates, 0, '2024-01-16T14:30:00')

    def test_daylight_saving(self):
        dates = ['2024-03-01', '2024-03-11', '2024-03-12', '2024-03-13']
        self.assertEqual(E.live_day(dates, 0, '2024-03-12T13:30:00Z'), 2)
        self.assertEqual(E.live_day(dates, 0, '2024-03-12T13:31:00Z'), 3)

    def test_pre_live_stop(self):
        self.s['low'][self.live - 1] = 90
        self.assertEqual(E.executable(self.s, 0, self.p)['status'], 'skip_stop')

    def test_pre_live_target(self):
        self.s['high'][1] = 130
        self.assertEqual(E.executable(self.s, 0, self.p)['status'], 'skip_target')

    def test_same_day_stop_first(self):
        self.s['low'][1], self.s['high'][1] = 90, 130
        self.assertEqual(E.executable(self.s, 0, self.p)['status'], 'skip_stop')

    def test_pre_live_limit_dip_does_not_fill(self):
        self.s['low'][1] = 99
        self.s['open'][self.live] = self.s['low'][self.live] = 98
        self.s['high'][self.live + 1] = 130
        got = E.executable(self.s, 0, self.p)
        self.assertEqual(got['fill'], self.s['date'][self.live])
        self.assertEqual(got['status'], 'win')
        self.assertAlmostEqual(got['R'], E.J.net_r(98, 130, 90))

    def test_wait_counted_from_original_signal(self):
        for day, expected in [(40, 'time'), (41, 'cancelled')]:
            s = series(200)
            s['low'][day] = 99
            self.assertEqual(E.executable(s, 0, self.p)['status'], expected)
        with patch.object(E.N, 'trade', wraps=E.N.trade) as trade:
            E.executable(self.s, 0, self.p)
            self.assertEqual(trade.call_args.kwargs, dict(hold=130, wait=40-(self.live-1)))

    def test_waiting_and_open_have_no_net_r(self):
        for n in [4, 8]:
            s = series(n)
            if n == 8:
                s['low'][7] = 99
            got = E.executable(s, 0, self.p)
            self.assertEqual(got['status'], 'waiting' if n == 4 else 'open')
            self.assertNotIn('R', got)

    def fixture(self):
        rec = dict(id='one', symbol='A', signal_day=self.s['date'][0], plan=self.p,
                   market={'ok': True}, dataset='fixture', recorded_at='2024-01-16T13:00:00Z')
        out = dict(computed_at='2024-01-16T23:00:00Z')
        return dict(datasets=['fixture']), rec, out

    def test_compute_caps_prices_and_filters(self):
        config, rec, out = self.fixture()
        self.s['low'][self.live] = 99
        self.s['high'][self.live + 1] = 130  # beyond outcomes, must not close
        with patch.object(E.J, 'cached_prices', return_value={'A': self.s}) as cached:
            got = E.compute(config, [rec, {**rec, 'id':'excluded', 'market':{'ok':False}}], out, 'now')
        cached.assert_called_once_with('fixture', config, '2024-01-16')
        self.assertEqual(got['summary']['open'], 1)
        self.assertEqual(got['summary']['trades'], 0)
        self.assertIsNone(got['summary']['mean_R'])
        self.assertEqual(len(got['rows']), 1)
        self.assertEqual(got['outcomes_computed_at'], out['computed_at'])

    def test_missing_prices_error(self):
        config, rec, out = self.fixture()
        with patch.object(E.J, 'cached_prices', return_value={}):
            with self.assertRaisesRegex(ValueError, 'missing prices'):
                E.compute(config, [rec], out, 'now')

    def test_unknown_dataset_error(self):
        config, rec, out = self.fixture()
        with self.assertRaisesRegex(ValueError, 'unknown'):
            E.compute(config, [{**rec, 'dataset':'unknown'}], out, 'now')

    def test_summary_closed_and_skips(self):
        config, rec, out = self.fixture()
        statuses = ['win', 'loss', 'time', 'skip_stop', 'skip_target', 'waiting', 'open', 'cancelled']
        replies = [dict(status=s, live='2024-01-16', **({'R':r} if s in E.J.DONE else {}))
                   for s,r in zip(statuses, [2,-1,.5,0,0,0,0,0])]
        with patch.object(E.J, 'cached_prices', return_value={'A':self.s}), patch.object(E, 'executable', side_effect=replies):
            got = E.compute(config, [{**rec,'id':str(i)} for i in range(8)], out, 'now')
        self.assertEqual(got['summary'], dict(trades=3,wins=2,mean_R=.5,sum_R=1.5,skipped_stop=1,skipped_target=1,waiting=1,open=1))

    def test_public_summary_whitelist_and_stale_refusal(self):
        config, _, out = self.fixture()
        value = E.compute(config, [], out, 'now')
        value['rows'] = [{'secret':'private'}]
        value['summary']['secret'] = 'private'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(app_data.load_executable(root, out))
            E.write(root, value)
            public = app_data.load_executable(root, out)
            self.assertEqual(set(public), set(E.SUMMARY_FIELDS) | {'computed_at'})
            self.assertNotIn('private', json.dumps(public))
            self.assertIsNone(app_data.load_executable(root, {'computed_at':'different'}))

    def test_publish_refuses_eod_before_git(self):
        with patch('research.lab.run_queue.in_eod_window', return_value=True), patch.object(E.subprocess, 'run') as git:
            with self.assertRaisesRegex(RuntimeError, 'EOD'): E.publish({})
            git.assert_not_called()

    def test_publish_only_own_folder_mock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / E.F.FOLDER / 'outcomes.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'computed_at':'fixed'}))
            def git(args, **kwargs):
                return Mock(returncode=1 if args[1:4] == ['diff','--cached','--quiet'] else 0)
            with patch.object(E.F, 'ROOT', root), patch('research.lab.run_queue.in_eod_window', return_value=False), patch.object(E.subprocess, 'run', side_effect=git) as run:
                E.publish(dict(outcomes_computed_at='fixed',computed_at='now'))
            commands=[c.args[0] for c in run.call_args_list]
            commit=next(c for c in commands if 'commit' in c)
            self.assertIn('--only', commit)
            self.assertEqual(commit[-2:], ['--', E.FOLDER])
            self.assertTrue((root / E.FOLDER / 'latest.json').exists())
