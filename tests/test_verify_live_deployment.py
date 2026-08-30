import unittest
from unittest.mock import patch

from services.scanner.favorite_pattern_tracker import GENERALIZATION_VERSION, PATTERN_VERSION
from services.scanner.verify_live_deployment import verify


DATE="2026-08-26"

def bundle(tracker_date=DATE):
 return [
  {"status":"up_to_date","source_latest_complete_date":DATE,"tracker_as_of":DATE,"factor_snapshot_as_of":DATE,"radar_as_of":DATE,"industry_radar_as_of":DATE,"market_context_as_of":DATE,"signal_history_as_of":DATE,"data_dates_match":True,"future_data_used":False,"checks":{"macd_trigger_first":True,"favorite_pattern_tracker":True}},
  {"as_of":tracker_date,"favorite_pattern_tracker":{"as_of":tracker_date,"pattern_version":PATTERN_VERSION,"generalization_version":GENERALIZATION_VERSION,"production_scoring_changed":False,"summary":{"watchlist":8,"entry_ready":2}},"details":{"AAPL":{"audit":{"latest_bar":DATE,"future_rows_used":False}}}},
  {"as_of":tracker_date,"pattern_version":PATTERN_VERSION,"generalization_version":GENERALIZATION_VERSION,"production_scoring_changed":False,"summary":{"watchlist":8,"entry_ready":2}},
  {"as_of":DATE,"eligible_count":10,"triggered_count":1,"snapshot_mode_version":"macd-trigger-first-v1","future_data_used":False},
  {"as_of":DATE,"scan":{"future_data_used":False}},
  {"as_of":DATE,"future_data_used":False},
  {"as_of":DATE,"future_data_used":False},
  {"as_of":DATE,"future_data_used":False,"cases":[]},
  {"as_of":DATE,"future_data_used":False,"cases":[]},
  {"as_of":DATE,"selection_future_data_used":False,"events":[]},
  {"as_of":DATE,"selection_future_data_used":False,"view":{"scope":"latest","full_event_count":0},"events":[]},
  {"coverage":{"end":DATE},"days":[{"date":DATE}]},
 ]

class LiveDeploymentVerificationTests(unittest.TestCase):
 def test_retries_the_full_bundle_after_mixed_date_propagation(self):
  with patch("services.scanner.verify_live_deployment.fetch",side_effect=bundle("2026-08-25")+bundle()),patch("services.scanner.verify_live_deployment.time.sleep") as sleep:
   result=verify("https://example.test",DATE,attempts=2,delay_seconds=0)
  self.assertEqual(result["result"],"verified")
  self.assertEqual(result["factor_symbols"],1)
  self.assertEqual(result["favorite_pattern_entry_ready"],2)
  sleep.assert_called_once_with(0)

 def test_fails_closed_when_bundle_never_converges(self):
  with patch("services.scanner.verify_live_deployment.fetch",side_effect=bundle("2026-08-25")*2),patch("services.scanner.verify_live_deployment.time.sleep"):
   with self.assertRaisesRegex(RuntimeError,"not consistent"):
    verify("https://example.test",DATE,attempts=2,delay_seconds=0)

if __name__=="__main__":unittest.main()
