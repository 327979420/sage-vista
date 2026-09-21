import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services.contracts.market_data import canonical_fingerprint
from services.scanner.daily_shape_public import validate, publish
from services.scanner.verify_live_deployment import verify_picker_asset

ROOT=Path(__file__).parents[1]

class PublicPickerTests(unittest.TestCase):
    def setUp(self):
        self.payload=json.loads((ROOT/'public/daily-shape-picker.json').read_bytes())
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
            changed=copy.deepcopy(self.payload);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate(self.reseal(changed),self.day)

    def test_modified_bottom_or_future_confirmation_fails_even_when_rehashed(self):
        for kind in ('price','confirmation','missing_bottom'):
            changed=copy.deepcopy(self.payload);row=changed['rows'][0]
            if kind=='price':row['bottom']['zone_lower']+=1
            elif kind=='confirmation':row['bottom']['anchors'][0]['confirmed_at']='2099-12-31'
            else:row['bottom']['anchors']=[]
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'derived_fact'):
                validate(self.reseal(changed),self.day)

    def test_false_waiting_state_cannot_hide_post_breakout_trade(self):
        changed=copy.deepcopy(self.payload)
        row=next(r for r in changed['rows'] if r['state']!='waiting')
        row['state']='waiting'
        with self.assertRaisesRegex(ValueError,'derived_fact'):validate(self.reseal(changed),self.day)

    def test_duplicate_and_broken_content_hash_fail(self):
        changed=copy.deepcopy(self.payload);changed['rows'].append(changed['rows'][0])
        with self.assertRaisesRegex(ValueError,'duplicate'):validate(self.reseal(changed),self.day)
        changed=copy.deepcopy(self.payload);changed['purpose_zh']='changed'
        with self.assertRaisesRegex(ValueError,'content_hash'):validate(changed,self.day)

    def test_live_verifier_compares_actual_reviewed_asset(self):
        with patch('services.scanner.verify_live_deployment.fetch',return_value=self.payload):
            receipt=verify_picker_asset('https://example.test',self.day,'commit')
        self.assertEqual(receipt['content_fingerprint'],self.payload['content_fingerprint'])
        changed=copy.deepcopy(self.payload);changed['purpose_zh']='different reviewed version'
        with patch('services.scanner.verify_live_deployment.fetch',return_value=self.reseal(changed)):
            with self.assertRaisesRegex(RuntimeError,'differs from reviewed'):
                verify_picker_asset('https://example.test',self.day,'commit')
