from __future__ import annotations

from dataclasses import replace
import itertools
import json
from pathlib import Path
import tempfile
import unittest

from services.context import produce_market_industry_context
from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError, validate_contract
from services.factors import produce_technical_evidence
from services.gates import produce_gate_batch
from services.market_data import RepositoryRead, prepare_shadow_consumer_input
from services.ranking import (
    RankingSnapshotStore,
    adapt_legacy_ranking_bytes,
    build_authority_activation,
    build_policy,
    produce_ranking_snapshot,
    produce_score_results,
    produce_versioned_ranking,
    validate_ranking_snapshot,
    validate_score_result,
)
from services.scanner.factor_detectors import evaluate_all_factors
from services.scanner.factor_snapshot import build_shadow_versioned_ranking
from services.scanner.unified_v2_scan import _present, _resonance_summary, shadow_versioned_ranking
from services.selectors import produce_model_assessments
from tests.test_m03_gates import GENERATED_AT
from tests.test_m06_context import price_rows
from tests.test_market_data_consumers import DAY, complete_gate_rows, forward_member, forward_snapshot


ROOT = Path(__file__).resolve().parents[1]


def reader_map(rows_by_id):
    def read(instrument_id, *, as_of):
        rows = tuple(row for row in rows_by_id[instrument_id] if row["date"] <= as_of)
        return RepositoryRead(
            instrument_id=instrument_id,
            as_of=as_of,
            rows=rows,
            point_in_time_fingerprint=canonical_fingerprint(list(rows)),
        )

    return read


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


class M07RankingTests(unittest.TestCase):
    def setUp(self):
        self.members = [forward_member(symbol) for symbol in ("AAA", "BBB", "CCC")]
        snapshot = forward_snapshot(members=self.members)
        stock_rows = {item["instrument_id"]: complete_gate_rows() for item in self.members}
        self.stock = prepare_shadow_consumer_input(
            consumer="factor_snapshot",
            mode="formal",
            as_of=DAY,
            snapshots=[snapshot],
            reader=reader_map(stock_rows),
            generated_at=f"{DAY}T23:05:00Z",
            data_source={"provider": "fixture", "dataset": "adjusted-daily", "market": "US"},
        )
        gates = produce_gate_batch(
            self.stock,
            generated_at=GENERATED_AT,
            scan_batch_id="m07-fixture",
        )
        self.events = gates.events
        def complete_detector(rows, as_of, *, fact_references):
            return [
                replace(state, available=True)
                for state in evaluate_all_factors(rows, as_of, fact_references=fact_references)
            ]

        self.evidence = produce_technical_evidence(
            self.stock,
            gate_events=self.events,
            generated_at=GENERATED_AT,
            detector=complete_detector,
        )
        self.assessments = produce_model_assessments(
            self.stock,
            gate_events=self.events,
            technical_evidence=self.evidence,
            generated_at=GENERATED_AT,
        )
        etf_member = forward_member("QQQ")
        etf_snapshot = forward_snapshot(members=[etf_member])
        self.etf = prepare_shadow_consumer_input(
            consumer="market_etf",
            mode="formal",
            as_of=DAY,
            snapshots=[etf_snapshot],
            reader=reader_map({etf_member["instrument_id"]: price_rows()}),
            generated_at=f"{DAY}T23:05:00Z",
            data_source={"provider": "fixture", "dataset": "adjusted-daily", "market": "US"},
        )
        self.registry = {
            "schema_version": "1.0.0",
            "registry_version": "m07-etf-fixture-1.0.0",
            "as_of_date": DAY,
            "etfs": [{
                "symbol": "QQQ",
                "etf_id": "etf:sha256:" + "1" * 64,
                "category": "broad_market",
                "label": "nasdaq_100",
                "issuer": "fixture issuer",
                "membership_source_url": "https://example.test/QQQ",
                "membership_as_of_date": DAY,
                "formal_current_forward_eligible": True,
                "historical_membership_evidence": "stable_instrument_id",
            }],
        }
        self.memberships = {
            "schema_version": "1.0.0",
            "mapping_registry_version": "m07-membership-fixture-1.0.0",
            "snapshots": [],
        }
        self.contexts = produce_market_industry_context(
            self.stock,
            self.etf,
            gate_events=self.events,
            technical_evidence=self.evidence,
            model_assessments=self.assessments,
            etf_registry=self.registry,
            membership_registry=self.memberships,
            generated_at=GENERATED_AT,
        )

    def produce(self, **changes):
        values = {
            "gate_events": self.events,
            "technical_evidence": self.evidence,
            "model_assessments": self.assessments,
            "contexts": self.contexts,
            "generated_at": GENERATED_AT,
        }
        values.update(changes)
        return produce_versioned_ranking(**values)

    def test_v1_reproduces_existing_technical_resonance_without_context_points(self):
        run = self.produce()
        evidence_by_event = {}
        for item in self.evidence.evidence:
            legacy_state = {
                "factor_id": item["factor_id"],
                "hit": item["raw_hit"],
                "recent_hit": item["recent_hit"],
            }
            if _present(legacy_state):
                evidence_by_event.setdefault(item["gate_event_id"], set()).add(item["factor_id"])
        for result in run.score_batch.results:
            old = _resonance_summary(evidence_by_event[result["gate_event_id"]])
            self.assertEqual(result["total_score"], old["technical_resonance_score"])
            self.assertEqual(result["metrics"]["positive_hit_count"], old["positive_hit_count"])
            self.assertEqual(result["metrics"]["family_count"], old["family_count"])
            self.assertEqual(result["metrics"]["parent_child_confirmation_bonus"], old["parent_child_confirmation_bonus"])
            self.assertEqual(result["metrics"]["timeframe_resonance_bonus"], old["timeframe_resonance_bonus"])
            self.assertEqual(result["context_reference"]["score_contribution"], 0)

    def test_recent_hit_compatibility_matches_the_existing_ranker(self):
        recent_id = "volume.bottom_expansion"

        def detector(rows, as_of, *, fact_references):
            states = evaluate_all_factors(rows, as_of, fact_references=fact_references)
            return [
                replace(state, available=True, hit=False, recent_hit=True)
                if state.factor_id == recent_id
                else replace(state, available=True)
                for state in states
            ]

        evidence = produce_technical_evidence(
            self.stock,
            gate_events=self.events,
            generated_at=GENERATED_AT,
            detector=detector,
        )
        assessments = produce_model_assessments(
            self.stock,
            gate_events=self.events,
            technical_evidence=evidence,
            generated_at=GENERATED_AT,
        )
        contexts = produce_market_industry_context(
            self.stock,
            self.etf,
            gate_events=self.events,
            technical_evidence=evidence,
            model_assessments=assessments,
            etf_registry=self.registry,
            membership_registry=self.memberships,
            generated_at=GENERATED_AT,
        )
        run = self.produce(
            technical_evidence=evidence,
            model_assessments=assessments,
            contexts=contexts,
        )
        by_event = {}
        for item in evidence.evidence:
            state = {
                "factor_id": item["factor_id"],
                "hit": item["raw_hit"],
                "recent_hit": item["recent_hit"],
            }
            if _present(state):
                by_event.setdefault(item["gate_event_id"], set()).add(item["factor_id"])
        for result in run.score_batch.results:
            old = _resonance_summary(by_event[result["gate_event_id"]])
            self.assertIn(recent_id, old["positive_factor_ids"])
            self.assertEqual(result["total_score"], old["technical_resonance_score"])

    def test_only_complex_model_enters_one_deterministic_main_ranking(self):
        run = self.produce(gate_events=reversed(self.events))
        self.assertEqual(len(run.score_batch.results), len(self.events))
        self.assertEqual(len(run.snapshot["ranked_entries"]), len(self.events))
        expected = sorted(item["instrument_id"] for item in self.events)
        self.assertEqual([item["instrument_id"] for item in run.snapshot["ranked_entries"]], expected)
        for entry in run.snapshot["ranked_entries"]:
            self.assertEqual(entry["sort_key"][-1]["field"], "instrument_id")
        forbidden = {"trade_plan", "entry", "stop", "target", "mfe", "mae", "outcome", "human_review", "excel"}
        self.assertFalse(forbidden & all_keys(run.snapshot))

    def test_repeated_inputs_are_idempotent_and_daily_replay_are_same_source(self):
        first = self.produce()
        second = self.produce()
        daily = build_shadow_versioned_ranking(
            gate_events=self.events,
            technical_evidence=self.evidence,
            model_assessments=self.assessments,
            contexts=self.contexts,
            generated_at=GENERATED_AT,
        )
        replay = shadow_versioned_ranking(
            gate_events=self.events,
            technical_evidence=self.evidence,
            model_assessments=self.assessments,
            contexts=self.contexts,
            generated_at=GENERATED_AT,
        )
        self.assertEqual(first, second)
        self.assertEqual(daily, replay)

    def test_missing_facts_are_unavailable_and_never_ranked_as_zero(self):
        def detector(rows, as_of, *, fact_references):
            states = evaluate_all_factors(rows, as_of, fact_references=fact_references)
            return [
                replace(state, available=False, hit=False)
                if state.factor_id == "rsi.daily_14"
                else state
                for state in states
            ]

        evidence = produce_technical_evidence(
            self.stock,
            gate_events=self.events,
            generated_at=GENERATED_AT,
            detector=detector,
        )
        assessments = produce_model_assessments(
            self.stock,
            gate_events=self.events,
            technical_evidence=evidence,
            generated_at=GENERATED_AT,
        )
        contexts = produce_market_industry_context(
            self.stock,
            self.etf,
            gate_events=self.events,
            technical_evidence=evidence,
            model_assessments=assessments,
            etf_registry=self.registry,
            membership_registry=self.memberships,
            generated_at=GENERATED_AT,
        )
        run = self.produce(technical_evidence=evidence, model_assessments=assessments, contexts=contexts)
        self.assertTrue(all(item["status"] == "unavailable" for item in run.score_batch.results))
        self.assertTrue(all(item["total_score"] is None for item in run.score_batch.results))
        self.assertEqual(run.snapshot["ranked_entries"], ())
        self.assertEqual(len(run.snapshot["excluded_entries"]), len(self.events))

    def test_upstream_batch_references_must_match(self):
        changed = object.__new__(type(self.assessments))
        object.__setattr__(changed, "batch_id", "assessment-batch:sha256:" + "0" * 64)
        object.__setattr__(changed, "as_of", self.assessments.as_of)
        object.__setattr__(changed, "path_status", self.assessments.path_status)
        object.__setattr__(changed, "assessments", self.assessments.assessments)
        with self.assertRaises(ContractError):
            self.produce(model_assessments=changed)

    def test_authority_requires_explicit_effective_activation(self):
        scores = self.produce().score_batch
        activation = build_authority_activation(
            effective_from=DAY,
            approval_ref="CR-fixture-approved",
        )
        authoritative = produce_ranking_snapshot(
            scores,
            generated_at=GENERATED_AT,
            ranking_role="authoritative",
            activation=activation,
        )
        self.assertEqual(authoritative["ranking_role"], "authoritative")

    def test_new_policy_before_effective_date_is_comparison_only(self):
        score_v2 = build_policy(
            kind="score",
            version="1.1.0",
            name="approved-future-fixture",
            rules=dict(self._policy_rules("score")),
        )
        ranking_v2 = build_policy(
            kind="ranking",
            version="1.1.0",
            name="approved-future-ranking-fixture",
            rules={**dict(self._policy_rules("ranking")), "accepted_score_policy_version": "1.1.0"},
        )
        scores = produce_score_results(
            gate_events=self.events,
            technical_evidence=self.evidence,
            model_assessments=self.assessments,
            contexts=self.contexts,
            generated_at=GENERATED_AT,
            score_policy=score_v2,
        )
        comparison = produce_ranking_snapshot(
            scores,
            generated_at=GENERATED_AT,
            ranking_role="comparison",
            comparison_to_snapshot_id=self.produce().snapshot["ranking_snapshot_id"],
            ranking_policy=ranking_v2,
        )
        self.assertEqual(comparison["ranking_role"], "comparison")
        self.assertNotEqual(comparison["ranking_snapshot_id"], self.produce().snapshot["ranking_snapshot_id"])
        activation = build_authority_activation(
            effective_from="2026-09-02",
            approval_ref="future-only",
            score_policy=score_v2,
            ranking_policy=ranking_v2,
        )
        with self.assertRaisesRegex(ContractError, "before"):
            produce_ranking_snapshot(
                scores,
                generated_at=GENERATED_AT,
                ranking_role="authoritative",
                activation=activation,
                ranking_policy=ranking_v2,
            )

    def _policy_rules(self, kind):
        from services.ranking import RANKING_POLICY, SCORE_POLICY

        return (SCORE_POLICY if kind == "score" else RANKING_POLICY)["rules"]

    def test_content_tampering_and_unknown_major_fail_closed(self):
        result = dict(self.produce().score_batch.results[0])
        result["total_score"] += 1
        with self.assertRaises(ContractError):
            validate_score_result(result)
        snapshot = dict(self.produce().snapshot)
        snapshot["ranked_entries"] = list(reversed(snapshot["ranked_entries"]))
        with self.assertRaises(ContractError):
            validate_ranking_snapshot(snapshot)
        old = dict(self.produce().score_batch.results[0])
        old["schema_version"] = "3.0.0"
        with self.assertRaises(ContractError):
            validate_contract("ScoreResult", old)

    def test_append_only_store_keeps_old_versions_and_rejects_authority_collision(self):
        shadow = self.produce().snapshot
        activation = build_authority_activation(effective_from=DAY, approval_ref="approved")
        authoritative = produce_ranking_snapshot(
            self.produce().score_batch,
            generated_at=GENERATED_AT,
            ranking_role="authoritative",
            activation=activation,
        )
        with tempfile.TemporaryDirectory() as folder:
            store = RankingSnapshotStore(folder)
            first = store.write(shadow)
            before = first.read_bytes()
            self.assertEqual(store.write(shadow), first)
            self.assertEqual(first.read_bytes(), before)
            store.write(authoritative)
            conflicting_activation = build_authority_activation(
                effective_from=DAY,
                approval_ref="different-approval",
            )
            conflicting = produce_ranking_snapshot(
                self.produce().score_batch,
                generated_at=GENERATED_AT,
                ranking_role="authoritative",
                activation=conflicting_activation,
            )
            with self.assertRaisesRegex(ContractError, "authoritative ranking"):
                store.write(conflicting)

    def test_legacy_archive_is_read_only_and_cannot_become_formal(self):
        raw = b'{"days":[{"date":"2026-08-28","ranking":[]}]}\n'
        before = bytes(raw)
        archive = adapt_legacy_ranking_bytes(raw)
        self.assertEqual(raw, before)
        self.assertEqual(archive.path_status, "legacy")
        with self.assertRaises(ContractError):
            validate_ranking_snapshot(archive.payload)

    def test_input_order_does_not_change_snapshot(self):
        expected = self.produce().snapshot
        for order in itertools.permutations(self.events):
            self.assertEqual(self.produce(gate_events=order).snapshot, expected)

    def test_only_ranking_package_creates_formal_score_and_ranking_identities(self):
        score_marker = 'payload["score_result_id"] = "score:" + canonical_fingerprint'
        ranking_marker = 'payload["ranking_snapshot_id"] = "ranking:" + canonical_fingerprint'
        score_creators = {
            str(path.relative_to(ROOT))
            for path in (ROOT / "services").rglob("*.py")
            if score_marker in path.read_text()
        }
        ranking_creators = {
            str(path.relative_to(ROOT))
            for path in (ROOT / "services").rglob("*.py")
            if ranking_marker in path.read_text()
        }
        self.assertEqual(score_creators, {"services/ranking/producer.py"})
        self.assertEqual(ranking_creators, {"services/ranking/producer.py"})
        ranking_text = "\n".join(
            path.read_text() for path in (ROOT / "services/ranking").glob("*.py")
        )
        for forbidden in (
            "produce_gate_batch(",
            "produce_technical_evidence(",
            "produce_model_assessments(",
            "produce_market_industry_context(",
            "evaluate_all_factors(",
            "evaluate_etf_state(",
        ):
            self.assertNotIn(forbidden, ranking_text)


if __name__ == "__main__":
    unittest.main()
