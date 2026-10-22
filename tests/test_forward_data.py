"""Offline projection tests; frozen twin oracle and explicit scoring boundaries."""
import copy
import hashlib
import json
import random
import statistics
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from research.lab import app_data as app


class ForwardTests(unittest.TestCase):
    def setUp(self):
        f=json.loads(Path('tests/fixtures/app/ticket.json').read_text())
        self.rec,self.s=f['record'],f['series']
        self.out={**f['outcomes'],'computed_at':'2013-01-01T00:00:00Z'}
        self.px={self.rec['symbol']:self.s}
        self.asof=self.s['date'][-1]

    def project(self, records=None, calls=()):
        return app.forward_data([self.rec] if records is None else records,self.out,
            {self.rec['dataset']:self.px},calls,[],self.asof,'fixed')

    def test_empty_is_null_not_zero_and_deterministic(self):
        result=self.project([])
        self.assertEqual(result['summary']['signals'],0)
        self.assertIsNone(result['summary']['average_R'])
        self.assertIsNone(result['summary']['beat_random_share'])
        self.assertEqual(result['cumulative_R'],[])
        self.assertEqual(app.json_bytes(result),app.json_bytes(self.project([])))
        encoded=app.encode({**dict.fromkeys(app.FILES,{}),'forward.json':result})
        self.assertLess(len(encoded['forward.json']),2_000_000)
        result['padding']='x'*2_000_001
        with self.assertRaises(ValueError): app.encode({**dict.fromkeys(app.FILES,{}),'forward.json':result})

    def test_replay_matches_frozen_sampling_and_mean(self):
        # Deliberately reverse the pool; sorting it would change this sample.
        pool=[f'T{i:02}' for i in range(39,-1,-1)]
        for i,sym in enumerate(pool):
            q=copy.deepcopy(self.s)
            d=q['date'].index(self.rec['signal_day'])
            # Different post-signal paths make the mean sensitive to sampling.
            for j in range(d+1,len(q['date'])):
                for k in ('open','high','low','close'): q[k][j]*=1+(i%5)*.02
            self.px[sym]=q
        W=app.triangle15.BS.periods(self.s,'week')
        m=(self.rec['plan']['level']-self.rec['plan']['stop'])/W['atr'][W['date'].index(self.rec['week'])]
        with patch.object(app.triangle_forward,'PX',self.px):
            expected=app.triangle_forward._twins(self.rec,pool,30,m,3.,130)
        signal=app.ticket_outcome(self.rec,self.s,self.out)
        result=app.twin_projection(self.rec,self.px,pool,{'r19':{'random_R':expected}},signal,self.asof)
        self.assertEqual(result['twins'],'verified')
        self.assertEqual(result['gross_mean_R'],expected)
        seed=int(hashlib.sha256(self.rec['id'].encode()).hexdigest()[:8],16)
        self.assertEqual([r['symbol'] for r in result['samples']],random.Random(seed).sample(pool,30))
        rs=[r['net_R'] for r in result['samples'] if r['net_R'] is not None]
        self.assertEqual(result['median_R'],statistics.median(rs))
        self.assertEqual(result['beat_share'],sum(app.forward_judge.net_r(signal['fill_price'],signal['exit'],self.rec['plan']['stop'])>r for r in rs)/len(rs))
        for recorded in (99,None):
            bad=app.twin_projection(self.rec,self.px,pool,{'r19':{'random_R':recorded}},signal,self.asof)
            self.assertEqual(bad['twins'],'unverified')
            for key in ('median_R','beat_share','samples','mean_R'): self.assertIsNone(bad[key])
            self.assertEqual(bad['mismatch']['recomputed_mean_R'],expected)

    def test_net_r_and_no_private_calls_in_public_output(self):
        calls=[dict(id=self.rec['id'],choice='no',private_marker='NEVER_PUBLIC')]
        result=self.project(calls=calls)
        row=result['signals'][0]
        outcome=app.ticket_outcome(self.rec,self.s,self.out)
        e,x,stop=outcome['fill_price'],outcome['exit'],self.rec['plan']['stop']
        expected=(x*.999-e*1.001)/(e-stop)
        self.assertAlmostEqual(row['R'],expected)
        self.assertEqual(row['gross_R'],-1)
        self.assertAlmostEqual(result['cumulative_R'][0]['R'],expected)
        self.assertAlmostEqual(result['summary']['average_R'],expected)
        self.assertEqual(row['lifecycle'],dict(status='stopped',date=outcome['exit_date']))
        self.assertEqual(row['alert_id'],'A-'+self.rec['id'][:6])
        self.assertNotIn('blind',app.json_bytes(result).decode())
        self.assertNotIn('NEVER_PUBLIC',app.json_bytes(result).decode())
        self.out['outcomes'][0]['r19']['R']=42
        result=self.project(calls=calls)
        self.assertEqual(result['signals'][0]['status'],'unverified')
        self.assertIsNone(result['signals'][0]['R'])
        self.assertEqual(result['cumulative_R'],[])

    def test_lifecycle_and_saved_alert_id(self):
        for status,kind,day in [('waiting','waiting',None),('filled','filled','2013-01-01'),
                                ('cancelled','expired','2013-01-02'),('skipped','skipped',None)]:
            o=dict(status=status,R=None,source='fixture',fill_date=day if status=='filled' else None,
                   cancel_date=day if status=='cancelled' else None,cancel_reason='no fill in 8 weeks')
            with patch.object(app,'ticket_outcome',return_value=o):
                r=app.forward_data([self.rec],self.out,{self.rec['dataset']:self.px},(),[],self.asof,'fixed',
                    discord_state={'notifications':{'3w-1.9:'+self.rec['id']:{'alert_id':'A-12345678'}}})['signals'][0]
            self.assertEqual(r['alert_id'],'A-12345678')
            self.assertEqual(r['lifecycle'],dict(status=kind,date=day))
            self.assertIsNone(r['R'])

    def test_judging_missing_stale_empty_and_private_allowlist(self):
        empty=app.forward_judge.score([])
        empty['computed_at']=self.out['computed_at']
        for card in (None,dict(empty,computed_at='old')):
            result=app.public_judging(card,self.out)
            self.assertEqual(result['verdict'],'本次运行未生成计分')
            self.assertIsNone(result['completed'])
            self.assertIsNone(result['alarm1'])
        result=app.public_judging(empty,self.out)
        self.assertEqual((result['completed'],result['next_checkpoint'],result['to_go']),(0,30,30))
        self.assertEqual(result['verdict'],'继续记录，未证明')
        self.assertFalse(result['alarm1'])
        empty.update(verdict='证明有效',paper={'satellite':{'secret':'NEVER_PUBLIC'}},rows=[{'secret':'NEVER_PUBLIC'}],
                     checkpoints=[dict(k=100,scored=100,unscorable=0,mean_d=.5,t=2,alarm1=False,verdict='证明有效',secret='NEVER_PUBLIC')])
        result=app.public_judging(empty,self.out)
        self.assertEqual(result['verdict'],app.PUBLIC_PAPER)
        self.assertEqual(result['checkpoints'][0]['verdict'],app.PUBLIC_PAPER)
        self.assertNotIn('NEVER_PUBLIC',app.json_bytes(result).decode())
        self.assertEqual(result['thresholds']['satellite_drawdown_gt'],.25)
        with tempfile.TemporaryDirectory(dir=app.ROOT/'work') as folder:
            root=Path(folder)
            self.assertIsNone(app.load_scorecard(root,self.out))
            (root/'work/forward-judge').mkdir(parents=True)
            path=root/'work/forward-judge/latest.json'
            path.write_text(json.dumps(empty))
            self.assertEqual(app.load_scorecard(root,self.out),empty)
            self.assertIsNone(app.load_scorecard(root,{'computed_at':'other run'}))

    def test_scheduled_loader_reads_scorecard_without_reading_private_judgements(self):
        with tempfile.TemporaryDirectory(dir=app.ROOT/'work') as folder:
            root=Path(folder)
            (root/app.FORWARD).mkdir(parents=True)
            (root/app.FORWARD/'outcomes.json').write_text(json.dumps(self.out))
            (root/'research/lab/app').mkdir()
            (root/'research/lab/app/record_facts.json').write_text('[]')
            (root/'work/forward-judge').mkdir(parents=True)
            card=dict(app.forward_judge.score([]),computed_at=self.out['computed_at'])
            (root/'work/forward-judge/latest.json').write_text(json.dumps(card))
            with patch.object(app.triangle_forward,'load_records',return_value=[]), \
                 patch.object(app.triangle_forward,'load_judgements',side_effect=AssertionError('private calls')), \
                 patch.object(app,'frozen_prices',return_value={}), \
                 patch.object(app,'extend_prices',return_value={'SPY':{'date':['2013-01-01']}}), \
                 patch.object(app,'build',return_value={}),patch.object(app,'ticket_payloads',return_value={}):
                payload=app.load_build(root,generated_at='fixed')['forward.json']
            self.assertEqual(payload['judging']['completed'],0)
            self.assertEqual(payload['judging']['status'],'available')
            self.assertNotIn('blind',payload['conventions'])

    def test_horizons_require_exact_mature_session(self):
        s={'date':['2026-10-02','2026-10-09','2026-10-30'],'close':[100,110,90]}
        result=app.horizon_moves(s,'2026-10-02','2026-10-09')
        self.assertAlmostEqual(result['1w']['move_pct'],10)
        self.assertIsNone(result['4w'])
        self.assertIsNone(result['13w'])
        s['date'].pop(1);s['close'].pop(1)
        self.assertIsNone(app.horizon_moves(s,'2026-10-02','2026-11-30')['1w'])

    def test_publish_refuses_new_upstream_blind_call_before_any_write(self):
        from types import SimpleNamespace
        commands=[]
        def git(args, **kwargs):
            commands.append(args[1])
            if args[1]=='show':
                data=(app.ROOT/args[2].split(':',1)[1]).read_bytes()
            elif args[1]=='ls-tree':
                data=b'research/lab/forward/triangle/judgements.jsonl\n'
            else: data=b'parent\n'
            return SimpleNamespace(stdout=data)
        with patch.object(app,'in_eod_window',return_value=False),patch.object(app.subprocess,'run',side_effect=git):
            with self.assertRaisesRegex(RuntimeError,'judgements.jsonl'):
                app.publish({'forward.json':b'{}'})
        self.assertNotIn('hash-object',commands)
        self.assertNotIn('commit-tree',commands)
        self.assertNotIn('push',commands)

    def test_example_is_generated_separately_with_frozen_replay(self):
        t=app.example_ticket()
        self.assertTrue(t['example'])
        self.assertEqual(t['outcome']['status'],'closed')
        p=self.rec['plan']
        got=app.triangle15.trade(self.s,self.s['date'].index(self.rec['signal_day']),
            p['level'],p['stop'],p['level']+3*(p['level']-p['stop']),hold=130)
        self.assertEqual(t['outcome']['fill_date'],self.s['date'][got['fill_day']])
        self.assertEqual(t['outcome']['exit_date'],self.s['date'][got['exit_day']])
        self.assertEqual(t['outcome']['exit'],got['exit'])
        self.assertEqual(t['outcome']['R'],got['R'])
        self.assertIn('not a forward record',t['outcome']['source'])
        self.assertLess(len(app.json_bytes(t)),60_000)
        self.assertEqual(json.loads(Path('public/app/tickets/index.json').read_text()),[])

if __name__=='__main__': unittest.main()
