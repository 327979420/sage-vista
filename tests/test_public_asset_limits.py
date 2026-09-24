import pathlib
import unittest
import json
import tempfile
from unittest.mock import patch
from services.scanner.daily_tracker_update import write_history_asset
from services.scanner.public_asset_limits import POLICY, validate_asset

FIXTURE=pathlib.Path(__file__).resolve().parent/"fixtures/public-2026-09-23"


class PublicAssetLimitTests(unittest.TestCase):
    def test_history_packaging_preserves_all_evidence_and_rejects_oversize_before_write(self):
        payload=json.loads((FIXTURE/"signal-history.json").read_bytes())
        with tempfile.TemporaryDirectory() as folder:
            out=pathlib.Path(folder)/"history.json"
            write_history_asset(out,payload)
            self.assertEqual(json.loads(out.read_bytes()),payload)
            self.assertLessEqual(validate_asset("signal-history.json",out.read_bytes()),POLICY["maxAssetBytes"])
            original=out.read_bytes()
            with patch.dict(POLICY,maxAssetBytes=20):
                with self.assertRaisesRegex(ValueError,"hosting limit"):
                    write_history_asset(out,payload)
            self.assertEqual(out.read_bytes(),original)

    def test_compressible_history_can_grow_beyond_raw_hosting_limit(self):
        content=b'x'*(25*1024*1024+1)
        self.assertLess(validate_asset("signal-history.json",content),POLICY["maxAssetBytes"])
        with self.assertRaisesRegex(ValueError,"hosting limit"):
            validate_asset("unpackaged.json",content)


if __name__ == "__main__":
    unittest.main()
