import json,pathlib,re,unittest

ROOT=pathlib.Path(__file__).parents[1]

class UiV2ContractTests(unittest.TestCase):
 def test_market_mvp_keeps_scope_date_and_separate_observation_layers(self):
  text=(ROOT/"app/zh/watch/market/dashboard.tsx").read_text()
  for label in ('固定样本','不代表整个美股市场','targetDate','market-cockpit-v1','Chart','期权成交结构'):
   self.assertIn(label,text)
  self.assertNotIn('source_page',text)
  self.assertNotIn('今日研究总览',(ROOT/"app/zh/watch/resonance/tracker-ui.tsx").read_text())

 def test_experiment_archive_is_git_only(self):
  text=(ROOT/"app/zh/watch/resonance/research/page.tsx").read_text()
  self.assertIn('redirect("/")',text)
  self.assertTrue((ROOT/"research/generated/experiment-catalog.json").exists())
  self.assertTrue((ROOT/"research/experiments.jsonl").exists())
  self.assertFalse((ROOT/"public/experiment-catalog.json").exists())

 def test_industry_page_is_dedicated_to_industry_and_reuses_daily_assets(self):
  text=(ROOT/"app/zh/watch/industry-radar/dashboard.tsx").read_text()
  for label in ('/industry-radar.json','useDailyData','待补数据的主题','相关候选','candidateDate===targetDate'):
   self.assertIn(label,text)
  for label in ('marketDecisionHero','/market-etf-watch.json','行业与大盘'):
   self.assertNotIn(label,text)

 def test_multifactor_keeps_only_the_current_decision_surface(self):
  self.assertFalse((ROOT/"app/zh/watch/resonance/macd/page.tsx").exists())
  text=(ROOT/"app/zh/watch/resonance/rare-opportunities/page.tsx").read_text()
  self.assertIn('<CandidateRanking/>',text)
  for retired in ('showLegacy','TimeframeProfilePanel','factorFamilyLegend','/opportunity-ledger.json','/unified-v2-rankings.json'):
   self.assertNotIn(retired,text)
  self.assertFalse((ROOT/"app/zh/watch/resonance/rare-opportunities/timeframe-profile.tsx").exists())
  self.assertTrue((ROOT/"public/opportunity-ledger.json").exists())
  self.assertTrue((ROOT/"research/experiments.jsonl").exists())

 def test_semiconductors_is_supported_and_ai_infrastructure_is_not_published(self):
  registry=json.loads((ROOT/"data/themes/theme-registry.json").read_text())
  themes={x["theme_id"]:x for x in registry["themes"]}
  self.assertEqual(themes["semiconductors"]["membership_source"]["provider"],"ishares")
  self.assertEqual(themes["semiconductors"]["membership_source"]["fund"],"SOXX")
  self.assertEqual(themes["ai-infrastructure"]["status"],"manual_curated_required")
  self.assertNotIn("membership_source",themes["ai-infrastructure"])
  # Live membership availability is a release warning, and the <5-member
  # Unavailable rule is gated by services.scanner.release_contract.

if __name__=="__main__":unittest.main()
