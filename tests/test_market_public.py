import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from services.scanner.market_internals_daily import validate_public, logic_fingerprint
from services.scanner.verify_live_deployment import verify_market_asset

ROOT=Path(__file__).resolve().parents[1]

class MarketPublicTests(unittest.TestCase):
    def setUp(self):
        self.payload=json.loads((ROOT/'public/market-internals.json').read_bytes())
    def test_published_history_matches_immutable_snapshots_and_current_logic(self):
        p=validate_public(self.payload)
        self.assertEqual(p['logic_fingerprint'],logic_fingerprint())
        state=ROOT/'data/market'/p['config']['series_id']
        for snapshot in p['history']:
            self.assertEqual(snapshot,json.loads((state/'snapshots'/f"{snapshot['date']}.json").read_bytes()))
        self.assertEqual(p['config'],json.loads((ROOT/'data/market/config-v1.json').read_bytes()))
        self.assertTrue(all(s['date']<=p['as_of'] for s in p['history']))
    def test_live_verification_requires_identical_version_and_same_day(self):
        p=self.payload
        with patch('services.scanner.verify_live_deployment.fetch',return_value=p):
            result=verify_market_asset('https://example.test',p['as_of'],'a'*40)
            self.assertEqual(result['content_fingerprint'],p['content_fingerprint'])
        bad=copy.deepcopy(p);bad['history'][-1]['temperature']['score']=99
        with patch('services.scanner.verify_live_deployment.fetch',return_value=bad):
            with self.assertRaises(ValueError):verify_market_asset('https://example.test',p['as_of'],'a'*40)
        with self.assertRaisesRegex(ValueError,'date_mismatch'):validate_public(p,'2099-01-01')

if __name__=='__main__':unittest.main()
