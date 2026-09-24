import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services.contracts.market_data import canonical_fingerprint
from services.scanner.daily_shape_public import validate, publish
from services.scanner.verify_live_deployment import verify_picker_asset
from tests.public_fixture import changed, fixture, local_public

ROOT=Path(__file__).parents[1]

class PublicPickerTests(unittest.TestCase):
    def setUp(self):
        # Frozen real asset: tamper checks must not depend on today's rows.
        self.payload=fixture('daily-shape-picker.json')
        self.day=self.payload['as_of']

    def reseal(self,payload):
        payload['content_fingerprint']=canonical_fingerprint({k:v for k,v in payload.items() if k!='content_fingerprint'})
        return payload

    def test_reviewed_asset_reproduces_shared_daily_facts(self):
        validate(self.payload,self.day)
        self.assertTrue(self.payload['rows'])
        self.assertTrue(all('old' not in r for r in self.payload['rows']))
        self.assertTrue(all(r['bottom_confirmed'] for r in self.payload['rows']))

    def test_different_date_policy_and_source_fail(self):
        for key,value in [('as_of','2000-01-01'),('policy_fingerprint','other'),('price_version','other')]:
            bad=changed(self.payload,lambda p:p.update({key:value}))
            with self.subTest(key=key),self.assertRaises(ValueError):validate(self.reseal(bad),self.day)

    def test_modified_bottom_or_future_confirmation_fails_even_when_rehashed(self):
        def mutate(kind):
            def apply(p):
                row=p['rows'][0]
                if kind=='price':row['bottom']['zone_lower']+=1
                elif kind=='confirmation':row['bottom']['anchors'][0]['confirmed_at']='2099-12-31'
                else:row['bottom']['anchors']=[]
            return apply
        for kind in ('price','confirmation','missing_bottom'):
            bad=changed(self.payload,mutate(kind))
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'derived_fact'):
                validate(self.reseal(bad),self.day)

    def test_false_waiting_state_cannot_hide_post_breakout_trade(self):
        def hide(p):next(r for r in p['rows'] if r['state']!='waiting')['state']='waiting'
        with self.assertRaisesRegex(ValueError,'derived_fact'):validate(self.reseal(changed(self.payload,hide)),self.day)

    def test_duplicate_and_broken_content_hash_fail(self):
        bad=changed(self.payload,lambda p:p['rows'].append(copy.deepcopy(p['rows'][0])))
        with self.assertRaisesRegex(ValueError,'duplicate'):validate(self.reseal(bad),self.day)
        bad=changed(self.payload,lambda p:p.update(purpose_zh='changed'))
        with self.assertRaisesRegex(ValueError,'content_hash'):validate(bad,self.day)

    def test_live_verifier_compares_actual_reviewed_asset(self):
        with local_public({'daily-shape-picker.json':self.payload}):
            with patch('services.scanner.verify_live_deployment.fetch',return_value=self.payload):
                receipt=verify_picker_asset('https://example.test',self.day,'commit')
            self.assertEqual(receipt['content_fingerprint'],self.payload['content_fingerprint'])
            bad=self.reseal(changed(self.payload,lambda p:p.update(purpose_zh='different reviewed version')))
            with patch('services.scanner.verify_live_deployment.fetch',return_value=bad):
                with self.assertRaisesRegex(RuntimeError,'differs from reviewed'):
                    verify_picker_asset('https://example.test',self.day,'commit')
