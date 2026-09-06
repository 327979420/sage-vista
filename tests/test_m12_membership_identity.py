"""Synthetic original acquisition bytes; no real supplier or persisted root."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone, date, timedelta
import hashlib
import json
import unittest
from unittest.mock import patch

from services.contracts.validation import ContractError, membership_observation_history
from services.market_data.membership_collection import collect_membership
from services.market_data.membership_identity import build_observed_membership
from services.market_data.qualification import build_same_day_qualifications
from services.market_data.normalization import bars_fingerprint
from services.market_data.repository import RepositoryRead
from services.market_data.universe import build_forward_universe_snapshot
from services.scanner.eodhd import MembershipHttpObservation
from tests.test_m12_membership_collection import MemoryArchive, EVIDENCE

D1, D2, D3 = '2026-09-08', '2026-09-09', '2026-09-10'


def symbol(code='SYNTHA', *, exchange='NYSE', isin=None, kind='Common Stock', name='Synthetic'):
    return {'Code': code, 'Exchange': exchange, 'Type': kind, 'Name': name,
            'Country': 'USA', 'Currency': 'USD', **({'Isin': isin} if isin else {})}


def raw(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def descriptor(data):
    digest = hashlib.sha256(data).hexdigest()
    return {'key': 'raw/' + digest, 'sha256': 'sha256:' + digest, 'size_bytes': len(data)}


def observation(day, rows, *, status=200, failure=None):
    data = raw(rows)
    archive = MemoryArchive()
    start = datetime.fromisoformat(day + 'T23:47:00+00:00')
    value = MembershipHttpObservation(start, start + timedelta(seconds=1), status, len(data), True, failure, data)
    with patch('services.market_data.membership_collection.observe_active_us_symbols', return_value=value):
        collected = collect_membership(day, authorize=lambda **_: EVIDENCE, archive=archive)
    original = archive.objects[collected.observation_key]
    body = json.loads(original)
    return {'observation_bytes': original, 'response_bytes': archive.objects[body['response']['key']],
            'acquisition_bytes': archive.objects[body['acquisition_evidence']['key']]}


def evidence(*observations):
    # Explicitly synthetic trusted-root stand-in, not a source of live authority.
    history = [descriptor(item['observation_bytes']) for item in observations]
    return {'current_index': {'revision': len(history), 'head': history[-1] if history else None, 'history': history},
            'observations': list(observations)}


def by_code(result):
    return {m['provider_code']: m for m in result.members}


class MembershipIdentityTests(unittest.TestCase):
    def test_real_collector_bytes_restore_without_network_and_bind_all_originals(self):
        source = observation(D1, [symbol()])
        restored = membership_observation_history(evidence(source), as_of=D1)
        self.assertEqual(restored[0][0].raw_bytes, source['response_bytes'])
        self.assertEqual(restored[0][1], descriptor(source['observation_bytes']))
        for field in source:
            bad = deepcopy(source); bad[field] += b' '
            with self.subTest(field=field), self.assertRaises(ContractError):
                membership_observation_history(evidence(source) | {'observations': [bad]}, as_of=D1)

    def test_continuity_gap_name_change_and_same_isin_do_not_rekey_or_merge(self):
        first = observation(D1, [symbol(isin='SYNTH-ISIN')])
        later = observation(D3, [symbol(isin='SYNTH-ISIN', name='Changed name'), symbol('SYNTHB', isin='SYNTH-ISIN')])
        initial = by_code(build_observed_membership(evidence(first), as_of=D1))
        current = by_code(build_observed_membership(evidence(first, later), as_of=D3))
        self.assertEqual(initial['SYNTHA']['instrument_id'], current['SYNTHA']['instrument_id'])
        self.assertEqual(current['SYNTHA']['observed_listing_epoch'], D1)
        self.assertEqual(current['SYNTHB']['observed_listing_epoch'], D3)
        self.assertNotEqual(current['SYNTHA']['instrument_id'], current['SYNTHB']['instrument_id'])
        self.assertIn(descriptor(first['observation_bytes'])['key'], current['SYNTHA']['identity_source'])

    def test_full_source_disappearance_reappearance_and_exchange_change_create_new_epochs(self):
        first = observation(D1, [symbol()])
        old = by_code(build_observed_membership(evidence(first), as_of=D1))['SYNTHA']['instrument_id']
        for middle in ([symbol('SYNTHB')], [symbol(kind='ETF'), symbol('SYNTHB')]):
            result = build_observed_membership(evidence(first, observation(D2, middle), observation(D3, [symbol()])), as_of=D3)
            current = by_code(result)['SYNTHA']
            self.assertEqual(current['observed_listing_epoch'], D3)
            self.assertNotEqual(current['instrument_id'], old)
        result = build_observed_membership(evidence(first, observation(D2, [symbol(exchange='NASDAQ')])), as_of=D2)
        self.assertEqual(result.members[0]['observed_listing_epoch'], D2)
        self.assertNotEqual(result.members[0]['instrument_id'], old)

    def test_missing_isin_preserves_known_evidence_and_later_conflict_fails(self):
        first = observation(D1, [symbol(isin='SYNTH-ONE')])
        missing = observation(D2, [symbol()])
        current = build_observed_membership(evidence(first, missing), as_of=D2).members[0]
        self.assertEqual(current['isin'], 'SYNTH-ONE')
        self.assertIn('isin_observation=' + descriptor(first['observation_bytes'])['key'], current['identity_source'])
        with self.assertRaisesRegex(ContractError, 'ISIN conflicts'):
            build_observed_membership(evidence(first, missing, observation(D3, [symbol(isin='SYNTH-TWO')])), as_of=D3)

    def test_failed_acquisition_cannot_advance_identity_or_count_as_absence(self):
        first = observation(D1, [symbol()])
        failed = observation(D2, [symbol('SYNTHB')], status=503, failure='http_status_rejected')
        later = observation(D3, [symbol()])
        with self.assertRaises(ContractError): build_observed_membership(evidence(first, failed, later), as_of=D3)
        recovered = build_observed_membership(evidence(first, later), as_of=D3)
        self.assertEqual(recovered.members[0]['observed_listing_epoch'], D1)

    def test_index_omission_reorder_same_day_conflict_wrong_head_and_old_target_fail(self):
        first, second = observation(D1, [symbol()]), observation(D2, [symbol()])
        good = evidence(first, second)
        mutations = []
        v = deepcopy(good); v['observations'].pop(0); mutations.append(v)
        v = deepcopy(good); v['current_index']['history'].pop(0); mutations.append(v)
        v = deepcopy(good); v['current_index']['revision'] = True; mutations.append(v)
        v = deepcopy(good); v['current_index']['head'] = v['current_index']['history'][0]; mutations.append(v)
        mutations += [evidence(second, first), evidence(first, first), evidence(first, observation(D1, [symbol('SYNTHB')]))]
        for v in mutations:
            with self.assertRaises(ContractError): build_observed_membership(v, as_of=D2)
        for day in ('2026-08-28', D1, D3):
            with self.assertRaises(ContractError): build_observed_membership(good, as_of=day)

    def test_resealed_bad_protocol_request_framing_or_time_still_fails(self):
        source = observation(D1, [symbol()])
        for key, value in [('version', True), ('eof', 1), ('content_length', True), ('http_status', 201),
            ('failure', 'http_transport_failed'), ('parsed_policy_version', 'other'),
            ('started_at', D2 + 'T23:00:00+00:00'), ('request', {'url': 'https://other.invalid'})]:
            changed = deepcopy(source); body = json.loads(changed['observation_bytes']); body[key] = value
            changed['observation_bytes'] = raw(body)
            with self.subTest(key=key), self.assertRaises(ContractError):
                build_observed_membership(evidence(changed), as_of=D1)
        changed = deepcopy(source); changed['observation_bytes'] = b'{"kind":1,"kind":2}'
        with self.assertRaises(ContractError): build_observed_membership(evidence(changed), as_of=D1)

    def test_idempotence_readonly_output_and_original_qualification_universe_composition(self):
        e = evidence(observation(D1, [symbol()]))
        result = build_observed_membership(e, as_of=D1)
        self.assertEqual(result, build_observed_membership(deepcopy(e), as_of=D1))
        with self.assertRaises(TypeError): result.members[0]['symbol'] = 'OTHER'
        with self.assertRaises(TypeError): result.source_history[0]['size_bytes'] = 0
        with self.assertRaises(FrozenInstanceError): result.as_of = D2
        rows = tuple({'date': (date.fromisoformat(D1) - timedelta(days=419-i)).isoformat(),
            'open': 5.0, 'high': 5.0, 'low': 5.0, 'close': 5.0, 'volume': 2_000_000} for i in range(420))
        reads = {m['instrument_id']: RepositoryRead(m['instrument_id'], D1, rows, bars_fingerprint(rows)) for m in result.members}
        qualifications = build_same_day_qualifications(as_of=D1, members=result.members, reads=reads,
            complete_history_instruments=set(reads))  # Synthetic source-completeness stand-in only.
        snapshot = build_forward_universe_snapshot(as_of=D1, generated_at=D1 + 'T23:48:00Z',
            source_version={'fixture': 'synthetic'}, eligibility_rule_version='m12-eodhd-primary-common-1.0.0',
            effective_from=D1, membership_evidence=result.membership_evidence, members=result.members,
            qualifications=qualifications)
        self.assertEqual(snapshot['schema_version'], '3.0.0')
        self.assertTrue(snapshot['qualifications'][0]['eligible'])
        self.assertEqual(snapshot['members'][0]['instrument_id'], result.members[0]['instrument_id'])


if __name__ == '__main__': unittest.main()
