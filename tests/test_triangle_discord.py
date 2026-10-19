import copy
import datetime as dt
import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.lab import triangle15
from research.lab.app_data import next_session, ticket_name
from services.scanner import triangle_discord as D

NOW = dt.datetime(2026, 10, 19, 8, 15, tzinfo=dt.timezone.utc)


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = {'schema_version': 1, 'notifications': {}}
        until = '2026-10-16'
        for _ in range(40):
            until = next_session(until)
        self.order = dict(limit=98., stop=90., target=122., eligible=True, R_multiple=3,
                          valid_until=until, valid_until_basis='regular_NYSE_sessions_estimate',
                          wait_sessions=40, max_hold_sessions=130)
        self.signal = dict(id='TEST-2026-10-16', symbol='TEST', version=D.VERSION,
                           dataset='synthetic', signal_day='2026-10-16', status='waiting',
                           quote={'stale': False, 'price_as_of': '2026-10-16'},
                           order=copy.deepcopy(self.order), market={'ok': True})
        self.ticket = {**self.signal, 'order': copy.deepcopy(self.order), 'example': False,
                       'outcome': {'status': 'waiting'}}
        self.snapshot = dict(as_of='2026-10-16', generated_at='2026-10-19T07:00:00Z', signals=[self.signal])
        (self.root / 'public/app/tickets').mkdir(parents=True)
        (self.root / 'automation').mkdir()
        self.write()

    def write(self):
        (self.root / 'public/app/signals.json').write_text(json.dumps(self.snapshot))
        (self.root / 'public/app' / ticket_name(self.signal['id'])).write_text(json.dumps(self.ticket))
        (self.root / D.STATE).write_text(json.dumps(self.state))

    def notices(self):
        self.write()
        return D.collect(self.root, self.state, NOW)

    def test_preview_is_read_only_and_has_frozen_prices(self):
        before = (self.root / D.STATE).read_bytes()
        result = D.run(self.root, now=NOW)
        text = json.dumps(result, ensure_ascii=False)
        for value in ('98.00', '90.00', '122.00', '40 个交易日', self.order['valid_until']):
            self.assertIn(value, text)
        self.assertEqual(before, (self.root / D.STATE).read_bytes())
        self.assertEqual(result['notices'][0]['payload']['allowed_mentions'], {'parse': []})

    def test_short_template_and_subcent_precision(self):
        payload = D.brief_payload('TEST', 98.1234, 90.1, 122.1936, '2026-12-14')
        embed = payload['embeds'][0]
        fields = embed['fields']
        self.assertEqual([f['value'] for f in fields[:3]], ['**$98.1234**', '**$90.10**', '**$122.1936**'])
        self.assertTrue(all(f['inline'] for f in fields[:3]))
        self.assertFalse(fields[3]['inline'])
        self.assertEqual(embed['footer']['text'], '3w-1.9 · USD')

    def test_simulation_works_without_market_data_and_deduplicates(self):
        (self.root / 'public/app/signals.json').unlink()
        before = (self.root / D.STATE).read_bytes()
        result = D.run(self.root, now=NOW, simulate=True)
        notice = result['notices'][0]
        self.assertTrue(notice['key'].startswith('simulation:'))
        self.assertIn('模拟', notice['payload']['embeds'][0]['title'])
        self.assertNotIn('非真实机会', json.dumps(notice['payload'], ensure_ascii=False))
        self.assertEqual(before, (self.root / D.STATE).read_bytes())
        self.state['notifications'][notice['key']] = {'status': 'sent'}
        self.write()
        self.assertEqual(D.run(self.root, now=NOW, simulate=True)['notices'], [])


    def test_non_actionable_statuses_and_market_gate(self):
        for status in ('open', 'closed', 'cancelled', 'skipped', 'unavailable'):
            self.signal['status'] = status
            self.assertEqual(self.notices(), [])
        self.signal['status'] = 'waiting'
        self.signal['order']['eligible'] = False
        self.assertEqual(self.notices(), [])
        self.signal['order']['eligible'] = True
        self.signal['market']['ok'] = False
        with self.assertRaises(ValueError): self.notices()

    def test_fail_closed_for_mismatches_and_examples(self):
        original = copy.deepcopy(self.ticket)
        for field, value in [('example', True), ('version', '3w-1.7'), ('symbol', 'OTHER')]:
            self.ticket = copy.deepcopy(original)
            self.ticket[field] = value
            with self.assertRaises(ValueError): self.notices()
        for field, value in [('target', 120), ('stop', float('nan')), ('wait_sessions', 56),
                             ('valid_until', '2026-12-31'), ('max_hold_sessions', 65)]:
            self.ticket = copy.deepcopy(original)
            self.ticket['order'][field] = value
            with self.assertRaises(ValueError): self.notices()
        self.ticket = copy.deepcopy(original)
        self.ticket['outcome']['status'] = 'unverified'
        with self.assertRaises(ValueError): self.notices()

    def test_stale_and_future_inputs(self):
        self.snapshot['as_of'] = '2026-10-15'
        with self.assertRaises(ValueError): self.notices()
        self.snapshot['as_of'] = '2026-10-16'
        self.signal['quote']['stale'] = True
        with self.assertRaises(ValueError): self.notices()
        self.signal['quote']['stale'] = False
        self.snapshot['generated_at'] = '2026-10-20T07:00:00Z'
        with self.assertRaises(ValueError): self.notices()

    def test_expired_order_not_sent_even_if_source_waiting(self):
        self.signal['signal_day'] = self.ticket['signal_day'] = '2026-07-01'
        until = self.signal['signal_day']
        for _ in range(40): until = next_session(until)
        self.ticket['order']['valid_until'] = until
        self.assertEqual(self.notices(), [])

    def test_reservation_before_http_and_persistent_dedup(self):
        events = []
        notices = self.notices()
        def persist(state): events.append(copy.deepcopy(state))
        def send(payload):
            self.assertEqual(events[-1]['notifications'][notices[0]['key']]['status'], 'reserved')
            events.append('HTTP')
        D.deliver(notices, self.state, persist, send, NOW)
        self.assertEqual(len(events), 3)
        self.assertEqual(events[-1]['notifications'][notices[0]['key']]['status'], 'sent')
        D.deliver(notices, self.state, persist, send, NOW)
        self.assertEqual(len(events), 3)
        self.assertEqual(self.notices(), [])

    def test_http_timeout_held_without_retry_or_secret_leak(self):
        notices = self.notices()
        def send(payload): raise OSError('secret-webhook-url')
        with self.assertRaisesRegex(RuntimeError, 'unconfirmed') as error:
            D.deliver(notices, self.state, lambda s: None, send, NOW)
        self.assertNotIn('secret-webhook-url', str(error.exception))
        self.assertEqual(self.notices(), [])
        self.assertEqual(self.state['notifications'][notices[0]['key']]['status'], 'reserved')

    def test_failed_reservation_never_calls_http(self):
        def persist(state): raise RuntimeError('push failed')
        with patch.object(D, 'post') as post:
            with self.assertRaises(RuntimeError):
                D.deliver(self.notices(), self.state, persist, post, NOW)
            post.assert_not_called()

    def test_calendar_weekend_holiday_dst(self):
        self.assertEqual(D.latest_session(NOW), '2026-10-16')
        self.assertEqual(D.latest_session(dt.datetime(2026, 12, 25, 23, tzinfo=dt.timezone.utc)), '2026-12-24')
        self.assertEqual(D.latest_session(dt.datetime(2026, 11, 2, 20, tzinfo=dt.timezone.utc)), '2026-10-30')

    def test_frozen_trade_matches_message_target_and_wait(self):
        self.assertEqual(triangle15.WAIT, self.order['wait_sessions'])
        # Synthetic OHLC only: a waiting order fills at the limit then exits at 3R.
        series = dict(open=[100, 99, 110], high=[101, 100, 123], low=[99, 97, 105], close=[100, 99, 122])
        got = triangle15.trade(series, 0, 98, 90, self.order['target'], hold=130)
        self.assertEqual((got['status'], got['entry'], got['exit'], got['R']), ('win', 98, 122, 3))

    def test_durable_state_push_preserves_unrelated_work_and_rejects_race(self):
        def git(*args, cwd=None):
            return subprocess.run(['git', *args], cwd=cwd or self.root,
                                  check=True, capture_output=True).stdout.decode().strip()
        remote = self.root / 'remote.git'
        git('init', '--bare', str(remote))
        git('init', '-b', 'main')
        git('config', 'user.name', 'Test')
        git('config', 'user.email', 'test@example.invalid')
        git('add', 'automation', 'public')
        git('commit', '-m', 'fixture')
        git('remote', 'add', 'origin', str(remote))
        git('push', '-u', 'origin', 'main')
        (self.root / 'unrelated.txt').write_text('must remain staged')
        git('add', 'unrelated.txt')
        self.state['notifications']['key'] = {'status': 'reserved'}
        with patch.object(D, 'in_eod_window', return_value=False):
            D.publish_state(self.root, self.state)
            self.assertEqual(git('diff', '--cached', '--name-only'), 'unrelated.txt')
            self.assertNotIn('unrelated.txt', git('ls-tree', '-r', '--name-only', 'origin/main'))
            durable = json.loads(git('show', 'origin/main:' + D.STATE))
            self.assertEqual(durable['notifications']['key']['status'], 'reserved')
            # Another publisher changed the remote state; stale local copy must stop.
            (self.root / D.STATE).write_text(json.dumps({'schema_version': 1, 'notifications': {}}))
            with self.assertRaisesRegex(RuntimeError, 'upstream'):
                D.publish_state(self.root, self.state)
        with patch.object(D, 'in_eod_window', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'EOD'):
                D.publish_state(self.root, self.state)

    def test_eod_exception_is_simulation_only_and_explicit(self):
        with self.assertRaisesRegex(ValueError, 'simulations'):
            D.run(self.root, allow_eod_window=True, now=NOW)
        with patch.dict('os.environ', {'GITHUB_ACTIONS': 'true', 'GITHUB_REF': 'refs/heads/main',
                                      'DISCORD_WEBHOOK_URL': 'synthetic-secret'}, clear=True):
            with patch.object(D, 'publish_state') as persist, patch.object(D, 'post') as post:
                result = D.run(self.root, send=True, simulate=True, allow_eod_window=True, now=NOW)
                self.assertEqual(result['result'], 'sent')
                self.assertEqual(post.call_count, 1)
                self.assertEqual(persist.call_count, 2)
                self.assertTrue(all(call.kwargs['allow_eod_window'] for call in persist.call_args_list))

    def test_send_restricted_and_secret_missing(self):
        with patch.dict('os.environ', {'GITHUB_ACTIONS': 'false'}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'restricted'): D.run(self.root, send=True, now=NOW)
        with patch.dict('os.environ', {'GITHUB_ACTIONS': 'true', 'GITHUB_REF': 'refs/heads/main'}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'secret'): D.run(self.root, send=True, now=NOW)


if __name__ == '__main__': unittest.main()
