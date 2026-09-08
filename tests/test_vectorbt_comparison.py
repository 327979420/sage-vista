import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from research.backtest.vectorbt_comparison import INPUT, EXPECTED_INPUT_SHA256, frozen_input, check, save, cache_replay, vectorbt_orders
from services.scanner.support_risk import simulate_execution


class VectorbtComparisonTests(unittest.TestCase):
    def test_frozen_selection_matches_original_ledger_without_outcome_filter(self):
        data, fingerprint=frozen_input()
        self.assertEqual(fingerprint,EXPECTED_INPUT_SHA256)
        self.assertEqual(data['selection']['excluded_other_or_missing_policy']+data['selection']['eligible_policy_count'],data['selection']['total_events'])
        self.assertEqual(data['selection']['outside_fixed_limit']+20,data['selection']['eligible_policy_count'])
        self.assertFalse(data['selection']['filter_by_outcome'])
        self.assertTrue(all(e['baseline']['status']=='resolved' for e in data['events']))
        self.assertEqual(data['events'],sorted(data['events'],key=lambda e:(e['signal_date'],e['event_id'])))

    def test_changed_frozen_sample_fails_before_engine_import(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'input.json';data=json.loads(INPUT.read_bytes());data['events'].reverse();p.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'fingerprint'):frozen_input(p)

    def test_rounding_difference_is_preserved_at_source_precision(self):
        result=check('return',.00850696,.008506930462614233,8)
        self.assertEqual(result['status'],'difference');self.assertNotEqual(result['delta'],0)

    def test_cache_replay_uses_old_policy_and_does_not_mutate_raw(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            rows=[{'date':f'2026-01-0{i}','open':100.,'high':101. if i<4 else 111.,'low':99.,'close':100.,'adjusted_close':100.,'volume':10000} for i in range(1,5)]
            raw=json.dumps(rows);(root/'AAA.json').write_text(raw);(root/'SPY.json').write_text(raw)
            event={'symbol':'AAA','signal_date':'2026-01-01','entry_date':'2026-01-02','baseline':simulate_execution(100,{'level':100,'source':'fixed'},rows[1:])}
            result=cache_replay(event,root)
            self.assertEqual(result['status'],'match');self.assertFalse(result['historical_revision_proven'])
            self.assertEqual((root/'AAA.json').read_text(),raw)
            rows[1]['adjusted_close']=99.;(root/'AAA.json').write_text(json.dumps(rows))
            changed=cache_replay(event,root)
            self.assertEqual(changed['status'],'difference')
            self.assertNotEqual(changed['adjustment_fingerprint'],result['adjustment_fingerprint'])
            (root/'SPY.json').unlink()
            self.assertEqual(cache_replay(event,root)['status'],'unavailable')

    def test_engine_fill_changes_cannot_pass(self):
        event=frozen_input()[0]['events'][0]
        base=event['baseline'];entry=event['entry_price'];exit_price=base['exit_price']
        trade={'size':1.,'entry_idx':0,'exit_idx':1,'status':1,'entry_price':entry+1,'exit_price':exit_price,'return':base['return'],'pnl':exit_price-entry,'entry_fees':0.,'exit_fees':0.}
        rec=lambda x:SimpleNamespace(records=SimpleNamespace(to_dict=lambda mode:x))
        engine=SimpleNamespace(Portfolio=SimpleNamespace(from_orders=lambda *a,**kw:SimpleNamespace(trades=rec([trade]),orders=rec([{'side':0},{'side':1}]))))
        result=vectorbt_orders(event,engine,SimpleNamespace(Series=lambda x:x))
        self.assertEqual(result['status'],'difference')
        self.assertTrue(any(c['field']=='entry_price' and c['status']=='difference' for c in result['checks']))
        self.assertIsNone(result['actual_fees']);self.assertIsNone(result['actual_net_return'])

    def test_report_cannot_write_public_or_overwrite_previous_run(self):
        root=Path(__file__).resolve().parents[1]
        with self.assertRaisesRegex(ValueError,'public'):save({},root/'public/forbidden.json')
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'report.json';save({'a':1},p)
            with self.assertRaises(FileExistsError):save({'a':2},p)
