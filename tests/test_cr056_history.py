import json, math, tempfile, unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from research.backtest.cr056_history import ticket_dates, prepare
from services.factors.cr056 import collect_entry_facts
from services.selectors.cr056 import assess_entry
from research.backtest.run_store import POLICY, CANDIDATE_POLICY, trade_csv, sha256, seal, save

class HistoryTests(unittest.TestCase):
 def rows(self):
  days=[date(2020,1,1)+timedelta(days=i) for i in range(900)]
  return [{'date':d.isoformat(),'open':100+8*math.sin(i/5),'high':111.,'low':89.,'close':100+8*math.sin(i/5),'adjusted_close':100+8*math.sin(i/5),'volume':1000000} for i,d in enumerate(days) if d.weekday()<5]
 def test_ticket_preindex_matches_shared_entry_on_every_historical_day(self):
  rows=self.rows();actual=set(ticket_dates(rows,rows[420]['date'],rows[-1]['date']))
  expected={r['date'] for i,r in enumerate(rows) if i>=420 and assess_entry(collect_entry_facts(rows[:i+1],as_of=r['date'],complete_session=True))['eligible']}
  self.assertEqual(actual,expected)
 def test_adapter_truncates_future_and_reuses_completed_days_without_current_watch(self):
  rows=self.rows();start,end=rows[430]['date'],rows[480]['date'];calls=[]
  def snapshot(cache,**kwargs):
   self.assertEqual(kwargs['history'],{'days':[]})
   for item in kwargs['input_report']['repaired']:
    path=Path(cache)/(item['symbol']+'.json');raw=path.read_bytes()
    self.assertEqual(sha256(raw),item['repaired_sha256'])
    self.assertTrue(all(r['date']<=kwargs['as_of'] for r in json.loads(raw)))
   calls.append(kwargs['as_of'])
   return {'snapshot_fingerprint':'test','reviews':[{'symbol':i['symbol'],'rank':n+1,'status':'rankable','reason_codes':[],'score':{'total_score':70.,'score_fingerprint':'test','timeframes':{'daily':{'normalized':.7}}}} for n,i in enumerate(kwargs['input_report']['repaired'])]}
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);cache=root/'cache';cache.mkdir()
   for symbol in ('AAA','SPY'):(cache/f'{symbol}.json').write_text(json.dumps(rows))
   request={'strategy':CANDIDATE_POLICY,'start':start,'end':end}
   with patch('research.backtest.cr056_history.ticket_dates',return_value=[start]),patch('research.backtest.cr056_history.collect_direction_facts',return_value={}),patch('research.backtest.cr056_history.assess_permission',return_value={'eligible':True}),patch('research.backtest.cr056_history.run_snapshot',side_effect=snapshot),patch('research.backtest.cr056_history.signal_support_plan',return_value={'level':90}):
    ledger,rankings=prepare(request,cache,root/'state','a'*40)
    self.assertEqual(len(calls),51)
    events=json.loads(ledger.read_bytes())['events']
    self.assertEqual(len(events),2)
    self.assertTrue(all(e['selection']['execution_policy_version']==POLICY for e in events))
    before=ledger.read_bytes();calls.clear()
    with patch('research.backtest.cr056_history.ticket_dates',side_effect=AssertionError('cached gate index must be reused')):
     prepare(request,cache,root/'state','b'*40)
    self.assertEqual(calls,[]);self.assertEqual(ledger.read_bytes(),before)
    with patch('research.backtest.cr056_history.POLICY_FINGERPRINT','changed-policy'):
     with self.assertRaisesRegex(ValueError,'checkpoint_policy_or_sources_changed'):
      prepare(request,cache,root/'state','b'*40)

class CsvTests(unittest.TestCase):
 def test_csv_escapes_formula_and_retains_unavailable_instead_of_zero(self):
  csv=trade_csv({'trades':[{'symbol':'=BAD','signal_date':'2026-01-01','status':'pending_next_session','signal_snapshot':{'selection':{'technical_score':0}}}]}).decode('utf-8-sig')
  self.assertIn("'=BAD",csv);self.assertIn('signal_score',csv)
 def test_csv_and_overview_persist_from_sealed_receipt(self):
  from research.backtest.run_store import OUTPUT
  original=next(json.loads(p.read_bytes()) for p in OUTPUT.glob('*/receipt.json') if json.loads(p.read_bytes())['status']=='completed')
  csv=trade_csv(original)
  receipt=seal({**original,'downloads':{'trades_csv':{'path':original['id']+'/trades.csv','sha256':sha256(csv)}}})
  with tempfile.TemporaryDirectory() as d:
   save(receipt,(OUTPUT/original['id']/'report.html').read_bytes(),root=d)
   path=Path(d)/receipt['id']
   self.assertEqual((path/'trades.csv').read_bytes(),csv)
   overview=json.loads((path/'overview.json').read_bytes())
   self.assertNotIn('trades',overview);self.assertEqual(overview['summary'],receipt['summary'])
   self.assertIn('overview_sha256',json.loads((Path(d)/'index.json').read_bytes())['runs'][0])

class NativeFrameCacheTests(unittest.TestCase):
 def test_exact_facts_and_tickets_across_period_boundaries(self):
  rows=HistoryTests().rows();cache={}
  # Consecutive days cross week and month closes; cold/reused frames must agree.
  for i in range(420,465):
   past=rows[:i+1];day=past[-1]['date']
   expected=collect_entry_facts(past,as_of=day,complete_session=True)
   actual=collect_entry_facts(past,as_of=day,complete_session=True,frame_cache=cache)
   self.assertEqual(actual,expected)
   self.assertEqual(assess_entry(actual),assess_entry(expected))
  self.assertLessEqual(len(cache),2)
  self.assertEqual(list(ticket_dates(rows,rows[420]['date'],rows[465]['date'])),
                   list(ticket_dates(rows,rows[420]['date'],rows[465]['date'],frame_cache={})))
 def test_revised_history_other_symbol_and_mutation_do_not_reuse_stale_frame(self):
  from copy import deepcopy
  rows=HistoryTests().rows()[:450];cache={};day=rows[-1]['date']
  actual=collect_entry_facts(rows,as_of=day,complete_session=True,frame_cache=cache)
  actual['frames']['monthly_completed']['bottoms'].append({'bad':True})
  self.assertEqual(collect_entry_facts(rows,as_of=day,complete_session=True,frame_cache=cache),
                   collect_entry_facts(rows,as_of=day,complete_session=True))
  changed=deepcopy(rows);changed[100]['high']+=20
  self.assertEqual(collect_entry_facts(changed,as_of=day,complete_session=True,frame_cache=cache),
                   collect_entry_facts(changed,as_of=day,complete_session=True))
  # A future-populated cache is safe when replay goes backwards.
  past=rows[:430]
  self.assertEqual(collect_entry_facts(past,as_of=past[-1]['date'],complete_session=True,frame_cache=cache),
                   collect_entry_facts(past,as_of=past[-1]['date'],complete_session=True))
 def test_factor_cache_preserves_all_states_and_rejects_revision(self):
  from copy import deepcopy
  from services.scanner.factor_detectors import evaluate_period_factors
  rows=HistoryTests().rows();cache={}
  for i in (430,431,432,430):
   past=rows[:i+1];day=past[-1]['date']
   self.assertEqual(evaluate_period_factors(past,day,complete_session=True,raw_cache=cache),
                    evaluate_period_factors(past,day,complete_session=True))
  changed=deepcopy(rows[:433]);changed[100]['high']+=20
  self.assertEqual(evaluate_period_factors(changed,changed[-1]['date'],complete_session=True,raw_cache=cache),
                   evaluate_period_factors(changed,changed[-1]['date'],complete_session=True))
  self.assertLessEqual(len(cache),96)

class SelectionPrefilterTests(unittest.TestCase):
 def test_blocked_entry_skips_diagnostic_only_and_default_keeps_it(self):
  from services.scanner.cr056_runner import run_snapshot
  rows=HistoryTests().rows();day=rows[-1]['date'];content=json.dumps(rows).encode()
  inputs={'as_of':day,'result_role':'legacy_comparison_input_repair','repaired':[{'symbol':'SPY','repaired_sha256':sha256(content),'source_sha256':sha256(content)}],'repaired_count':1,'excluded_count':0,'excluded':{}}
  with tempfile.TemporaryDirectory() as td:
   (Path(td)/'SPY.json').write_bytes(content)
   with patch('services.scanner.cr056_runner.assess_entry',return_value={'eligible':True,'paths':[],'reason_codes':[]}),patch('services.scanner.cr056_runner.evaluate_period_factors',side_effect=AssertionError('diagnostic scorer called')):
    report=run_snapshot(td,as_of=day,history={'days':[]},code_commit='a'*40,input_report=inputs,selection_only=True)
    self.assertEqual(report['ranked_symbols'],[])
    self.assertTrue(report['reviews'][0]['diagnostic_score_omitted'])
    self.assertFalse(report['reviews'][0]['permission']['eligible'])
    with self.assertRaisesRegex(AssertionError,'diagnostic scorer called'):
     run_snapshot(td,as_of=day,history={'days':[]},code_commit='a'*40,input_report=inputs)
   with self.assertRaisesRegex(ValueError,'empty nomination history'):
    run_snapshot(td,as_of=day,history={'days':[{}]},code_commit='a'*40,input_report=inputs,selection_only=True)
