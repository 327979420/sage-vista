import json,pathlib,re,unittest

ROOT=pathlib.Path(__file__).parents[1]

class UiV2ContractTests(unittest.TestCase):
 def test_home_puts_market_risk_before_stock_research(self):
  text=(ROOT/"app/zh/watch/resonance/page.tsx").read_text()
  self.assertLess(text.index("overviewHero"),text.index("opportunityWorkspace"))
  for label in ("TODAY&apos;S DECISION","精选机会，不追高","今日先看这些机会","WHY IT RANKS HERE","热点与研究"):
   self.assertIn(label,text)

 def test_research_separates_three_evidence_modes(self):
  text=(ROOT/"app/zh/watch/resonance/research/page.tsx").read_text()
  for label in ("Backtesting","Forward Testing","Experiments","/signal-history.json"):
   self.assertIn(label,text)
  self.assertIn('cache:"no-store"',text)

 def test_tracker_is_presentation_join_only(self):
  text=(ROOT/"app/zh/watch/resonance/macd/page.tsx").read_text()
  for label in ("OPPORTUNITY SCREENER","Technical Summary","Multi-Factor Evidence","Industry Context","Risks","Signal History"):
   self.assertIn(label,text)
  self.assertNotRegex(text,re.compile(r"ranking_score\s*=|macd_rank_score\s*="))

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
  self.assertGreaterEqual(semi["valid_member_count"],5)
  self.assertFalse(radar["future_data_used"])

if __name__=="__main__":unittest.main()
