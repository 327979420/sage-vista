import tempfile,unittest
from pathlib import Path
from services.scanner.backtest_progress import build_state,plan,previous_week,write_state


class BacktestProgressTests(unittest.TestCase):
 def report(self,start="2026-05-01",end="2026-08-27"):
  return {"version":"old-model","model":{"factor_registry_version":"0.7"},"coverage":{"start":start,"end":end,"sessions":82},"days":[{"date":start,"model_version":"old-model","factor_registry_version":"0.7"},{"date":end,"model_version":"old-model","factor_registry_version":"0.7"}]}

 def test_plans_the_previous_natural_week_without_repeating_coverage(self):
  self.assertEqual(previous_week("2026-05-01"),{"label":"2026-04-27_to_2026-04-30","start":"2026-04-27","end":"2026-04-30"})
  result=plan(self.report());self.assertEqual(result["next_window"]["start"],"2026-04-27")

 def test_new_batch_keeps_earlier_rule_versions_and_advances_only_after_completion(self):
  initial=build_state(self.report(),completed_at="2026-08-28T00:00:00Z")
  expanded=self.report("2026-04-27","2026-08-27");expanded["days"][0]={"date":"2026-04-27","model_version":"new-model","factor_registry_version":"0.8"}
  done=build_state(expanded,initial,{"label":"2026-04-27_to_2026-04-30","start":"2026-04-27","end":"2026-04-30"},"2026-08-29T00:00:00Z")
  self.assertEqual(done["last_successful_batch"]["model_versions"],["new-model"])
  self.assertEqual(done["next_window"]["start"],"2026-04-20")
  self.assertTrue(done["policy"]["completed_weeks_never_recomputed_automatically"])

 def test_a_holiday_only_window_is_recorded_and_not_retried(self):
  # 2025-09-01 was Labor Day: coverage starts 2025-09-02, the planned window is that Monday alone and yields no sessions.
  initial=build_state(self.report("2025-09-02","2026-10-14"),completed_at="2026-10-11T00:00:00Z")
  self.assertEqual(initial["next_window"],{"label":"2025-09-01_to_2025-09-01","start":"2025-09-01","end":"2025-09-01"})
  done=build_state(self.report("2025-09-02","2026-10-14"),initial,initial["next_window"],"2026-10-12T00:00:00Z")
  batch=done["last_successful_batch"]
  self.assertEqual(batch["sessions"],0)
  self.assertEqual(batch["model_versions"],["old-model"])
  self.assertTrue(batch["factor_registry_versions"])
  self.assertEqual(done["scanned_start"],"2025-09-01")
  self.assertEqual(done["next_window"],{"label":"2025-08-25_to_2025-08-31","start":"2025-08-25","end":"2025-08-31"})
  self.assertEqual(plan(self.report("2025-09-02","2026-10-14"),done)["next_window"]["start"],"2025-08-25")

 def test_state_and_internal_mirror_are_identical(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);report=root/"report.json";state=root/"state.json";mirror=root/"mirror.json"
   import json;report.write_text(json.dumps(self.report()))
   payload=write_state(report,state,mirror,completed_at="2026-08-28T00:00:00Z")
   self.assertEqual(state.read_text(),mirror.read_text());self.assertEqual(payload["status"],"scheduled")


if __name__=="__main__":unittest.main()
