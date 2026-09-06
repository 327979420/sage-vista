"""Fixed membership computation with synthetic authority/source and real Git."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import time
import unittest
from unittest.mock import patch

from services.contracts.validation import ContractError, membership_registration_input
from services.publication.configuration import ROOT, build_research_configuration
from services.publication.membership_validation import validate_membership_registration_input
from services.publication import preparation_execution as process
from tests.test_m12_preparation_validation import fixture
from tests.test_m12_membership_identity import observation, symbol, descriptor, raw


def membership_wire(commit, config, now):
    prepared = fixture(commit, config, now)
    day = prepared['evidence']['as_of']
    source = observation(day, [symbol()])
    body = json.loads(source['observation_bytes'])
    # Synthetic observation is fully completed before computation; no real IO.
    stamp = datetime.fromtimestamp(now // 1000, timezone.utc).isoformat()
    body.update(started_at=stamp, completed_at=stamp)
    source['observation_bytes'] = raw(body)
    return {'protocol': 'm12-membership-registration/1', 'identity': deepcopy(prepared['identity']),
        'preparation_base64': base64.b64encode(raw(prepared)).decode(),
        'expected_index': {'revision': 0, 'head': None, 'history': []},
        'candidate_archive': descriptor(source['observation_bytes']),
        'acquisition_archive': body['acquisition_evidence'],
        'observations_base64': [{k: base64.b64encode(v).decode() for k, v in source.items()}]}


class MembershipValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        cls.config = build_research_configuration(cls.commit)
        cls.now = time.time_ns() // 1_000_000

    def wire(self): return membership_wire(self.commit, self.config, self.now)
    def validate(self, wire, *, end=None):
        times = iter([self.now, self.now + 1 if end is None else end])
        return json.loads(validate_membership_registration_input(raw(wire), clock=lambda: next(times)))

    def test_actual_git_and_sole_identity_producer_bind_exact_registration_target(self):
        wire = self.wire(); result = self.validate(wire)
        self.assertEqual(result['input_sha256'], 'sha256:' + hashlib.sha256(raw(wire)).hexdigest())
        self.assertEqual(result['input_size_bytes'], len(raw(wire)))
        self.assertEqual(result['membership_registration']['expected_index'], wire['expected_index'])
        self.assertEqual(result['membership_registration']['candidate_archive'], wire['candidate_archive'])
        self.assertEqual(result['membership_registration']['member_count'], 1)
        self.assertEqual(result['preparation']['config_ref'], dict(self.config.config_ref))
        self.assertNotIn('registered', result)
        self.assertNotIn('permissions', result)

    def test_current_head_replay_does_not_append_duplicate_source(self):
        wire = self.wire()
        wire['expected_index'] = {'revision': 1, 'head': wire['candidate_archive'], 'history': [wire['candidate_archive']]}
        value = membership_registration_input(raw(wire))
        self.assertEqual(value['membership_evidence']['current_index']['revision'], 1)
        self.assertEqual(self.validate(wire)['membership_registration']['member_count'], 1)

    def test_identity_index_original_bytes_and_fixed_license_mismatches_fail(self):
        changes = [lambda w: w.update(protocol='other'), lambda w: w['identity'].update(actor_id='999'),
            lambda w: w['expected_index'].update(revision=True), lambda w: w['expected_index'].update(revision=1),
            lambda w: w['candidate_archive'].update(size_bytes=1),
            lambda w: w['observations_base64'][0].update(response_bytes='e30='),
            lambda w: w.update(acquisition_archive=descriptor(b'unrelated-license')),
            lambda w: w.update(extra=True), lambda w: w.update(preparation_base64='Zh==')]
        for change in changes:
            wire = self.wire(); change(wire)
            with self.assertRaises(ContractError): membership_registration_input(raw(wire))
        for data in (bytearray(raw(self.wire())), b'{"protocol":1,"protocol":2}', b'{}'):
            with self.assertRaises(ContractError): membership_registration_input(data)

    def test_matching_source_cannot_bypass_current_revoke_or_frozen_configuration(self):
        wire = self.wire()
        prepared = fixture(self.commit, self.config, self.now, revoke=True)
        wire['preparation_base64'] = base64.b64encode(raw(prepared)).decode()
        with self.assertRaisesRegex(ContractError, 'current head'): self.validate(wire)
        from services.ranking import policies
        with patch.object(policies, 'SCORE_POLICY', {}), self.assertRaises(ContractError): self.validate(self.wire())

    def test_expiry_and_future_acquisition_cannot_produce_success(self):
        wire = self.wire()
        with self.assertRaises(ContractError): self.validate(wire, end=wire['identity']['expires_at'] * 1000)
        body = json.loads(base64.b64decode(wire['observations_base64'][0]['observation_bytes']))
        body['completed_at'] = datetime.fromtimestamp(self.now // 1000 + 1, timezone.utc).isoformat()
        data = raw(body); wire['candidate_archive'] = descriptor(data)
        wire['observations_base64'][0]['observation_bytes'] = base64.b64encode(data).decode()
        with self.assertRaises(ContractError): self.validate(wire)

    def test_fixed_executor_rejects_wrong_protocol_and_wrong_result_without_retry(self):
        data = raw(self.wire())
        with self.assertRaises(process.PreparationExecutionError): process.execute_preparation_validation(data)
        class Child:
            calls = 0
            def __init__(self, _): Child.calls += 1
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def poll(self): return b'{"protocol":"m12-preparation-validation/1"}'
        with patch.object(process, 'PreparationValidationProcess', Child):
            with self.assertRaisesRegex(process.PreparationExecutionError, '^membership computation failed$'):
                process.execute_membership_validation(data)
        self.assertEqual(Child.calls, 1)

    def test_real_fixed_membership_process_uses_same_verified_worker(self):
        wire = membership_wire(self.commit, self.config, time.time_ns() // 1_000_000)
        result = json.loads(process.execute_membership_validation(raw(wire)))
        self.assertEqual(result['membership_registration']['candidate_archive'], wire['candidate_archive'])
        self.assertEqual(result['membership_registration']['member_count'], 1)
        with self.assertRaises(TypeError): process.execute_membership_validation(raw(wire), command='other')


if __name__ == '__main__': unittest.main()
