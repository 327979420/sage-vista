import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research.lab import own_picks as P, forward_judge as J
from tests.test_forward_judge import rows


def fixture():
    dates = ['2024-01-02']
    while len(dates) < 650: dates.append(P.next_session(dates[-1]))
    s = {'date': dates, 'open': [100.]*650, 'high': [102.]*650, 'low': [98.]*650,
         'close': [100.]*650, 'volume': [1e7]*650}
    return {'TEST': s, **{f'T{i:02}': copy.deepcopy(s) for i in range(35)}}


def pick(px, **kwargs):
    day = px['TEST']['date'][500]
    now = dt.datetime.fromisoformat(day+'T17:00:00').replace(tzinfo=P.NY)
    return P.make_pick(px, 'synthetic', 'TEST', 90., 130., 'synthetic test', now, rid='fixed-id', **kwargs)


class OwnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (P.ROOT/'work/own-picks-038').mkdir(parents=True, exist_ok=True)

    def test_late_refused(self):
        with self.assertRaises(ValueError): P.validate_deadline('2026-10-16', '2026-10-19T13:30:00Z')
        self.assertEqual(P.validate_deadline('2026-10-16', '2026-10-19T13:29:59Z'), '2026-10-19')
        self.assertEqual(P.registration_day('2026-10-19T14:00:00Z'), '2026-10-16')

    def test_dst_holiday_deadlines(self):
        self.assertEqual(P.next_session('2026-11-25'), '2026-11-27')
        self.assertEqual(P.session_open('2026-11-02').astimezone(P.UTC).hour, 14)
        self.assertEqual(P.session_open('2026-10-19').astimezone(P.UTC).hour, 13)

    def test_append_only_and_reject_mutations(self):
        px = fixture(); p = pick(px)
        with tempfile.TemporaryDirectory(dir=P.ROOT/'work/own-picks-038') as d:
            path = Path(d)/'picks.jsonl'
            with P.locked_log(path) as (f, es): P.append_event(f, es, p)
            before = path.read_bytes()
            cancel = {'event': 'cancel', 'id': p['id'], 'recorded_at': p['recorded_at']}
            with P.locked_log(path) as (f, es): P.append_event(f, es, cancel)
            self.assertTrue(path.read_bytes().startswith(before))
            for event in ({**p, 'event': 'edit'}, p, cancel):
                with P.locked_log(path) as (f, es):
                    with self.assertRaises(ValueError): P.append_event(f, es, event)

    def test_gap_through_stop(self):
        px = fixture(); p = pick(px); s = px['TEST']; s['open'][502] = 85; s['low'][502] = 84
        r = P.replay(s, p)
        self.assertEqual(r['exit'], 85); self.assertAlmostEqual(r['net_R'], J.net_r(100, 85, 90))

    def test_stop_target_same_day(self):
        px = fixture(); p = pick(px); s = px['TEST']; s['low'][501] = 85; s['high'][501] = 135
        r = P.replay(s, p)
        self.assertEqual(r['exit'], 90); self.assertEqual(r['status'], 'loss')

    def test_market_gap_on_entry_r_undefined_counted(self):
        px = fixture(); p = pick(px); s = px['TEST']; s['open'][501] = 85; s['low'][501] = 84
        report = P.compute({'synthetic': px}, [p])
        self.assertEqual(report['completed'], 1); self.assertEqual(report['unscorable'], 1)
        self.assertIsNone(report['rows'][0]['trade']['net_R'])

    def test_market_gap_above_target(self):
        px = fixture(); p = pick(px); s = px['TEST']; s['open'][501] = 140; s['high'][501] = 145; s['low'][501] = 139
        self.assertEqual(P.replay(s, p)['exit'], 140)

    def test_limit_never_filled_and_wait(self):
        px = fixture(); p = pick(px, limit=95, wait=2)
        self.assertEqual(P.replay(px['TEST'], p)['status'], 'cancelled')
        with self.assertRaises(ValueError): pick(px, wait=J.N.WAIT+1)

    def test_limit_cancel_before_fill(self):
        px = fixture(); p = pick(px, limit=95); s = px['TEST']; s['open'][501] = 85
        self.assertEqual(P.replay(s, p)['why'], 'stop before the fill')
        s['open'][501] = 100; s['high'][501] = 140
        self.assertEqual(P.replay(s, p)['why'], 'target before the fill')

    def test_limit_parity_frozen(self):
        px = fixture(); p = pick(px, limit=99); s = px['TEST']; s['low'][501] = 98
        expected = J.N.trade(s, 500, 99, 90, 130, hold=130, wait=40)
        result = P.replay(s, p)
        for k, v in expected.items(): self.assertEqual(result[k], v)

    def test_hold_fill_counts_as_one(self):
        px = fixture(); p = pick(px, weeks=2)
        self.assertEqual(P.replay(px['TEST'], p)['exit_day'], 510)
        self.assertEqual(P.replay(px['TEST'], p)['status'], 'time')

    def test_twins_market_parameters_and_no_future(self):
        px = fixture(); p = pick(px)
        twins = P.draw_twins(px, p)
        self.assertEqual(len(twins), 30)
        for t in twins:
            self.assertAlmostEqual((t['ref']-t['stop'])/t['atr'], p['m'])
            self.assertAlmostEqual((t['target']-t['ref'])/(t['ref']-t['stop']), p['r_target'])
            self.assertEqual(t['entry']['type'], 'market')
        for s in px.values():
            for key in ('open','high','low','close'): s[key][501:] = [10000.]*149
        self.assertEqual(pick(px), p)

    def test_twins_limit_parameters(self):
        px = fixture(); p = pick(px, limit=95)
        for t in P.draw_twins(px, p):
            level = t['entry']['limit']
            self.assertAlmostEqual(level/t['ref'], .95)
            self.assertAlmostEqual((level-t['stop'])/t['atr'], p['m'])
            self.assertAlmostEqual((t['target']-level)/(level-t['stop']), p['r_target'])

    def test_cancel_does_not_erase_filled_trade(self):
        px = fixture(); p = pick(px)
        later = px['TEST']['date'][502]+'T21:00:00Z'
        self.assertEqual(P.replay(px['TEST'], p, later), P.replay(px['TEST'], p))
        self.assertEqual(P.replay(px['TEST'], p, p['recorded_at'])['status'], 'cancelled')

    def test_missing_session_stops(self):
        px = fixture(); p = pick(px)
        for v in px['TEST'].values(): del v[501]
        with self.assertRaises(ValueError): P.replay(px['TEST'], p)

    def test_stale_reference_stops(self):
        px = fixture(); p = pick(px)
        for v in px['TEST'].values(): del v[500]
        with self.assertRaises(ValueError): P.reference(px['TEST'], p['signal_day'])

    def test_week_atr_last_complete(self):
        px = fixture(); s = px['TEST']
        friday = next(d for d in s['date'][450:] if dt.date.fromisoformat(d).weekday() == 4)
        monday = P.next_session(friday)
        self.assertEqual(P.reference(s, friday)['atr_week'], friday)
        self.assertEqual(P.reference(s, monday)['atr_week'], friday)

    def test_29_30_and_under_100(self):
        self.assertEqual(J.score(rows(29), checkpoint_judge=P.checkpoint)['checkpoints'], [])
        self.assertEqual(J.score(rows(30), checkpoint_judge=P.checkpoint)['verdict'], '提醒owner')
        self.assertNotEqual(J.score(rows(99, True), checkpoint_judge=P.checkpoint)['verdict'], '有效')
        self.assertEqual(J.score(rows(100, True), checkpoint_judge=P.checkpoint)['verdict'], '有效')

    def test_every_checkpoint_and_exit_sort(self):
        rs = rows(201, True)
        for r in rs[:30]: r['d'] *= -1
        result = J.score(list(reversed(rs)), checkpoint_judge=P.checkpoint)
        self.assertEqual([c['k'] for c in result['checkpoints']], [30,60,100,200])
        self.assertTrue(result['alarm1'])
        rs[-1]['d'] = -10000
        self.assertEqual(result['checkpoints'], J.score(rs, checkpoint_judge=P.checkpoint)['checkpoints'])

    def test_missing_twins_counted_pause(self):
        rs = rows(30)
        for r in rs[:4]: r['scored'] = False
        result = J.score(rs, checkpoint_judge=P.checkpoint)
        self.assertEqual(result['completed'], 30)
        self.assertEqual(result['verdict'], '暂停判断（对照不足）')
        self.assertFalse(result['alarm1'])

    def test_zero_compute(self):
        result = P.compute({}, [])
        self.assertEqual(result['completed'], 0); self.assertEqual(result['next_checkpoint'], 30)

    def test_compute_pool_and_seed_equal_frozen(self):
        import random, hashlib
        px = fixture(); p = pick(px)
        rules = {**J.N.POOL, 'exclude': J.selection.impossible_jumps(px) | J.N.FUNDS}
        pool = [s for s in J.selection.eligible_pool(px, p['signal_day'], rules) if s != p['symbol']]
        seed = int(hashlib.sha256(p['id'].encode()).hexdigest()[:8], 16)
        self.assertEqual([t['symbol'] for t in P.draw_twins(px, p)], random.Random(seed).sample(pool, 30))

    def test_registration_without_any_next_bar(self):
        px = fixture(); p = pick(px)
        truncated = {s: P.clipped(q, p['signal_day']) for s, q in px.items()}
        self.assertEqual(p, P.make_pick(truncated, 'synthetic', 'TEST', 90., 130., 'synthetic test',
                                       p['recorded_at'], rid='fixed-id'))
        self.assertEqual(P.draw_twins(truncated, p), [])
        result = P.compute({'synthetic': truncated}, [p])
        self.assertEqual(result['rows'][0]['trade']['why'], '等待次日行情')
        self.assertEqual(result['rows'][0]['twins'], [])

    def test_compute_market_twins_next_open_and_fixed_levels(self):
        px = fixture(); p = pick(px)
        before = P.draw_twins(px, p)
        for s in px.values():
            s['open'][501] = 101
        self.assertEqual(P.draw_twins(px, p), before)
        result = P.compute({'synthetic': px}, [p])
        self.assertTrue(all(t['trade']['entry'] == 101 for t in result['rows'][0]['twins']))
