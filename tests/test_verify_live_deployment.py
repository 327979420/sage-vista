import unittest
from unittest.mock import patch
from services.scanner.verify_live_deployment import verify

class LiveDeploymentVerificationTests(unittest.TestCase):
 def payloads(self,date="2026-08-25"):
  return [
   {"status":"up_to_date","source_latest_complete_date":date,"tracker_as_of":date,"radar_as_of":date,"data_dates_match":True,"future_data_used":False},
   {"as_of":date,"details":{"AAA":{"audit":{"latest_bar":date,"future_rows_used":False}}}},
   {"as_of":date,"scan":{"future_data_used":False}},
  ]
 def test_accepts_exact_live_date_and_safe_audits(self):
  with patch("services.scanner.verify_live_deployment.fetch",side_effect=self.payloads()):self.assertEqual(verify("https://example.workers.dev","2026-08-25")["result"],"verified")
 def test_rejects_any_date_mismatch(self):
  payloads=self.payloads();payloads[2]["as_of"]="2026-08-24"
  with patch("services.scanner.verify_live_deployment.fetch",side_effect=payloads),self.assertRaises(RuntimeError):verify("https://example.workers.dev","2026-08-25")
 def test_rejects_future_data(self):
  payloads=self.payloads();payloads[0]["future_data_used"]=True
  with patch("services.scanner.verify_live_deployment.fetch",side_effect=payloads),self.assertRaises(RuntimeError):verify("https://example.workers.dev","2026-08-25")
