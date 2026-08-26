import io,json,unittest,urllib.error
from unittest.mock import patch
from services.scanner.verify_live_deployment import fetch,verify

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
 def test_retries_during_cloudflare_propagation(self):
  response=io.BytesIO(json.dumps({"status":"up_to_date"}).encode());response.status=200
  response.__enter__=lambda value:value;response.__exit__=lambda *args:None
  error=urllib.error.HTTPError("https://example.workers.dev/update-status.json",404,"Not Found",{},None)
  with patch("services.scanner.verify_live_deployment.urllib.request.urlopen",side_effect=[error,response]),patch("services.scanner.verify_live_deployment.time.sleep") as sleep:
   self.assertEqual(fetch("https://example.workers.dev","update-status.json","2026-08-25",attempts=2,delay_seconds=1)["status"],"up_to_date")
   sleep.assert_called_once_with(1)
