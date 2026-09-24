import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from services.scanner.market_external import parse_history, observation, run, validate, SOURCES
from services.scanner.verify_live_deployment import verify_external_market_asset
from services.contracts.market_data import canonical_fingerprint

CSV=b'DATE,OPEN,HIGH,LOW,CLOSE\n09/17/2026,16,17,15,15.44\n09/18/2026,15,16,14,14.81\n09/21/2026,15,16,14,99\n'
ROOT=Path(__file__).resolve().parents[1]

class ExternalMarketTests(unittest.TestCase):
 def test_future_rows_excluded_and_changes_use_only_observed_rows(self):
  o=observation('vix',CSV,'2026-09-18','2026-09-21T00:00:00Z')
  self.assertEqual(o['value'],14.81);self.assertEqual(o['change_previous'],-0.63)
  self.assertEqual(len(o['history']),2);self.assertEqual(o['status'],'current')
 def test_stale_data_keeps_real_date_not_target(self):
  o=observation('vix',CSV,'2026-09-20','2026-09-21T00:00:00Z')
  self.assertEqual(o['status'],'stale');self.assertEqual(o['observation_date'],'2026-09-18')
 def test_malformed_duplicate_nonfinite_and_future_only_are_rejected(self):
  for data in (b'DATE,CLOSE\n09/18/2026\n',b'DATE,CLOSE\n,14.8\n',b'<html>blocked</html>',CSV+CSV.splitlines()[2]+b'\n',CSV.replace(b'14.81',b'nan'),b'DATE,CLOSE\n09/21/2026,15\n'):
   with self.subTest(data=data),self.assertRaises((ValueError,KeyError)):
    parse_history(data,'2026-09-18')
 def test_one_failed_source_does_not_fake_value_or_hide_other_source(self):
  def fetcher(key):
   if key=='vix9d':raise OSError('offline')
   return CSV
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'public.json';run('2026-09-18',out=out,state=Path(d)/'archive',fetcher=fetcher)
   p=validate(json.loads(out.read_text()),'2026-09-18')
   self.assertEqual(p['indicators']['vix']['status'],'current')
   self.assertIsNone(p['indicators']['vix9d']['value'])
   self.assertEqual(p['indicators']['vix9d']['history'],[])
 def test_same_day_revision_keeps_both_observations(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'public.json';archive=Path(d)/'archive'
   run('2026-09-18',out=out,state=archive,fetcher=lambda _:CSV)
   old=out.read_bytes()
   run('2026-09-18',out=out,state=archive,fetcher=lambda _:CSV.replace(b'14.81',b'14.82'),refresh=True)
   self.assertEqual(len(list(archive.glob('*.json'))),2)
   self.assertIn(json.loads(old),[json.loads(p.read_bytes()) for p in archive.glob('*.json')])
 def test_current_day_reuses_saved_observations_without_network(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'public.json';archive=Path(d)/'archive'
   first=run('2026-09-18',out=out,state=archive,fetcher=lambda _:CSV)
   before=out.read_bytes()
   def no_fetch(key):raise AssertionError('same day must reuse saved data')
   again=run('2026-09-18',out=out,state=archive,fetcher=no_fetch)
   self.assertFalse(again['changed']);self.assertEqual(before,out.read_bytes())
   self.assertEqual(first['content_fingerprint'],again['content_fingerprint'])
   self.assertEqual(len(list(archive.glob('*.json'))),1)
 def test_only_failed_source_retries_and_next_day_fetches_both(self):
  with tempfile.TemporaryDirectory() as d:
   out=Path(d)/'public.json';archive=Path(d)/'archive';calls=[]
   def partial(key):
    if key=='vix9d':raise OSError('offline')
    return CSV
   run('2026-09-18',out=out,state=archive,fetcher=partial)
   original=json.loads(out.read_bytes())['indicators']['vix']
   def recovered(key):calls.append(key);return CSV
   run('2026-09-18',out=out,state=archive,fetcher=recovered)
   self.assertEqual(calls,['vix9d'])
   self.assertEqual(json.loads(out.read_bytes())['indicators']['vix'],original)
   calls.clear();run('2026-09-21',out=out,state=archive,fetcher=recovered)
   self.assertEqual(calls,['vix','vix9d'])
   self.assertEqual(len(list(archive.glob('*.json'))),3)
 def test_published_asset_and_source_identity_are_valid(self):
  p=validate(json.loads((ROOT/'public/market-external.json').read_bytes()))
  for key in SOURCES:
   bad=copy.deepcopy(p)
   original=bad['indicators'][key]['status']
   bad['indicators'][key]['status']='current' if original=='stale' else 'stale'
   self.assertNotEqual(bad['indicators'][key]['status'],original)
   with self.assertRaises(ValueError):validate(bad)
  with self.assertRaisesRegex(ValueError,'target_date'):validate(p,'2099-01-01')
  with patch('services.scanner.verify_live_deployment.fetch',return_value=p):
   self.assertEqual(verify_external_market_asset('https://example.test',p['as_of'],'a'*40)['content_fingerprint'],p['content_fingerprint'])
  bad=copy.deepcopy(p);bad['fetched_at']='2026-09-22T00:00:00Z';bad['content_fingerprint']=canonical_fingerprint({k:v for k,v in bad.items() if k!='content_fingerprint'})
  with patch('services.scanner.verify_live_deployment.fetch',return_value=bad),self.assertRaises(RuntimeError):
   verify_external_market_asset('https://example.test',p['as_of'],'a'*40)

 def test_status_tampering_is_rejected_for_current_and_stale_observations(self):
  for target,expected in [('2026-09-18','current'),('2026-09-20','stale')]:
   with self.subTest(status=expected),tempfile.TemporaryDirectory() as d:
    out=Path(d)/'public.json'
    run(target,out=out,state=Path(d)/'archive',fetcher=lambda _:CSV)
    payload=validate(json.loads(out.read_bytes()),target)
    for key in SOURCES:
     self.assertEqual(payload['indicators'][key]['status'],expected)
     bad=copy.deepcopy(payload)
     bad['indicators'][key]['status']='stale' if expected=='current' else 'current'
     # Re-sign to prove the freshness contract rejects the lie independently
     # of the fingerprint check, including legitimately delayed providers.
     bad['content_fingerprint']=canonical_fingerprint({k:v for k,v in bad.items() if k!='content_fingerprint'})
     with self.assertRaisesRegex(ValueError,'external_freshness_mismatch'):
      validate(bad,target)

if __name__=='__main__':unittest.main()
