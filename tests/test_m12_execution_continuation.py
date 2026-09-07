"""Synthetic original M07/M09 fixtures + real local shadow stores, no cloud."""
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError
from services.execution import ExecutionShadowStore, advance_exit_state, current_exit_state
from services.factors import produce_support_evidence
from services.ledger import EventLedgerStore, produce_event_ledger_batch
from services.market_data import RepositoryRead
from services.publication.execution_continuation import freeze_execution_signal, continue_execution_signal
from services.ranking import build_authority_activation
from tests import test_m07_ranking as fixtures
from tests.test_m03_gates import GENERATED_AT
from tests.test_market_data_consumers import DAY, complete_gate_rows, forward_snapshot
from tests.test_m06_context import price_rows
from services.publication.daily_chain import produce_daily_chain


def sessions(count):
    result, day = [], date.fromisoformat(DAY)
    while len(result) < count:
        day += timedelta(days=1)
        if day.weekday() < 5:
            result.append(day.isoformat())
    return tuple(result)


class ExecutionContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = fixtures.M07RankingTests()
        fixture.setUp()  # Explicit synthetic available-factor fixture, not acquisition.
        cls.fixture = fixture
        ranking = fixture.produce(ranking_role='authoritative', activation=build_authority_activation(
            effective_from=DAY, approval_ref='synthetic-continuation-only')).snapshot
        support = produce_support_evidence(fixture.stock, gate_events=fixture.events,
                                            technical_evidence=fixture.evidence, generated_at=GENERATED_AT)
        events = produce_event_ledger_batch(
            gate_events=fixture.events, technical_evidence=fixture.evidence,
            model_assessments=fixture.assessments, contexts=fixture.contexts,
            ranking_snapshot=ranking, generated_at=GENERATED_AT)
        cls.signal = freeze_execution_signal(ranking, support, events)
        cls.instrument = fixture.members[0]['instrument_id']
        cls.entry = dict(date=sessions(1)[0], open=100., high=101., low=99., close=100., volume=1_000_000)
        cls.entry_read = cls.read(tuple(complete_gate_rows()) + (cls.entry,))

    @classmethod
    def read(cls, rows):
        return RepositoryRead(instrument_id=cls.instrument, as_of=rows[-1]['date'], rows=tuple(rows),
                              point_in_time_fingerprint=canonical_fingerprint(list(rows)))

    def run_chain(self, *, days=1, rows=None, existing_plans=(), existing_states=(), **changes):
        dates = sessions(days)
        rows = rows if rows is not None else tuple({**self.entry, 'date': day} for day in dates)
        inputs = dict(as_of=dates[-1], sessions_by_instrument={self.instrument: dates},
                      entry_reads={self.instrument: self.entry_read},
                      completed_reads={self.instrument: self.read(rows)},
                      existing_plans=existing_plans, existing_states=existing_states,
                      generated_at=dates[-1] + 'T23:00:00Z')
        inputs.update(changes)
        return continue_execution_signal(self.signal, **inputs)

    def test_d_pending_then_original_d_plan_even_after_drop_from_new_ranking(self):
        pending = continue_execution_signal(self.signal, as_of=DAY,
            sessions_by_instrument={}, entry_reads={}, completed_reads={}, generated_at=GENERATED_AT)
        self.assertEqual(len(pending.plan_batch.plans), 0)
        self.assertEqual(pending.pending[self.instrument], 'next_adjusted_open_unavailable')
        self.assertIn(self.instrument, {e['instrument_id'] for e in self.signal.ranking['selected_entries']})
        next_day = sessions(1)[0]
        stock_member, etf_member = self.fixture.members[0], fixtures.forward_member('QQQ')
        later = produce_daily_chain(
            as_of=next_day, stock_snapshots=[forward_snapshot(as_of=next_day, members=[stock_member])],
            etf_snapshots=[forward_snapshot(as_of=next_day, members=[etf_member])],
            stock_reader=fixtures.reader_map({self.instrument: price_rows(end=next_day)}),
            etf_reader=fixtures.reader_map({etf_member['instrument_id']: price_rows(end=next_day)}),
            data_source={'provider': 'fixture', 'dataset': 'adjusted-daily', 'market': 'US'},
            etf_registry=self.fixture.registry, membership_registry=self.fixture.memberships,
            activation=build_authority_activation(effective_from=DAY, approval_ref='synthetic-only'),
            generated_at=next_day + 'T23:00:00Z', scan_batch_id='synthetic-dropped-next-day')
        self.assertEqual(later.ranking.snapshot['selected_entries'], ())
        # The real new-day composition drops A; continuation still uses D.
        result = self.run_chain()
        self.assertEqual(len(result.plan_batch.plans), 1)
        plan = result.plan_batch.plans[0]
        self.assertEqual(plan['signal_date'], DAY)
        self.assertEqual(plan['entry_date'], sessions(1)[0])
        self.assertEqual(plan['entry']['price'], 100.)
        self.assertEqual(plan['ranking_snapshot_id'], self.signal.ranking['ranking_snapshot_id'])
        states = [obj for kind, obj in result.records if kind == 'exit']
        self.assertEqual([state['holding_sessions'] for state in states], [1])
        self.assertEqual(states[0]['state'], 'active')

    def test_late_backfill_uses_original_entry_and_steps_each_session(self):
        result = self.run_chain(days=3)
        states = [obj for kind, obj in result.records if kind == 'exit']
        self.assertEqual([state['holding_sessions'] for state in states], [1, 2, 3])
        self.assertEqual([state['as_of'] for state in states], list(sessions(3)))
        self.assertEqual(result.plan_batch.plans[0]['entry_date'], sessions(1)[0])
        late_entry = self.read(({**self.entry, 'date': sessions(3)[-1]},))
        with self.assertRaisesRegex(ContractError, 'first original tradable session'):
            self.run_chain(days=3, entry_reads={self.instrument: late_entry})

    def test_gap_stops_prefix_then_repair_reuses_leaf(self):
        dates = sessions(3)
        rows = tuple({**self.entry, 'date': day} for day in (dates[0], dates[2]))
        partial = self.run_chain(days=3, rows=rows)
        states = [obj for kind, obj in partial.records if kind == 'exit']
        self.assertEqual(len(states), 1)
        self.assertEqual(partial.pending[self.instrument], 'completed_session_unavailable:' + dates[1])
        repaired = self.run_chain(days=3, existing_plans=partial.plan_batch.plans, existing_states=states)
        states2 = [obj for kind, obj in repaired.records if kind == 'exit']
        self.assertEqual([state['holding_sessions'] for state in states2], [1, 2, 3])
        self.assertEqual(states2[0], states[0])
        self.assertNotIn(self.instrument, repaired.pending)

    def test_prefix_revision_and_exit_fork_fail_closed(self):
        initial = self.run_chain(days=2)
        states = [obj for kind, obj in initial.records if kind == 'exit']
        revised = tuple({**self.entry, 'date': day, 'close': 100.5 if i == 1 else 100.}
                        for i, day in enumerate(sessions(3)))
        with self.assertRaises(ContractError):
            self.run_chain(days=3, rows=revised, existing_plans=initial.plan_batch.plans, existing_states=states)
        alternate = advance_exit_state(initial.plan_batch.plans[0],
            completed_bars=[{**self.entry, 'date': day} for day in sessions(3)],
            previous_state=states[0], generated_at=sessions(3)[-1] + 'T23:00:00Z')
        with self.assertRaises(ContractError):
            self.run_chain(days=3, existing_plans=initial.plan_batch.plans, existing_states=states + [alternate])

    def test_original_forty_session_exit_and_terminal_retry(self):
        result = self.run_chain(days=41)
        states = [obj for kind, obj in result.records if kind == 'exit']
        self.assertEqual(len(states), 40)
        self.assertEqual(current_exit_state(states)['state'], 'closed_time_40d')
        retried = self.run_chain(days=41, completed_reads={},
            existing_plans=result.plan_batch.plans, existing_states=states)
        self.assertEqual([obj for kind, obj in retried.records if kind == 'exit'], states)
        revised = tuple({**self.entry, 'date': day, 'close': 100.5 if i == 1 else 100.}
                        for i, day in enumerate(sessions(41)))
        with self.assertRaises(ContractError):
            self.run_chain(days=41, rows=revised, existing_plans=result.plan_batch.plans, existing_states=states)

    def test_actual_store_recovery_after_plan_or_exit_before_link(self):
        for interrupted_kind in ('plan', 'exit'):
            with self.subTest(interrupted_kind=interrupted_kind), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                execution, ledger = ExecutionShadowStore(root / 'm08'), EventLedgerStore(root / 'm09')
                for event in self.signal.events.events:
                    ledger.write_event(event)
                original_event_bytes = {p: p.read_bytes() for p in (root / 'm09/events').rglob('*.json')}
                pending = continue_execution_signal(self.signal, as_of=DAY,
                    sessions_by_instrument={}, entry_reads={}, completed_reads={}, generated_at=GENERATED_AT)
                for kind, obj in pending.records:
                    ledger.write_machine_link(obj)
                writers = {'plan': execution.write_plan, 'exit': execution.write_exit_state,
                           'link': ledger.write_machine_link}
                for kind, obj in self.run_chain().records:
                    writers[kind](obj)
                    if kind == interrupted_kind:
                        break  # Simulated crash before its paired M09 link.
                saved_plans = [json.loads(p.read_bytes()) for p in (root / 'm08/plans').rglob('*.json')]
                saved_states = [json.loads(p.read_bytes()) for p in (root / 'm08/exit-states').rglob('*.json')]
                old_bytes = {p: p.read_bytes() for p in root.rglob('*.json')}
                retry = self.run_chain(existing_plans=saved_plans, existing_states=saved_states)
                for kind, obj in retry.records:
                    writers[kind](obj)
                after = {p: p.read_bytes() for p in root.rglob('*.json')}
                for p, content in old_bytes.items():
                    self.assertEqual(after[p], content)
                for kind, obj in retry.records:
                    writers[kind](obj)
                self.assertEqual(after, {p: p.read_bytes() for p in root.rglob('*.json')})
                self.assertEqual(len(list((root / 'm08/plans').rglob('*.json'))), 1)
                self.assertEqual(len(list((root / 'm08/exit-states').rglob('*.json'))), 1)
                self.assertEqual(original_event_bytes, {p: p.read_bytes() for p in (root / 'm09/events').rglob('*.json')})

    def test_existing_plan_cannot_be_lost_when_entry_read_missing(self):
        initial = self.run_chain()
        with self.assertRaisesRegex(ContractError, 'stored plan conflicts'):
            self.run_chain(entry_reads={}, existing_plans=initial.plan_batch.plans)

    def test_completed_read_tampering_and_future_calendar_are_rejected(self):
        from dataclasses import replace
        read = self.read((self.entry,))
        with self.assertRaises(ContractError):
            self.run_chain(completed_reads={self.instrument: replace(read, point_in_time_fingerprint='sha256:' + '0' * 64)})
        with self.assertRaises(ContractError):
            self.run_chain(sessions_by_instrument={self.instrument: sessions(2)})

    def test_frozen_signal_is_detached_and_unknown_exit_history_is_rejected(self):
        from services.ledger.producer import _plain
        mutable = _plain(self.signal.ranking)
        frozen = freeze_execution_signal(mutable, self.signal.support, self.signal.events)
        mutable['selected_entries'].clear()
        self.assertEqual(frozen.ranking, self.signal.ranking)
        initial = self.run_chain()
        states = [obj for kind, obj in initial.records if kind == 'exit']
        with self.assertRaises(ContractError):
            self.run_chain(entry_reads={}, existing_states=states)
