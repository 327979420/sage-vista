import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from research.lab import eye_judge as E
from tests.test_forward_judge import rows


class EyeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (E.ROOT/'work/eye-judge').mkdir(parents=True, exist_ok=True)

    def bank(self, n, answered, bank='hk1'):
        tmp = tempfile.TemporaryDirectory(dir=E.ROOT/'work/eye-judge')
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        keys = {'cases': [{'id': f'{bank}-{i:03}', 'trade': {'net_R': i/10}, 'period': 'day'} for i in range(n)]}
        (root/'keys.json').write_text(json.dumps(keys))
        (root/'answers').mkdir()
        for i in range(answered):
            (root/'answers'/f'{bank}-{i:03}.json').write_text(json.dumps({'choice': 'do' if i%2 else 'no', 'answered_at': (dt.datetime(2026,10,19,tzinfo=dt.timezone.utc)+dt.timedelta(minutes=i)).isoformat()}))
        return root

    def test_empty_bank(self):
        root = self.bank(34, 0)
        r = E.load_bank('hk1', root/'answers', root/'keys.json')
        self.assertEqual((r['revealed'], r['unanswered']), (0, 34))
        self.assertIsNone(r['ci95'])

    def test_hk_last_four_not_revealed_at_33(self):
        root = self.bank(34, 33)
        r = E.load_bank('hk1', root/'answers', root/'keys.json')
        self.assertEqual((r['revealed'], r['unrevealed_answered'], r['unanswered']), (30, 3, 1))

    def test_hk_all_34_revealed(self):
        root = self.bank(34, 34)
        self.assertEqual(E.load_bank('hk1', root/'answers', root/'keys.json')['revealed'], 34)

    def test_answer_order_not_key_order(self):
        root = self.bank(20, 11, 'daily1')
        p = root/'answers/daily1-000.json'
        a = json.loads(p.read_text()); a['answered_at'] = '2026-10-19T01:00:00Z'; p.write_text(json.dumps(a))
        r = E.load_bank('daily1', root/'answers', root/'keys.json')
        self.assertNotIn('daily1-000', [x['id'] for x in r['rows']])
        self.assertIn('daily1-010', [x['id'] for x in r['rows']])

    def test_missing_net_R_stops(self):
        root = self.bank(10, 0)
        k = json.loads((root/'keys.json').read_text()); del k['cases'][0]['trade']['net_R']
        (root/'keys.json').write_text(json.dumps(k))
        with self.assertRaises(ValueError): E.load_bank('hk1', None, root/'keys.json')

    def test_missing_choice_stops(self):
        root = self.bank(10, 1)
        (root/'answers/hk1-000.json').write_text('{}')
        with self.assertRaises(ValueError): E.load_bank('hk1', root/'answers', root/'keys.json')

    def test_one_group_ci_undefined(self):
        r = E.eye_stats([{'choice': 'do', 'net_R': 1}]*100, True)
        self.assertIsNone(r['ci95']); self.assertEqual(r['verdict'], '未证明')

    def test_pooled_only_and_reproducible(self):
        rs = [{'choice': 'do' if i%2 else 'no', 'net_R': 1 if i%2 else -1} for i in range(100)]
        self.assertEqual(E.eye_stats(rs)['verdict'], '仅描述')
        a = E.eye_stats(rs, True)
        self.assertEqual(a['verdict'], '眼光有用'); self.assertEqual(a, E.eye_stats(rs, True))
        for r in rs: r['net_R'] *= -1
        self.assertEqual(E.eye_stats(rs, True)['verdict'], '眼光有害')

    def test_below_100_cannot_conclude(self):
        rs = [{'choice': 'do' if i%2 else 'no', 'net_R': 10 if i%2 else -10} for i in range(90)]
        self.assertEqual(E.eye_stats(rs, True)['verdict'], '样本太少，仅供参考')

    def forward(self, n):
        rr = rows(n, True)
        js = []
        for r in rr:
            r['trade']['fill_date'] = '2019-12-31'
            js.append({'id': r['id'], 'choice': 'do', 'judged_at': '2019-12-30T10:00:00Z'})
        return rr, js

    def test_forward_zero(self):
        r = E.forward_eye([], [])
        self.assertEqual(r['completed'], 0); self.assertEqual(r['next_checkpoint'], 30)

    def test_forward_boundary_and_all_prefixes(self):
        self.assertFalse(E.forward_eye(*self.forward(29))['checkpoints'])
        self.assertEqual([x['k'] for x in E.forward_eye(*self.forward(101))['checkpoints']], [30, 60, 100])
        self.assertEqual(E.forward_eye(*self.forward(99))['verdict'], '继续记录，未证明')
        self.assertEqual(E.forward_eye(*self.forward(100))['verdict'], '有用')

    def test_forward_late_answer_excluded(self):
        rr, js = self.forward(100)
        for j in js: j['judged_at'] = '2020-01-01T00:00:00Z'
        report = E.forward_eye(rr, js)
        self.assertEqual(report['excluded_judgements'], 100)
        self.assertNotEqual(report['verdict'], '有用')

    def test_forward_prefix_no_lookahead(self):
        rr, js = self.forward(101)
        before = E.forward_eye(rr, js)
        rr[-1]['d'] = -10000
        after = E.forward_eye(list(reversed(rr)), js)
        self.assertEqual(before['checkpoints'], after['checkpoints'])

    def test_mixed_80_eight_full_batches(self):
        root = self.bank(80, 80, 'mixed1')
        report = E.load_bank('mixed1', root/'answers', root/'keys.json')
        self.assertEqual(report['revealed'], 80)
        self.assertEqual(report['unrevealed_answered'], 0)
        self.assertEqual(report['verdict'], '样本太少，仅供参考')

    def test_top_level_net_R_key(self):
        root = self.bank(10, 10)
        p = root/'keys.json'; k = json.loads(p.read_text())
        for r in k['cases']: r['net_R'] = r.pop('trade')['net_R']
        p.write_text(json.dumps(k))
        self.assertEqual(E.load_bank('hk1', root/'answers', p)['revealed'], 10)
