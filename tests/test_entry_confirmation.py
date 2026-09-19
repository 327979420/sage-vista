import unittest
from unittest.mock import patch
from research.backtest.entry_confirmation import transition, triggers, forward, replay, combine, summarize

class EntryConfirmationTests(unittest.TestCase):
    def setUp(self):
        from datetime import date,timedelta
        self.rows=[dict(date=(date(2020,1,1)+timedelta(days=i)).isoformat(),open=100+i,close=101+i,high=103+i,low=99+i,volume=1000) for i in range(100)]
        self.spy={r['date']:dict(r) for r in self.rows};self.days=list(self.spy)
        self.event={'symbol':'ABC','episode_id':'e1','signal_date':self.days[0],'timeframe':'daily',
            'timeframe_scores':{'daily':80,'weekly_completed':20,'monthly_completed':10},
            'entry_gate':{'paths':[{'timeframe':'daily','structure_floor':90,'structure_key':'x','confirmed_through':self.days[0]}]}}
        self.op=combine([self.event],self.days)[0];self.op['wait_end']=self.days[4]
    def facts(self,rows,as_of,**kw):
        self.assertEqual(rows[-1]['date'],as_of)
        self.assertTrue(all(r['date']<=as_of for r in rows))
        return {'frames':{'daily':{'completed_through':as_of,'close':rows[-1]['close'],
            'breakout':as_of==self.days[2],'support_reversal':False,'pullback_momentum':{'confirmed':False}}}}
    def run_op(self):
        with patch('research.backtest.entry_confirmation.collect_entry_facts',side_effect=self.facts):
            return replay(self.op,self.rows,self.spy,{}, {})
    def test_next_open_and_holding_from_fill(self):
        result=self.run_op();v=result['methods']['breakout']
        self.assertEqual(v['trigger_date'],self.days[2]);self.assertEqual(v['fill_date'],self.days[3])
        self.assertEqual(v['outcomes']['5']['end'],self.days[7])
        self.assertAlmostEqual(v['outcomes']['5']['return'],108/103-1)
        self.assertEqual(v['outcomes']['5']['excess'],0)
    def test_no_trigger_remains_wait_not_expired(self):
        self.assertEqual(self.run_op()['methods']['support']['states'][-1]['state'],'WAITING_FOR_DAILY_CONFIRMATION')
    def test_illegal_transition(self):
        with self.assertRaises(ValueError):transition([{'state':'DETECTED','date':'2020-01-01'}],'OPEN_POSITION','2020-01-02')
    def test_momentum_is_not_standalone_histogram(self):
        self.assertFalse(triggers({'negative_histogram_confirmation':{'confirmed':True}})['momentum'])
    def test_missing_execution_is_not_delayed_fill(self):
        self.rows.pop(1)
        self.assertEqual(self.run_op()['methods']['direct']['status'],'missing_prices')
    def test_gap_reject_and_no_close_lookahead(self):
        self.rows[1]['open']=89
        v=self.run_op()['methods']['direct'];self.assertEqual(v['status'],'gap_invalidated')
    def test_merge_preserves_source_event_and_classification(self):
        e={**self.event,'episode_id':'e2','signal_date':self.days[2]}
        ops=combine([self.event,e],self.days)
        self.assertEqual(len(ops),1);self.assertEqual(len(ops[0]['source_events']),2)
        self.assertEqual(ops[0]['timeframe'],'daily')
    def test_forward_missing_and_fill_day_low(self):
        prices=dict(self.spy);prices[self.days[0]]={**prices[self.days[0]],'low':50}
        self.assertEqual(forward(prices,self.spy,self.days,self.days[0],5)['mae'],-.5)
        del prices[self.days[2]]
        self.assertEqual(forward(prices,self.spy,self.days,self.days[0],5)['status'],'missing_prices')
    def test_invalidation_terminal_and_future_source_not_applied(self):
        self.rows[1]['close']=80
        self.assertEqual(self.run_op()['methods']['support']['status'],'invalidated')
    def test_fill_precedes_same_day_close_invalidation(self):
        self.rows[1]['close']=80
        self.assertEqual(self.run_op()['methods']['direct']['status'],'filled')
    def test_future_sources_do_not_resurrect_invalidated_wait(self):
        import copy
        later=copy.deepcopy(self.event);later['episode_id']='e2';later['signal_date']=self.days[2]
        later['entry_gate']['paths'][0].update(structure_key='future',structure_floor=50,confirmed_through=self.days[2])
        self.op['source_events'].append(later);self.rows[1]['close']=80
        result=self.run_op()
        self.assertEqual(result['methods']['breakout']['status'],'invalidated')
        self.assertNotIn('e2',result['applied_event_ids'])
    def test_last_day_trigger_executes_following_open(self):
        self.op['wait_end']=self.days[2]
        self.assertEqual(self.run_op()['methods']['breakout']['fill_date'],self.days[3])

if __name__=='__main__':unittest.main()
