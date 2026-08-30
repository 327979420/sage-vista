import hashlib,pathlib,re,unittest

ROOT=pathlib.Path(__file__).parents[1]

class ProductConsolidationTests(unittest.TestCase):
 def test_legacy_signal_board_is_removed(self):
  self.assertFalse((ROOT/"app/stock-board.tsx").exists())
  self.assertFalse((ROOT/"app/data.ts").exists())
  root=(ROOT/"app/page.tsx").read_text()
  self.assertNotIn("StockBoard",root);self.assertIn("Overview",root)

 def test_navigation_has_the_four_current_products(self):
  nav=(ROOT/"app/zh/watch/resonance/tracker-ui.tsx").read_text()
  self.assertNotRegex(nav,re.compile(r"US Equity Signals|Signal Board|个股研究",re.I))
  for label in ("今日研究总览","多因子机会","我最喜欢形态","行业与大盘"):self.assertIn(label,nav)
  self.assertNotIn("历史与实验",nav)
  self.assertFalse((ROOT/"app/zh/watch/resonance/macd/page.tsx").exists())
  self.assertNotIn("/zh/watch/resonance/macd",(ROOT/"app/layout.tsx").read_text())
  self.assertIn("/zh/watch/resonance/favorite-pattern",(ROOT/"app/layout.tsx").read_text())

 def test_fast_production_json_fetches_are_no_store(self):
  consumers={
   "daily-factor-snapshot.json":"app/zh/watch/resonance/rare-opportunities/page.tsx",
   "factor-effectiveness.json":"app/zh/watch/resonance/rare-opportunities/page.tsx",
   "unified-v2-latest.json":"app/zh/watch/resonance/rare-opportunities/page.tsx",
   "opportunity-ledger-latest.json":"app/zh/watch/resonance/rare-opportunities/page.tsx",
   "unified-v2-rankings.json":"app/zh/watch/resonance/rare-opportunities/page.tsx",
   "opportunity-ledger.json":"app/zh/watch/resonance/rare-opportunities/page.tsx",
   "favorite-pattern.json":"app/zh/watch/resonance/favorite-pattern/page.tsx",
   "industry-radar.json":"app/zh/watch/industry-radar/page.tsx",
   "market-etf-watch.json":"app/zh/watch/industry-radar/page.tsx",
   "update-status.json":"app/zh/watch/resonance/tracker-ui.tsx",
  }
  for asset,path in consumers.items():
   text=(ROOT/path).read_text();match=re.search(rf'fetch\("/{re.escape(asset)}"[^)]*\)',text)
   self.assertIsNotNone(match,asset);self.assertIn('cache:"no-store"',match.group(0),asset)
  self.assertNotIn("resonance-tracker.json",(ROOT/"app/zh/watch/resonance/tracker-ui.tsx").read_text())
  home=(ROOT/"app/zh/watch/resonance/page.tsx").read_text()
  self.assertIn("/unified-v2-latest.json",home);self.assertIn("/signal-history-summary.json",home)
  self.assertNotIn('json("/unified-v2-rankings.json")',home);self.assertNotIn('json("/signal-history.json")',home)

 def test_experiment_payloads_are_git_only(self):
  self.assertFalse((ROOT/"public/experiment-catalog.json").exists())
  self.assertFalse((ROOT/"public/macd-factor-backtest.json").exists())
  self.assertFalse((ROOT/"public/factor-family-combination.json").exists())
  self.assertTrue((ROOT/"research/generated/experiment-catalog.json").exists())
  self.assertTrue((ROOT/"research/backtest/output/macd-factor-backtest.json").exists())
  self.assertIn('redirect("/")',(ROOT/"app/zh/watch/resonance/research/page.tsx").read_text())

 def test_home_context_does_not_modify_tracker_ranking(self):
  tracker=ROOT/"services/scanner/resonance_tracker.py"
  before=hashlib.sha256(tracker.read_bytes()).hexdigest()
  home=(ROOT/"app/zh/watch/resonance/page.tsx").read_text()
  self.assertIn("ticker_context",home);self.assertNotIn("ranking_score=",home)
  self.assertEqual(hashlib.sha256(tracker.read_bytes()).hexdigest(),before)

if __name__=="__main__":unittest.main()
