import json,pathlib,re,unittest

ROOT=pathlib.Path(__file__).parents[1]

class UiV2ContractTests(unittest.TestCase):
 def test_home_puts_market_risk_before_stock_research(self):
  text=(ROOT/"app/zh/watch/resonance/page.tsx").read_text()
  self.assertLess(text.index("overviewHero"),text.index("opportunityWorkspace"))
  for label in ("TODAY&apos;S DECISION","精选机会，不追高","现在能用什么","今日 V2 技术机会","WHY IT RANKS HERE"):
   self.assertIn(label,text)

 def test_research_separates_three_evidence_modes(self):
  text=(ROOT/"app/zh/watch/resonance/research/page.tsx").read_text()
  for label in ("历史回测","真实跟踪","实验档案","全部实验时间线","最早记录","开始","结束","现在怎么用","/signal-history.json"):
   self.assertIn(label,text)
  self.assertIn('cache:"no-store"',text)

 def test_industry_page_starts_with_market_decision_and_practical_groups(self):
  text=(ROOT/"app/zh/watch/industry-radar/page.tsx").read_text()
  for label in ("/market-etf-watch.json","今天怎么用","趋势主线","回调与修复","当前偏弱的行业背景","只调整观察优先级"):
   self.assertIn(label,text)
  self.assertLess(text.index("marketDecisionHero"),text.index("TODAY&apos;S INDUSTRY MAP"))

 def test_multifactor_absorbs_stock_research_and_timeframe_profile(self):
  self.assertFalse((ROOT/"app/zh/watch/resonance/macd/page.tsx").exists())
  text=(ROOT/"app/zh/watch/resonance/rare-opportunities/page.tsx").read_text()
  profile=(ROOT/"app/zh/watch/resonance/rare-opportunities/timeframe-profile.tsx").read_text()
  for label in ("WHY IT RANKS HERE","股票技术证据查询","RISK PLAN","TimeframeProfilePanel"):
   self.assertIn(label,text)
  for label in ("周线","月线","不是建议持仓天数","不改变当前 V2 排名"):
   self.assertIn(label,profile)

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
