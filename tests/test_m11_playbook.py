"""Fixed synthetic acceptance for the M11 strategy promotion gate."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import importlib
from pathlib import Path
import tempfile
import unittest

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError
from services.evaluation import EvaluationShadowStore, build_experiment_run_receipt, finalize_result
from services.ledger import EventLedgerStore, create_human_review
from services.playbook import (
    PlaybookShadowStore,
    assess_persisted_strategy_evidence,
    build_preregistration,
    current_strategy_assessment,
    current_strategy_lifecycle,
    derive_strategy_registry_snapshot,
    empty_current_registry,
    produce_strategy_proposal,
    record_evidence_assessment,
    record_main_implementation,
    record_production_activation,
    record_retirement,
    record_user_decision,
    register_strategy_proposal,
    validate_strategy_proposal,
    validate_strategy_registry_snapshot,
)
from tests.test_m10_evaluation_contracts import forward_2_1_values, plain, receipt_values


SHA = "sha256:" + "a" * 64


def proof(role: str, digit: str = "a") -> dict[str, str]:
    return {"id": f"{role}:sha256:{digit * 64}", "content_fingerprint": f"sha256:{digit * 64}"}


def resign_proposal(original, **changes):
    values = plain(original)
    for field in ("proposal_id", "proposal_content_fingerprint", "strategy_id"):
        values.pop(field, None)
    values.update(changes)
    return produce_strategy_proposal(**values)


class M11PlaybookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_type = importlib.import_module("tests.test_m09_ledger").M09LedgerTests
        fixture = fixture_type("test_all_authoritative_ranked_entries_create_one_root")
        fixture.setUp()
        cls.event = plain(fixture.batch.events[0])
        cls.baseline_event = plain(fixture.batch.events[1])
        cls.review = create_human_review(
            subject_type="event",
            subject_reference={"event_id": cls.event["event_id"]},
            review_type="hypothesis",
            author_id="author:synthetic-reviewer",
            authored_at="2026-09-05T09:00:00Z",
            body="Synthetic candidate only; no production claim.",
            known_event_ids={cls.event["event_id"]},
        )
        cls.review = plain(cls.review)

        dummy = finalize_result("ForwardOutcome", forward_2_1_values())
        pending_values = receipt_values(dummy)
        pending_values.update({
            "status": "pending", "result_refs": [], "finished_at": None,
            "partition_role": "validation", "supersedes_run_receipt_id": None,
            "input_refs": [
                {"id": cls.event["event_id"], "content_fingerprint": cls.event["event_content_fingerprint"]},
                proof("market", "b"), proof("universe", "c"),
            ],
        })
        cls.pending = plain(build_experiment_run_receipt(**pending_values))
        outcome_values = forward_2_1_values(mature=True)
        outcome_values.update({
            "run_id": cls.pending["run_id"], "event_id": cls.event["event_id"],
            "event_content_fingerprint": cls.event["event_content_fingerprint"],
            "instrument_id": cls.event["instrument_id"], "signal_date": cls.event["signal_date"],
            "partition_role": "validation",
        })
        cls.outcome = plain(finalize_result("ForwardOutcome", outcome_values))
        completed_values = {
            key: plain(value) for key, value in cls.pending.items()
            if key not in {"run_id", "run_receipt_id", "run_content_fingerprint", "input_set_fingerprint", "result_set_fingerprint"}
        }
        completed_values.update({
            "status": "completed",
            "result_refs": [{"id": cls.outcome["forward_outcome_id"], "content_fingerprint": cls.outcome["forward_content_fingerprint"]}],
            "finished_at": "2026-09-03T22:01:00Z",
            "supersedes_run_receipt_id": cls.pending["run_receipt_id"],
        })
        cls.completed = plain(build_experiment_run_receipt(**completed_values))

        baseline_pending_values = receipt_values(dummy)
        baseline_pending_values.update({
            "status": "pending", "result_refs": [], "finished_at": None,
            "partition_role": "validation", "supersedes_run_receipt_id": None,
            "attempt_id": "attempt-baseline", "experiment_id": "M11-baseline-fixture",
            "config_ref": {"config_id": "m11-baseline-fixed", "config_version": "0.9.0", "content_fingerprint": SHA},
            "input_refs": [
                {"id": cls.baseline_event["event_id"], "content_fingerprint": cls.baseline_event["event_content_fingerprint"]},
                proof("market", "b"), proof("universe", "c"),
            ],
        })
        cls.baseline_pending = plain(build_experiment_run_receipt(**baseline_pending_values))
        baseline_outcome_values = forward_2_1_values(mature=True)
        baseline_outcome_values.update({
            "run_id": cls.baseline_pending["run_id"], "event_id": cls.baseline_event["event_id"],
            "event_content_fingerprint": cls.baseline_event["event_content_fingerprint"],
            "instrument_id": cls.baseline_event["instrument_id"], "signal_date": cls.baseline_event["signal_date"],
            "partition_role": "validation",
        })
        cls.baseline_outcome = plain(finalize_result("ForwardOutcome", baseline_outcome_values))
        baseline_completed_values = {
            key: plain(value) for key, value in cls.baseline_pending.items()
            if key not in {"run_id", "run_receipt_id", "run_content_fingerprint", "input_set_fingerprint", "result_set_fingerprint"}
        }
        baseline_completed_values.update({
            "status": "completed",
            "result_refs": [{"id": cls.baseline_outcome["forward_outcome_id"], "content_fingerprint": cls.baseline_outcome["forward_content_fingerprint"]}],
            "finished_at": "2026-09-03T22:01:00Z",
            "supersedes_run_receipt_id": cls.baseline_pending["run_receipt_id"],
        })
        cls.baseline_completed = plain(build_experiment_run_receipt(**baseline_completed_values))
        cls.prereg = build_preregistration(
            required_partitions=["validation"],
            required_result_contracts=["ForwardOutcome"],
            requires_cost_policy=False,
            criteria=[{
                "criterion_id": "criterion-001-status-mature",
                "result_ref": {"id": cls.outcome["forward_outcome_id"], "content_fingerprint": cls.outcome["forward_content_fingerprint"]},
                "field": "status", "operator": "eq", "expected": "mature",
            }],
        )
        cls.proposal = produce_strategy_proposal(
            as_of="2026-09-05", generated_at="2026-09-05T10:00:00Z",
            strategy_key="synthetic.validation.gate", strategy_version="1.0.0",
            proposal_kind="playbook_candidate", candidate_version="1.0.0", baseline_version="0.9.0",
            definition={"rule_id": "synthetic-only", "description": "Fixed contract fixture", "definition_fingerprint": SHA},
            affected_modules=["M11"],
            applicability={"universe_scope": "synthetic", "market_scope": "synthetic", "timeframes": ["daily"]},
            m09_review_refs=[{"id": cls.review["review_id"], "content_fingerprint": cls.review["review_content_fingerprint"], "review_type": "hypothesis"}],
            case_roles=[{"event_id": cls.event["event_id"], "case_label": "SYNTH-UNSEEN", "role": "validation", "seen_before": False}],
            preregistration=cls.prereg, created_by="author:synthetic-owner", created_at="2026-09-05T10:00:00Z", bias_labels=[],
        )

    def seeded(self):
        context = tempfile.TemporaryDirectory()
        root = Path(context.name)
        ledger = EventLedgerStore(root / "ledger")
        ledger.write_event(self.event)
        ledger.write_event(self.baseline_event)
        ledger.write_human_review(self.review)
        evaluation = EvaluationShadowStore(root / "evaluation")
        evaluation.write_run_receipt(self.pending)
        evaluation.write_result("ForwardOutcome", self.outcome)
        evaluation.write_run_receipt(self.completed)
        evaluation.write_run_receipt(self.baseline_pending)
        evaluation.write_result("ForwardOutcome", self.baseline_outcome)
        evaluation.write_run_receipt(self.baseline_completed)
        playbook = PlaybookShadowStore(root / "playbook")
        return context, ledger, evaluation, playbook

    def assess(self, ledger, evaluation, **changes):
        values = {
            "proposal": self.proposal, "ledger_store": ledger,
            "evaluation_store": evaluation, "run_ids": [self.completed["run_id"], self.baseline_completed["run_id"]],
            "assessed_at": "2026-09-05T11:00:00Z",
        }
        values.update(changes)
        return assess_persisted_strategy_evidence(**values)

    def lifecycle(self, assessment=None):
        root = register_strategy_proposal(self.proposal, author_id="author:owner", occurred_at="2026-09-05T12:00:00Z")
        events = [root]
        if assessment is not None:
            events.append(record_evidence_assessment(self.proposal, assessment, existing_events=events, author_id="system:m11", occurred_at="2026-09-05T12:01:00Z"))
        return events

    def test_proposal_is_deterministic_and_timestamp_not_strategy_identity(self):
        validate_strategy_proposal(self.proposal)
        changed = resign_proposal(self.proposal, generated_at="2026-09-05T10:30:00Z")
        self.assertEqual(self.proposal["proposal_id"], changed["proposal_id"])
        self.assertEqual(self.proposal["proposal_content_fingerprint"], changed["proposal_content_fingerprint"])

    def test_new_definition_requires_new_version_or_conflicts(self):
        changed_definition = plain(self.proposal["definition"])
        changed_definition["description"] = "changed"
        changed = resign_proposal(self.proposal, definition=changed_definition)
        self.assertEqual(self.proposal["proposal_id"], changed["proposal_id"])
        self.assertNotEqual(self.proposal["proposal_content_fingerprint"], changed["proposal_content_fingerprint"])
        v2 = resign_proposal(self.proposal, strategy_version="2.0.0", definition=changed_definition)
        self.assertNotEqual(self.proposal["proposal_id"], v2["proposal_id"])

    def test_observation_cannot_source_proposal(self):
        refs = plain(self.proposal["m09_review_refs"])
        refs[0]["review_type"] = "observation"
        with self.assertRaises(ContractError):
            resign_proposal(self.proposal, m09_review_refs=refs)

    def test_known_seen_cases_cannot_claim_independent_validation(self):
        cases = plain(self.proposal["case_roles"])
        cases[0].update({"case_label": "CGEM", "role": "validation", "seen_before": True})
        with self.assertRaises(ContractError):
            resign_proposal(self.proposal, case_roles=cases)

    def test_bare_or_unpersisted_m09_review_fails(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            missing = resign_proposal(self.proposal, m09_review_refs=[{"id": "human-review:sha256:" + "f" * 64, "content_fingerprint": SHA, "review_type": "hypothesis"}])
            with self.assertRaisesRegex(ContractError, "not persisted"):
                self.assess(ledger, evaluation, proposal=missing)

    def test_persisted_formal_validation_evidence_can_validate(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            self.assertEqual("validated", assessment["evidence_state"])
            self.assertEqual(["validation"], list(assessment["partitions"]))

    def test_pending_or_failed_run_cannot_support_validated(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            other = EvaluationShadowStore(Path(context.name) / "pending-evaluation")
            other.write_run_receipt(self.pending)
            assessment = self.assess(ledger, other, run_ids=[self.pending["run_id"]])
            self.assertEqual("evidence_incomplete", assessment["evidence_state"])

    def test_comparison_or_legacy_cannot_support_validated(self):
        context, ledger, _, _ = self.seeded()
        with context:
            for role, path, biases, suffix in (
                ("comparison", "formal", [], "comparison"),
                ("comparison", "legacy", ["legacy_evidence"], "legacy"),
            ):
                evaluation = EvaluationShadowStore(Path(context.name) / suffix)
                pending_values = {
                    key: plain(value) for key, value in self.pending.items()
                    if key not in {"run_id", "run_receipt_id", "run_content_fingerprint", "input_set_fingerprint", "result_set_fingerprint"}
                }
                pending_values.update({"result_role": role, "path_status": path, "bias_labels": biases, "attempt_id": suffix})
                pending = plain(build_experiment_run_receipt(**pending_values))
                outcome_values = plain(self.outcome)
                for field in ("forward_outcome_id", "forward_content_fingerprint", "logical_result_id", "input_fingerprint"):
                    outcome_values.pop(field, None)
                outcome_values.update({"run_id": pending["run_id"], "result_role": role, "path_status": path, "bias_labels": biases})
                outcome = plain(finalize_result("ForwardOutcome", outcome_values))
                completed_values = {
                    key: plain(value) for key, value in pending.items()
                    if key not in {"run_id", "run_receipt_id", "run_content_fingerprint", "input_set_fingerprint", "result_set_fingerprint"}
                }
                completed_values.update({"status": "completed", "result_refs": [{"id": outcome["forward_outcome_id"], "content_fingerprint": outcome["forward_content_fingerprint"]}], "finished_at": "2026-09-03T22:01:00Z", "supersedes_run_receipt_id": pending["run_receipt_id"]})
                completed = plain(build_experiment_run_receipt(**completed_values))
                evaluation.write_run_receipt(pending)
                evaluation.write_result("ForwardOutcome", outcome)
                evaluation.write_run_receipt(completed)
                evaluation.write_run_receipt(self.baseline_pending)
                evaluation.write_result("ForwardOutcome", self.baseline_outcome)
                evaluation.write_run_receipt(self.baseline_completed)
                assessment = self.assess(ledger, evaluation, run_ids=[completed["run_id"], self.baseline_completed["run_id"]])
                self.assertEqual("evidence_incomplete", assessment["evidence_state"])

    def test_required_cost_policy_missing_is_evidence_incomplete(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            prereg = build_preregistration(required_partitions=["validation"], required_result_contracts=["ForwardOutcome"], requires_cost_policy=True, criteria=plain(self.prereg["criteria"]))
            proposal = resign_proposal(self.proposal, strategy_version="1.0.5", preregistration=prereg)
            self.assertEqual("evidence_incomplete", self.assess(ledger, evaluation, proposal=proposal)["evidence_state"])

    def test_evidence_input_order_does_not_change_identity(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            first = self.assess(ledger, evaluation)
            second = self.assess(ledger, evaluation, run_ids=list(reversed([self.completed["run_id"], self.baseline_completed["run_id"]])))
            self.assertEqual(first, second)

    def test_missing_required_partition_is_evidence_incomplete(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            prereg = build_preregistration(required_partitions=["forward", "validation"], required_result_contracts=["ForwardOutcome"], requires_cost_policy=False, criteria=plain(self.prereg["criteria"]))
            proposal = resign_proposal(self.proposal, strategy_version="1.0.1", preregistration=prereg)
            assessment = self.assess(ledger, evaluation, proposal=proposal)
            self.assertEqual("evidence_incomplete", assessment["evidence_state"])

    def test_discovery_only_case_is_evidence_incomplete(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            cases = plain(self.proposal["case_roles"])
            cases[0].update({"role": "discovery", "seen_before": True})
            proposal = resign_proposal(self.proposal, strategy_version="1.0.2", case_roles=cases)
            self.assertEqual("evidence_incomplete", self.assess(ledger, evaluation, proposal=proposal)["evidence_state"])

    def test_failed_preregistered_criterion_is_not_validated(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            criteria = plain(self.prereg["criteria"])
            criteria[0]["expected"] = "pending"
            prereg = build_preregistration(required_partitions=["validation"], required_result_contracts=["ForwardOutcome"], requires_cost_policy=False, criteria=criteria)
            proposal = resign_proposal(self.proposal, strategy_version="1.0.3", preregistration=prereg)
            self.assertEqual("not_validated", self.assess(ledger, evaluation, proposal=proposal)["evidence_state"])

    def test_unpersisted_m10_object_or_bad_fingerprint_fails(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            criteria = plain(self.prereg["criteria"])
            criteria[0]["result_ref"]["content_fingerprint"] = SHA
            prereg = build_preregistration(required_partitions=["validation"], required_result_contracts=["ForwardOutcome"], requires_cost_policy=False, criteria=criteria)
            proposal = resign_proposal(self.proposal, strategy_version="1.0.4", preregistration=prereg)
            with self.assertRaisesRegex(ContractError, "fingerprint"):
                self.assess(ledger, evaluation, proposal=proposal)

    def test_user_approval_changes_decision_not_machine_evidence(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            events = self.lifecycle(assessment)
            approved = record_user_decision(self.proposal, existing_events=events, decision="approved_for_implementation", approval_ref=proof("approval", "d"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="approved intent")
            self.assertEqual("validated", approved["state_after"]["evidence"])
            self.assertEqual("approved_for_implementation", approved["state_after"]["decision"])
            self.assertEqual("inactive", approved["state_after"]["production"])

    def test_approval_before_validation_is_allowed_but_not_active(self):
        events = self.lifecycle()
        approved = record_user_decision(self.proposal, existing_events=events, decision="approved_for_implementation", approval_ref=proof("approval", "d"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="approve candidate implementation")
        self.assertEqual("candidate", approved["state_after"]["evidence"])
        with self.assertRaisesRegex(ContractError, "prerequisites"):
            record_production_activation(self.proposal, existing_events=[*events, approved], m12_activation_proof=proof("m12-activation", "e"), author_id="system:m12", occurred_at="2026-09-05T12:03:00Z", reason="invalid")

    def test_implemented_in_main_is_not_active(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            events = self.lifecycle(assessment)
            approved = record_user_decision(self.proposal, existing_events=events, decision="approved_for_implementation", approval_ref=proof("approval", "d"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="approved")
            implemented = record_main_implementation(self.proposal, existing_events=[*events, approved], implementation_proof=proof("implementation-proof", "e"), test_proof=proof("test-proof", "f"), author_id="system:git", occurred_at="2026-09-05T12:03:00Z", reason="merged")
            self.assertEqual("implemented_in_main", implemented["state_after"]["implementation"])
            self.assertEqual("inactive", implemented["state_after"]["production"])

    def test_activation_requires_all_three_axes_and_m12_proof(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            events = self.lifecycle(assessment)
            approved = record_user_decision(self.proposal, existing_events=events, decision="approved_for_implementation", approval_ref=proof("approval", "d"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="approved")
            implemented = record_main_implementation(self.proposal, existing_events=[*events, approved], implementation_proof=proof("implementation-proof", "e"), test_proof=proof("test-proof", "f"), author_id="system:git", occurred_at="2026-09-05T12:03:00Z", reason="merged")
            active = record_production_activation(self.proposal, existing_events=[*events, approved, implemented], m12_activation_proof=proof("m12-activation", "1"), author_id="system:m12", occurred_at="2026-09-05T12:04:00Z", reason="synthetic proof")
            self.assertEqual("active", active["state_after"]["production"])

    def test_retirement_preserves_history_and_cannot_reactivate(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            events = self.lifecycle(assessment)
            approved = record_user_decision(self.proposal, existing_events=events, decision="approved_for_implementation", approval_ref=proof("approval", "d"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="approved")
            implemented = record_main_implementation(self.proposal, existing_events=[*events, approved], implementation_proof=proof("implementation-proof", "e"), test_proof=proof("test-proof", "f"), author_id="system:git", occurred_at="2026-09-05T12:03:00Z", reason="merged")
            active = record_production_activation(self.proposal, existing_events=[*events, approved, implemented], m12_activation_proof=proof("m12-activation", "1"), author_id="system:m12", occurred_at="2026-09-05T12:04:00Z", reason="synthetic proof")
            chain = [*events, approved, implemented, active]
            retired = record_retirement(self.proposal, existing_events=chain, retirement_proof=proof("retirement-proof", "2"), author_id="system:m12", occurred_at="2026-09-05T12:05:00Z", reason="retired")
            self.assertEqual("retired", retired["state_after"]["production"])
            with self.assertRaisesRegex(ContractError, "retired"):
                record_user_decision(self.proposal, existing_events=[*chain, retired], decision="deferred", approval_ref=proof("approval", "3"), author_id="author:user", occurred_at="2026-09-05T12:06:00Z", reason="cannot revive")

    def test_assessment_chain_rejects_dangling_fork_and_cross_version(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            first = self.assess(ledger, evaluation)
            second = self.assess(ledger, evaluation, assessed_at="2026-09-06T11:00:00Z", supersedes_assessment=first)
            current_strategy_assessment([second, first])
            with self.assertRaises(ContractError):
                current_strategy_assessment([second])
            with self.assertRaises(ContractError):
                current_strategy_assessment([first, second, dict(second)])

    def test_lifecycle_chain_rejects_dangling_fork_and_cross_version(self):
        root = self.lifecycle()[0]
        first = record_user_decision(self.proposal, existing_events=[root], decision="deferred", approval_ref=proof("approval", "4"), author_id="author:user", occurred_at="2026-09-05T12:01:00Z", reason="defer")
        second = record_user_decision(self.proposal, existing_events=[root], decision="rejected", approval_ref=proof("approval", "5"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="reject")
        with self.assertRaisesRegex(ContractError, "fork"):
            current_strategy_lifecycle([root, first, second])
        with self.assertRaises(ContractError):
            current_strategy_lifecycle([first])

    def test_append_only_store_is_idempotent_and_rejects_forks(self):
        context, _, _, store = self.seeded()
        with context:
            root = self.lifecycle()[0]
            store.write_proposal(self.proposal)
            path = store.write_lifecycle_event(root)
            before = path.read_bytes()
            self.assertEqual(path, store.write_lifecycle_event(root))
            first = record_user_decision(self.proposal, existing_events=[root], decision="deferred", approval_ref=proof("approval", "4"), author_id="author:user", occurred_at="2026-09-05T12:01:00Z", reason="defer")
            second = record_user_decision(self.proposal, existing_events=[root], decision="rejected", approval_ref=proof("approval", "5"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="reject")
            store.write_lifecycle_event(first)
            with self.assertRaisesRegex(ContractError, "current leaf"):
                store.write_lifecycle_event(second)
            self.assertEqual(before, path.read_bytes())

    def test_storage_requires_exact_proposal_and_assessment_authority(self):
        context, ledger, evaluation, store = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            root = self.lifecycle(assessment)[0]
            with self.assertRaisesRegex(ContractError, "persisted proposal"):
                store.write_assessment(assessment)
            with self.assertRaisesRegex(ContractError, "persisted proposal"):
                store.write_lifecycle_event(root)
            store.write_proposal(self.proposal)
            store.write_assessment(assessment)
            assessed_event = record_evidence_assessment(self.proposal, assessment, existing_events=[root], author_id="system:m11", occurred_at="2026-09-05T12:01:00Z")
            store.write_lifecycle_event(root)
            store.write_lifecycle_event(assessed_event)

    def test_concurrent_lifecycle_children_at_most_one_succeeds(self):
        context, _, _, store = self.seeded()
        with context:
            root = self.lifecycle()[0]
            store.write_proposal(self.proposal)
            store.write_lifecycle_event(root)
            children = [
                record_user_decision(self.proposal, existing_events=[root], decision=decision, approval_ref=proof("approval", digit), author_id="author:user", occurred_at=f"2026-09-05T12:0{index}:00Z", reason=decision)
                for index, (decision, digit) in enumerate((("deferred", "4"), ("rejected", "5")), 1)
            ]
            def write(item):
                try:
                    store.write_lifecycle_event(item)
                    return True
                except ContractError:
                    return False
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(1, sum(pool.map(write, children)))

    def test_registry_is_deterministic_read_only_derivation(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            events = self.lifecycle(assessment)
            first = derive_strategy_registry_snapshot([self.proposal], [assessment], events, as_of="2026-09-05", generated_at="2026-09-05T13:00:00Z", code_commit="1" * 40)
            second = derive_strategy_registry_snapshot(reversed([self.proposal]), reversed([assessment]), reversed(events), as_of="2026-09-05", generated_at="2026-09-05T13:00:00Z", code_commit="1" * 40)
            self.assertEqual(first, second)
            validate_strategy_registry_snapshot(first)
            self.assertEqual("validated", first["entries"][0]["evidence_state"])
            self.assertEqual("inactive", first["entries"][0]["production_state"])

    def test_registry_distinguishes_approved_unvalidated_and_validated_unapproved(self):
        approved = record_user_decision(self.proposal, existing_events=self.lifecycle(), decision="approved_for_implementation", approval_ref=proof("approval", "d"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="approved")
        first = derive_strategy_registry_snapshot([self.proposal], [], [*self.lifecycle(), approved], as_of="2026-09-05", generated_at="2026-09-05T13:00:00Z", code_commit="1" * 40)
        self.assertEqual(("candidate", "approved_for_implementation"), (first["entries"][0]["evidence_state"], first["entries"][0]["decision_state"]))

    def test_registry_rejects_missing_sources_and_stale_assessment_state(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            with self.assertRaisesRegex(ContractError, "proposal"):
                derive_strategy_registry_snapshot([], [assessment], [], as_of="2026-09-05", generated_at="2026-09-05T13:00:00Z", code_commit="1" * 40)
            with self.assertRaisesRegex(ContractError, "reflect"):
                derive_strategy_registry_snapshot([self.proposal], [assessment], self.lifecycle(), as_of="2026-09-05", generated_at="2026-09-05T13:00:00Z", code_commit="1" * 40)

    def test_v1_v2_coexist_without_overwriting(self):
        v2 = resign_proposal(self.proposal, strategy_version="2.0.0")
        snapshot = derive_strategy_registry_snapshot([v2, self.proposal], [], [], as_of="2026-09-05", generated_at="2026-09-05T13:00:00Z", code_commit="1" * 40)
        self.assertEqual(["1.0.0", "2.0.0"], [item["strategy_version"] for item in snapshot["entries"]])

    def test_empty_real_repository_snapshot_reports_zero(self):
        snapshot = empty_current_registry(as_of="2026-09-05", generated_at="2026-09-05T13:00:00Z", code_commit="1" * 40)
        self.assertEqual(0, snapshot["formal_validated_count"])
        self.assertEqual(0, snapshot["active_count"])
        self.assertEqual(0, snapshot["alpha_risk_hard_rule_count"])

    def test_storage_rejects_production_paths(self):
        with self.assertRaises(ContractError):
            PlaybookShadowStore(Path(__file__).resolve().parents[1] / "public" / "m11")

    def test_no_performance_or_production_side_effect_fields_exist(self):
        forbidden = {"return", "win_rate", "profit_factor", "mfe", "mae", "deploy", "discord"}
        self.assertFalse(forbidden & set(self.proposal))


if __name__ == "__main__":
    unittest.main()
