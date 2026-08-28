import json,tempfile,unittest
from pathlib import Path
from services.scanner.merge_unified_v2_reports import merge


class MergeUnifiedV2ReportsTests(unittest.TestCase):
 def test_merges_partitions_by_unique_session(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);a=root/"a.json";b=root/"b.json";out=root/"out.json"
   common={"version":"unified-v2-shadow-1.0.0","future_data_used":False,"model":{}}
   a.write_text(json.dumps({**common,"days":[{"date":"2026-07-02"},{"date":"2026-07-01"}]}))
   b.write_text(json.dumps({**common,"days":[{"date":"2026-07-02","new":True},{"date":"2026-08-03"}]}))
   result=merge([a,b],out)
   self.assertEqual(result["coverage"],{"start":"2026-07-01","end":"2026-08-03","sessions":3})
   self.assertTrue(result["days"][1]["new"])

 def test_preserves_mixed_versions_without_recalculating_old_days(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);a=root/"a.json";b=root/"b.json"
   a.write_text(json.dumps({"version":"a","future_data_used":False,"days":[{"date":"2026-01-01"}]}));b.write_text(json.dumps({"version":"b","future_data_used":False,"days":[{"date":"2026-01-02"}]}))
   result=merge([a,b],root/"out.json")
   self.assertEqual(result["model_versions"],["a","b"])
   self.assertEqual(result["days"][0]["model_version"],"a")
   self.assertEqual(result["days"][1]["model_version"],"b")

 def test_public_history_keeps_full_recent_audit_and_only_hits_on_older_days(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/"source.json"
   days=[]
   for index in range(31):
    days.append({"date":f"2026-01-{index+1:02d}","ranking":[{"factor_ledger":[{"factor_id":"hit","hit":True,"points":0},{"factor_id":"miss","hit":False,"points":0}]}]})
   source.write_text(json.dumps({"version":"v","future_data_used":False,"days":days}))
   result=merge([source],root/"out.json")
   self.assertEqual([item["factor_id"] for item in result["days"][0]["ranking"][0]["factor_ledger"]],["hit"])
   self.assertEqual(len(result["days"][-1]["ranking"][0]["factor_ledger"]),2)


if __name__=="__main__":unittest.main()
