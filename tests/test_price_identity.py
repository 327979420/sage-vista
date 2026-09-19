import unittest
from research.backtest.price_identity import freeze_manifest, bind, require_consistent_baseline


class PriceIdentityTests(unittest.TestCase):
    def contract(self):
        manifest=freeze_manifest({'ELV':{'raw_sha256':'a','normalized_sha256':'b'},'SPY':{'raw_sha256':'c'}},source={'run':'frozen'})
        return {'manifest':manifest,**{role:bind({'value':123},manifest,symbols=['ELV'],verified=True) for role in ('signal','support','account')}}
    def test_same_verified_world_passes(self):
        c=self.contract();self.assertEqual(require_consistent_baseline(c),c['manifest']['price_version'])
    def test_mixed_or_missing_versions_fail(self):
        for role in ('signal','support','account'):
            for version in ('other',None):
                c=self.contract();c[role]['price_version']=version
                with self.assertRaisesRegex(ValueError,'price_version_mismatch'):require_consistent_baseline(c)
    def test_relabelled_unverified_signals_fail(self):
        c=self.contract();c['signal']['verified']=False
        with self.assertRaisesRegex(ValueError,'unverified'):require_consistent_baseline(c)
    def test_modified_price_or_dependency_fails(self):
        c=self.contract();c['manifest']['files']['ELV']['raw_sha256']='changed'
        with self.assertRaisesRegex(ValueError,'manifest'):require_consistent_baseline(c)
        c=self.contract();c['support']['payload']['value']=120
        with self.assertRaisesRegex(ValueError,'tampered'):require_consistent_baseline(c)
    def test_incomplete_symbols_fail(self):
        c=self.contract();c['account']['symbols']=[]
        with self.assertRaisesRegex(ValueError,'unverified'):require_consistent_baseline(c)
    def test_contract_cannot_be_attached_to_an_unrelated_account(self):
        from research.backtest.price_identity import validate_baseline_receipt
        c=self.contract()
        with self.assertRaisesRegex(ValueError,'wrong_account'):
            validate_baseline_receipt({'price_consistency':c,'portfolio_ledger':{'other':456}})
    def test_actual_trade_bindings_are_required(self):
        from research.backtest.price_identity import validate_baseline_receipt
        c=self.contract();m=c['manifest']
        event={'event_id':'e','symbol':'ELV','signal_date':'2026-02-18','selection':{'support_plan':{'level':341}}}
        c['signal']=bind([event],m,symbols=['ELV'],verified=True)
        c['support']=bind({'ELV':event['selection']['support_plan']},m,symbols=['ELV'],verified=True)
        r={'price_consistency':c,'portfolio_ledger':c['account']['payload'],'trades':[
            {'event_id':'e','symbol':'ELV','signal_date':'2026-02-18','signal_snapshot':{'selection':event['selection']}}]}
        self.assertEqual(validate_baseline_receipt(r),m['price_version'])
        r['trades'][0]['signal_date']='2026-02-19'
        with self.assertRaisesRegex(ValueError,'wrong_signal'):validate_baseline_receipt(r)
    def test_formal_receipt_without_price_contract_is_rejected(self):
        import json
        from pathlib import Path
        from research.backtest.run_store import validate_receipt,seal
        p=Path('research/backtest/output/reusable-runs/34240123213-1/receipt.json')
        r=json.loads(p.read_bytes());r['baseline_eligible']=True
        with self.assertRaisesRegex(ValueError,'price_contract_required'):seal(r)

if __name__=='__main__':unittest.main()
