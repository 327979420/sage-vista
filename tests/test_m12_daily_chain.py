"""Local synthetic original 3.x inputs, never real acquisition evidence."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import unittest

from services.contracts.validation import ContractError
from services.execution import produce_trade_plans
from services.factors import produce_technical_evidence, produce_support_evidence
from services.ledger import produce_event_ledger_batch, produce_trade_plan_links
from services.publication.daily_chain import produce_daily_chain
from services.ranking import build_authority_activation
from tests import test_m07_ranking as fixtures
from tests.test_m03_gates import GENERATED_AT
from tests.test_m06_context import price_rows
from tests.test_market_data_consumers import (
    DAY, complete_gate_rows, forward_member, forward_snapshot, legacy_snapshot,
    qualification,
)


class DailyChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse registry/reader fixtures only: the new chain runs real default
        # detectors, not the older fixture's available=True detector override.
        fixture = fixtures.M07RankingTests()
        fixture.setUp()
        cls.member = forward_member('AAA')
        cls.etf_member = forward_member('QQQ')
        cls.inputs = dict(
            as_of=DAY,
            stock_snapshots=[forward_snapshot(members=[cls.member])],
            etf_snapshots=[forward_snapshot(members=[cls.etf_member])],
            stock_reader=fixtures.reader_map({cls.member['instrument_id']: complete_gate_rows()}),
            etf_reader=fixtures.reader_map({cls.etf_member['instrument_id']: price_rows()}),
            data_source={'provider': 'fixture', 'dataset': 'adjusted-daily', 'market': 'US'},
            etf_registry=fixture.registry, membership_registry=fixture.memberships,
            activation=build_authority_activation(effective_from=DAY, approval_ref='synthetic-local-only'),
            generated_at=GENERATED_AT, scan_batch_id='m12-local-synthetic',
        )
        cls.result = produce_daily_chain(**cls.inputs)

    def test_original_default_evidence_and_ledger_are_unchanged(self):
        result = self.result
        shared = dict(gate_events=result.gates.events, generated_at=GENERATED_AT)
        self.assertEqual(result.technical, produce_technical_evidence(result.stock, **shared))
        self.assertEqual(result.support, produce_support_evidence(
            result.stock, technical_evidence=result.technical, **shared))
        self.assertEqual(result.events, produce_event_ledger_batch(
            technical_evidence=result.technical, model_assessments=result.models,
            contexts=result.context, ranking_snapshot=result.ranking.snapshot, **shared))
        self.assertEqual(result.plans, produce_trade_plans(
            result.ranking.snapshot, result.support, entry_reads={}, generated_at=GENERATED_AT))
        self.assertEqual(result.plan_links, produce_trade_plan_links(
            result.events, result.plans, generated_at=GENERATED_AT))
        self.assertEqual(len(result.plans.plans), 0)
        self.assertTrue(any(not item['available'] for item in result.technical.evidence))

    def test_retry_same_originals_keeps_all_ids_and_contents(self):
        self.assertEqual(self.result, produce_daily_chain(**self.inputs))
        with self.assertRaises(FrozenInstanceError):
            self.result.events = None
        with self.assertRaises(TypeError):
            self.result.ranking.snapshot['selected_entries'] = []

    def test_no_detector_policy_or_future_entry_override(self):
        for key in ('detector', 'ranking_policy', 'entry_reads'):
            with self.subTest(key=key), self.assertRaises(TypeError):
                produce_daily_chain(**{**self.inputs, key: {}})

    def test_original_validator_rejects_missing_tampered_and_legacy_sources(self):
        tampered = deepcopy(self.inputs['stock_snapshots'][0])
        tampered['membership_evidence']['complete'] = False
        for snapshots in ([], [tampered], [legacy_snapshot()]):
            with self.subTest(snapshots=snapshots), self.assertRaises(ContractError):
                produce_daily_chain(**{**self.inputs, 'stock_snapshots': snapshots})

    def test_missing_market_snapshot_is_not_a_fake_empty_ranking(self):
        excluded = forward_snapshot(members=[self.member], qualifications=[
            qualification(self.member['instrument_id'], eligible=False)])
        with self.assertRaisesRegex(ContractError, 'original M02 market snapshots'):
            produce_daily_chain(**{**self.inputs, 'stock_snapshots': [excluded]})

    def test_complete_prices_with_no_gate_produce_valid_empty_day(self):
        result = produce_daily_chain(**{**self.inputs, 'stock_reader': fixtures.reader_map({
            self.member['instrument_id']: price_rows()})})
        self.assertEqual(len(result.gates.events), 0)
        self.assertEqual(len(result.events.events), 0)
        self.assertEqual(len(result.ranking.snapshot['ranked_entries']), 0)
        self.assertEqual(result.plan_links, ())

    def test_missing_authority_is_rejected_by_original_m07(self):
        with self.assertRaises(ContractError):
            produce_daily_chain(**{**self.inputs, 'activation': None})
