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

 def test_rejects_mixed_versions(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);a=root/"a.json";b=root/"b.json"
   a.write_text(json.dumps({"version":"a","future_data_used":False,"days":[{"date":"2026-01-01"}]}));b.write_text(json.dumps({"version":"b","future_data_used":False,"days":[{"date":"2026-01-02"}]}))
   with self.assertRaisesRegex(RuntimeError,"versions"):merge([a,b],root/"out.json")


if __name__=="__main__":unittest.main()
