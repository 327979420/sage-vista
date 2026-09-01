from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError, validate_contract
from services.context import produce_market_industry_context
from services.execution import produce_trade_plans, validate_trade_plan_batch
from services.factors import produce_support_evidence, produce_technical_evidence
from services.ledger import (
    EventLedgerStore,
    adapt_legacy_opportunity_ledger,
    adapt_legacy_signal_history,
    create_human_review,
    produce_event_ledger_batch,
    produce_ranking_revision_link,
    produce_trade_plan_links,
    query_events,
    ranking_exclusion_subjects,
    reconcile_legacy_ledgers,
    validate_event_ledger_batch,
    validate_human_review,
    validate_machine_link,
    validate_opportunity_event,
)
from services.market_data import RepositoryRead
from services.ranking import (
    RANKING_POLICY,
    build_authority_activation,
    build_policy,
    produce_ranking_snapshot,
)
from services.scanner.factor_snapshot import build_shadow_event_ledger
from services.scanner.factor_detectors import evaluate_all_factors
from services.scanner.unified_v2_scan import shadow_event_ledger
from services.selectors import produce_model_assessments, validate_model_assessment_batch
from tests import test_m07_ranking as m07_fixtures
from tests.test_m03_gates import GENERATED_AT
from tests.test_market_data_consumers import DAY, complete_gate_rows


ROOT = Path(__file__).resolve().parents[1]
ENTRY_DAY = "2026-09-02"
ENTRY_GENERATED_AT = f"{ENTRY_DAY}T23:00:00Z"


def plain(value):
    if hasattr(value, "items"):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def all_keys(value):
    keys = set()
    if hasattr(value, "items"):
        for key, item in value.items():
            keys.add(str(key))
            keys.update(all_keys(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys.update(all_keys(item))
    return keys


class M09LedgerTests(unittest.TestCase):
    def setUp(self):
        upstream = m07_fixtures.M07RankingTests(
            "test_v1_reproduces_existing_technical_resonance_without_context_points"
        )
        upstream.setUp()
        self.upstream = upstream
        shadow = upstream.produce()
        rules = plain(RANKING_POLICY["rules"])
        rules["selected_limit"] = 1
        self.ranking_policy = build_policy(
            kind="ranking",
            version="1.0.1",
            name="m09_one_selected_fixture",
            rules=rules,
        )
        activation = build_authority_activation(
            effective_from=DAY,
            approval_ref="CR-M09-fixture-approved",
            ranking_policy=self.ranking_policy,
        )
        self.ranking = produce_ranking_snapshot(
            shadow.score_batch,
            generated_at=GENERATED_AT,
            ranking_role="authoritative",
            activation=activation,
            ranking_policy=self.ranking_policy,
        )
        self.batch = self.produce()
        self.support = produce_support_evidence(
            upstream.stock,
            gate_events=upstream.events,
            technical_evidence=upstream.evidence,
            generated_at=GENERATED_AT,
        )

    def produce(self, **changes):
        values = {
            "gate_events": self.upstream.events,
            "technical_evidence": self.upstream.evidence,
            "model_assessments": self.upstream.assessments,
            "contexts": self.upstream.contexts,
            "ranking_snapshot": self.ranking,
            "generated_at": GENERATED_AT,
        }
        values.update(changes)
        return produce_event_ledger_batch(**values)

    def entry_reads(self):
        reads = {}
        for member in self.upstream.members:
            rows = [dict(row) for row in complete_gate_rows()]
            rows.append({
                "date": ENTRY_DAY,
                "open": 100.0,
                "high": 104.0,
                "low": 96.0,
                "close": 101.0,
                "volume": 1_000_000,
            })
            reads[member["instrument_id"]] = RepositoryRead(
                instrument_id=member["instrument_id"],
                as_of=ENTRY_DAY,
                rows=tuple(rows),
                point_in_time_fingerprint=canonical_fingerprint(rows),
            )
        return reads

    def test_all_authoritative_ranked_entries_create_one_root(self):
        self.assertEqual(len(self.batch.events), len(self.ranking["ranked_entries"]))
        self.assertEqual(
            {item["instrument_id"] for item in self.batch.events},
            {item["instrument_id"] for item in self.ranking["ranked_entries"]},
        )
        self.assertEqual(sum(item["selected"] for item in self.batch.events), 1)
        self.assertEqual(len({item["event_id"] for item in self.batch.events}), len(self.batch.events))
        for event in self.batch.events:
            validate_contract("OpportunityEvent", event)
            self.assertEqual(event["event_role"], "authoritative")
            self.assertEqual(len(event["model_assessments"]["items"]), 2)

    def test_shadow_and_comparison_cannot_masquerade_as_authoritative_events(self):
        shadow = self.upstream.produce().snapshot
        with self.assertRaisesRegex(ContractError, "authoritative"):
            self.produce(ranking_snapshot=shadow)
        comparison = plain(shadow)
        comparison["ranking_role"] = "comparison"
        comparison["comparison_to_snapshot_id"] = self.ranking["ranking_snapshot_id"]
        # Use M07 itself to construct a valid comparison rather than hand-waving its identity.
        valid_comparison = produce_ranking_snapshot(
            self.upstream.produce().score_batch,
            generated_at=GENERATED_AT,
            ranking_role="comparison",
            comparison_to_snapshot_id=self.ranking["ranking_snapshot_id"],
        )
        with self.assertRaisesRegex(ContractError, "authoritative"):
            self.produce(ranking_snapshot=valid_comparison)

    def test_complete_references_are_bound_and_tampered_batches_fail(self):
        event = self.batch.events[0]
        self.assertEqual(event["input_identity"]["technical_evidence_batch_id"], self.upstream.evidence.batch_id)
        self.assertEqual(event["input_identity"]["model_assessment_batch_id"], self.upstream.assessments.batch_id)
        self.assertEqual(event["input_identity"]["context_batch_id"], self.upstream.contexts.batch_id)
        changed = replace(self.upstream.assessments, batch_id="model-assessment-batch:sha256:" + "0" * 64)
        with self.assertRaises(ContractError):
            self.produce(model_assessments=changed)
        changed_assessments = list(self.upstream.assessments.assessments)
        changed_item = plain(changed_assessments[0])
        changed_item["warnings"] = ["tampered"]
        changed_assessments[0] = changed_item
        changed = replace(self.upstream.assessments, assessments=tuple(changed_assessments))
        with self.assertRaises(ContractError):
            self.produce(model_assessments=changed)

    def test_repeated_and_reordered_inputs_are_idempotent(self):
        reordered = self.produce(gate_events=reversed(self.upstream.events))
        self.assertEqual(self.batch, self.produce())
        self.assertEqual(self.batch, reordered)
        validate_event_ledger_batch(self.batch)

    def test_same_root_different_content_conflicts_in_append_only_store(self):
        event = plain(self.batch.events[0])
        changed = plain(event)
        changed["frozen_ranking"]["warnings"] = ["later text"]
        changed["event_content_fingerprint"] = canonical_fingerprint({
            key: value for key, value in changed.items()
            if key not in {"generated_at", "event_content_fingerprint"}
        })
        validate_opportunity_event(changed)
        with tempfile.TemporaryDirectory() as folder:
            store = EventLedgerStore(folder)
            path = store.write_event(event)
            before = path.read_bytes()
            self.assertEqual(store.write_event(event), path)
            with self.assertRaisesRegex(ContractError, "different content"):
                store.write_event(changed)
            self.assertEqual(path.read_bytes(), before)

    def test_later_ranking_evidence_is_a_link_not_a_second_root(self):
        event = self.batch.events[0]
        revision_policy = build_policy(
            kind="ranking",
            version="1.0.2",
            name="m09_later_approved_ranking_fixture",
            rules=plain(self.ranking_policy["rules"]),
        )
        activation = build_authority_activation(
            effective_from=DAY,
            approval_ref="CR-M09-later-ranking-fixture",
            ranking_policy=revision_policy,
        )
        revised_ranking = produce_ranking_snapshot(
            self.upstream.produce().score_batch,
            generated_at=GENERATED_AT,
            ranking_role="authoritative",
            activation=activation,
            ranking_policy=revision_policy,
        )
        link = produce_ranking_revision_link(
            event,
            gate_events=self.upstream.events,
            technical_evidence=self.upstream.evidence,
            model_assessments=self.upstream.assessments,
            contexts=self.upstream.contexts,
            ranking_snapshot=revised_ranking,
            generated_at="2026-09-02T11:00:00Z",
        )
        self.assertEqual(link["event_id"], event["event_id"])
        self.assertEqual(link["link_type"], "ranking_evidence_revision")
        self.assertEqual(link["source_reference"]["ranking_snapshot_id"], revised_ranking["ranking_snapshot_id"])
        validate_machine_link(link)

    def test_event_exists_before_next_open_and_m08_links_append_later(self):
        unavailable = produce_trade_plans(
            self.ranking,
            self.support,
            entry_reads={},
            generated_at=ENTRY_GENERATED_AT,
        )
        unavailable_links = produce_trade_plan_links(
            self.batch, unavailable, generated_at=ENTRY_GENERATED_AT
        )
        self.assertEqual(len(unavailable_links), len(self.batch.events))
        self.assertIn("next_adjusted_open_unavailable", {item["reason"] for item in unavailable_links})
        complete = produce_trade_plans(
            self.ranking,
            self.support,
            entry_reads=self.entry_reads(),
            generated_at=ENTRY_GENERATED_AT,
        )
        validate_trade_plan_batch(complete)
        links = produce_trade_plan_links(self.batch, complete, generated_at=ENTRY_GENERATED_AT)
        self.assertEqual(len(links), len(self.batch.events))
        self.assertEqual([item["status"] for item in links].count("created"), 1)
        self.assertEqual([item["status"] for item in links].count("not_created"), 2)
        self.assertEqual(
            {item["reason"] for item in links if item["status"] == "not_created"},
            {"not_selected_for_plan"},
        )
        self.assertEqual(self.batch, self.produce())

    def test_machine_link_is_immutable_and_store_rejects_production_paths(self):
        plan_batch = produce_trade_plans(
            self.ranking,
            self.support,
            entry_reads=self.entry_reads(),
            generated_at=ENTRY_GENERATED_AT,
        )
        link = produce_trade_plan_links(self.batch, plan_batch, generated_at=ENTRY_GENERATED_AT)[0]
        validate_machine_link(link)
        tampered = plain(link)
        tampered["source_reference"]["score_result_id"] = "score:sha256:" + "0" * 64
        tampered["link_content_fingerprint"] = canonical_fingerprint({
            key: value for key, value in tampered.items()
            if key not in {"generated_at", "link_content_fingerprint"}
        })
        with self.assertRaises(ContractError):
            validate_machine_link(tampered)
        with tempfile.TemporaryDirectory() as folder:
            store = EventLedgerStore(folder)
            with self.assertRaisesRegex(ContractError, "before its event root"):
                store.write_machine_link(link)
            event_path = store.write_event(self.batch.events[0])
            crossed = plain(link)
            crossed["instrument_id"] = self.batch.events[1]["instrument_id"]
            crossed["source_reference"]["ranking_snapshot_id"] = "ranking:sha256:" + "0" * 64
            crossed["link_content_fingerprint"] = canonical_fingerprint({
                key: value for key, value in crossed.items()
                if key not in {"generated_at", "link_content_fingerprint"}
            })
            validate_machine_link(crossed)
            with self.assertRaisesRegex(ContractError, "stored event root"):
                store.write_machine_link(crossed)
            link_path = store.write_machine_link(link)
            self.assertEqual(store.write_machine_link(link), link_path)
            self.assertTrue(event_path.exists() and link_path.exists())
        with self.assertRaises(ContractError):
            EventLedgerStore(ROOT / "public", workspace_root=ROOT)

    def test_human_reviews_append_without_mutating_machine_event(self):
        event = self.batch.events[0]
        before = json.dumps(plain(event), sort_keys=True)
        observation = create_human_review(
            subject_type="event",
            subject_reference={"event_id": event["event_id"]},
            review_type="observation",
            author_id="author:human-reviewer-001",
            authored_at="2026-09-02T09:00:00Z",
            body="可能是误收，保留机器原证据。",
            tags=["误收"],
            known_event_ids={event["event_id"]},
        )
        correction = create_human_review(
            subject_type="event",
            subject_reference={"event_id": event["event_id"]},
            review_type="hypothesis",
            author_id="author:human-reviewer-001",
            authored_at="2026-09-02T10:00:00Z",
            body="候选假设，等待独立验证。",
            supersedes_review=observation,
            known_event_ids={event["event_id"]},
        )
        self.assertNotEqual(observation["review_id"], correction["review_id"])
        self.assertEqual(correction["supersedes_review_id"], observation["review_id"])
        self.assertEqual(before, json.dumps(plain(event), sort_keys=True))
        with tempfile.TemporaryDirectory() as folder:
            store = EventLedgerStore(folder)
            store.write_event(event)
            first = store.write_human_review(observation)
            second = store.write_human_review(correction)
            self.assertNotEqual(first, second)

    def test_author_and_approved_change_evidence_are_mandatory(self):
        subject = {"event_id": self.batch.events[0]["event_id"]}
        with self.assertRaises(ContractError):
            create_human_review(
                subject_type="event",
                subject_reference=subject,
                review_type="observation",
                author_id="",
                authored_at="2026-09-02T09:00:00Z",
                body="text",
                known_event_ids={self.batch.events[0]["event_id"]},
            )
        with self.assertRaises(ContractError):
            create_human_review(
                subject_type="event",
                subject_reference=subject,
                review_type="approved_change",
                author_id="author:001",
                authored_at="2026-09-02T09:00:00Z",
                body="intent only",
                known_event_ids={self.batch.events[0]["event_id"]},
                known_approval_refs={"CR-real-approved-intent"},
            )
        approved = create_human_review(
            subject_type="event",
            subject_reference=subject,
            review_type="approved_change",
            author_id="author:001",
            authored_at="2026-09-02T09:00:00Z",
            body="批准变更意图；尚未实现。",
            approval_ref="CR-fixture-approved-intent",
            known_event_ids={self.batch.events[0]["event_id"]},
            known_approval_refs={"CR-fixture-approved-intent"},
        )
        validate_human_review(
            approved,
            known_event_ids={self.batch.events[0]["event_id"]},
            known_approval_refs={"CR-fixture-approved-intent"},
            require_known_subject=True,
        )

    def test_excluded_entry_can_be_reviewed_but_never_becomes_event(self):
        def missing_detector(rows, as_of, *, fact_references):
            return [
                replace(state, available=False, hit=False)
                if state.factor_id == "rsi.daily_14"
                else state
                for state in evaluate_all_factors(
                    rows, as_of, fact_references=fact_references
                )
            ]

        evidence = produce_technical_evidence(
            self.upstream.stock,
            gate_events=self.upstream.events,
            generated_at=GENERATED_AT,
            detector=missing_detector,
        )
        assessments = produce_model_assessments(
            self.upstream.stock,
            gate_events=self.upstream.events,
            technical_evidence=evidence,
            generated_at=GENERATED_AT,
        )
        contexts = produce_market_industry_context(
            self.upstream.stock,
            self.upstream.etf,
            gate_events=self.upstream.events,
            technical_evidence=evidence,
            model_assessments=assessments,
            etf_registry=self.upstream.registry,
            membership_registry=self.upstream.memberships,
            generated_at=GENERATED_AT,
        )
        run = self.upstream.produce(
            technical_evidence=evidence,
            model_assessments=assessments,
            contexts=contexts,
        )
        activation = build_authority_activation(
            effective_from=DAY,
            approval_ref="CR-M09-exclusion-fixture",
            ranking_policy=self.ranking_policy,
        )
        ranking = produce_ranking_snapshot(
            run.score_batch,
            generated_at=GENERATED_AT,
            ranking_role="authoritative",
            activation=activation,
            ranking_policy=self.ranking_policy,
        )
        subjects = ranking_exclusion_subjects(ranking)
        self.assertEqual(len(subjects), len(ranking["excluded_entries"]))
        self.assertEqual(ranking["ranked_entries"], ())
        empty_batch = produce_event_ledger_batch(
            gate_events=self.upstream.events,
            technical_evidence=evidence,
            model_assessments=assessments,
            contexts=contexts,
            ranking_snapshot=ranking,
            generated_at=GENERATED_AT,
        )
        self.assertEqual(empty_batch.events, ())
        subject = next(iter(subjects))
        review = create_human_review(
            subject_type="ranking_exclusion",
            subject_reference={
                "ranking_snapshot_id": subject[0],
                "score_result_id": subject[1],
            },
            review_type="observation",
            author_id="author:001",
            authored_at="2026-09-02T09:00:00Z",
            body="漏检候选，仅作人工观察。",
            known_ranking_exclusions=subjects,
        )
        self.assertEqual(review["subject_type"], "ranking_exclusion")
        self.assertNotIn("event_id", review["subject_reference"])

    def test_daily_and_replay_use_the_same_m09_producer(self):
        arguments = {
            "gate_events": self.upstream.events,
            "technical_evidence": self.upstream.evidence,
            "model_assessments": self.upstream.assessments,
            "contexts": self.upstream.contexts,
            "ranking_snapshot": self.ranking,
            "generated_at": GENERATED_AT,
        }
        daily = build_shadow_event_ledger(**arguments)
        replay = shadow_event_ledger(**arguments)
        self.assertEqual(daily, replay)
        self.assertEqual(daily, self.batch)

    def test_query_is_a_disposable_view_not_a_second_ledger(self):
        event = self.batch.events[0]
        result = query_events(
            self.batch.events,
            instrument_id=event["instrument_id"],
            date_from=DAY,
            date_to=DAY,
            selected=event["selected"],
            rank=event["rank"],
            score_policy_version=self.ranking["score_policy_version"],
        )
        self.assertEqual(result, (event,))

    def test_legacy_ledgers_remain_bytes_exact_and_ticker_date_is_ambiguous(self):
        opportunity_raw = json.dumps({
            "schema_version": "1.0.0",
            "as_of": DAY,
            "events": [{"event_id": "op-1", "symbol": "AAA", "signal_date": DAY}],
        }, sort_keys=True).encode()
        signal_raw = json.dumps({
            "signal_schema_version": "1.0.0",
            "as_of": DAY,
            "cases": [{"signal_id": "different-1", "symbol": "AAA", "first_seen_date": DAY}],
        }, sort_keys=True).encode()
        opportunity = adapt_legacy_opportunity_ledger(opportunity_raw)
        signal = adapt_legacy_signal_history(signal_raw)
        report = reconcile_legacy_ledgers(opportunity, signal)
        self.assertEqual(opportunity.source_bytes, opportunity_raw)
        self.assertEqual(signal.source_bytes, signal_raw)
        self.assertEqual(report.classification_counts["ambiguous"], 1)
        self.assertEqual(report.formal_records_created, 0)
        self.assertTrue(all(not item.formal_eligible for item in (*opportunity.records, *signal.records)))

    def test_current_legacy_samples_adapt_without_writing_or_formal_promotion(self):
        opportunity_path = ROOT / "public/opportunity-ledger.json"
        signal_path = ROOT / "public/signal-history.json"
        opportunity_raw = opportunity_path.read_bytes()
        signal_raw = signal_path.read_bytes()
        opportunity = adapt_legacy_opportunity_ledger(opportunity_raw)
        signal = adapt_legacy_signal_history(signal_raw)
        report = reconcile_legacy_ledgers(opportunity, signal)
        self.assertEqual((opportunity.record_count, signal.record_count), (4451, 69))
        self.assertEqual(report.formal_records_created, 0)
        self.assertGreater(report.classification_counts["ambiguous"], 0)
        self.assertEqual(opportunity_path.read_bytes(), opportunity_raw)
        self.assertEqual(signal_path.read_bytes(), signal_raw)

    def test_m09_outputs_do_not_contain_m10_or_production_fields(self):
        forbidden = {
            "return", "returns", "return_pct", "r_return", "mfe", "mae",
            "forward_outcome", "win_rate", "profit_factor", "excel",
            "website", "discord", "manifest",
        }
        self.assertFalse(forbidden & all_keys(self.batch.events))

    def test_legacy_opportunity_event_1x_stays_legacy_only(self):
        legacy = {
            "schema_version": "1.0.0",
            "as_of": DAY,
            "generated_at": GENERATED_AT,
            "source_version": {"legacy": "fixture"},
            "future_data_used": False,
            "event_id": "event:AAA:2026-09-01",
            "symbol": "AAA",
            "signal_date": DAY,
            "gate_event_id": "gate:AAA:2026-09-01:legacy",
            "model_assessments": {},
        }
        validate_contract("OpportunityEvent", legacy)
        with self.assertRaises(ContractError):
            validate_opportunity_event(legacy)

    def test_model_and_plan_batch_validators_reject_content_under_old_id(self):
        validate_model_assessment_batch(self.upstream.assessments)
        plans = produce_trade_plans(
            self.ranking,
            self.support,
            entry_reads=self.entry_reads(),
            generated_at=ENTRY_GENERATED_AT,
        )
        changed_decisions = list(plans.decisions)
        changed = plain(changed_decisions[0])
        changed["reason"] = "tampered"
        changed_decisions[0] = changed
        with self.assertRaises(ContractError):
            validate_trade_plan_batch(replace(plans, decisions=tuple(changed_decisions)))

    def test_model_batch_rejects_two_valid_judgments_for_one_gate_and_model(self):
        original = next(
            plain(item)
            for item in self.upstream.assessments.assessments
            if item["model_id"] == "complex_multifactor"
        )
        duplicate = plain(original)
        duplicate["model_specific_facts"] = {"fixture_variant": "second-valid-record"}
        duplicate["model_specific_facts_fingerprint"] = canonical_fingerprint(
            duplicate["model_specific_facts"]
        )
        assessment_identity = {
            "gate_event_id": duplicate["gate_event_id"],
            "instrument_id": duplicate["instrument_id"],
            "as_of": duplicate["as_of"],
            "path_status": duplicate["path_status"],
            "input_identity": duplicate["input_identity"],
            "model_id": duplicate["model_id"],
            "model_version": duplicate["model_version"],
            "evidence_batch_id": duplicate["evidence_batch_id"],
            "technical_evidence_ids": duplicate["technical_evidence_ids"],
            "model_specific_facts_fingerprint": duplicate[
                "model_specific_facts_fingerprint"
            ],
        }
        duplicate["assessment_id"] = "assessment:" + canonical_fingerprint(
            assessment_identity
        )
        duplicate["assessment_content_fingerprint"] = canonical_fingerprint({
            key: value
            for key, value in duplicate.items()
            if key not in {"generated_at", "assessment_content_fingerprint"}
        })
        items = [plain(item) for item in self.upstream.assessments.assessments]
        items.append(duplicate)
        items.sort(key=lambda item: (item["instrument_id"], item["model_id"]))
        batch_identity = {
            "as_of": self.upstream.assessments.as_of,
            "path_status": self.upstream.assessments.path_status,
            "selector_policy": original["source_version"]["selector_policy"],
            "assessments": [
                {
                    "assessment_id": item["assessment_id"],
                    "content": item["assessment_content_fingerprint"],
                }
                for item in items
            ],
        }
        forged = replace(
            self.upstream.assessments,
            batch_id="model-assessment-batch:" + canonical_fingerprint(batch_identity),
            assessments=tuple(items),
        )
        with self.assertRaisesRegex(ContractError, "duplicate model assessments"):
            validate_model_assessment_batch(forged)


if __name__ == "__main__":
    unittest.main()
