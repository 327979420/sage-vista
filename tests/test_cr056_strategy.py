import copy
import unittest
from services.contracts.cr056_policy import WHITE_LIST
from services.selectors.cr056 import direction_permission, assess_permission
from services.ranking.cr056 import score_candidate
from services.gates.long_term_state import completed_period_bars, period_closed_at_session


def facts():
    return {'as_of': '2026-09-04', 'input_fingerprint': 'test', 'daily_rows': 2000,
      'monthly': {'completed_count': 70, 'histogram': [0.5, 0.8, 1.0]},
      'weekly': {'histogram': [1.0]*13}, 'close': 80, 'observed_history_high': 120,
      'prior_60_high': 100, 'legacy_long_trend': True,
      'monthly_high_zone': {'ema20': 90, 'latest_line': 1, 'latest_histogram': 1,
        'normalized_line': .01, 'normalized_histogram': .01, 'line_p90': .02, 'histogram_p90': .02},
      'local_structure': {'status': 'observed', 'classification': 'structure_intact'},
      'base': {'low': 60, 'high': 85, 'prior_peak': 140, 'touch_indices': [0, 5],
               'first_half_low': 60, 'last_half_low': 61, 'median_close': 75}}


def states():
    return [{'factor_id': fid, 'hit': True, 'available': True, 'recent_hit': False, 'bars_since_hit': 0}
            for ids in WHITE_LIST.values() for fid in ids if fid != 'direction.macd_state.monthly']

class PermissionTests(unittest.TestCase):
    def test_month_shrinking_and_new_bear_block_but_old_negative_improvement_allows(self):
        for h, expected in [([.5, 1, .8], 'blocked'), ([.5, .1, -.1], 'blocked'),
                            ([-3, -2, -1], 'allowed'), ([-3, -2, -2], 'blocked')]:
            self.assertEqual(direction_permission(h, timeframe='monthly')['status'], expected)

    def test_weekly_near_cross_boundary_and_ordinary_shrink_penalty(self):
        self.assertEqual(direction_permission([1]*12+[.1], timeframe='weekly')['status'], 'blocked')
        self.assertEqual(direction_permission([1]*12+[.5], timeframe='weekly')['score_multiplier'], .75)

    def test_long_base_path_survives_failed_legacy_ema_gate(self):
        f = facts(); f['legacy_long_trend'] = False
        r = assess_permission(f)
        self.assertTrue(r['eligible'])
        self.assertEqual(r['primary_background'], 'long_base_pullback')

    def test_observed_high_blocks_without_claiming_all_time_coverage(self):
        f = facts(); f['close'] = 114
        r = assess_permission(f)
        self.assertIn('near_observed_history_high', r['reason_codes'])
        self.assertFalse(r['eligible'])

    def test_missing_structure_is_unavailable_not_neutral(self):
        f = facts(); f['local_structure'] = {'status': 'unavailable'}
        self.assertEqual(assess_permission(f)['permission'], 'unavailable')

class ScoreTests(unittest.TestCase):
    def test_fixed_caps_are_reachable_and_duplicate_stories_do_not_inflate(self):
        r = score_candidate(states(), assess_permission(facts()))
        self.assertEqual(r['total_score'], 100)
        self.assertEqual([r['timeframes'][tf]['raw'] for tf in WHITE_LIST], [5, 2, 3.25])
        self.assertTrue(r['high_score_eligible'])

    def test_month_veto_cannot_be_bought_back_by_all_factors(self):
        f = facts(); f['monthly']['histogram'] = [.5, 1, .8]
        r = score_candidate(states(), assess_permission(f))
        self.assertIsNone(r['total_score'])
        self.assertFalse(r['high_score_eligible'])

    def test_missing_group_does_not_reduce_denominator_or_raise_alarm(self):
        st = states(); st[0]['available'] = False
        r = score_candidate(st, assess_permission(facts()))
        self.assertEqual(r['score_status'], 'partial')
        self.assertEqual(r['timeframes']['daily']['cap'], 5)
        self.assertFalse(r['high_score_eligible'])

    def test_month_direction_remains_scored_after_cross_day(self):
        r = score_candidate(states(), assess_permission(facts()))
        self.assertEqual(r['timeframes']['monthly_completed']['families']['macd'], 1)

class PeriodBoundaryTests(unittest.TestCase):
    def test_friday_needs_completed_session_evidence_and_legacy_is_unchanged(self):
        rows = [{'date': d, 'open': 1, 'high': 2, 'low': .5, 'close': 1, 'volume': 1}
                for d in ('2026-08-28', '2026-08-31', '2026-09-04')]
        old = completed_period_bars(rows, as_of='2026-09-04', period='weekly')
        new = completed_period_bars(rows, as_of='2026-09-04', period='weekly', complete_session=True)
        self.assertEqual(old[-1]['date'], '2026-08-28')
        self.assertEqual(new[-1]['date'], '2026-09-04')
        self.assertFalse(period_closed_at_session('2026-09-03', 'weekly', complete_session=True))

    def test_factor_detector_and_direction_share_completed_friday(self):
        from datetime import date, timedelta
        import math
        from services.factors.cr056 import collect_direction_facts
        from services.scanner.factor_detectors import evaluate_all_factors
        rows = []
        day = date(2018, 1, 1)
        end = date(2026, 9, 4)
        while day <= end:
            if day.weekday() < 5:
                value = 80 + len(rows)*.01 + 5*math.sin(len(rows)/20)
                rows.append({'date': day.isoformat(), 'open': value, 'high': value+1,
                             'low': value-1, 'close': value, 'volume': 1000000})
            day += timedelta(days=1)
        facts = collect_direction_facts(rows, as_of=end.isoformat(), complete_session=True)
        states = evaluate_all_factors(rows, end.isoformat(), complete_session=True)
        weekly = next(s for s in states if s.factor_id == 'macd.weekly_histogram_improving')
        self.assertEqual(facts['weekly']['completed_through'], '2026-09-04')
        self.assertEqual(weekly.evidence['completed_week_end'], '2026-09-04')
        old = evaluate_all_factors(rows, end.isoformat())
        old_weekly = next(s for s in old if s.factor_id == 'macd.weekly_histogram_improving')
        self.assertEqual(old_weekly.evidence['completed_week_end'], '2026-08-28')
