import unittest
from services.scanner.legacy_signal_recovery import recover

def radar(day,score,commit):
 return {"commit":commit,"radar":{"as_of":day,"registry_version":"0.4.0","signals":[{"symbol":"PG","date":day,"price":145,"score":score,"total_score":score,"official_score":0,"components":["日线MACD近5日金叉"],"factor_ids":["macd.daily_bull_cross"]}]}}

class LegacySignalRecoveryTests(unittest.TestCase):
 def test_pg_is_one_permanent_case_with_original_daily_scores(self):
  payload=recover({"cases":[]},[radar("2026-08-25",6,"a"),radar("2026-08-26",5,"b")],"2026-08-26")
  self.assertEqual(len(payload["cases"]),1);case=payload["cases"][0]
  self.assertEqual(case["first_seen_date"],"2026-08-25");self.assertEqual(case["signal_time_snapshot"]["multi_factor"]["legacy_production_score"],6)
  self.assertEqual([x["legacy_production_score"] for x in case["daily_states"]],[6,5]);self.assertTrue(case["recovery"]["recovered_from_git"])

 def test_later_same_day_rewrite_cannot_erase_or_lower_original_alert(self):
  payload=recover({"cases":[]},[radar("2026-08-25",6,"a"),radar("2026-08-25",5,"b")],"2026-08-25")
  self.assertEqual(payload["cases"][0]["daily_states"][0]["legacy_production_score"],6)

 def test_existing_recorder_case_is_enriched_not_duplicated(self):
  first=recover({"cases":[]},[radar("2026-08-25",6,"a")],"2026-08-25");case=first["cases"][0]
  case.pop("recovery");case["signal_time_snapshot"]["multi_factor"].pop("legacy_production_score");case["daily_states"]=[]
  from services.scanner.signal_history import _immutable_fingerprint
  case["immutable_fingerprint"]=_immutable_fingerprint(case)
  merged=recover(first,[radar("2026-08-25",6,"a")],"2026-08-25")
  self.assertEqual(len(merged["cases"]),1);self.assertTrue(merged["cases"][0]["recovery"]["recovered_from_git"])

if __name__=="__main__":unittest.main()
