import json,tempfile,unittest
from pathlib import Path
from services.scanner.cache_theme_etfs import funds

class ThemeEtfCacheTests(unittest.TestCase):
 def test_funds_are_unique_and_skip_manual_themes(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/"registry.json";path.write_text(json.dumps({"themes":[{"membership_source":{"fund":"SOXX"}},{"membership_source":{"fund":"SOXX"}},{"status":"manual"}]}))
   self.assertEqual(funds(path),["SOXX"])

if __name__=="__main__":unittest.main()
