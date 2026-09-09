import copy
import unittest
from services.contracts.cr056_policy import WHITE_LIST, MAPPED_FACTORS, CAPS
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
    return [{'factor_id': fid, 'as_of': '2026-09-04', 'hit': True, 'available': True, 'recent_hit': False, 'bars_since_hit': 0, 'value': 1.0}
            for fid in MAPPED_FACTORS]

class PermissionTests(unittest.TestCase):
    def test_month_shrinking_and_new_bear_block_but_old_negative_improvement_allows(self):
        for h, expected in [([.5, 1, .8], 'blocked'), ([.5, .1, -.1], 'blocked'),
                            ([-3, -2, -1], 'allowed'), ([-3, -2, -2], 'blocked')]:
            self.assertEqual(direction_permission(h, timeframe='monthly')['status'], expected)

    def test_first_negative_contraction_is_monthly_only(self):
        h = [-2]*11 + [-3, -2]
        self.assertEqual(direction_permission(h, timeframe='monthly')['status'], 'allowed')
        self.assertEqual(direction_permission(h, timeframe='weekly')['status'], 'blocked')
        self.assertEqual(direction_permission(h + [-1], timeframe='weekly')['status'], 'allowed')

    def test_monthly_first_contraction_boundary(self):
        for h, expected in [([-3, -2], 'allowed'), ([-2, -2], 'blocked'),
                            ([-2, -3], 'blocked'), ([.1, -.1], 'blocked'),
                            ([-1, 0], 'blocked'), ([-1], 'unavailable')]:
            with self.subTest(histogram=h):
                self.assertEqual(direction_permission(h, timeframe='monthly')['status'], expected)

    def test_first_contraction_does_not_override_other_exclusions(self):
        f = facts(); f['monthly']['histogram'] = [-2, -3, -2]
        self.assertTrue(assess_permission(f)['eligible'])
        f['close'] = 114
        self.assertFalse(assess_permission(f)['eligible'])
        f = facts(); f['monthly']['histogram'] = [-2, -3, -2]
        f['legacy_long_trend'] = False; f['base']['prior_peak'] = 65
        self.assertIn('no_available_background', assess_permission(f)['reason_codes'])

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
        self.assertEqual([r['timeframes'][tf]['raw'] for tf in WHITE_LIST], list(CAPS.values()))
        self.assertTrue(r['high_score_eligible'])

    def test_month_veto_cannot_be_bought_back_by_all_factors(self):
        f = facts(); f['monthly']['histogram'] = [.5, 1, .8]
        r = score_candidate(states(), assess_permission(f))
        self.assertIsNone(r['total_score'])
        self.assertFalse(r['high_score_eligible'])

    def test_missing_group_does_not_reduce_denominator_or_raise_alarm(self):
        st = states(); next(x for x in st if x['factor_id'] == WHITE_LIST['daily'][0])['available'] = False
        r = score_candidate(st, assess_permission(facts()))
        self.assertEqual(r['score_status'], 'partial')
        self.assertEqual(r['timeframes']['daily']['cap'], CAPS['daily'])
        self.assertFalse(r['high_score_eligible'])

    def test_old_factor_date_cannot_be_mixed_with_today_permission(self):
        st = states(); st[0]['as_of'] = '2020-01-01'
        with self.assertRaisesRegex(ValueError, 'factor date'):
            score_candidate(st, assess_permission(facts()))

    def test_equal_scores_keep_distinct_price_and_factor_sources(self):
        f = facts(); p1 = assess_permission(f)
        f['input_fingerprint'] = 'another-price-snapshot'; p2 = assess_permission(f)
        a = score_candidate(states(), p1); b = score_candidate(states(), p2)
        self.assertEqual(a['total_score'], b['total_score'])
        self.assertNotEqual(a['score_fingerprint'], b['score_fingerprint'])
        st = states(); st[0]['evidence'] = {'source': 'another-factor-input'}
        c = score_candidate(st, p1)
        self.assertNotEqual(a['factor_input_fingerprint'], c['factor_input_fingerprint'])
        self.assertIn('registry_fingerprint', a)

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


class PeriodMappingTests(unittest.TestCase):
    def rows(self):
        import calendar
        result = []
        for i in range(40):
            year, month = 2023 + i//12, i%12+1
            last = calendar.monthrange(year,month)[1]
            from datetime import date, timedelta
            day = date(year,month,last)
            while day.weekday()>4: day -= timedelta(days=1)
            result.append(dict(date=day.isoformat(),open=100,high=102,low=98,close=101,volume=100))
        result[-1].update(open=110,high=113,low=110,close=111,volume=300)
        return result

    def test_all_original_ids_are_accounted_for_and_aliases_do_not_duplicate(self):
        from services.scanner.factor_registry import FACTORS
        from services.contracts.cr056_policy import MAPPED_FACTORS
        self.assertEqual({f.id for f in FACTORS}, {sid for m in MAPPED_FACTORS.values() for sid in m['source_ids']})
        for tf in WHITE_LIST:
            templates = [m['template'] for m in MAPPED_FACTORS.values() if m['timeframe']==tf]
            self.assertEqual(len(templates),len(set(templates)))
            self.assertTrue(all(MAPPED_FACTORS[fid]['role']=='score' for fid in WHITE_LIST[tf]))

    def test_monthly_volume_and_fvg_use_month_bars_and_preserve_missing_history(self):
        from services.scanner.factor_detectors import evaluate_period_factors
        rows=self.rows(); states={s['factor_id']:s for s in evaluate_period_factors(rows,rows[-1]['date'],complete_session=True)}
        volume=states['monthly_completed::volume.relative_expansion']
        self.assertEqual(volume['evidence']['ratio'],3)
        self.assertTrue(volume['hit'])
        self.assertTrue(states['monthly_completed::structure.bullish_fvg_support']['hit'])
        self.assertFalse(states['monthly_completed::support.close_congestion']['available'])
        ema=states['monthly_completed::support.ema_proximity']
        self.assertEqual(set(ema['evidence']['distance_by_period']),{'21'})
        self.assertEqual(states['monthly_completed::volume.pullback_contraction']['runtime_status'],'definition_required')

    def test_unfinished_and_future_month_cannot_change_completed_month_facts(self):
        from services.scanner.factor_detectors import evaluate_period_factors
        rows=self.rows(); first=evaluate_period_factors(rows,rows[-1]['date'],complete_session=True)
        rows.append(dict(date='2026-05-08',open=999,high=9999,low=1,close=999,volume=999999))
        rows.append(dict(date='2026-06-08',open=999,high=9999,low=1,close=999,volume=999999))
        after=evaluate_period_factors(rows,'2026-05-08',complete_session=True)
        a=[{k:v for k,v in f.items() if k!='as_of'} for f in first if f['timeframe']=='monthly_completed']
        b=[{k:v for k,v in f.items() if k!='as_of'} for f in after if f['timeframe']=='monthly_completed']
        self.assertEqual(a,b)

class MacdEventDateRegressionTests(unittest.TestCase):
    def test_window_does_not_move_event_and_dead_cross_invalidates_it(self):
        from unittest.mock import patch
        from services.scanner.factor_detectors import _period_macd_event
        rows=[{'date':f'bar-{i}','close':100} for i in range(40)]
        for tail, expected_hit, expected_age, expected_recent in (
            ([-1,-1,-1,-1,1],True,0,True),
            ([1,1,1,1,1],False,4,True),
            ([1,1,1,1,-1],False,4,False),
            ([1,1,-1,-1,1],True,0,True),
            ([-1,-1,-1,-1,-1],False,None,False)):
            line=[-1]*35+tail
            with self.subTest(tail=tail),patch('services.scanner.factor_detectors.macd',return_value=(line,[0]*40)):
                hit, day, age, recent, evidence=_period_macd_event(rows,5)
            self.assertEqual((hit,age,recent),(expected_hit,expected_age,expected_recent))
            self.assertEqual(day,None if age is None else rows[-1-age]['date'])
        with patch('services.scanner.factor_detectors.macd',return_value=([-1]*34+[1]*6,[0]*40)):
            hit, day, age, recent, evidence=_period_macd_event(rows,5)
        self.assertFalse(recent);self.assertEqual(age,5);self.assertEqual(day,'bar-34')

    def test_real_macd_matches_strict_gate_in_all_completed_periods(self):
        from services.scanner.factor_detectors import evaluate_period_factors
        from services.scanner.technical import macd
        from services.gates.baseline import exact_daily_macd_bull_cross
        rows=PeriodMappingTests().rows()
        rows[-2].update(open=108,high=111,low=107,close=110)
        rows.append(dict(date='2026-05-01',open=111,high=114,low=110,close=112,volume=100))
        as_of=rows[-1]['date']
        states={s['factor_id']:s for s in evaluate_period_factors(rows,as_of,complete_session=True)}
        for tf,period in [('daily',None),('weekly_completed','weekly'),('monthly_completed','monthly')]:
            bars=rows if period is None else completed_period_bars(rows,as_of=as_of,period=period,complete_session=True)
            line,signal=macd([r['close'] for r in bars])
            crosses=[i for i in range(1,len(bars)) if line[i]>signal[i] and line[i-1]<=signal[i-1]]
            self.assertTrue(crosses)
            state=states[tf+'::macd.daily_bull_cross']
            self.assertEqual(state['hit'],exact_daily_macd_bull_cross(bars))
            self.assertEqual(state['latest_hit_date'],bars[crosses[-1]]['date'])
            self.assertEqual(state['bars_since_hit'],len(bars)-1-crosses[-1])
            self.assertFalse(state['hit']);self.assertTrue(state['recent_hit'])
