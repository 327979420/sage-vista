import pathlib,re,unittest

ROOT=pathlib.Path(__file__).parents[1]

class ProductConsolidationTests(unittest.TestCase):
 def test_legacy_signal_board_is_removed(self):
  self.assertFalse((ROOT/"app/stock-board.tsx").exists())
  self.assertFalse((ROOT/"app/data.ts").exists())
  root=(ROOT/"app/page.tsx").read_text()
  self.assertNotIn("StockBoard",root);self.assertIn("./zh/watch/market/page",root)

 def test_navigation_has_the_four_current_products(self):
  nav=(ROOT/"app/zh/watch/resonance/tracker-ui.tsx").read_text()
  self.assertNotRegex(nav,re.compile(r"US Equity Signals|Signal Board|个股研究",re.I))
  for label in ("大盘","多因子机会","我最喜欢形态","行业"):self.assertIn(label,nav)
  self.assertNotIn("历史与实验",nav)
  self.assertFalse((ROOT/"app/zh/watch/resonance/macd/page.tsx").exists())
  self.assertNotIn("/zh/watch/resonance/macd",(ROOT/"app/layout.tsx").read_text())
  self.assertIn("/zh/watch/resonance/favorite-pattern",(ROOT/"app/layout.tsx").read_text())

 def test_fast_production_json_fetches_are_no_store(self):
  consumers={
   "cr056-ranking.json":"app/zh/watch/resonance/rare-opportunities/cr056-ranking.tsx",
   "daily-shape-picker.json":"app/zh/watch/resonance/favorite-pattern/page.tsx",
   "update-status.json":"app/zh/watch/resonance/tracker-ui.tsx",
  }
  for asset,path in consumers.items():
   text=(ROOT/path).read_text();match=re.search(rf'fetch\("/{re.escape(asset)}"[^)]*\)',text)
   self.assertIsNotNone(match,asset);self.assertIn('cache:"no-store"',match.group(0),asset)
  for page in ('market/dashboard.tsx','industry-radar/dashboard.tsx'):
   self.assertIn('useDailyData',(ROOT/'app/zh/watch'/page).read_text())
  daily=(ROOT/'app/zh/watch/market/daily-data.ts').read_text()
  self.assertIn("cache:'no-store'",daily)
  self.assertIn('Promise.allSettled',daily)
  self.assertNotIn("resonance-tracker.json",(ROOT/"app/zh/watch/resonance/tracker-ui.tsx").read_text())
  home=(ROOT/"app/zh/watch/market/dashboard.tsx").read_text()
  self.assertIn("/market-cockpit.json",home)
  self.assertIn("/market-internals.json",home)
  for retired in ('/unified-v2-latest.json','/signal-history-summary.json','/rare-opportunity-radar.json'):
   self.assertNotIn(retired,home)

 def test_experiment_payloads_are_git_only(self):
  self.assertFalse((ROOT/"public/experiment-catalog.json").exists())
  self.assertFalse((ROOT/"public/macd-factor-backtest.json").exists())
  self.assertFalse((ROOT/"public/factor-family-combination.json").exists())
  self.assertTrue((ROOT/"research/generated/experiment-catalog.json").exists())
  self.assertTrue((ROOT/"research/backtest/output/macd-factor-backtest.json").exists())
  self.assertIn('redirect("/")',(ROOT/"app/zh/watch/resonance/research/page.tsx").read_text())

 def test_market_module_is_separate_from_candidate_and_trading_inputs(self):
  from services.scanner import market_internals_daily
  import inspect
  text=inspect.getsource(market_internals_daily)
  for forbidden in ('cr056-ranking.json','account_runner','unified_v2_scan','daily_shape_picker','factor_scoring'):
   self.assertNotIn(forbidden,text)
  self.assertFalse((ROOT/"app/home-v3.css").exists())

if __name__=="__main__":unittest.main()
