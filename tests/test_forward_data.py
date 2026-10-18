"""Offline projection tests; frozen twin oracle and explicit scoring boundaries."""
import copy
import hashlib
import json
import random
import statistics
import unittest
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
        self.assertEqual(result['mean_R'],expected)
        seed=int(hashlib.sha256(self.rec['id'].encode()).hexdigest()[:8],16)
        self.assertEqual([r['symbol'] for r in result['samples']],random.Random(seed).sample(pool,30))
        rs=[r['R'] for r in result['samples'] if r['R'] is not None]
        self.assertEqual(result['median_R'],statistics.median(rs))
        self.assertEqual(result['beat_share'],sum(signal['R']>r for r in rs)/len(rs))
        for recorded in (99,None):
            bad=app.twin_projection(self.rec,self.px,pool,{'r19':{'random_R':recorded}},signal,self.asof)
            self.assertEqual(bad['twins'],'unverified')
            for key in ('median_R','beat_share','samples','mean_R'): self.assertIsNone(bad[key])
            self.assertEqual(bad['mismatch']['recomputed_mean_R'],expected)

    def test_scoring_closed_win_loss_zero_and_unfilled(self):
        for status,R,choice,score in [('closed',3,'do','right'),('closed',-1,'do','wrong'),
            ('closed',-1,'no','right'),('closed',0,'no','right'),('closed',0,'do','wrong'),
            ('closed',3,None,'not yet scored'),('waiting',None,'do','not yet scored'),
            ('filled',.2,'no','not yet scored'),('skipped',None,'no','not yet scored')]:
            outcome=dict(status=status,R=R,source='fixture',source_status='win' if R and R>0 else 'loss',exit_date='2013-01-01' if status=='closed' else None)
            with patch.object(app,'ticket_outcome',return_value=outcome):
                result=self.project(calls=[dict(id=self.rec['id'],choice=choice)])
            row=result['signals'][0]
            self.assertEqual(row['blind']['score'],score,(status,R,choice))
            self.assertEqual(result['summary']['closed'],int(status=='closed'))
            if status!='closed':self.assertIsNone(row['R'])

    def test_first_blind_call_and_real_outcome_mismatch(self):
        calls=[dict(id=self.rec['id'],choice='no'),dict(id=self.rec['id'],choice='do')]
        r=self.project(calls=calls)
        self.assertEqual(r['signals'][0]['blind']['score'],'right')
        self.assertEqual(r['cumulative_R'][0]['R'],-1)
        self.out['outcomes'][0]['r19']['R']=42
        r=self.project(calls=calls)
        self.assertEqual(r['signals'][0]['status'],'unverified')
        self.assertEqual(r['signals'][0]['blind']['score'],'not yet scored')
        self.assertEqual(r['cumulative_R'],[])

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

    def test_example_is_generated_separately_and_never_verified(self):
        t=app.example_ticket()
        self.assertTrue(t['example'])
        self.assertEqual(t['outcome']['status'],'unverified')
        self.assertLess(len(app.json_bytes(t)),60_000)
        self.assertEqual(json.loads(Path('public/app/tickets/index.json').read_text()),[])

if __name__=='__main__': unittest.main()
