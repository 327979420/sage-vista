"""Synthetic whole-member qualifications and exact original M03 equivalence."""
import ast
from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta
import subprocess
import unittest
from unittest.mock import patch

from services.contracts.configuration import DEFINITION_COMMIT
from services.contracts.validation import ContractError
from services.gates import baseline
from services.market_data.normalization import bars_fingerprint
from services.market_data.qualification import build_same_day_qualifications
from services.market_data.repository import RepositoryRead
from tests.test_market_data_consumers import DAY, ROOT, forward_member, forward_snapshot


def history(count=420, *, close=5.0, volume=2_000_000):
    # Synthetic ordered dates, not evidence of the real exchange calendar.
    return tuple({'date': (date.fromisoformat(DAY) - timedelta(days=count-i-1)).isoformat(),
                  'open': close, 'high': close, 'low': close, 'close': close, 'volume': volume}
                 for i in range(count))


def reading(member, rows):
    return RepositoryRead(member['instrument_id'], DAY, rows, bars_fingerprint(rows))


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.members = [forward_member('SYNTHA'), forward_member('SYNTHB')]
        self.reads = {m['instrument_id']: reading(m, history()) for m in self.members}
        self.complete = set(self.reads)

    def build(self, **changes):
        return build_same_day_qualifications(**{'as_of': DAY, 'members': self.members,
            'reads': self.reads, 'complete_history_instruments': self.complete, **changes})

    def test_exact_thresholds_qualify_without_macd_and_feed_original_universe(self):
        with patch.object(baseline, 'exact_daily_macd_bull_cross', side_effect=AssertionError('not M02')):
            facts = self.build()
        self.assertTrue(all(item['eligible'] for item in facts))
        self.assertEqual(len(facts), 2)
        snapshot = forward_snapshot(members=self.members, qualifications=facts)
        self.assertEqual(snapshot['qualifications'], facts)
        self.assertEqual(self.build(members=list(reversed(self.members))), facts)
        self.assertEqual(baseline.creation_boundary_reason(history(), as_of=DAY), 'no_exact_daily_macd_cross')

    def test_complete_short_history_is_excluded_unknown_history_fails_entire_batch(self):
        member = self.members[0]; key = member['instrument_id']
        self.reads[key] = reading(member, history(419))
        fact = next(item for item in self.build() if item['instrument_id'] == key)
        self.assertEqual(fact['exclusion_reasons'], ['insufficient_history'])
        self.assertFalse(fact['eligible']); self.assertTrue(fact['price_complete'])
        with self.assertRaisesRegex(ContractError, 'complete history'): self.build(complete_history_instruments=self.complete - {key})
        for value in (True, list(self.complete), self.complete | {'unknown'}):
            with self.assertRaises(ContractError): self.build(complete_history_instruments=value)

    def test_price_liquidity_and_all_independent_reasons_are_saved(self):
        member = self.members[0]; key = member['instrument_id']
        for rows, expected in [(history(close=4.99, volume=3_000_000), ['below_price_floor']),
                (history(volume=1_999_999), ['below_liquidity_floor']),
                (history(2, close=1.0, volume=0), ['below_liquidity_floor', 'below_price_floor', 'insufficient_history'])]:
            self.reads[key] = reading(member, rows)
            fact = next(item for item in self.build() if item['instrument_id'] == key)
            self.assertEqual(sorted(fact['exclusion_reasons']), expected)
            self.assertFalse(fact['eligible']); self.assertEqual(fact['inclusion_reasons'], [])

    def test_missing_or_extra_read_and_identity_or_asof_mismatch_fail(self):
        key = self.members[0]['instrument_id']
        for reads in ({k:v for k,v in self.reads.items() if k != key}, {**self.reads, 'other': self.reads[key]},
                {**self.reads, key: replace(self.reads[key], instrument_id=self.members[1]['instrument_id'])},
                {**self.reads, key: replace(self.reads[key], as_of='2026-09-02')}, {**self.reads, key: None}):
            with self.assertRaises(ContractError): self.build(reads=reads)
        for members in ([], self.members + [self.members[0]]):
            with self.assertRaises(ContractError): self.build(members=members)

    def test_actual_rows_missing_day_future_corrupt_or_false_digest_fail(self):
        member = self.members[0]; key = member['instrument_id']
        bad = list(history()); bad[-1]['volume'] = True
        future = list(history()); future[-1]['date'] = '2026-09-02'
        for rows in ((), history()[:-1], tuple(bad), tuple(future), (*history(), history()[-1])):
            with self.subTest(rows=len(rows)), self.assertRaises(ContractError):
                self.build(reads={**self.reads, key: reading(member, rows)})
        with self.assertRaisesRegex(ContractError, 'fingerprint'):
            self.build(reads={**self.reads, key: replace(self.reads[key], point_in_time_fingerprint='sha256:' + '0'*64)})

    def test_member_inactive_or_not_yet_effective_fails_and_inputs_are_detached(self):
        for field, value in [('listing_status', 'delisted'), ('membership_effective_from', '2026-09-02')]:
            members = deepcopy(self.members); members[0][field] = value
            with self.assertRaises(ContractError): self.build(members=members)
        facts = self.build(); original = deepcopy(facts)
        self.reads[self.members[0]['instrument_id']].rows[-1]['close'] = 1
        self.members[0]['symbol'] = 'OTHER'
        self.assertEqual(facts, original)

    def test_original_gate_short_circuit_and_boundary_behavior_is_identical(self):
        raw = subprocess.check_output(['git', '--no-replace-objects', 'show',
            DEFINITION_COMMIT + ':services/gates/baseline.py'], cwd=ROOT, text=True)
        node = next(n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == 'creation_boundary_reason')
        namespace = dict(vars(baseline))
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<fixed-original-M03>', 'exec'), namespace)
        original = namespace['creation_boundary_reason']
        cases = [(), ({'date': DAY},), history(419), history(), history(close=4.99), history(volume=1_999_999),
                 history(close=6, volume=3_000_000), history()[:-1]]
        for cross in (False, True):
            namespace['exact_daily_macd_bull_cross'] = lambda _: cross
            with patch.object(baseline, 'exact_daily_macd_bull_cross', return_value=cross):
                for rows in cases:
                    with self.subTest(count=len(rows), cross=cross):
                        self.assertEqual(baseline.creation_boundary_reason(rows, as_of=DAY), original(rows, as_of=DAY))


if __name__ == '__main__': unittest.main()
