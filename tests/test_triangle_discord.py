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
        text = payload['content']
        self.assertIn('限价入场　**$98.1234**\n', text)
        self.assertIn('止损　　　**$90.10**\n', text)
        self.assertIn('止盈　　　**$122.1936** · 3R\n\n', text)
        self.assertIn('有效至约 **2026-12-14**', text)
        self.assertNotIn(D.VERSION, text)
        self.assertNotIn('embeds', payload)

    def test_simulation_works_without_market_data_and_deduplicates(self):
        (self.root / 'public/app/signals.json').unlink()
        before = (self.root / D.STATE).read_bytes()
        result = D.run(self.root, now=NOW, simulate=True)
        notice = result['notices'][0]
        self.assertTrue(notice['key'].startswith('simulation:'))
        self.assertIn('模拟', notice['payload']['content'])
        self.assertNotIn('非真实机会', json.dumps(notice['payload'], ensure_ascii=False))
        self.assertEqual(before, (self.root / D.STATE).read_bytes())
        self.state['notifications'].update({n['key']: {'status': 'sent'} for n in result['notices']})
        (self.root / D.SIM_STATE).write_text(json.dumps(self.state))
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
        # Simulation ledger is a separate durable file, including its first publication.
        (self.root / D.STATE).write_text(git('show', 'origin/main:' + D.STATE) + '\n')
        production = git('show', 'origin/main:' + D.STATE)
        sim = {'schema_version': 1, 'notifications': {'simulation:test': {'status': 'reserved'}}}
        with patch.object(D, 'in_eod_window', return_value=False):
            D.publish_state(self.root, sim, state_path=D.SIM_STATE)
        self.assertEqual(git('show', 'origin/main:' + D.STATE), production)
        self.assertEqual(json.loads(git('show', 'origin/main:' + D.SIM_STATE)), sim)
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
                self.assertEqual(post.call_count, 7)
                self.assertEqual(persist.call_count, 14)
                self.assertTrue(all(call.kwargs['allow_eod_window'] for call in persist.call_args_list))

    def test_send_restricted_and_secret_missing(self):
        with patch.dict('os.environ', {'GITHUB_ACTIONS': 'false'}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'restricted'): D.run(self.root, send=True, now=NOW)
        with patch.dict('os.environ', {'GITHUB_ACTIONS': 'true', 'GITHUB_REF': 'refs/heads/main'}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'secret'): D.run(self.root, send=True, now=NOW)


class LifecycleTests(unittest.TestCase):
    setUp = NotificationTests.setUp
    write = NotificationTests.write
    notices = NotificationTests.notices

    def alerted(self):
        self.state['notifications'][f'{D.VERSION}:{self.signal["id"]}'] = {'status': 'sent', 'alert_id':'A-TEST-2'}

    def test_share_limits_and_tiny_equity(self):
        self.assertEqual(D.shares(100000, 100, 80), (100, 2000, '风险2%'))
        self.assertEqual(D.shares(100000, 100, 99), (200, 200, '仓位20%'))
        self.assertEqual(D.shares(1, 100, 99)[0], 0)
        self.assertIn('每 $10,000：', D.brief_payload('X',100,99,103,'2026-12-01')['content'])
        for e in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError): D.shares(e,100,99)

    def test_id_collision_snapshot_state_and_stability(self):
        snapshot = {'signals':[{'id':'abcdef11'}, {'id':'abcdef22'}]}
        ids = D.alert_ids(snapshot, self.state)
        self.assertEqual(ids, {'abcdef11':'A-abcdef11','abcdef22':'A-abcdef22'})
        self.state['notifications'][D.VERSION+':abcdef11'] = {'alert_id':'A-abcdef11'}
        self.assertEqual(D.alert_ids({'signals':[{'id':'abcdef22'}]}, self.state), ids)
        with self.assertRaises(ValueError):
            D.alert_ids({'signals':[{'id':'abcdefgh1'},{'id':'abcdefgh2'}]}, self.state)

    def test_all_events_order_and_dedupe(self):
        self.alerted()
        for kind, event, price in [('loss','stopped',90),('win','target',122),('time','time',105)]:
            self.signal['status'] = 'closed'
            self.ticket['outcome'] = dict(status='closed', source_status=kind, fill_date='2026-10-16',
                fill_price=98, exit_date='2026-10-16', exit=price)
            notices = self.notices()
            self.assertEqual([n['key'].split(':')[-1] for n in notices], ['filled',event])
            self.assertIn(f'{(price*.999-98*1.001)/8:+.4f}',notices[-1]['payload']['content'])
        D.deliver(notices, self.state, lambda s: None, lambda p: None, NOW)
        self.assertEqual(self.notices(), [])

    def test_open_fill_and_no_unalerted_followup(self):
        self.signal['status']='open'
        self.ticket['outcome']=dict(status='filled', fill_date='2026-10-16', fill_price=97)
        self.assertEqual(self.notices(), [])
        self.alerted()
        self.assertEqual(len(self.notices()),1)
        self.assertIn('$97.00',self.notices()[0]['payload']['content'])

    def test_cancel_expiry_confirmation(self):
        self.alerted()
        self.signal['status']='cancelled'
        for why, event, price in [('stop before the fill','cancelled',89),
                                 ('target before the fill','cancelled',122),
                                 ('no fill in 8 weeks','expired',None)]:
            self.ticket['outcome']=dict(status='cancelled', cancel_reason=why,
                cancel_date='2026-10-16',confirmed_date='2026-10-16',cancel_price=price)
            self.assertTrue(self.notices()[0]['key'].endswith(':'+event))
        self.ticket['outcome']['confirmed_date']='2026-10-19'
        with self.assertRaises(ValueError): self.notices()

    def test_followup_failure_retains_reservation(self):
        self.alerted()
        self.signal['status']='open'
        self.ticket['outcome']=dict(status='filled', fill_date='2026-10-16',fill_price=98)
        notices=self.notices()
        def fail(p): raise RuntimeError('sensitive')
        with self.assertRaisesRegex(RuntimeError,'unconfirmed'):
            D.deliver(notices,self.state,lambda s:None,fail,NOW)
        self.assertEqual(self.notices(),[])
        self.assertEqual(self.state['notifications'][notices[0]['key']]['status'],'reserved')

    def test_preview_never_reads_equity_secret(self):
        with patch.dict('os.environ',{'SV_ACCOUNT_EQUITY_USD':'SECRET-NOT-A-NUMBER'}):
            result=D.run(self.root,now=NOW)
        self.assertNotIn('SECRET',json.dumps(result))
        self.assertIn('每 $10,000',json.dumps(result,ensure_ascii=False))

    def test_simulation_send_never_writes_production(self):
        before=(self.root/D.STATE).read_bytes()
        with patch.dict('os.environ',{'GITHUB_ACTIONS':'true','GITHUB_REF':'refs/heads/main','DISCORD_WEBHOOK_URL':'fake'},clear=True):
            with patch.object(D,'publish_state') as persist, patch.object(D,'post'):
                D.run(self.root,send=True,simulate=True,now=NOW)
        self.assertTrue(all(c.kwargs['state_path']==D.SIM_STATE for c in persist.call_args_list))
        self.assertEqual(before,(self.root/D.STATE).read_bytes())

    def test_secret_only_in_sent_payload_not_ledger_or_result(self):
        with patch.dict('os.environ', {'GITHUB_ACTIONS':'true','GITHUB_REF':'refs/heads/main',
                'DISCORD_WEBHOOK_URL':'fake-webhook', 'SV_ACCOUNT_EQUITY_USD':'1234567'}, clear=True):
            with patch.object(D,'publish_state') as persist, patch.object(D,'post') as post:
                result=D.run(self.root,send=True,now=NOW)
                self.assertIn('实盘账户',post.call_args.args[1]['content'])
                persisted=json.dumps(persist.call_args.args[1])
                for text in (persisted,json.dumps(result)):
                    self.assertNotIn('1234567',text)
                    self.assertNotIn('实盘账户',text)
                    self.assertNotIn('fake-webhook',text)
        self.assertEqual(persist.call_args.args[1]['notifications'][D.VERSION+':'+self.signal['id']]['alert_id'],'A-TEST-2')

    def test_followup_keeps_identity_and_freshness_guards(self):
        self.alerted()
        self.signal['status']='open'
        self.ticket['outcome']=dict(status='filled',fill_date='2026-10-16',fill_price=98)
        self.ticket['symbol']='OTHER'
        with self.assertRaises(ValueError): self.notices()
        self.ticket['symbol']='TEST'
        self.signal['quote']['stale']=True
        with self.assertRaises(ValueError): self.notices()
        self.signal['quote']['stale']=False
        self.ticket['outcome']['fill_date']='2026-10-19'
        with self.assertRaises(ValueError): self.notices()

    def test_ticket_projection_frozen_expiry_boundary_and_prices(self):
        from research.lab.app_data import ticket_outcome
        start=dt.date(2026,1,1)
        dates=[(start+dt.timedelta(days=i)).isoformat() for i in range(42)]
        series=dict(date=dates,open=[100]*42,high=[101]*42,low=[99]*42,close=[100]*42)
        rec=dict(id='fixture',signal_day=dates[0],plan=dict(go=True,level=98,stop=90),market={'ok':True})
        def project(q):
            raw=triangle15.trade(q,0,98,90,122,hold=130)
            return ticket_outcome(rec,q,{'outcomes':[dict(id='fixture',r19=raw)]})
        short={k:v[:41] for k,v in series.items()}
        self.assertEqual(project(short)['status'],'waiting')
        expired=project(series)
        self.assertEqual(expired['cancel_date'],dates[40])
        self.assertEqual(expired['confirmed_date'],dates[41])
        series['low'][1]=97
        self.assertEqual(project(series)['fill_price'],98)
        series['low'][1]=89
        stopped=project(series)
        self.assertEqual(stopped['source_status'],'loss')
        self.assertEqual(stopped['fill_date'],stopped['exit_date'])
        self.assertEqual(stopped['exit'],90)
        series['open'][1]=89
        cancelled=project(series)
        self.assertEqual(cancelled['cancel_price'],89)
        self.assertEqual(cancelled['cancel_date'],dates[1])
        series['open'][1]=100;series['low'][1]=99;series['high'][1]=123
        self.assertEqual(project(series)['cancel_price'],122)


if __name__ == '__main__': unittest.main()


class CancelReasonTests(unittest.TestCase):
    def test_cancel_and_expiry_lines(self):
        from services.scanner import triangle_discord as td
        c = td.follow_payload('X', 'A-000001', 'cancelled', '2026-01-02', 10.0, reason='stop before the fill')['content']
        self.assertIn('原因：成交前先碰到止损', c)
        self.assertIn('如有挂单，请撤销', c)
        e = td.follow_payload('X', 'A-000001', 'expired', '2026-01-02')['content']
        self.assertNotIn('原因', e)
        self.assertIn('如有挂单，请撤销', e)
        f = td.follow_payload('X', 'A-000001', 'filled', '2026-01-02', 10.0)['content']
        self.assertNotIn('撤销', f)
