"""Synthetic original M02 data, actual Git configuration, no supplier requests."""
import base64
import json
import subprocess
import unittest
from services.contracts.validation import ContractError
from services.publication.configuration import build_research_configuration
from services.publication.execution_history import encode, _signal, execution_task_id, prepare_execution_pairs
from services.publication.execution_inventory import encode_execution_source_root, build_execution_source_inventory
from tests.test_market_data_consumers import DAY, complete_gate_rows, forward_member, forward_snapshot
from tests.test_m06_context import price_rows
from tests.test_m07_ranking import reader_map
from services.ranking import build_authority_activation
from tests.test_m12_execution_history import put, append


class ExecutionInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
        cls.config = build_research_configuration(cls.commit)
        members = [forward_member('AAA')]
        etfs = [forward_member(symbol) for symbol in ('BOTZ', 'IWM', 'QQQ', 'SOXX', 'SPY', 'XLE')]
        def reads(members, rows):
            reader = reader_map({member['instrument_id']: rows for member in members})
            return {member['instrument_id']: reader(member['instrument_id'], as_of=DAY) for member in members}
        cls.inputs = dict(as_of=DAY, stock_snapshots=[forward_snapshot(members=members)],
            etf_snapshots=[forward_snapshot(members=etfs)], stock_reads=reads(members, complete_gate_rows()),
            etf_reads=reads(etfs, price_rows()),
            data_source={'provider': 'EODHD', 'market': 'US', 'dataset': 'synthetic-local-only'},
            membership_registry={'schema_version': '1.0.0', 'mapping_registry_version': 'synthetic-1.0.0', 'snapshots': []},
            activation=build_authority_activation(effective_from=DAY, approval_ref='synthetic-local-only'),
            generated_at=DAY + 'T23:10:00Z', scan_batch_id='synthetic-inventory')
        cls.root_bytes = encode_execution_source_root(cls.config.raw_bytes, encode(cls.inputs))

    def setUp(self):
        self.objects = {}
        self.snapshot = {'root': {'task_id': execution_task_id(_signal(self.root_bytes)),
            'root': put(self.objects, self.root_bytes)}, 'revision': 0, 'history': []}

    def build(self):
        return build_execution_source_inventory(self.snapshot, self.objects, generated_at=DAY + 'T23:20:00Z')

    def test_complete_original_source_replay_builds_existing_inventory_contract(self):
        inventory = self.build()
        ids = {ref['id'] for ref in inventory['records']}
        self.assertTrue(any(value.startswith('market:') for value in ids))
        self.assertTrue(any(value.startswith('universe:') for value in ids))
        self.assertIn(self.config.config_ref['id'], ids)
        self.assertTrue(any(value.startswith('ranking:') for value in ids))
        self.assertEqual(inventory['config_ref'], dict(self.config.config_ref))
        self.assertEqual(inventory, self.build())

    def test_complete_paired_history_is_included_in_task_root(self):
        before = self.build()
        request = dict(as_of=DAY, sessions_by_instrument={}, entry_reads={}, completed_reads={},
                       generated_at=DAY + 'T23:15:00Z')
        for pair in prepare_execution_pairs(self.snapshot, self.objects, request):
            append(self.snapshot, self.objects, pair)
        after = self.build()
        self.assertNotEqual(before['roots'], after['roots'])
        self.assertTrue(any(ref['id'].startswith('trade-plan-batch:') for ref in after['records']))

    def test_missing_source_fields_or_configured_etf_cannot_be_replaced_by_claims(self):
        value = json.loads(encode(self.inputs))
        value['stock_reads'] = {}
        with self.assertRaises(ContractError):
            encode_execution_source_root(self.config.raw_bytes, encode(value))
        value = json.loads(encode(self.inputs))
        value['etf_snapshots'] = [forward_snapshot(members=[forward_member('QQQ')])]
        value['etf_reads'] = {key: read for key, read in value['etf_reads'].items()
                              if key == forward_member('QQQ')['instrument_id']}
        with self.assertRaisesRegex(ContractError, 'configured ETF set'):
            encode_execution_source_root(self.config.raw_bytes, encode(value))

    def test_rehashed_source_replacement_cannot_change_the_frozen_signal(self):
        root = json.loads(self.root_bytes)
        inputs = json.loads(base64.b64decode(root['sources']['daily_input_bytes']))
        from services.contracts.market_data import canonical_fingerprint
        original = next(iter(inputs['stock_reads'].values()))
        original['rows'][-1]['high'] += 1
        original['point_in_time_fingerprint'] = canonical_fingerprint(original['rows'])
        root['sources']['daily_input_bytes'] = base64.b64encode(encode(inputs)).decode()
        self.objects = {}
        self.snapshot['root']['root'] = put(self.objects, encode(root))
        with self.assertRaises(ContractError):
            self.build()

    def test_old_signal_only_root_never_self_certifies_complete_sources(self):
        root = json.loads(self.root_bytes)
        root.pop('sources'); root['format'] = 'm12-execution-signal/1'
        self.objects = {}
        self.snapshot['root']['root'] = put(self.objects, encode(root))
        with self.assertRaisesRegex(ContractError, 'no complete registered source'):
            self.build()
