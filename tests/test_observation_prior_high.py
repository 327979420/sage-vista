import unittest
from research.backtest.observation_prior_high import prior_high,evaluate,summarize

class PriorHighTests(unittest.TestCase):
 def fixture(self):
  rows=[{'date':f'2020-01-{i+1:02d}','high':h,'low':h-2,'close':h-1,'open':h-1,'volume':10} for i,h in enumerate([5,6,10,8,7,6,5])]
  e={'episode_id':'a','symbol':'A','timeframe':'daily','signal_date':'2020-01-07','signal_close':4,'entry_gate':{'evidence':{'daily':{'completed_through':'2020-01-07','support_zone':{'start_source':'three_push_anchor','structure_start':'2020-01-03'}}}}}
  return e,rows
 def test_target_uses_frozen_anchor_not_later_prices(self):
  e,rows=self.fixture();a=prior_high(e,rows)
  self.assertEqual(a['price'],10);self.assertEqual(a['confirmed_at'],'2020-01-05')
  self.assertEqual(a,prior_high(e,rows+[dict(rows[-1],date='2020-02-01',high=999)]))
 def test_unconfirmed_or_missing_anchor_is_not_guessed(self):
  e,rows=self.fixture();e['entry_gate']['evidence']['daily']['support_zone']['structure_start']='2020-01-06'
  self.assertEqual(prior_high(e,rows)['status'],'no_matching_confirmed_high')
 def test_signal_day_touch_separated(self):
  e,rows=self.fixture();rows[-1]['high']=10
  self.assertEqual(prior_high(e,rows)['status'],'already_touched_on_signal')
 def test_touch_day_risk_order_and_never_hit_denominator(self):
  from datetime import date,timedelta
  e,rows=self.fixture()
  for i in range(1,61):
   rows.append({'date':(date(2020,1,7)+timedelta(days=i)).isoformat(),'high':10 if i==3 else 5,'low':1 if i==3 else 3,'close':4,'open':4,'volume':10})
  v=evaluate(e,rows,[r['date'] for r in rows]);self.assertEqual(v['hit_day'],3)
  self.assertEqual(v['downside_before_hit'],-.25);self.assertEqual(v['downside_including_hit'],-.75)
  rows[9]['high']=5
  never=evaluate(e,rows,[r['date'] for r in rows]);never['episode_id']='b'
  self.assertIsNone(never['hit_day'])
  c={'classification':{'a':{'research_label':'daily'},'b':{'research_label':'daily'}}}
  g=summarize([v,never],c)[0];self.assertEqual(g['n'],2);self.assertEqual(g['hit_n'],1)
 def test_missing_followup_is_not_nonhit(self):
  from datetime import date,timedelta
  e,rows=self.fixture();sessions=[r['date'] for r in rows]+[(date(2020,1,7)+timedelta(days=i)).isoformat() for i in range(1,61)]
  self.assertEqual(evaluate(e,rows,sessions)['status'],'missing_followup_prices')

if __name__=='__main__':unittest.main()
