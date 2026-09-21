import json,pathlib,re,unittest

ROOT=pathlib.Path(__file__).parents[1]

class UiV2ContractTests(unittest.TestCase):
 def test_market_page_keeps_risk_reason_and_trend_layers(self):
  text=(ROOT/"app/zh/watch/market/dashboard.tsx").read_text()
  self.assertLess(text.index('<section className="marketTemperature"'),text.index('<div className="marketSignalsHeading"'))
  self.assertLess(text.index('<div className="marketSignalsHeading"'),text.index('<section className="marketHistory"'))
  self.assertIn('不代表整个美股市场',text)
  self.assertIn('分数越高',text)
  self.assertNotIn('今日研究总览',(ROOT/"app/zh/watch/resonance/tracker-ui.tsx").read_text())

 def test_experiment_archive_is_git_only(self):
  text=(ROOT/"app/zh/watch/resonance/research/page.tsx").read_text()
  self.assertIn('redirect("/")',text)
  self.assertTrue((ROOT/"research/generated/experiment-catalog.json").exists())
  self.assertTrue((ROOT/"research/experiments.jsonl").exists())
  self.assertFalse((ROOT/"public/experiment-catalog.json").exists())

 def test_industry_page_starts_with_market_decision_and_practical_groups(self):
  text=(ROOT/"app/zh/watch/industry-radar/page.tsx").read_text()
  for label in ("/market-etf-watch.json","SPY","QQQ","IWM","RSP","SOXX","旧快照成员广度","独立背景，不改当前排名"):
   self.assertIn(label,text)
  self.assertLess(text.index("marketDecisionHero"),text.index("<IndustryContext/>"))
  self.assertLess(text.index("<IndustryContext/>"),text.index("旧成员广度证据"))

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
  radar=json.loads((ROOT/"public/industry-radar.json").read_text())
  semi=next(x for x in radar["themes"] if x["theme_id"]=="semiconductors")
  self.assertEqual(semi["source_status"],"available")
  self.assertGreaterEqual(semi["member_count"],5)
  if semi["valid_member_count"]<5:self.assertEqual(semi["state"],"Unavailable")
  self.assertFalse(radar["future_data_used"])

if __name__=="__main__":unittest.main()
