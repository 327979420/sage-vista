import copy
import unittest
from research.backtest.observation_classification import classify
from research.backtest.observation_level_horizons import study

class LevelTests(unittest.TestCase):
    def event(self):
        return {'episode_id':'a'*64,'symbol':'A','signal_date':'2014-01-02','timeframe':'monthly_completed',
          'timeframe_scores':{'daily':50,'weekly_completed':60,'monthly_completed':70},
          'entry_gate':{'paths':[{'timeframe':'monthly_completed','structure_floor':90}]},
          'outcomes':{k:{'status':'complete','return':.1,'spy_return':.05,'excess':.05,'mae':-.2} for k in ('3m','6m','9m','12m')}}

    def test_gap_boundary_and_all_three_frames(self):
        e=self.event();self.assertEqual(classify(e,10)['research_label'],'monthly_completed')
        self.assertEqual(classify(e,15)['reason'],'lead_too_small')
        e['timeframe_scores']['daily']=90
        self.assertEqual(classify(e,10)['reason'],'leader_without_matching_ticket')

    def test_tie_missing_and_invalid_floor_are_not_assigned(self):
        e=self.event();e['timeframe_scores']['daily']=70
        self.assertEqual(classify(e)['reason'],'tied_scores')
        e=self.event();e['entry_gate']['paths'][0]['structure_floor']=None
        self.assertEqual(classify(e)['reason'],'leader_without_matching_ticket')
        e=self.event();e['timeframe_scores']['daily']=None
        self.assertEqual(classify(e)['reason'],'scores_unavailable')

    def test_future_outcomes_do_not_affect_group(self):
        e=self.event();expected=classify(e)
        e['outcomes']={'12m':{'return':-1}}
        self.assertEqual(classify(e),expected)

    def test_common_sample_periods_and_original_events_preserved(self):
        a=self.event();b=copy.deepcopy(a);b.update(episode_id='b'*64,symbol='B',signal_date='2020-01-02')
        b['outcomes']['12m']={'status':'missing_prices'}
        events=[a,b];before=copy.deepcopy(events);result=study(events)
        self.assertEqual(events,before)
        main=result['comparisons'][1]
        rows=[r for r in main['groups'] if r['timeframe']=='monthly_completed' and r['cohort']=='common_planned']
        self.assertTrue(all(r['events']==1 for r in rows))
        self.assertAlmostEqual(rows[0]['median_return'],.1)
        self.assertEqual(result['comparisons'][2]['selected_events'],0)
