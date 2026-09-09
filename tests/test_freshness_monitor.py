import unittest
from services.scanner.freshness_monitor import evaluate, evaluate_live

class FreshnessMonitorTests(unittest.TestCase):
 def status(self,date="2026-08-26"):
  return {"source_latest_complete_date":date,"tracker_as_of":date,"radar_as_of":date,"factor_snapshot_as_of":date,"industry_radar_as_of":date,"market_context_as_of":date,"signal_history_as_of":date,"data_dates_match":True,"future_data_used":False}

 def test_fresh_repository_passes(self):
  result=evaluate("2026-08-26",self.status())
  self.assertEqual(result["result"],"fresh")
  self.assertTrue(result["data_dates_match"])

 def test_missed_daily_cron_is_detected(self):
  result=evaluate("2026-08-26",self.status("2026-08-25"))
  self.assertEqual(result["result"],"stale")
  self.assertFalse(result["data_dates_match"])

 def test_missing_snapshot_or_failed_leakage_audit_is_stale(self):
  missing=self.status();missing.pop("factor_snapshot_as_of")
  unsafe=self.status();unsafe["future_data_used"]=True
  self.assertEqual(evaluate("2026-08-26",missing)["result"],"stale")
  self.assertEqual(evaluate("2026-08-26",unsafe)["result"],"stale")

 def test_online_old_date_or_old_policy_is_stale_even_when_repository_is_fresh(self):
  from services.contracts.cr056_policy import POLICY_VERSION, POLICY_FINGERPRINT
  day='2026-09-08'
  candidate={'as_of':day,'policy_version':POLICY_VERSION,'policy_fingerprint':POLICY_FINGERPRINT,'refresh_status':{'status':'current'}}
  market={'as_of':day};industry={'as_of':day,'display_context':{'as_of':day}}
  self.assertEqual(evaluate_live(day,self.status(day),candidate,market,industry)['result'],'fresh')
  self.assertEqual(evaluate_live(day,self.status(day),{**candidate,'refresh_status':{'status':'updated'}},market,industry)['result'],'fresh')
  for change in ({'as_of':'2026-09-04'},{'policy_fingerprint':'old'},{'refresh_status':{'status':'failed'}}):
   self.assertEqual(evaluate_live(day,self.status(day),{**candidate,**change},market,industry)['result'],'stale')

if __name__=="__main__":unittest.main()
