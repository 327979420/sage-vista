"""Synthetic-only context-tag contracts; no work/ dependency."""
import copy
from datetime import date, timedelta
import math
import unittest
from unittest.mock import patch

from research.lab import factor_tags as ft
from services.scanner import factor_detectors as fd
from services.scanner.technical import macd, rsi


def sample(n=330):
    result = []
    day = date(2010, 1, 4)
    while len(result) < n:
        if day.weekday() < 5:
            i = len(result)
            close = 100 + i*.02 + 7*math.sin(i/8)
            result.append(dict(date=day.isoformat(), open=close-.3, high=close+1,
                               low=close-1, close=close, volume=1000000 + (i % 7)*10000))
        day += timedelta(days=1)
    return result


class FactorTagsTests(unittest.TestCase):
    def test_registry_and_unknown_are_explicit(self):
        availability = ft.factor_availability()
        self.assertEqual(len(availability), 39)
        missing = {x['id'] for x in availability if not x['available']}
        self.assertEqual(missing, {'trend.dual_ma_alignment', 'trend.dual_ma_fresh_cross',
                                  'structure.dual_ma_pullback_hold', 'structure.breakout_retest',
                                  'volume.pullback_contraction'})
        self.assertEqual(ft.factor_availability(['made.up'])[0]['reason'], 'unknown_factor')
        self.assertFalse(next(x for x in ft.risk_availability() if x['id']=='rsi.bearish_divergence')['available'])

    def test_entry_future_invariance_and_canonical_hits(self):
        rows = sample()
        before = copy.deepcopy(rows)
        result = ft.entry_audit(rows, 299)
        self.assertTrue(result['tags'])
        states = fd.evaluate_all_factors(rows[:300], rows[299]['date'], complete_session=True)
        self.assertEqual({t['id'] for t in result['tags']}, {s.factor_id for s in states if s.available and s.hit})
        for row in rows[300:]:
            row.update(close=5000, high=6000, low=.01, volume=1)
        self.assertEqual(result, ft.entry_audit(rows, 299))
        self.assertEqual(result, ft.entry_audit(rows[:300], 299))
        self.assertEqual(before[:300], rows[:300])
        for tag in result['tags']:
            self.assertLessEqual(tag['first_observed_date'], rows[299]['date'])
            self.assertIn(tag['direction'], ('利好', '利空'))

    def test_insufficient_history_is_not_false(self):
        result = ft.entry_audit(sample(30), 29)
        self.assertEqual(result['tags'], [])
        self.assertEqual(len(result['unavailable']), 39)
        with self.assertRaises(ValueError):
            ft.entry_tags(sample(3), -1)

    def test_risk_future_invariance_at_every_day(self):
        rows = sample(240)
        timeline = ft.risk_timeline(rows, 239)
        self.assertTrue(any(x['tags'] for x in timeline))
        for i in (0, 14, 80, 199, 211, 238):
            self.assertEqual(timeline[i]['tags'], ft.risk_tags(rows[:i+1], i))
        rows.extend(sample(20))  # malformed future dates must never be inspected
        self.assertEqual(timeline[-1]['tags'], ft.risk_tags(rows, 239))

    def test_engulfing_mirror_symmetry(self):
        bars = [dict(date='2010-01-08', open=105, high=106, low=99, close=100, volume=1),
                dict(date='2010-01-15', open=99, high=108, low=98, close=107, volume=1)]
        self.assertTrue(fd.higher_timeframe_bullish_engulfing(bars, 'weekly_completed')[0])
        self.assertTrue(ft.bearish_engulfing(ft.mirror_bars(bars)))
        self.assertFalse(ft.bearish_engulfing(bars))
        self.assertEqual(bars, ft.mirror_bars(ft.mirror_bars(bars)))
        for i in range(2, 30):
            bars = sample(i)
            self.assertEqual(fd.higher_timeframe_bullish_engulfing(bars, 'weekly_completed')[0],
                             ft.bearish_engulfing(ft.mirror_bars(bars)))

    def test_macd_and_rsi_reflect_symmetrically(self):
        values = [r['close'] for r in sample(90)]
        a, b = macd(values)
        c, d = macd([-v for v in values])
        for i in range(1, len(values)):
            self.assertAlmostEqual(a[i], -c[i])
            self.assertEqual(a[i] > b[i] and a[i-1] <= b[i-1], c[i] < d[i] and c[i-1] >= d[i-1])
        for x, y in zip(rsi(values)[14:], rsi([-v for v in values])[14:]):
            self.assertAlmostEqual(x+y, 100)

    def test_weekly_signal_waits_for_completed_friday(self):
        rows = sample(10)
        for row in rows[:5]:
            row.update(open=100, close=105, high=106, low=99)
        for row in rows[5:]:
            row.update(open=106, close=99, high=107, low=98)
        fid = 'structure.weekly_bearish_engulfing'
        self.assertNotIn(fid, {t['id'] for t in ft.risk_tags(rows, 8)})
        tag = next(t for t in ft.risk_tags(rows, 9) if t['id']==fid)
        # First two weeks are insufficient to prove a preceding false state.
        self.assertTrue(tag['left_censored'])
        self.assertEqual(tag['first_observed_date'], rows[9]['date'])

    def test_daily_thresholds_and_onset(self):
        rows = sample(210)
        for i, row in enumerate(rows):
            row.update(open=100+i, high=101+i, low=99+i, close=100+i)
        rows[-2].update(open=95, close=90, high=96, low=89)
        rows[-1].update(open=89, close=85, high=90, low=84)
        tag = next(t for t in ft.risk_tags(rows, 209) if t['id']=='trend.below_ema200')
        self.assertEqual(tag['date'], rows[-2]['date'])
        self.assertNotIn('trend.below_ema200', {t['id'] for t in ft.risk_tags(rows, 207)})

    def test_only_new_post_entry_episodes_count(self):
        fid = 'rsi.overbought'
        def obs(day, onset):
            return dict(date=day, tags=[] if onset is False else
                        [dict(id=fid, date=onset, as_of=day)])
        old = [obs('2010-01-04', '2010-01-01'), obs('2010-01-05', '2010-01-01'),
               obs('2010-01-06', False), obs('2010-01-07', '2010-01-07')]
        self.assertEqual(ft.first_new_warnings(old, '2010-01-04', '2010-01-07'), {})
        warning = ft.first_new_warnings(old, '2010-01-04', '2010-01-08')[fid]
        self.assertEqual(warning['date'], '2010-01-07')
        self.assertEqual(warning['first_week'], '2010-W01')
        self.assertEqual(ft.first_new_warnings([obs('2010-01-05', None)], '2010-01-04', '2010-01-08'), {})

    def test_state_onset_not_latest_observation(self):
        rows = sample(270)
        # Controlled canonical states isolate the date contract from price patterns.
        state = next(s for s in fd.evaluate_all_factors(rows, rows[-1]['date'])
                     if s.factor_id == 'qualification.pullback_60d')
        state = fd.FactorState(**{**state.dict(), 'hit': True, 'available': True,
                                 'latest_hit_date': rows[-1]['date']})
        with patch.object(fd, 'evaluate_all_factors', return_value=[state]), patch.object(
                fd, '_raw', side_effect=lambda r, i, **kw: {state.factor_id: (i >= 265, {})}):
            tag = ft.entry_tags(rows, 269)[0]
        self.assertEqual(tag['date'], rows[265]['date'])

    def test_monthly_setup_uses_completed_bars_and_two_falls(self):
        rows = sample(1500)
        timeline = ft.risk_timeline(rows, len(rows)-1)
        fid = 'macd.monthly_high_bear_setup'
        tagged = [i for i, x in enumerate(timeline) if fid in {t['id'] for t in x['tags']}]
        self.assertTrue(tagged)
        from services.gates.long_term_state import completed_period_bars
        for i in (tagged[0], tagged[-1], 700):
            bars = completed_period_bars(rows[:i+1], as_of=rows[i]['date'], period='monthly', complete_session=True)
            line, signal = macd([r['close'] for r in bars])
            h = [a-b for a,b in zip(line,signal)]
            expected = line[-1]>0 and h[-1]<h[-2]<h[-3]
            self.assertEqual(fid in {t['id'] for t in timeline[i]['tags']}, expected)

    def test_gap_reuses_existing_detector(self):
        from services.scanner.macd_factor_backtest import overhead_unfilled_gap
        rows = sample(50)
        for row in rows[:40]:
            row.update(open=110, close=110, low=109, high=111)
        for row in rows[40:]:
            row.update(open=100, close=100, low=99, high=101)
        timeline = ft.risk_timeline(rows, 49)
        fid = 'risk.overhead_unfilled_gap'
        self.assertTrue(any(fid in {t['id'] for t in x['tags']} for x in timeline))
        for i,x in enumerate(timeline[1:],1):
            self.assertEqual(fid in {t['id'] for t in x['tags']}, overhead_unfilled_gap(rows[:i+1],i))

    def test_event_onset_and_latest_event_are_separate(self):
        rows = sample(270)
        state = next(s for s in fd.evaluate_all_factors(rows, rows[-1]['date'])
                     if s.factor_id == 'volume.relative_expansion')
        state = fd.FactorState(**{**state.dict(), 'hit': True, 'available': True,
                                 'latest_hit_date': rows[-1]['date']})
        with patch.object(fd, 'evaluate_all_factors', return_value=[state]), patch.object(
                fd, '_raw', side_effect=lambda r, i, **kw: {state.factor_id: (i >= 265, {})}):
            tag = ft.entry_tags(rows, 269)[0]
        self.assertEqual(tag['date'], rows[265]['date'])
        self.assertEqual(tag['latest_event_date'], rows[269]['date'])


if __name__ == '__main__':
    unittest.main()
