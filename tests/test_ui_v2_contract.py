import json,pathlib,re,unittest

ROOT=pathlib.Path(__file__).parents[1]

class UiV2ContractTests(unittest.TestCase):
 def test_home_puts_market_risk_before_stock_research(self):
  text=(ROOT/"app/zh/watch/resonance/page.tsx").read_text()
  self.assertLess(text.index("overviewHero"),text.index("opportunityWorkspace"))
  for label in ("TODAY&apos;S DECISION","精选机会，不追高","现在能用什么","今日 V2 技术机会","WHY IT RANKS HERE"):
   self.assertIn(label,text)

 def test_experiment_archive_is_git_only(self):
  text=(ROOT/"app/zh/watch/resonance/research/page.tsx").read_text()
  self.assertIn('redirect("/")',text)
  self.assertTrue((ROOT/"research/generated/experiment-catalog.json").exists())
  self.assertTrue((ROOT/"research/experiments.jsonl").exists())
  self.assertFalse((ROOT/"public/experiment-catalog.json").exists())

 def test_industry_page_starts_with_market_decision_and_practical_groups(self):
  text=(ROOT/"app/zh/watch/industry-radar/page.tsx").read_text()
  for label in ("/market-etf-watch.json","SPY","QQQ","IWM","RSP","SOXX","常用行业，一张表读完","只影响优先级，不改技术分"):
   self.assertIn(label,text)
  self.assertLess(text.index("marketDecisionHero"),text.index("EVERYDAY SECTOR ETFS"))

 def test_multifactor_keeps_only_the_current_decision_surface(self):
  self.assertFalse((ROOT/"app/zh/watch/resonance/macd/page.tsx").exists())
  text=(ROOT/"app/zh/watch/resonance/rare-opportunities/page.tsx").read_text()
  profile=(ROOT/"app/zh/watch/resonance/rare-opportunities/timeframe-profile.tsx").read_text()
  for label in ("WHY IT RANKS HERE","RISK PLAN","TimeframeProfilePanel","37个因子，现在分别怎么处理","factorFamilyLegend","统一机会账本"):
   self.assertIn(label,text)
  for retired in ("旧系统历史机会参考","统一因子库","股票技术证据查询","旧评分兼容观察","查看当前动态观察评分规则","/research-opportunity-pool.json","/rare-opportunity-radar.json","/signal-history.json","/factor-registry.json"):
   self.assertNotIn(retired,text)
  styles=(ROOT/"app/globals.css").read_text()+(ROOT/"app/product-v2.css").read_text()
  for retired_selector in ("rareFactorLibrary","rareCurrent","rareLegacy","rareExamples","rareScoreDial"):
   self.assertNotIn(retired_selector,styles)
  factor_view=json.loads((ROOT/"public/factor-effectiveness.json").read_text())
  self.assertEqual([factor_view["quadrants"][key]["label_zh"] for key in factor_view["quadrant_order"]],["正在使用","候选观察","暂停加权","准备弃用"])
  self.assertNotIn("factor-family-combination.json",text)
  self.assertFalse((ROOT/"public/factor-family-combination.json").exists())
  family_combo=json.loads((ROOT/"research/backtest/output/factor-family-return-combination-v1.json").read_text())
  self.assertFalse(family_combo["production_scoring_changed"])
  self.assertNotIn("旧系统因子实验",text)
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
