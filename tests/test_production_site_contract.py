import pathlib
import unittest

from services.scanner.discord_daily_digest import DEFAULT_SITE


ROOT=pathlib.Path(__file__).parents[1]
PRODUCTION="https://sage-vista-parallel.gizmo-allied-0s.workers.dev"

class ProductionSiteContractTests(unittest.TestCase):
 def test_cloudflare_worker_is_the_only_runtime_production(self):
  workflow=(ROOT/".github/workflows/daily-eod.yml").read_text()
  self.assertIn(PRODUCTION,workflow)
  self.assertNotIn("chatgpt.site",workflow)
  self.assertNotIn("sage-vista-sites",workflow)
  self.assertNotIn("mode == 'notify'",workflow)
  self.assertEqual(DEFAULT_SITE,PRODUCTION)

 def test_sites_binding_is_retired(self):
  self.assertFalse((ROOT/".openai/hosting.json").exists())

if __name__=="__main__":unittest.main()
