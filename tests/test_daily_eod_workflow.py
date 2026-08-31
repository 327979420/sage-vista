import pathlib,re,unittest

WORKFLOW=pathlib.Path(__file__).parents[1]/".github/workflows/daily-eod.yml"
ROOT=WORKFLOW.parents[2]

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
  self.assertIn('--deployment-commit "${{ steps.audited_data_commit.outputs.deployment_commit }}"',text)
  self.assertNotIn('--deployment-commit "$GITHUB_SHA"',text)
  self.assertIn("verify_live_deployment persist --receipt-path live-verification.json",text)
  self.assertLess(text.index("Persist verified website deployment receipt"),text.index("Send deduplicated Discord daily digest"))
  self.assertIn("public/signal-history.json",text)
  self.assertIn("public/favorite-pattern.json",text)
  self.assertIn("public/signal-history-summary.json",text)
  self.assertIn("public/unified-v2-latest.json",text)
  self.assertIn("public/opportunity-ledger-latest.json",text)
  self.assertIn("public/market-etf-watch.json",text)
  self.assertIn("unified_v2_scan --published-latest",text)
  self.assertNotIn("services.scanner.experiment_catalog",text)
  self.assertIn("Refresh pre-deployment machine status",text)
  self.assertIn("docs/CURRENT_STATUS_ZH.md",text)
  self.assertIn("UPDATE_TRIGGER_SOURCE",text)
  self.assertIn("cloudflare_cron",text)
  self.assertIn("freshness_recovery",text)
  self.assertNotIn("--start 2026-07-01",text)
 def test_cloudflare_is_independent_primary_scheduler_and_monitor_recovers(self):
  config=(ROOT/"wrangler.eod-scheduler.jsonc").read_text()
  worker=(ROOT/"services/automation/eod_scheduler_worker.mjs").read_text()
  monitor=(WORKFLOW.parent/"eod-freshness-monitor.yml").read_text()
  deploy=(WORKFLOW.parent/"deploy-eod-scheduler.yml").read_text()
  self.assertIn('"name": "sage-vista-eod-scheduler"',config)
  self.assertIn('"37 4 * * 2-6"',config)
  self.assertIn("GITHUB_ACTIONS_TOKEN",worker)
  self.assertNotIn("test-token-must-not-leak",worker)
  self.assertIn("actions: write",monitor)
  self.assertIn("trigger_source=freshness_recovery",monitor)
  self.assertIn("SAGE_VISTA_SCHEDULER_GITHUB_TOKEN",deploy)
 def test_code_changes_deploy_without_republishing_research(self):
  text=(WORKFLOW.parent/"deploy-site.yml").read_text()
  self.assertIn("push:",text);self.assertIn('"app/**"',text);self.assertNotIn('"research/**"',text)
  self.assertNotIn("services.scanner.experiment_catalog",text);self.assertNotIn("docs/EXPERIMENT_SUMMARY_ZH.md",text)
  self.assertIn("services.scanner.project_status",text);self.assertIn("docs/CURRENT_STATUS_ZH.md",text)
  self.assertIn('verify_live_deployment verify --url "$PRODUCTION_SITE_URL"',text)
  self.assertIn('--deployment-commit "${{ steps.production_head.outputs.deployment_commit }}"',text)
  self.assertNotIn('--deployment-commit "$GITHUB_SHA"',text)
  self.assertIn("website-deployment-receipt-${{ github.run_id }}",text)
  self.assertIn("verify_live_deployment persist --receipt-path live-verification.json",text)
  self.assertIn("[skip ci]",text)
  self.assertNotIn("live experiment catalog mismatch",text)
  self.assertNotIn("live backtest progress mismatch",text)

 def test_production_deployments_share_one_lock_and_one_receipt_writer(self):
  daily=WORKFLOW.read_text();site=(WORKFLOW.parent/"deploy-site.yml").read_text()
  groups=[re.search(r"concurrency:\s+group: ([^\n]+)",text).group(1) for text in (daily,site)]
  self.assertEqual(groups,["sage-vista-production-deploy"]*2)
  for text in (daily,site):
   self.assertIn("cancel-in-progress: false",text)
   self.assertEqual(text.count("verify_live_deployment persist --receipt-path live-verification.json"),1)
   self.assertNotIn('state.update({"as_of":receipt',text)

 def test_daily_deploys_the_commit_created_by_the_data_step(self):
  text=WORKFLOW.read_text()
  commit=text.index("name: Commit audited website data")
  output=text.index('echo "deployment_commit=$(git rev-parse HEAD)"')
  rebuild=text.index("name: Rebuild production website for deployment commit")
  deploy=text.index("name: Deploy production to Cloudflare Workers")
  verify=text.index("name: Verify live Cloudflare dates and audits")
  self.assertLess(commit,output);self.assertLess(output,rebuild);self.assertLess(rebuild,deploy);self.assertLess(deploy,verify)
  self.assertIn("id: audited_data_commit",text[commit:output])
  self.assertNotIn("exit 0",text[commit:output])
  self.assertIn("if ! git diff --cached --quiet; then",text[commit:output])
  self.assertIn('GITHUB_SHA: ${{ steps.audited_data_commit.outputs.deployment_commit }}',text[rebuild:deploy])
  self.assertIn("run: npm run build",text[rebuild:deploy])

 def test_both_workflows_sync_latest_main_before_production_work(self):
  daily=WORKFLOW.read_text();site=(WORKFLOW.parent/"deploy-site.yml").read_text()
  for text,first_operation in ((daily,"name: Run fail-closed daily update"),(site,"name: Verify repository status snapshot is current")):
   checkout=text.index("uses: actions/checkout@v7")
   sync=text.index("name: Sync latest production main")
   operation=text.index(first_operation)
   self.assertLess(checkout,sync);self.assertLess(sync,operation)
   block=text[sync:operation]
   self.assertIn("git fetch origin main",block)
   self.assertIn("git switch --detach origin/main",block)

 def test_site_build_and_verification_use_synced_head(self):
  text=(WORKFLOW.parent/"deploy-site.yml").read_text()
  sync=text.index("name: Sync latest production main")
  build=text.index("name: Build and test website")
  deploy=text.index("name: Deploy existing audited data and website")
  verify=text.index("name: Verify live website and write deployment receipt")
  self.assertLess(sync,build);self.assertLess(build,deploy);self.assertLess(deploy,verify)
  self.assertIn('echo "deployment_commit=$(git rev-parse HEAD)"',text[sync:build])
  self.assertIn('GITHUB_SHA: ${{ steps.production_head.outputs.deployment_commit }}',text[build:deploy])
  self.assertIn('--deployment-commit "${{ steps.production_head.outputs.deployment_commit }}"',text[verify:])
  self.assertNotIn('--deployment-commit "$GITHUB_SHA"',text)

 def test_both_deployments_upload_receipt_before_persisting_it(self):
  for text in (WORKFLOW.read_text(),(WORKFLOW.parent/"deploy-site.yml").read_text()):
   upload=text.index("name: Upload deployment receipt")
   persist=text.index("verify_live_deployment persist --receipt-path live-verification.json")
   self.assertLess(upload,persist)
   block=text[upload:persist]
   self.assertIn("website-deployment-receipt-${{ github.run_id }}",block)
   self.assertIn("path: live-verification.json",block)
   self.assertIn("retention-days: 30",block)
 def test_historical_backfill_is_isolated_from_daily_delivery(self):
  backfill=(WORKFLOW.parent/"unified-v2-backfill.yml").read_text()
  self.assertIn("workflow_dispatch",backfill)
  self.assertNotIn("schedule:",backfill)
  self.assertIn("--replace",backfill)
  self.assertLess(backfill.index("git pull --rebase origin main"),backfill.index("merge_unified_v2_reports"))
  nightly=(WORKFLOW.parent/"nightly-backtest.yml").read_text()
  self.assertIn('cron: "30 11 * * *"',nightly)
  self.assertIn("services.scanner.backtest_progress plan",nightly)
  self.assertIn("services.scanner.project_status",nightly)
  self.assertNotIn("gh workflow run deploy-site.yml",nightly)
  self.assertIn("one older natural week",nightly)
  self.assertIn("weekly checkpoint",nightly)
  self.assertIn("failure does not advance progress",nightly)
  self.assertNotIn("timeout-minutes",nightly)
 def test_saved_week_recovery_does_not_recalculate_history(self):
  recovery=(WORKFLOW.parent/"recover-unified-v2-backfill.yml").read_text()
  self.assertIn("gh run download",recovery)
  self.assertIn("merge_unified_v2_reports",recovery)
  self.assertNotIn("unified_v2_scan --start",recovery)
