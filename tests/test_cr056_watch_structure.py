import copy
from datetime import date,timedelta
import unittest
from unittest.mock import patch
from services.ledger.cr056 import track_entry_structures

class StructureWatchTests(unittest.TestCase):
 def setUp(self):
  self.rows=[{'date':str(date(2020,1,1)+timedelta(days=i)),'open':100.,'high':102.,'low':98.,'close':100.,'volume':1000000} for i in range(426)]
 def facts(self,rows,*,as_of,**kwargs):
  index=len(rows)-1
  frame={'available':True,'completed_through':as_of,'close':rows[-1]['close'],'current_low':rows[-1]['low'],
   'bottoms':[{'date':'2019-12-01','price':90.},{'date':'2019-12-10','price':91.}],
   'cross_date':'2020-01-01','macd_valid':index==420,'breakout':False,'support_reversal':index==423,
   'support':{'date':'2019-12-20','price':92.}}
  return {'as_of':as_of,'frames':{'daily':frame}}
 def test_observation_survives_no_new_cross_and_has_actual_price_change(self):
  rows=copy.deepcopy(self.rows);rows[-1]['close']=105.
  with patch('services.factors.cr056.collect_entry_facts',side_effect=self.facts):
   result=track_entry_structures(rows,as_of=rows[-1]['date'])
  self.assertTrue(result['eligible']);self.assertEqual(len(result['records']),2)
  first=result['records'][0]
  self.assertEqual(first['trigger_date'],rows[420]['date']);self.assertAlmostEqual(first['observation_return'],.05)
  self.assertEqual(first['observed_sessions'],5)
 def test_break_then_rebound_does_not_resurrect_old_episode(self):
  rows=copy.deepcopy(self.rows);rows[422]['close']=89.
  with patch('services.factors.cr056.collect_entry_facts',side_effect=self.facts):
   result=track_entry_structures(rows,as_of=rows[-1]['date'])
  self.assertEqual(result['records'][0]['state'],'invalidated')
  self.assertEqual(result['records'][0]['invalidated_at'],rows[422]['date'])
  self.assertEqual(result['records'][1]['state'],'active')
 def test_incremental_resume_matches_full_and_same_day_does_not_replay(self):
  with patch('services.factors.cr056.collect_entry_facts',side_effect=self.facts) as detect:
   old=track_entry_structures(self.rows[:423],as_of=self.rows[422]['date'])
   detect.reset_mock()
   incremental=track_entry_structures(self.rows,as_of=self.rows[-1]['date'],previous=old)
   self.assertEqual(detect.call_count,3)
   full=track_entry_structures(self.rows,as_of=self.rows[-1]['date'])
   self.assertEqual(incremental,full)
   detect.reset_mock()
   self.assertEqual(track_entry_structures(self.rows,as_of=self.rows[-1]['date'],previous=full),full)
   detect.assert_not_called()
 def test_source_revision_reconstructs_without_mutating_previous(self):
  with patch('services.factors.cr056.collect_entry_facts',side_effect=self.facts) as detect:
   old=track_entry_structures(self.rows,as_of=self.rows[-1]['date']);frozen=copy.deepcopy(old)
   revised=copy.deepcopy(self.rows);revised[420]['close']=101.
   detect.reset_mock();new=track_entry_structures(revised,as_of=revised[-1]['date'],previous=old)
   self.assertGreater(detect.call_count,0);self.assertEqual(old,frozen)
   self.assertEqual(new['records'][0]['trigger_close'],101.)
 def test_missing_gate_never_grandfathers_an_old_nomination(self):
  def no_signal(rows,**kwargs):
   f=self.facts(rows,**kwargs);f['frames']['daily'].update(macd_valid=False,support_reversal=False);return f
  with patch('services.factors.cr056.collect_entry_facts',side_effect=no_signal):
   self.assertFalse(track_entry_structures(self.rows,as_of=self.rows[-1]['date'])['eligible'])
