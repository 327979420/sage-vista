import unittest
from unittest.mock import patch

from services.scanner.verify_live_deployment import verify


DATE="2026-08-26"

def bundle(tracker_date=DATE):
 return [
  {"status":"up_to_date","source_latest_complete_date":DATE,"tracker_as_of":DATE,"factor_snapshot_as_of":DATE,"radar_as_of":DATE,"data_dates_match":True,"future_data_used":False},
  {"as_of":tracker_date,"details":{"AAPL":{"audit":{"latest_bar":DATE,"future_rows_used":False}}}},
  {"as_of":DATE,"eligible_count":1,"future_data_used":False},
  {"as_of":DATE,"scan":{"future_data_used":False}},
 ]

class LiveDeploymentVerificationTests(unittest.TestCase):
 def test_retries_the_full_bundle_after_mixed_date_propagation(self):
  with patch("services.scanner.verify_live_deployment.fetch",side_effect=bundle("2026-08-25")+bundle()),patch("services.scanner.verify_live_deployment.time.sleep") as sleep:
   result=verify("https://example.test",DATE,attempts=2,delay_seconds=0)
  self.assertEqual(result["result"],"verified")
  self.assertEqual(result["factor_symbols"],1)
  sleep.assert_called_once_with(0)

 def test_fails_closed_when_bundle_never_converges(self):
  with patch("services.scanner.verify_live_deployment.fetch",side_effect=bundle("2026-08-25")*2),patch("services.scanner.verify_live_deployment.time.sleep"):
   with self.assertRaisesRegex(RuntimeError,"not consistent"):
    verify("https://example.test",DATE,attempts=2,delay_seconds=0)

if __name__=="__main__":unittest.main()
