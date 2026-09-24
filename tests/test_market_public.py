import unittest
from unittest.mock import patch
from services.scanner.market_internals_daily import validate_public
from services.scanner.verify_live_deployment import verify_market_asset
from tests.public_fixture import changed, fixture, local_public, reseal

# Live-data checks (current logic fingerprint, immutable snapshot equality)
# run on the generated asset in services.scanner.release_contract.

class MarketPublicTests(unittest.TestCase):
    def setUp(self):
        self.payload=fixture('market-internals.json')
    def test_frozen_published_history_validates(self):
        p=validate_public(self.payload,self.payload['as_of'])
        self.assertTrue(all(s['date']<=p['as_of'] for s in p['history']))
    def test_tampered_or_resealed_history_fails(self):
        with self.assertRaisesRegex(ValueError,'market_public_hash_mismatch'):
            validate_public(changed(self.payload,lambda p:p.update(generated_at='2026-09-23T00:00:00Z')))
        bad=changed(self.payload,lambda p:p['history'][-1]['temperature'].update(score=99))
        with self.assertRaisesRegex(ValueError,'market_snapshot_hash_mismatch'):validate_public(reseal(bad))
        future=changed(self.payload,lambda p:p['history'].append(dict(p['history'][-1],date='2099-01-01')))
        with self.assertRaisesRegex(ValueError,'market_latest_missing'):validate_public(reseal(future))
    def test_live_verification_requires_identical_version_and_same_day(self):
        p=self.payload
        with local_public({'market-internals.json':p}):
            with patch('services.scanner.verify_live_deployment.fetch',return_value=p):
                result=verify_market_asset('https://example.test',p['as_of'],'a'*40)
                self.assertEqual(result['content_fingerprint'],p['content_fingerprint'])
            bad=changed(p,lambda x:x['history'][-1]['temperature'].update(score=99))
            with patch('services.scanner.verify_live_deployment.fetch',return_value=bad):
                with self.assertRaises(ValueError):verify_market_asset('https://example.test',p['as_of'],'a'*40)
        with self.assertRaisesRegex(ValueError,'date_mismatch'):validate_public(p,'2099-01-01')

if __name__=='__main__':unittest.main()
