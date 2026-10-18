"""Offline evidence contracts against frozen helpers, including rejected boundaries."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from research.lab import app_data as app, triangle15 as N

FIXTURE = Path(__file__).parent / 'fixtures/app/ticket.json'


class SignalTicketTests(unittest.TestCase):
    def setUp(self):
        f = json.loads(FIXTURE.read_text())
        self.rec, self.series, self.outcomes = f['record'], f['series'], f['outcomes']
        self.market = f['market']

    def ticket(self):
        with patch.object(app, 'market_state', return_value=self.market):
            return app.build_ticket(self.rec, {self.rec['symbol']: self.series}, self.outcomes,
                                    start='2005-01-01', end='2025-06-30')

    def test_passing_ticket_and_frozen_sources(self):
        t = self.ticket()
        self.assertTrue(all(c['pass'] for c in t['checks']))
        self.assertEqual(len(t['weekly']), 60)
        self.assertEqual(len(t['pushes']), 3)
        self.assertGreaterEqual(len(t['bottoms']), 2)
        self.assertEqual(t['trend_line'], [t['pushes'][0], t['pushes'][2]])
        self.assertEqual(t['weekly'][-1]['date'], self.rec['week'])
        self.assertEqual(t['order']['max_hold_sessions'], 130)
        self.assertEqual(t['order']['wait_sessions'], N.WAIT)
        p = self.rec['plan']
        self.assertEqual(t['order']['target'], p['level'] + 3 * (p['level'] - p['stop']))
        checks = {c['id']: c for c in t['checks']}
        W = N.BS.periods(self.series, 'week'); i = W['date'].index(self.rec['week'])
        rows = [dict(date=W['date'][j], **{k:W[k][j] for k in ('open','high','low','close')})
                for j in range(len(W['date'])-1)]
        self.assertEqual(checks['near_bottom']['value']['shape_atr'], N._atr(rows)[i])
        self.assertEqual(checks['plan_stop']['value']['plan_atr'], W['atr'][i])
        self.assertEqual(checks['breadth_over_half']['value']['sample_size'], 232)
        self.assertTrue(checks['pullback_pct']['derived'])

    def test_market_blocked_ticket_identifies_failure(self):
        self.market.update(spy_over_200d=False, ok=False)
        self.rec['market'].update(spy_over_200d=False, ok=False)
        t = self.ticket()
        self.assertEqual([c['id'] for c in t['checks'] if not c['pass']], ['spy_over_200d'])
        self.assertFalse(t['order']['eligible'])
        self.assertEqual(t['outcome']['status'], 'skipped')
        self.assertIsNone(t['outcome']['exit'])
        self.market.update(breadth=.5, breadth_over_half=False)
        self.rec['market']['breadth'] = .5
        self.assertEqual([c['id'] for c in self.ticket()['checks'] if not c['pass']],
                         ['spy_over_200d', 'breadth_over_half'])

    def test_outcome_matches_recorded_R_and_uses_19_dates(self):
        # Deliberately wrong outer (rule 1.7) values must never be copied.
        self.outcomes['outcomes'][0].update(fill='1900-01-01', exit='1900-01-02', R=123)
        o = app.ticket_outcome(self.rec, self.series, self.outcomes)
        self.assertEqual(o['source'], 'frozen trade() recompute, R matches outcomes.json')
        self.assertEqual(o['status'], 'closed')
        self.assertEqual(o['R'], self.outcomes['outcomes'][0]['r19']['R'])
        p = self.rec['plan']; d = self.series['date'].index(self.rec['signal_day'])
        got = N.trade(self.series, d, p['level'], p['stop'], p['level']+3*(p['level']-p['stop']), hold=130)
        self.assertEqual(o['fill_date'], self.series['date'][got['fill_day']])
        self.assertEqual(o['exit_date'], self.series['date'][got['exit_day']])
        self.assertEqual(o['exit'], got['exit'])

    def test_R_or_status_mismatch_is_unverified(self):
        for change in ({'R': 42}, {'status': 'win'}, {'R': None}):
            outcomes = copy.deepcopy(self.outcomes)
            outcomes['outcomes'][0]['r19'].update(change)
            o = app.ticket_outcome(self.rec, self.series, outcomes)
            self.assertEqual(o['status'], 'unverified')
            for key in ('fill_date', 'exit_date', 'exit', 'R'):
                self.assertIsNone(o[key])
            self.assertIn('mismatch', o)

    def test_waiting_missing_and_plan_skipped_are_not_fake_zero_R(self):
        d = self.series['date'].index(self.rec['signal_day'])
        s = {k: v[:d+1] for k,v in self.series.items()}
        outcomes = {'outcomes': [dict(id=self.rec['id'], r19=dict(status='waiting'))]}
        o = app.ticket_outcome(self.rec, s, outcomes)
        self.assertEqual(o['status'], 'waiting')
        self.assertIsNone(o['R'])
        self.assertNotIn('R matches', o['source'])
        self.assertEqual(app.ticket_outcome(self.rec, s, {'outcomes': []})['status'], 'unverified')
        self.rec['plan'].update(go=False, why='monthly veto')
        self.assertEqual(app.ticket_outcome(self.rec, s, {'outcomes': []})['status'], 'skipped')

    def test_open_mark_is_not_an_exit(self):
        p = self.rec['plan']; d = self.series['date'].index(self.rec['signal_day'])
        for end in range(d+2, len(self.series['date'])):
            s = {k:v[:end] for k,v in self.series.items()}
            g = N.trade(s,d,p['level'],p['stop'],p['level']+3*(p['level']-p['stop']),hold=130)
            if g['status'] == 'open':
                outcomes = {'outcomes': [dict(id=self.rec['id'],r19=dict(status='open',R=round(g['R'],4)))]}
                o = app.ticket_outcome(self.rec,s,outcomes)
                self.assertEqual(o['status'],'filled')
                self.assertIsNone(o['exit_date'])
                self.assertIsNone(o['exit'])
                self.assertEqual(o['mark'],g['exit'])
                return
        self.fail('fixture should include an open position')

    def test_derived_shape_gates_match_frozen_decisions_on_boundaries(self):
        sig = N.signals(self.series, start='2005-01-01', end=self.rec['week'])[-1]
        W = N.BS.periods(self.series, 'week'); t = sig['t']
        rows = [dict(date=W['date'][i], **{k:W[k][i] for k in ('open','high','low','close')})
                for i in range(len(W['date'])-1)]
        highs = N.pivots([r['high'] for r in rows], 'high')
        ln = next(l for l in N.T.push_lines(rows,highs,t,broken=None) if l['pushes']==sig['pushes'])
        bots = N.T.bottoms_of(rows,ln['pushes'],t+1)
        atr = N._atr(rows)
        passed = failed = 0
        # Cross pullback, flat-bottom, old-low, stop ATR and target boundaries.
        for depth in (.09,.10,.11,.59,.60,.61):
            for rise in (0,.10,.11):
                for scale in (.1,1,10):
                    b = [(j,rows[ln['pushes'][0]]['high']*(1-depth)*(1+rise if k==len(bots)-1 else 1))
                         for k,(j,v) in enumerate(bots)]
                    ar = list(atr); ar[t] *= scale
                    expected = N._shape(rows,highs,ar,ln,b,t) is not None
                    evidence = app.shape_evidence(rows,highs,ar,ln,b,t)
                    derived = [c for c in evidence if c['derived']]
                    self.assertEqual(all(c['pass'] for c in derived), expected, (depth,rise,scale))
                    passed += expected; failed += not expected
        self.assertGreater(passed,0)
        self.assertGreater(failed,0)

    def test_derived_signal_gates_match_frozen_rejections(self):
        sig = next(s for s in N.signals(self.series,start='2005-01-01') if s['week']==self.rec['week'])
        original = N.BS.periods
        t = sig['t']
        for gate in ('bullish_week','golden_cross','dif_under_zero','tradable_pool'):
            series = copy.deepcopy(self.series)
            if gate == 'tradable_pool':
                series['raw_close'] = series['close'][:]
                series['raw_close'][sig['day']] = 4
            def changed(s,period):
                W = original(s,period)
                if period == 'week':
                    if gate == 'bullish_week': W['open'][t] = W['close'][t]
                    if gate == 'golden_cross': W['dif'][t] = W['dea'][t] - 1
                    if gate == 'dif_under_zero': W['dif'][t],W['dea'][t] = 2,1
                return W
            with patch.object(N.BS,'periods',side_effect=changed):
                frozen = N.signals(series,start='2005-01-01',end=self.rec['week'])
                checks,_,_ = app.ticket_checks(series,sig,self.market,start='2005-01-01',end=self.rec['week'])
            self.assertNotIn(self.rec['week'],[r['week'] for r in frozen],gate)
            self.assertFalse(next(c['pass'] for c in checks if c['id']==gate),gate)

    def test_cooldown_replay_matches_frozen_shape_calls(self):
        found = []
        original = N._shape
        def capture(*args):
            got = original(*args)
            if got:
                found.append(got['t'])
            return got
        with patch.object(N,'_shape',side_effect=capture):
            signals = N.signals(self.series,start='2005-01-01',end=self.rec['week'])
        sig = next(s for s in signals if s['week']==self.rec['week'])
        previous = [t for t in found if t<sig['t']]
        t = self.ticket()
        check = next(c for c in t['checks'] if c['id']=='cooldown')
        self.assertEqual(check['value']['previous_shape_index'],previous[-1] if previous else None)

    def test_determinism_size_guard_and_path_validation(self):
        t = self.ticket(); name = app.ticket_name(t['id'])
        payload = {**dict.fromkeys(app.FILES,{}),name:t,'tickets/index.json':[]}
        first = app.encode(payload)
        self.assertEqual(first,app.encode({**payload,name:self.ticket()}))
        self.assertLess(len(first[name]),60_000)
        t['padding']='x'*60_000
        with self.assertRaisesRegex(ValueError,'60 KB'):
            app.encode(payload)
        for ident in ('../escape','index','a/b','a.json'):
            with self.assertRaises(ValueError):app.ticket_name(ident)
        with self.assertRaises(ValueError):app.encode({**dict.fromkeys(app.FILES,{}),'other.json':{}})

    def test_append_only_except_outcome_and_unchanged_bytes(self):
        t = self.ticket(); name = app.ticket_name(t['id']); old = app.json_bytes(t)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            app.write({name:old},folder)
            stamp = (folder/name).stat().st_mtime_ns
            new = copy.deepcopy(t); new['weekly']=[]; new['order']['limit']=999
            app.write({name:app.json_bytes(new)},folder)
            self.assertEqual((folder/name).read_bytes(),old)
            self.assertEqual((folder/name).stat().st_mtime_ns,stamp)
            new['outcome']['status']='unverified'
            app.write({name:app.json_bytes(new)},folder)
            result=json.loads((folder/name).read_text())
            self.assertEqual(result['weekly'],t['weekly'])
            self.assertEqual(result['order'],t['order'])
            self.assertEqual(result['outcome'],new['outcome'])

    def test_existing_ticket_skips_evidence_rebuild_and_index_tracks_outcome(self):
        t=self.ticket(); name=app.ticket_name(t['id'])
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); app.write({name:app.json_bytes(t)},folder)
            self.outcomes['outcomes'][0]['r19']['R']=99
            with patch.object(app,'build_ticket',side_effect=AssertionError('immutable evidence')):
                result=app.ticket_payloads([self.rec],self.outcomes,{self.rec['dataset']:{self.rec['symbol']:self.series}},folder,start='2005-01-01')
            self.assertEqual(result[name]['weekly'],t['weekly'])
            self.assertEqual(result['tickets/index.json'][0]['status'],'unverified')
            self.assertIsNone(result['tickets/index.json'][0]['R'])

    def test_fresh_dataset_uses_shared_SPY_without_adding_it_to_breadth(self):
        spy = copy.deepcopy(self.series)
        spy['close'] = list(range(1, len(spy['date'])+1))
        px = {'A': self.series}
        day = self.rec['signal_day']
        state = app.market_state(px,day,spy=spy)
        self.assertTrue(state['spy_over_200d'])
        self.assertEqual(state['breadth_sample'],1)
        old = app.triangle_forward.PX, app.triangle_forward.SPY, app.triangle_forward.BREADTH
        try:
            app.triangle_forward.PX, app.triangle_forward.SPY, app.triangle_forward.BREADTH = px,spy,{}
            expected = app.triangle_forward.market(day)
        finally:
            app.triangle_forward.PX, app.triangle_forward.SPY, app.triangle_forward.BREADTH = old
        self.assertEqual({k:state[k] for k in expected},expected)
        self.assertEqual(list(px),['A'])

    def test_future_prices_do_not_enter_evidence_or_chart(self):
        first = self.ticket()
        d = self.series['date'].index(self.rec['signal_day'])
        for k in ('open','high','low','close','volume','raw_close'):
            if k in self.series:
                self.series[k][d+1:] = [v*2 for v in self.series[k][d+1:]]
        second = self.ticket()
        for key in ('checks','weekly','pushes','bottoms','trend_line','order'):
            self.assertEqual(first[key],second[key],key)

    def test_load_build_wires_tickets_and_index_with_real_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); forward=root/app.FORWARD; forward.mkdir(parents=True)
            (forward/'signals.jsonl').write_text(json.dumps(self.rec)+'\n')
            (forward/'config.json').write_text(json.dumps(dict(start='2005-01-01')))
            outcomes=dict(self.outcomes,computed_at='2012-12-01T00:00:00Z')
            (forward/'outcomes.json').write_text(json.dumps(outcomes))
            (root/'research/lab/app').mkdir()
            (root/'research/lab/app/record_facts.json').write_text('[]')
            px={self.rec['symbol']:self.series,'SPY':self.series}
            with patch.object(app,'frozen_prices',return_value=px), patch.object(app,'market_state',return_value=self.market):
                payload=app.load_build(root,generated_at='2012-12-01T00:00:00Z')
            name=app.ticket_name(self.rec['id'])
            self.assertEqual(payload[name]['outcome']['status'],'closed')
            self.assertEqual(payload['tickets/index.json'],[dict(id=self.rec['id'],symbol=self.rec['symbol'],
                signal_week=self.rec['week'],status='closed',R=-1.0)])
            self.assertIn(name,app.encode(payload))

    def test_publish_preserves_remote_evidence_and_uses_same_window_guard(self):
        t=self.ticket(); name=app.ticket_name(t['id']); old=app.json_bytes(t)
        new=copy.deepcopy(t); new['weekly']=[]; new['outcome']['status']='unverified'
        payload={name:app.json_bytes(new),'tickets/index.json':b'[]\n'}
        writes=[]
        def git(args,**kwargs):
            command=args[1]
            if command=='show':
                path=args[2].split(':',1)[1]
                data=old if path=='public/app/'+name else (app.ROOT/path).read_bytes()
            elif command=='ls-tree':data=('public/app/'+name+'\n').encode()
            elif command=='hash-object':writes.append(kwargs['input']);data=b'object\n'
            else:data=(command+'\n').encode()
            return SimpleNamespace(stdout=data)
        with patch.object(app,'in_eod_window',return_value=False),patch.object(app.subprocess,'run',side_effect=git):
            self.assertTrue(app.publish(payload))
        saved=json.loads(writes[0]);self.assertEqual(saved['weekly'],t['weekly'])
        self.assertEqual(saved['outcome']['status'],'unverified')
        with patch.object(app,'in_eod_window',return_value=True),patch.object(app.subprocess,'run') as run:
            with self.assertRaises(RuntimeError):app.publish(payload)
            run.assert_not_called()


if __name__=='__main__':
    unittest.main()
