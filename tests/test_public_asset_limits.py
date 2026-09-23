import pathlib
import unittest
import json
import tempfile
from services.scanner.daily_tracker_update import write_history_asset


class PublicAssetLimitTests(unittest.TestCase):
    def test_history_packaging_preserves_all_evidence_and_rejects_oversize_before_write(self):
        payload=json.loads(pathlib.Path("public/signal-history.json").read_bytes())
        with tempfile.TemporaryDirectory() as folder:
            out=pathlib.Path(folder)/"history.json"
            write_history_asset(out,payload)
            self.assertEqual(json.loads(out.read_bytes()),payload)
            self.assertLess(out.stat().st_size,25*1024*1024)
            original=out.read_bytes()
            with self.assertRaisesRegex(ValueError,"hosting limit"):
                write_history_asset(out,{"evidence":"x"*(25*1024*1024)})
            self.assertEqual(out.read_bytes(),original)

    def test_cloudflare_assets_stay_below_25_mib(self):
        oversized = [
            (path.name, path.stat().st_size)
            for path in pathlib.Path("public").iterdir()
            if path.is_file() and path.stat().st_size > 25 * 1024 * 1024
        ]
        self.assertEqual(oversized, [], f"Cloudflare cannot publish these assets: {oversized}")


if __name__ == "__main__":
    unittest.main()
