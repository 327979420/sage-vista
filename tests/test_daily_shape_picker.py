import copy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from services.scanner.daily_shape_picker import evaluate_shape, liquidity, build_preview
from services.factors.cr056 import collect_entry_facts
from services.scanner.detectors import multi_bottom_structure
from services.contracts.cr056_policy import ENTRY_SETTINGS


def bars():
    rows = [dict(date=(date(2025,1,1)+timedelta(days=i)).isoformat(),open=104,high=105,low=103,close=104,volume=1000000) for i in range(180)]
    # Independent confirmed tests with intervening rebounds.
    for i in (130,145,160): rows[i].update(open=101,high=103,low=100,close=102)
    return rows


def raw_rows(rows):
    return [{**r, 'adjusted_close':r['close']} for r in rows]


class PickerTests(unittest.TestCase):
    def test_unbroken_bottom_can_be_selected_without_breakout(self):
        rows=bars(); result=evaluate_shape(rows,as_of=rows[-1]['date'])
        self.assertTrue(result['bottom_confirmed'])
        self.assertEqual(result['state'],'waiting')
        self.assertIsNone(result['three_push'])
        self.assertEqual(result['shape_zh'],'多底支撑')
        self.assertEqual(result['bottom'],collect_entry_facts(rows,as_of=rows[-1]['date'])['frames']['daily']['support_zone'])

    def test_bottom_confirmation_waits_for_two_completed_right_bars(self):
        rows=bars()[:148]
        for i in (145,146,147): rows[i].update(open=104,high=105,low=103,close=104)
        rows[145].update(open=101,high=103,low=100,close=102)
        before=evaluate_shape(rows[:147],as_of=rows[146]['date'])
        after=evaluate_shape(rows,as_of=rows[-1]['date'])
        self.assertFalse(before['selected'])
        self.assertTrue(after['selected'])
        self.assertEqual(after['bottom']['anchors'][-1]['confirmed_at'],rows[147]['date'])

    def test_invalidated_zone_and_sweep_cannot_be_selected(self):
        rows=bars(); rows[-1].update(open=100,high=101,low=90,close=91)
        self.assertFalse(evaluate_shape(rows,as_of=rows[-1]['date'])['selected'])
        rows[-1].update(close=100)
        self.assertFalse(evaluate_shape(rows,as_of=rows[-1]['date'])['selected'])

    def test_future_data_cannot_enter_current_evaluation(self):
        rows=bars(); cutoff=rows[-2]['date']
        before=evaluate_shape(rows[:-1],as_of=cutoff)
        rows[-1].update(high=9999,close=9999)
        self.assertEqual(before,evaluate_shape(rows[:-1],as_of=cutoff))
        with self.assertRaises(ValueError): evaluate_shape(rows,as_of=cutoff)

    def test_no_future_confirmation_in_all_prefixes(self):
        rows=bars()
        for end in range(125,len(rows),3):
            result=evaluate_shape(rows[:end+1],as_of=rows[end]['date'])
            for a in result['bottom']['anchors']:
                self.assertLessEqual(a['confirmed_at'],rows[end]['date'])
                self.assertGreater(a['confirmed_at'],a['date'])
            self.assertEqual(result['bottom'],multi_bottom_structure(rows[:end+1][-121:],cfg=ENTRY_SETTINGS))

    def test_three_push_uses_confirmed_shared_anchors(self):
        rows=bars()
        for i,p in ((125,115),(140,111),(155,107)):
            rows[i].update(high=p,close=p-2,open=p-3,low=p-4)
        result=evaluate_shape(rows[:160],as_of=rows[159]['date'])
        self.assertIsNotNone(result['three_push'])
        self.assertNotIn('breakout_index',result['three_push'])
        for a in result['three_push']['anchors']:
            self.assertLessEqual(a['confirmed_at'],rows[159]['date'])

    def test_turnover_uses_unadjusted_price_and_prior_volume(self):
        rows=raw_rows(bars()); rows[-1].update(close=100,adjusted_close=50,volume=2000000)
        self.assertEqual(liquidity(rows,as_of=rows[-1]['date'])['dollar_volume'],200000000)
        self.assertEqual(liquidity(rows,as_of=rows[-1]['date'])['relative_volume'],2)

    def test_membership_stale_data_and_hash_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); cache=root/'cache'; cache.mkdir()
            rows=raw_rows(bars()); as_of=rows[-1]['date']
            common=root/'common.json'; common.write_text(json.dumps([{'Code':'AAA'},{'Code':'OLD'}]))
            (cache/'AAA.json').write_text(json.dumps(rows))
            (cache/'OLD.json').write_text(json.dumps(rows[:-1]))
            (cache/'ETF.json').write_text(json.dumps(rows))
            report=build_preview(cache,common,as_of=as_of)
            self.assertEqual([r['symbol'] for r in report['rows']],['AAA'])
            self.assertIn('OLD',report['excluded'])
            index=root/'index.json'; index.write_text(json.dumps({'as_of':as_of,'repaired':[{'symbol':s,'repaired_sha256':hashlib.sha256((cache/(s+'.json')).read_bytes()).hexdigest()} for s in ('AAA','OLD')]}))
            (cache/'AAA.json').write_text(json.dumps(rows)+' ')
            with self.assertRaisesRegex(ValueError,'hash_mismatch'):
                build_preview(cache,common,as_of=as_of,index_path=index)
            with self.assertRaises(FileNotFoundError): build_preview(cache,root/'missing.json',as_of=as_of)

    def test_real_detector_breakout_not_faked_by_unconfirmed_setup_field(self):
        rows=bars()
        with patch('services.scanner.daily_shape_picker.three_push_breakout_setup',return_value=None):
            result=evaluate_shape(rows,as_of=rows[-1]['date'])
        self.assertEqual(result['state'],'waiting')


if __name__=='__main__': unittest.main()
