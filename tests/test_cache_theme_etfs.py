import json,tempfile,unittest
from pathlib import Path
from services.scanner.cache_theme_etfs import funds

class ThemeEtfCacheTests(unittest.TestCase):
 def test_funds_are_unique_and_skip_manual_themes(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/"registry.json";path.write_text(json.dumps({"themes":[{"membership_source":{"fund":"SOXX"}},{"membership_source":{"fund":"SOXX"}},{"status":"manual"}]}))
   self.assertEqual(funds(path),["SOXX"])

 def test_registry_preserves_software_memory_and_ai_chain(self):
  root=Path(__file__).parents[1];registry=json.loads((root/"data/themes/theme-registry.json").read_text())
  themes={row["theme_id"]:row for row in registry["themes"]}
  self.assertEqual(registry["version"],3)
  self.assertEqual(themes["software-applications"]["membership_source"]["fund"],"IGV")
  self.assertEqual(themes["memory-storage"]["status"],"manual_curated_required")
  self.assertEqual(themes["ai-software-applications"]["status"],"manual_curated_required")
  self.assertTrue({"semiconductors","robotics-automation","ai-infrastructure","semiconductor-equipment","data-center-power"}.issubset(themes))

if __name__=="__main__":unittest.main()
