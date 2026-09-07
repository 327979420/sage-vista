"""Original synthetic execution packets; production input factory remains absent."""
import copy
import hashlib
import unittest
from services.contracts.validation import ContractError
from services.publication.execution_history import (
    encode_signal, execution_task_id, prepare_execution_pairs, restore_execution_history,
)
from tests import test_m12_execution_continuation as fixtures


def put(objects, raw):
    digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
    key = 'raw/' + digest[7:]
    objects[key] = raw
    return {'key': key, 'sha256': digest, 'size_bytes': len(raw)}


def append(snapshot, objects, pair):
    position = snapshot['revision'] + 1
    row = {'task_id': snapshot['root']['task_id'], 'position': position,
           'step_id': pair['step_id'], 'previous_step_id': snapshot['history'][-1]['step_id'] if snapshot['history'] else None}
    for name in ('input', 'object', 'link'):
        row[name] = put(objects, pair[name + '_bytes'])
    snapshot['history'].append(row)
    snapshot['revision'] = position


class ExecutionHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.ExecutionContinuationTests.setUpClass()
        cls.fixture = fixtures.ExecutionContinuationTests()

    def setUp(self):
        self.objects = {}
        self.snapshot = {'root': {'task_id': execution_task_id(self.fixture.signal),
            'root': put(self.objects, encode_signal(self.fixture.signal))}, 'revision': 0, 'history': []}
        dates = fixtures.sessions(3)
        self.request = dict(as_of=dates[-1], sessions_by_instrument={self.fixture.instrument: dates},
            entry_reads={self.fixture.instrument: self.fixture.entry_read},
            completed_reads={self.fixture.instrument: self.fixture.read(
                tuple({**self.fixture.entry, 'date': day} for day in dates))},
            generated_at=dates[-1] + 'T23:00:00Z')

    def commit_all(self):
        pairs = prepare_execution_pairs(self.snapshot, self.objects, self.request)
        for pair in pairs:
            append(self.snapshot, self.objects, pair)
        return pairs

    def test_original_packets_restore_only_linked_leaves_and_reuse_frozen_entry(self):
        pairs = self.commit_all()
        self.assertEqual(len(pairs), 4)
        restored = restore_execution_history(self.snapshot, self.objects)
        self.assertEqual(len(restored.plans), 1)
        self.assertEqual([state['holding_sessions'] for state in restored.states], [1, 2, 3])
        self.assertEqual(set(restored.confirmed_through.values()), {fixtures.sessions(3)[-1]})
        retry = {**self.request, 'entry_reads': {}, 'generated_at': fixtures.sessions(3)[-1] + 'T23:59:00Z'}
        self.assertEqual(prepare_execution_pairs(self.snapshot, self.objects, retry), ())

    def test_missing_registered_link_prevents_any_business_checkpoint(self):
        self.commit_all()
        del self.objects[self.snapshot['history'][-1]['link']['key']]
        with self.assertRaises(ContractError):
            restore_execution_history(self.snapshot, self.objects)

    def test_rehashed_wrong_pair_is_rejected_by_original_replay(self):
        pairs = self.commit_all()
        self.snapshot['history'][-1]['link'] = put(self.objects, pairs[0]['link_bytes'])
        required = {self.snapshot['root']['root']['key']} | {
            row[k]['key'] for row in self.snapshot['history'] for k in ('input', 'object', 'link')}
        self.objects = {k: v for k, v in self.objects.items() if k in required}
        with self.assertRaisesRegex(ContractError, 'original producers'):
            restore_execution_history(self.snapshot, self.objects)

    def test_exit_pair_cannot_precede_registered_plan_pair(self):
        pairs = prepare_execution_pairs(self.snapshot, self.objects, self.request)
        append(self.snapshot, self.objects, pairs[1])
        with self.assertRaisesRegex(ContractError, 'precedes'):
            restore_execution_history(self.snapshot, self.objects)

    def test_history_root_and_omitted_step_cannot_be_replaced(self):
        self.commit_all()
        altered = copy.deepcopy(self.snapshot)
        altered['root']['task_id'] = 'execution-task:sha256:' + '0' * 64
        with self.assertRaises(ContractError):
            restore_execution_history(altered, self.objects)
        self.snapshot['history'].pop()
        with self.assertRaises(ContractError):
            restore_execution_history(self.snapshot, self.objects)

    def test_frozen_entry_replacement_is_rejected(self):
        self.commit_all()
        bad = self.fixture.read(tuple(fixtures.complete_gate_rows()) + ({**self.fixture.entry, 'open': 100.5},))
        with self.assertRaisesRegex(ContractError, 'frozen entry'):
            prepare_execution_pairs(self.snapshot, self.objects,
                {**self.request, 'entry_reads': {self.fixture.instrument: bad}})
