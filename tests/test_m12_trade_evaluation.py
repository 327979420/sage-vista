"""Synthetic paired M08/M09 history -> original M10, with real shadow IO."""
import json
from pathlib import Path
import tempfile
import unittest

from services.contracts.validation import ContractError
from services.evaluation.runner import store_baseline_evaluation_batch
from services.evaluation.storage import EvaluationShadowStore
from services.publication.execution_history import encode, prepare_execution_pairs
from services.publication.trade_evaluation import evaluate_registered_trade
from tests.test_m10_baseline_evaluator import market_evidence
from tests import test_m12_execution_history as history_fixtures
from tests.test_market_data_consumers import DAY, forward_snapshot
from tests.test_m12_execution_continuation import sessions


class RegisteredTradeEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        history_fixtures.ExecutionHistoryTests.setUpClass()

    def setUp(self):
        self.history = history_fixtures.ExecutionHistoryTests()
        self.history.setUp()
        self.fixture = self.history.fixture
        self.event = next(event for event in self.fixture.signal.events.events
                          if event['instrument_id'] == self.fixture.instrument)
        self.universe = forward_snapshot(members=self.fixture.fixture.members)

    def evaluate(self, *, previous=()):
        states = self.history.snapshot['history']
        from services.publication.execution_history import restore_execution_history
        restored = restore_execution_history(self.history.snapshot, self.history.objects)
        leaf = restored.states[-1] if restored.states else None
        as_of = leaf['as_of'] if leaf else DAY
        rows = tuple({**self.fixture.entry, 'date': day} for day in sessions(40) if day <= as_of)
        if not rows:
            rows = ({**self.fixture.entry, 'date': DAY},)
        read, market = market_evidence(self.event, rows, as_of=as_of)
        self.assertEqual(len(states), self.history.snapshot['revision'])
        return evaluate_registered_trade(self.history.snapshot, self.history.objects,
            event_id=self.event['event_id'], market_read=read, market_snapshot=market,
            universe_snapshot=self.universe, code_commit='d' * 40,
            generated_at=as_of + 'T23:01:00Z', finished_at=as_of + 'T23:02:00Z',
            previous_outcomes=previous)

    def advance(self, days):
        dates = sessions(days)
        request = {**self.history.request, 'as_of': dates[-1],
            'sessions_by_instrument': {self.fixture.instrument: dates},
            'completed_reads': {self.fixture.instrument: self.fixture.read(
                tuple({**self.fixture.entry, 'date': day} for day in dates))},
            'generated_at': dates[-1] + 'T23:00:00Z'}
        for pair in prepare_execution_pairs(self.history.snapshot, self.history.objects, request):
            history_fixtures.append(self.history.snapshot, self.history.objects, pair)

    def test_unavailable_then_open_then_original_terminal_and_shadow_reopen(self):
        missing = self.evaluate()
        self.assertIsNone(missing.batch)
        request = dict(as_of=DAY, sessions_by_instrument={}, entry_reads={},
                       completed_reads={}, generated_at=DAY + 'T23:00:00Z')
        for pair in prepare_execution_pairs(self.history.snapshot, self.history.objects, request):
            history_fixtures.append(self.history.snapshot, self.history.objects, pair)
        unavailable = self.evaluate()
        self.assertEqual(unavailable.state, 'queued')
        self.assertEqual(unavailable.batch.outcomes[0]['status'], 'unavailable')
        self.advance(1)
        active = self.evaluate(previous=unavailable.batch.outcomes)
        self.assertEqual(active.state, 'queued')
        self.assertEqual(active.reason, 'trade_open')
        self.assertEqual(active.batch.completed_run_receipt['status'], 'completed')
        self.advance(40)
        terminal = self.evaluate(previous=(*unavailable.batch.outcomes, *active.batch.outcomes))
        self.assertEqual(terminal.state, 'completed')
        self.assertEqual(terminal.batch.outcomes[0]['exit_reason'], 'time_40d')
        self.assertEqual(terminal.batch.outcomes[0]['holding_sessions'], 40)
        self.assertEqual({r.task_id for r in (missing, unavailable, active, terminal)}, {terminal.task_id})
        self.assertEqual(terminal.batch.outcomes[0]['net_return_status'], 'unavailable')
        with tempfile.TemporaryDirectory() as directory:
            store = EvaluationShadowStore(Path(directory) / 'm10')
            for result in (unavailable, active, terminal):
                store_baseline_evaluation_batch(store, result.batch)
            before = {p: p.read_bytes() for p in store.root.rglob('*.json')}
            store = EvaluationShadowStore(store.root)
            store_baseline_evaluation_batch(store, terminal.batch)
            self.assertEqual(before, {p: p.read_bytes() for p in store.root.rglob('*.json')})
            refs = store.result_references_for_run(terminal.batch.pending_run_receipt['run_id'])
            self.assertEqual(encode(refs), encode(terminal.batch.completed_run_receipt['result_refs']))
        dependency = json.loads(terminal.dependency_bytes)
        self.assertEqual(dependency['execution_snapshot'], self.history.snapshot)
        self.assertEqual(dependency['arguments']['event']['event_id'], self.event['event_id'])

    def test_plan_without_exit_pair_waits_and_missing_registered_link_fails(self):
        pair = prepare_execution_pairs(self.history.snapshot, self.history.objects, self.history.request)[0]
        history_fixtures.append(self.history.snapshot, self.history.objects, pair)
        result = self.evaluate()
        self.assertEqual(result.reason, 'exit_state_link_unavailable')
        self.assertIsNone(result.batch)
        del self.history.objects[self.history.snapshot['history'][0]['link']['key']]
        with self.assertRaises(ContractError):
            self.evaluate()

    def test_frozen_universe_mismatch_fails(self):
        self.advance(1)
        self.universe = forward_snapshot(as_of=sessions(1)[0], members=self.fixture.fixture.members)
        with self.assertRaisesRegex(ContractError, 'frozen universe'):
            self.evaluate()
