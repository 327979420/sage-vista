import json,pathlib,tempfile,unittest
from unittest.mock import patch

from services.scanner.favorite_pattern_tracker import GENERALIZATION_VERSION, PATTERN_VERSION
from services.scanner.verify_live_deployment import persist_verified_receipt, verify


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
  {"version":"unified-v2-macd-trigger-1.4.0","coverage":{"end":DATE},"days":[{"date":DATE}]},
 ]

class LiveDeploymentVerificationTests(unittest.TestCase):
 def test_retries_the_full_bundle_after_mixed_date_propagation(self):
  with patch("services.scanner.verify_live_deployment.fetch",side_effect=bundle("2026-08-25")+bundle()),patch("services.scanner.verify_live_deployment.fetch_text",return_value="<p>Build abcdef1</p>"),patch("services.scanner.verify_live_deployment.time.sleep") as sleep:
   result=verify("https://example.test",DATE,"abcdef1234567890",attempts=2,delay_seconds=0)
  self.assertEqual(result["result"],"verified")
  self.assertEqual(result["factor_symbols"],1)
  self.assertEqual(result["favorite_pattern_entry_ready"],2)
  sleep.assert_called_once_with(0)

 def test_fails_closed_when_bundle_never_converges(self):
  with patch("services.scanner.verify_live_deployment.fetch",side_effect=bundle("2026-08-25")*2),patch("services.scanner.verify_live_deployment.fetch_text",return_value="<p>Build abcdef1</p>"),patch("services.scanner.verify_live_deployment.time.sleep"):
   with self.assertRaisesRegex(RuntimeError,"not consistent"):
    verify("https://example.test",DATE,"abcdef1234567890",attempts=2,delay_seconds=0)

 def test_receipt_records_live_version_and_verified_deployment_commit(self):
  commit="abcdef1234567890"
  with patch("services.scanner.verify_live_deployment.fetch",side_effect=bundle()),patch("services.scanner.verify_live_deployment.fetch_text",return_value="<p>Build abcdef1</p>"):
   result=verify("https://example.test",DATE,deployment_commit=commit,attempts=1)
  self.assertEqual(result["website_version"],"unified-v2-macd-trigger-1.4.0")
  self.assertEqual(result["deployment_commit"],commit)

 def test_fails_closed_when_deployment_commit_is_not_live(self):
  with patch("services.scanner.verify_live_deployment.fetch",side_effect=bundle()),patch("services.scanner.verify_live_deployment.fetch_text",return_value="<p>Build 0000000</p>"):
   with self.assertRaisesRegex(RuntimeError,"commit marker mismatch"):
    verify("https://example.test",DATE,deployment_commit="abcdef1234567890",attempts=1)

 def test_fails_immediately_without_deployment_commit(self):
  with patch("services.scanner.verify_live_deployment.fetch") as fetch:
   with self.assertRaisesRegex(RuntimeError,"commit evidence is required"):
    verify("https://example.test",DATE,"")
  fetch.assert_not_called()

 def test_incomplete_receipt_never_changes_production_state(self):
  complete={"result":"verified","as_of":DATE,"site_url":"https://example.test","website_version":"1.4","deployment_commit":"abcdef123"}
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);receipt=root/"receipt.json";state=root/"state.json"
   original={"discord_result":"sent","trigger_source":"manual","other":"keep"}
   for missing in ("result","as_of","site_url","website_version","deployment_commit"):
    state.write_text(json.dumps(original)+"\n");candidate=dict(complete);candidate.pop(missing);receipt.write_text(json.dumps(candidate)+"\n")
    with self.assertRaises(RuntimeError):persist_verified_receipt(receipt,state)
    self.assertEqual(json.loads(state.read_text()),original)

 def test_persisted_receipt_preserves_unrelated_state(self):
  receipt_data={"result":"verified","as_of":DATE,"site_url":"https://example.test","website_version":"1.4","deployment_commit":"abcdef123"}
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);receipt=root/"receipt.json";state=root/"state.json"
   receipt.write_text(json.dumps(receipt_data)+"\n");state.write_text(json.dumps({"discord_result":"sent","trigger_source":"manual","other":"keep"})+"\n")
   persisted=persist_verified_receipt(receipt,state)
   self.assertEqual(persisted["discord_result"],"sent");self.assertEqual(persisted["trigger_source"],"manual");self.assertEqual(persisted["other"],"keep")
   self.assertEqual(persisted["deployment_commit"],"abcdef123");self.assertTrue(persisted["live_verified"])
   self.assertEqual(json.loads(state.read_text()),persisted)

 def test_older_receipt_cannot_replace_newer_state(self):
  receipt_data={"result":"verified","as_of":"2026-08-25","site_url":"https://old.example","website_version":"1.3","deployment_commit":"oldcommit"}
  original={"as_of":"2026-08-26","site_url":"https://new.example","website_version":"1.4","deployment_commit":"newcommit","discord_result":"sent"}
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);receipt=root/"receipt.json";state=root/"state.json"
   receipt.write_text(json.dumps(receipt_data)+"\n");original_text=json.dumps(original,indent=2)+"\n";state.write_text(original_text)
   with self.assertRaisesRegex(RuntimeError,"Older deployment receipt"):
    persist_verified_receipt(receipt,state)
   self.assertEqual(state.read_text(),original_text)

 def test_same_date_receipt_can_update_deployment(self):
  receipt_data={"result":"verified","as_of":DATE,"site_url":"https://example.test","website_version":"1.4","deployment_commit":"newcommit"}
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);receipt=root/"receipt.json";state=root/"state.json"
   receipt.write_text(json.dumps(receipt_data)+"\n");state.write_text(json.dumps({"as_of":DATE,"deployment_commit":"oldcommit","discord_result":"sent"})+"\n")
   persisted=persist_verified_receipt(receipt,state)
   self.assertEqual(persisted["deployment_commit"],"newcommit");self.assertEqual(persisted["discord_result"],"sent")

 def test_newer_date_receipt_updates_state(self):
  receipt_data={"result":"verified","as_of":"2026-08-27","site_url":"https://example.test","website_version":"1.4","deployment_commit":"newcommit"}
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);receipt=root/"receipt.json";state=root/"state.json"
   receipt.write_text(json.dumps(receipt_data)+"\n");state.write_text(json.dumps({"as_of":DATE,"deployment_commit":"oldcommit"})+"\n")
   self.assertEqual(persist_verified_receipt(receipt,state)["as_of"],"2026-08-27")

 def test_invalid_existing_or_receipt_date_never_changes_state(self):
  complete={"result":"verified","as_of":DATE,"site_url":"https://example.test","website_version":"1.4","deployment_commit":"newcommit"}
  with tempfile.TemporaryDirectory() as directory:
   root=pathlib.Path(directory);receipt=root/"receipt.json";state=root/"state.json"
   cases=[({**complete,"as_of":"2026-8-27"},{"as_of":DATE}), (complete,{"as_of":"2026-02-30"})]
   for receipt_data,state_data in cases:
    receipt.write_text(json.dumps(receipt_data)+"\n");original_text=json.dumps(state_data,indent=2)+"\n";state.write_text(original_text)
    with self.assertRaisesRegex(RuntimeError,"YYYY-MM-DD"):
     persist_verified_receipt(receipt,state)
    self.assertEqual(state.read_text(),original_text)

if __name__=="__main__":unittest.main()
