import json, math, tempfile, unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from research.backtest.cr056_history import ticket_dates, prepare
from services.gates.baseline import exact_daily_macd_bull_cross
from research.backtest.run_store import POLICY, CANDIDATE_POLICY, trade_csv, sha256, seal, save

class HistoryTests(unittest.TestCase):
 def rows(self):
  days=[date(2020,1,1)+timedelta(days=i) for i in range(900)]
  return [{'date':d.isoformat(),'open':100+8*math.sin(i/5),'high':111.,'low':89.,'close':100+8*math.sin(i/5),'adjusted_close':100+8*math.sin(i/5),'volume':1000000} for i,d in enumerate(days) if d.weekday()<5]
 def test_ticket_preindex_matches_same_baseline_on_every_historical_day(self):
  rows=self.rows();actual=set(ticket_dates(rows,rows[420]['date'],rows[-1]['date']))
  expected={r['date'] for i,r in enumerate(rows) if i>=420 and exact_daily_macd_bull_cross(rows[:i+1])}
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
   with patch('research.backtest.cr056_history.collect_direction_facts',return_value={}),patch('research.backtest.cr056_history.assess_permission',return_value={'eligible':True}),patch('research.backtest.cr056_history.run_snapshot',side_effect=snapshot),patch('research.backtest.cr056_history.signal_support_plan',return_value={'level':90}):
    ledger,rankings=prepare(request,cache,root/'state','a'*40)
    self.assertEqual(len(calls),51)
    events=json.loads(ledger.read_bytes())['events']
    self.assertEqual(len(events),2)
    self.assertTrue(all(e['selection']['execution_policy_version']==POLICY for e in events))
    before=ledger.read_bytes();calls.clear()
    prepare(request,cache,root/'state','b'*40)
    self.assertEqual(calls,[]);self.assertEqual(ledger.read_bytes(),before)

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
