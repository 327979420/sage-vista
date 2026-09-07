"""Bounded execution wire/fixed-process checks with original synthetic sources."""
import base64
import copy
import hashlib
import json
import time
import unittest
from unittest.mock import patch
from services.contracts.validation import ContractError, execution_computation_input
from services.publication.execution_history import encode, prepare_execution_pairs
from services.publication.execution_validation import validate_execution_input
from services.publication.preparation_execution import execute_execution_validation, PreparationExecutionError
from tests import test_m12_execution_inventory as source


class ExecutionValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source.ExecutionInventoryTests.setUpClass()

    def setUp(self):
        fixture = source.ExecutionInventoryTests()
        fixture.setUp()
        self.fixture = fixture
        self.now = time.time_ns() // 1_000_000
        identity = {'job': {'repository_id': '1', 'workflow_ref': 'local/synthetic@main',
            'workflow_commit': fixture.commit, 'run_id': '1', 'run_attempt': 1, 'environment': 'synthetic'},
            'code_commit': fixture.commit, 'actor_id': '1', 'subject': 'synthetic-only', 'token_id': 'synthetic-only',
            'issued_at': self.now // 1000 - 1, 'expires_at': self.now // 1000 + 300}
        self.request = {'as_of': source.DAY, 'entry_reads': {}, 'completed_reads': {},
            'sessions_by_instrument': {}, 'generated_at': source.DAY + 'T23:15:00Z'}
        self.value = {'protocol': 'm12-execution-validation/1', 'identity': identity,
            'snapshot': fixture.snapshot,
            'objects': {key: base64.b64encode(raw).decode() for key, raw in fixture.objects.items()},
            'request_bytes': base64.b64encode(encode(self.request)).decode()}

    def test_original_inventory_and_next_pair_bind_actual_input_bytes(self):
        raw = encode(self.value)
        result = json.loads(validate_execution_input(raw, clock=lambda: self.now))
        self.assertEqual(result['input_sha256'], 'sha256:' + hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['input_size_bytes'], len(raw))
        expected = prepare_execution_pairs(self.fixture.snapshot, self.fixture.objects, self.request)[0]
        for name in ('input_bytes', 'object_bytes', 'link_bytes'):
            self.assertEqual(base64.b64decode(result['next_pair'][name]), expected[name])
        inventory = json.loads(base64.b64decode(result['inventory_bytes']))
        self.assertEqual(inventory['config_ref'], dict(self.fixture.config.config_ref))

    def test_identity_config_and_expired_computation_fail(self):
        value = copy.deepcopy(self.value)
        value['identity']['code_commit'] = 'a' * 40
        with self.assertRaises(ContractError): validate_execution_input(encode(value), clock=lambda: self.now)
        values = iter([self.now, self.value['identity']['expires_at'] * 1000])
        with self.assertRaises(ContractError): validate_execution_input(encode(self.value), clock=lambda: next(values))

    def test_strict_wire_missing_original_and_unknown_fields_fail(self):
        value = copy.deepcopy(self.value)
        value['objects'] = {}
        with self.assertRaises(ContractError): validate_execution_input(encode(value), clock=lambda: self.now)
        for change in ({'command': 'other'}, {'protocol': 'other'}, {'request_bytes': 'not base64'}):
            with self.subTest(change=change), self.assertRaises(ContractError):
                execution_computation_input(encode({**self.value, **change}))

    def test_wrapper_discards_wrong_input_binding_without_retry(self):
        class Child:
            def __init__(self, raw): pass
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def poll(self): return encode({'protocol': 'm12-execution-validation/1', 'input_sha256': 'bad', 'input_size_bytes': 1})
        with patch('services.publication.preparation_execution.PreparationValidationProcess', Child):
            with self.assertRaisesRegex(PreparationExecutionError, '^execution computation failed$'):
                execute_execution_validation(encode(self.value))

    def test_real_fixed_worker_computes_registered_source_inventory(self):
        raw = encode(self.value)
        result = json.loads(execute_execution_validation(raw))
        self.assertEqual(result['task_id'], self.fixture.snapshot['root']['task_id'])
        self.assertEqual(result['input_sha256'], 'sha256:' + hashlib.sha256(raw).hexdigest())
        self.assertIsNotNone(result['next_pair'])
