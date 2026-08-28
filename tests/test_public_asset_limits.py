import pathlib
import unittest


class PublicAssetLimitTests(unittest.TestCase):
    def test_cloudflare_assets_stay_below_25_mib(self):
        oversized = [
            (path.name, path.stat().st_size)
            for path in pathlib.Path("public").iterdir()
            if path.is_file() and path.stat().st_size > 25 * 1024 * 1024
        ]
        self.assertEqual(oversized, [], f"Cloudflare cannot publish these assets: {oversized}")


if __name__ == "__main__":
    unittest.main()
