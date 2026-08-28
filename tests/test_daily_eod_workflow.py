import pathlib,re,unittest

WORKFLOW=pathlib.Path(__file__).parents[1]/".github/workflows/daily-eod.yml"

class DailyEodWorkflowTests(unittest.TestCase):
 def test_retry_window_uses_independent_crons(self):
  text=WORKFLOW.read_text();crons=re.findall(r'- cron: "([^"]+)"',text)
  self.assertEqual(crons,["47 23 * * 1-5","17 0 * * 2-6","47 0 * * 2-6","17 1 * * 2-6","47 1 * * 2-6","17 2 * * 2-6","17 3 * * 2-6"])
 def test_retries_are_idempotent_and_visible(self):
  text=WORKFLOW.read_text()
  self.assertIn("already_current",text)
  self.assertIn("GITHUB_STEP_SUMMARY",text)
  self.assertIn("eod-freshness-${{ github.run_id }}",text)
  self.assertIn("needs_release",text)
  self.assertIn("automation/production-state.json",text)
  self.assertIn("services.scanner.verify_live_deployment",text)
  self.assertIn("public/signal-history.json",text)
  self.assertIn("public/market-etf-watch.json",text)
  self.assertIn("unified_v2_scan --published-latest",text)
  self.assertIn("services.scanner.experiment_catalog",text)
  self.assertNotIn("--start 2026-07-01",text)
 def test_code_and_experiment_changes_auto_deploy(self):
  text=(WORKFLOW.parent/"deploy-site.yml").read_text()
  self.assertIn("push:",text);self.assertIn('"app/**"',text);self.assertIn('"research/**"',text)
  self.assertIn("services.scanner.experiment_catalog",text);self.assertIn("docs/EXPERIMENT_SUMMARY_ZH.md",text)
  self.assertIn("Sage Vista UI v5.6",text)
  self.assertIn("live experiment catalog mismatch",text)
 def test_historical_backfill_is_isolated_from_daily_delivery(self):
  backfill=(WORKFLOW.parent/"unified-v2-backfill.yml").read_text()
  self.assertIn("workflow_dispatch",backfill)
  self.assertNotIn("schedule:",backfill)
  self.assertIn("--replace",backfill)
  self.assertLess(backfill.index("git pull --rebase origin main"),backfill.index("merge_unified_v2_reports"))
 def test_saved_week_recovery_does_not_recalculate_history(self):
  recovery=(WORKFLOW.parent/"recover-unified-v2-backfill.yml").read_text()
  self.assertIn("gh run download",recovery)
  self.assertIn("merge_unified_v2_reports",recovery)
  self.assertNotIn("unified_v2_scan --start",recovery)
