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
    build_preregistration_authority_record,
    build_preregistration,
    build_strategy_evidence_assessment,
    build_strategy_proposal,
    current_strategy_assessment,
    current_strategy_lifecycle,
    derive_strategy_registry_snapshot,
    empty_current_registry,
    produce_strategy_proposal,
    proposal_preregistration_semantic_fingerprint,
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


def resign_snapshot(payload):
    result = plain(payload)
    result["source_refs"] = sorted(
        result["source_refs"], key=lambda item: (item["id"], item["content_fingerprint"])
    )
    result["source_set_fingerprint"] = canonical_fingerprint(result["source_refs"])
    result["registry_snapshot_id"] = "strategy-registry:" + canonical_fingerprint({
        "as_of": result["as_of"],
        "source_set_fingerprint": result["source_set_fingerprint"],
        "code_commit": result["code_commit"],
    })
    result["registry_content_fingerprint"] = canonical_fingerprint({
        key: value for key, value in result.items()
        if key not in {"generated_at", "registry_content_fingerprint"}
    })
    validate_strategy_registry_snapshot(result)
    return result


class SyntheticCaseAuthority:
    authority_mode = "test"

    def __init__(self, events, *, seen=()):
        self.records = {
            item["event_id"]: {
                "event_id": item["event_id"],
                "instrument_id": item["instrument_id"],
                "signal_date": item["signal_date"],
                "event_content_fingerprint": item["event_content_fingerprint"],
                "seen_before": item["event_id"] in set(seen),
            }
            for item in events
        }

    def resolve_case(self, event_id):
        if event_id not in self.records:
            raise ContractError("synthetic case is not registered")
        return self.records[event_id]


class SyntheticLifecycleAuthority:
    authority_mode = "test"

    def resolve_user_approval(self, proposal, event):
        return event["proposal_id"] == proposal["proposal_id"]

    def resolve_main_implementation(self, proposal, event):
        return event["proposal_id"] == proposal["proposal_id"]

    def resolve_m12_activation(self, proposal, event):
        return event["proposal_id"] == proposal["proposal_id"]


class SyntheticPreregistrationAuthority:
    authority_mode = "test"

    def __init__(self):
        self.records = {}

    def register(
        self, proposal_values, *, registered_at="2026-09-03T21:00:00Z",
        run_code_commits=(), registration_commit="0" * 40,
    ):
        record = build_preregistration_authority_record(
            proposal_semantic_fingerprint=(
                proposal_preregistration_semantic_fingerprint(proposal_values)
            ),
            registered_at=registered_at,
            registration_commit=registration_commit,
            verified_run_code_commits=run_code_commits,
            authority_mode=self.authority_mode,
        )
        self.records[record["authority_id"]] = record
        return {
            "id": record["authority_id"],
            "content_fingerprint": record["content_fingerprint"],
        }

    def resolve_preregistration(self, authority_id):
        if authority_id not in self.records:
            raise ContractError("synthetic preregistration is not registered")
        return self.records[authority_id]

    def verify_registration_commit_ancestry(self, registration_commit, run_code_commit):
        return any(
            record["registration_commit"] == registration_commit
            and run_code_commit in record["verified_run_code_commits"]
            for record in self.records.values()
        )


class RejectingPreregistrationAncestry(SyntheticPreregistrationAuthority):
    def verify_registration_commit_ancestry(self, registration_commit, run_code_commit):
        return False


class M11PlaybookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_type = importlib.import_module("tests.test_m09_ledger").M09LedgerTests
        fixture = fixture_type("test_all_authoritative_ranked_entries_create_one_root")
        fixture.setUp()
        cls.event = plain(fixture.batch.events[0])
        cls.baseline_event = plain(fixture.batch.events[1])
        cls.third_event = plain(fixture.batch.events[2])
        cls.review = create_human_review(
            subject_type="event",
            subject_reference={"event_id": cls.event["event_id"]},
            review_type="hypothesis",
            author_id="author:synthetic-reviewer",
            authored_at="2026-09-03T20:00:00Z",
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
        cls.case_authority = SyntheticCaseAuthority([
            cls.event, cls.baseline_event, cls.third_event,
        ])
        cls.prereg_authority = SyntheticPreregistrationAuthority()
        cls.lifecycle_authority = SyntheticLifecycleAuthority()
        evidence_scope = {
            "expected_run_ids": sorted([
                cls.completed["run_id"], cls.baseline_completed["run_id"],
            ]),
            "evidence_window": plain(cls.completed["evidence_window"]),
            "required_input_refs": sorted(
                [proof("market", "b"), proof("universe", "c")],
                key=lambda item: item["id"],
            ),
            "required_policy_refs": plain(cls.completed["policy_refs"]),
            "required_window_sessions": [5],
        }
        cls.prereg = build_preregistration(
            required_partitions=["validation"],
            required_result_contracts=["ForwardOutcome"],
            requires_cost_policy=False,
            evidence_scope=evidence_scope,
            criteria=[{
                "criterion_id": "criterion-001-status-mature",
                "result_contract": "ForwardOutcome",
                "run_role": "baseline",
                "partition_role": "validation",
                "window_sessions": 5,
                "field": "status", "operator": "eq", "expected": "mature",
            }],
        )
        proposal_values = {
            "as_of": "2026-09-05", "generated_at": "2026-09-05T10:00:00Z",
            "strategy_key": "synthetic.validation.gate", "strategy_version": "1.0.0",
            "proposal_kind": "playbook_candidate", "candidate_version": "1.0.0", "baseline_version": "0.9.0",
            "definition": {"rule_id": "synthetic-only", "description": "Fixed contract fixture", "definition_fingerprint": SHA},
            "affected_modules": ["M11"],
            "applicability": {"universe_scope": "synthetic", "market_scope": "synthetic", "timeframes": ["daily"]},
            "m09_review_refs": [{"id": cls.review["review_id"], "content_fingerprint": cls.review["review_content_fingerprint"], "review_type": "hypothesis"}],
            "case_roles": [
                {**cls.case_authority.records[cls.event["event_id"]], "case_label": "SYNTH-UNSEEN", "role": "validation"},
                {**cls.case_authority.records[cls.baseline_event["event_id"]], "case_label": "SYNTH-BASELINE", "role": "validation"},
            ],
            "preregistration": cls.prereg, "created_by": "author:synthetic-owner",
            "created_at": "2026-09-05T10:00:00Z", "bias_labels": [],
        }
        proposal_values["preregistration_authority_ref"] = cls.prereg_authority.register(
            proposal_values,
            run_code_commits=sorted({
                cls.pending["code_commit"], cls.baseline_pending["code_commit"],
            }),
        )
        cls.proposal = produce_strategy_proposal(
            **{key: value for key, value in proposal_values.items() if key != "case_roles"},
            case_roles=[
                {"event_id": cls.event["event_id"], "case_label": "SYNTH-UNSEEN", "role": "validation"},
                {"event_id": cls.baseline_event["event_id"], "case_label": "SYNTH-BASELINE", "role": "validation"},
            ],
            persisted_case_events=[cls.event, cls.baseline_event],
            case_authority_resolver=cls.case_authority,
            preregistration_authority_resolver=cls.prereg_authority,
        )

    def seeded(self):
        context = tempfile.TemporaryDirectory()
        root = Path(context.name)
        ledger = EventLedgerStore(root / "ledger")
        ledger.write_event(self.event)
        ledger.write_event(self.baseline_event)
        ledger.write_event(self.third_event)
        ledger.write_human_review(self.review)
        evaluation = EvaluationShadowStore(root / "evaluation")
        evaluation.write_run_receipt(self.pending)
        evaluation.write_result("ForwardOutcome", self.outcome)
        evaluation.write_run_receipt(self.completed)
        evaluation.write_run_receipt(self.baseline_pending)
        evaluation.write_result("ForwardOutcome", self.baseline_outcome)
        evaluation.write_run_receipt(self.baseline_completed)
        playbook = PlaybookShadowStore(
            root / "playbook", ledger_store=ledger, evaluation_store=evaluation,
            case_authority_resolver=self.case_authority,
            lifecycle_authority_resolver=self.lifecycle_authority,
            preregistration_authority_resolver=self.prereg_authority,
        )
        return context, ledger, evaluation, playbook

    def assess(self, ledger, evaluation, **changes):
        values = {
            "proposal": self.proposal, "ledger_store": ledger,
            "evaluation_store": evaluation, "run_ids": [self.completed["run_id"], self.baseline_completed["run_id"]],
            "assessed_at": "2026-09-05T11:00:00Z",
            "case_authority_resolver": self.case_authority,
            "preregistration_authority_resolver": self.prereg_authority,
        }
        values.update(changes)
        return assess_persisted_strategy_evidence(**values)

    def resign(self, original, **changes):
        return self.proposal_with_preregistration(original, **changes)

    def proposal_with_preregistration(
        self, original, *, preregistration_resolver=None,
        case_resolver=None,
        registered_at="2026-09-03T21:00:00Z", run_code_commits=None,
        **changes,
    ):
        resolver = preregistration_resolver or self.prereg_authority
        case_authority = case_resolver or self.case_authority
        values = plain(original)
        for field in (
            "proposal_id", "proposal_content_fingerprint", "strategy_id",
            "preregistration_authority_ref",
        ):
            values.pop(field, None)
        cases = changes.pop("case_roles", values.pop("case_roles"))
        values.update(changes)
        declared_cases = [
            {
                "event_id": item["event_id"],
                "case_label": item["case_label"],
                "role": item["role"],
            }
            for item in cases
        ]
        resolved_cases = [
            {
                **case_authority.records[item["event_id"]],
                "case_label": item["case_label"],
                "role": item["role"],
            }
            for item in declared_cases
        ]
        values["preregistration_authority_ref"] = resolver.register(
            {**values, "case_roles": resolved_cases},
            registered_at=registered_at,
            run_code_commits=(run_code_commits or [self.pending["code_commit"]]),
        )
        return produce_strategy_proposal(
            **values,
            case_roles=declared_cases,
            persisted_case_events=[self.event, self.baseline_event, self.third_event],
            case_authority_resolver=case_authority,
            preregistration_authority_resolver=resolver,
        )

    def scope_for(self, *receipts):
        return {
            "expected_run_ids": sorted(item["run_id"] for item in receipts),
            "evidence_window": plain(receipts[0]["evidence_window"]),
            "required_input_refs": sorted(
                [proof("market", "b"), proof("universe", "c")],
                key=lambda item: item["id"],
            ),
            "required_policy_refs": plain(receipts[0]["policy_refs"]),
            "required_window_sessions": [5],
        }

    def make_forward_run(
        self, event, *, attempt_id, experiment_id, config_version="1.0.0",
        gross_return=0.1, policy_refs=None,
    ):
        dummy = finalize_result("ForwardOutcome", forward_2_1_values())
        pending_values = receipt_values(dummy)
        pending_values.update({
            "status": "pending", "result_refs": [], "finished_at": None,
            "partition_role": "validation", "supersedes_run_receipt_id": None,
            "attempt_id": attempt_id, "experiment_id": experiment_id,
            "config_ref": {
                "config_id": experiment_id, "config_version": config_version,
                "content_fingerprint": SHA,
            },
            "input_refs": [
                {"id": event["event_id"], "content_fingerprint": event["event_content_fingerprint"]},
                proof("market", "b"), proof("universe", "c"),
            ],
        })
        if policy_refs is not None:
            pending_values["policy_refs"] = plain(policy_refs)
        pending = plain(build_experiment_run_receipt(**pending_values))
        outcome_values = forward_2_1_values(mature=True)
        outcome_values.update({
            "run_id": pending["run_id"], "event_id": event["event_id"],
            "event_content_fingerprint": event["event_content_fingerprint"],
            "instrument_id": event["instrument_id"], "signal_date": event["signal_date"],
            "partition_role": "validation", "gross_return": gross_return,
            "endpoint": {"date": "2026-09-09", "price": 100.0 * (1.0 + gross_return)},
        })
        outcome = plain(finalize_result("ForwardOutcome", outcome_values))
        completed_values = {
            key: plain(value) for key, value in pending.items()
            if key not in {
                "run_id", "run_receipt_id", "run_content_fingerprint",
                "input_set_fingerprint", "result_set_fingerprint",
            }
        }
        completed_values.update({
            "status": "completed",
            "result_refs": [{
                "id": outcome["forward_outcome_id"],
                "content_fingerprint": outcome["forward_content_fingerprint"],
            }],
            "finished_at": "2026-09-03T22:01:00Z",
            "supersedes_run_receipt_id": pending["run_receipt_id"],
        })
        completed = plain(build_experiment_run_receipt(**completed_values))
        return pending, outcome, completed

    def lifecycle(self, assessment=None):
        root = register_strategy_proposal(self.proposal, author_id="author:owner", occurred_at="2026-09-05T12:00:00Z")
        events = [root]
        if assessment is not None:
            events.append(record_evidence_assessment(self.proposal, assessment, existing_events=events, author_id="system:m11", occurred_at="2026-09-05T12:01:00Z"))
        return events

    def test_proposal_is_deterministic_and_timestamp_not_strategy_identity(self):
        validate_strategy_proposal(self.proposal)
        changed = self.resign(self.proposal, generated_at="2026-09-05T10:30:00Z")
        self.assertEqual(self.proposal["proposal_id"], changed["proposal_id"])
        self.assertEqual(self.proposal["proposal_content_fingerprint"], changed["proposal_content_fingerprint"])

    def test_new_definition_requires_new_version_or_conflicts(self):
        changed_definition = plain(self.proposal["definition"])
        changed_definition["description"] = "changed"
        changed = self.resign(self.proposal, definition=changed_definition)
        self.assertEqual(self.proposal["proposal_id"], changed["proposal_id"])
        self.assertNotEqual(self.proposal["proposal_content_fingerprint"], changed["proposal_content_fingerprint"])
        v2 = self.resign(self.proposal, strategy_version="2.0.0", definition=changed_definition)
        self.assertNotEqual(self.proposal["proposal_id"], v2["proposal_id"])

    def test_observation_cannot_source_proposal(self):
        refs = plain(self.proposal["m09_review_refs"])
        refs[0]["review_type"] = "observation"
        with self.assertRaises(ContractError):
            self.resign(self.proposal, m09_review_refs=refs)

    def test_case_label_is_display_only_for_unseen_case(self):
        cases = plain(self.proposal["case_roles"])
        cases[0].update({"case_label": "CGEM", "role": "validation"})
        changed = self.resign(self.proposal, case_roles=cases)
        self.assertFalse(changed["case_roles"][0]["seen_before"])
        self.assertEqual("validation", changed["case_roles"][0]["role"])
        self.assertNotEqual(
            self.proposal["proposal_content_fingerprint"],
            changed["proposal_content_fingerprint"],
        )

    def test_case_label_cannot_hide_stably_seen_case(self):
        case_authority = SyntheticCaseAuthority(
            [self.event, self.baseline_event], seen=[self.event["event_id"]]
        )
        cases = plain(self.proposal["case_roles"])
        cases[0].update({"case_label": "SYNTH-UNSEEN", "role": "calibration"})
        changed = self.proposal_with_preregistration(
            self.proposal, case_roles=cases, case_resolver=case_authority,
        )
        self.assertTrue(changed["case_roles"][0]["seen_before"])
        validation_cases = plain(changed["case_roles"])
        validation_cases[0]["role"] = "validation"
        with self.assertRaisesRegex(ContractError, "previously seen"):
            self.proposal_with_preregistration(
                changed, case_roles=validation_cases, case_resolver=case_authority,
            )

    def test_seen_case_identity_cannot_be_hidden_by_display_alias(self):
        resolver = SyntheticCaseAuthority(
            [self.event, self.baseline_event], seen=[self.event["event_id"]]
        )
        values = plain(self.proposal)
        for field in ("proposal_id", "proposal_content_fingerprint", "strategy_id", "case_roles"):
            values.pop(field, None)
        with self.assertRaisesRegex(ContractError, "previously seen"):
            produce_strategy_proposal(
                **values,
                case_roles=[
                    {
                        "event_id": self.event["event_id"],
                        "case_label": "renamed-alias",
                        "role": "validation",
                    },
                    {
                        "event_id": self.baseline_event["event_id"],
                        "case_label": "baseline",
                        "role": "validation",
                    },
                ],
                persisted_case_events=[self.event, self.baseline_event],
                case_authority_resolver=resolver,
                preregistration_authority_resolver=self.prereg_authority,
            )

    def test_case_seen_before_and_stable_identity_are_not_caller_controlled(self):
        values = plain(self.proposal)
        for field in ("proposal_id", "proposal_content_fingerprint", "strategy_id", "case_roles"):
            values.pop(field, None)
        with self.assertRaisesRegex(ContractError, "authority-derived"):
            produce_strategy_proposal(
                **values,
                case_roles=[{
                    "event_id": self.event["event_id"], "case_label": "alias",
                    "role": "validation", "seen_before": False,
                }],
                persisted_case_events=[self.event],
                case_authority_resolver=self.case_authority,
                preregistration_authority_resolver=self.prereg_authority,
            )

        context, ledger, evaluation, _ = self.seeded()
        with context:
            attacks = (
                ("instrument_id", self.third_event["instrument_id"]),
                ("signal_date", "2026-09-04"),
            )
            for index, (field, replacement) in enumerate(attacks, 6):
                tampered = plain(self.proposal)
                for identity in ("proposal_id", "proposal_content_fingerprint", "strategy_id"):
                    tampered.pop(identity, None)
                tampered["strategy_version"] = f"1.{index}.0"
                tampered["case_roles"][0][field] = replacement
                forged = build_strategy_proposal(**tampered)
                with self.subTest(field=field), self.assertRaisesRegex(
                    ContractError, "persisted M09 event identity"
                ):
                    self.assess(ledger, evaluation, proposal=forged)

            missing = plain(self.proposal)
            for identity in ("proposal_id", "proposal_content_fingerprint", "strategy_id"):
                missing.pop(identity, None)
            missing["case_roles"][0].pop("instrument_id")
            with self.assertRaises(ContractError):
                build_strategy_proposal(**missing)

    def test_legacy_m11_proposal_is_read_only_not_formal_writable(self):
        legacy = plain(self.proposal)
        for field in (
            "proposal_id", "proposal_content_fingerprint", "strategy_id",
            "preregistration_authority_ref",
        ):
            legacy.pop(field, None)
        legacy["schema_version"] = "2.0.0"
        legacy["source_version"] = {"playbook": "m11-shadow-1.0.0"}
        legacy["preregistration"] = build_preregistration(
            required_partitions=legacy["preregistration"]["required_partitions"],
            required_result_contracts=legacy["preregistration"]["required_result_contracts"],
            requires_cost_policy=legacy["preregistration"]["requires_cost_policy"],
            criteria=[{
                "criterion_id": "legacy-criterion",
                "result_ref": {
                    "id": self.outcome["forward_outcome_id"],
                    "content_fingerprint": self.outcome["forward_content_fingerprint"],
                },
                "field": "status", "operator": "eq", "expected": "mature",
            }],
            schema_version="2.0.0",
        )
        for case in legacy["case_roles"]:
            for field in (
                "instrument_id", "signal_date", "event_content_fingerprint",
            ):
                case.pop(field)
        legacy = build_strategy_proposal(**legacy)
        validate_strategy_proposal(legacy)
        context, ledger, evaluation, _ = self.seeded()
        with context:
            store = PlaybookShadowStore(
                Path(context.name) / "legacy-reject",
                ledger_store=ledger, evaluation_store=evaluation,
                case_authority_resolver=self.case_authority,
            )
            with self.assertRaisesRegex(ContractError, "read-only"):
                store.write_proposal(legacy)

    def test_intermediate_2_1_proposal_is_read_only_not_formal_assessable(self):
        intermediate = plain(self.proposal)
        for field in (
            "proposal_id", "proposal_content_fingerprint", "strategy_id",
            "preregistration_authority_ref",
        ):
            intermediate.pop(field, None)
        intermediate["schema_version"] = "2.1.0"
        intermediate["source_version"] = {"playbook": "m11-shadow-1.1.0"}
        intermediate["preregistration"] = build_preregistration(
            required_partitions=["validation"],
            required_result_contracts=["ForwardOutcome"],
            requires_cost_policy=False,
            criteria=[{
                "criterion_id": "intermediate-post-result-criterion",
                "result_ref": {
                    "id": self.outcome["forward_outcome_id"],
                    "content_fingerprint": self.outcome["forward_content_fingerprint"],
                },
                "field": "status", "operator": "eq", "expected": "mature",
            }],
            evidence_scope=plain(self.prereg["evidence_scope"]),
            schema_version="2.1.0",
        )
        intermediate = build_strategy_proposal(**intermediate)
        validate_strategy_proposal(intermediate)
        context, ledger, evaluation, _ = self.seeded()
        with context, self.assertRaisesRegex(ContractError, "read-only"):
            self.assess(ledger, evaluation, proposal=intermediate)

    def test_same_case_cannot_cross_calibration_and_validation_roles(self):
        values = plain(self.proposal)
        for field in ("proposal_id", "proposal_content_fingerprint", "strategy_id", "case_roles"):
            values.pop(field, None)
        with self.assertRaisesRegex(ContractError, "sorted and unique"):
            produce_strategy_proposal(
                **values,
                case_roles=[
                    {"event_id": self.event["event_id"], "case_label": "one", "role": "calibration"},
                    {"event_id": self.event["event_id"], "case_label": "alias", "role": "validation"},
                ],
                persisted_case_events=[self.event],
                case_authority_resolver=self.case_authority,
                preregistration_authority_resolver=self.prereg_authority,
            )

    def test_bare_or_unpersisted_m09_review_fails(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            missing = self.resign(self.proposal, m09_review_refs=[{"id": "human-review:sha256:" + "f" * 64, "content_fingerprint": SHA, "review_type": "hypothesis"}])
            with self.assertRaisesRegex(ContractError, "not persisted"):
                self.assess(ledger, evaluation, proposal=missing)

    def test_persisted_formal_validation_evidence_can_validate(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            self.assertEqual("validated", assessment["evidence_state"])
            self.assertEqual(["validation"], list(assessment["partitions"]))

    def test_preregistration_must_precede_every_m10_pending_root(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            late = SyntheticPreregistrationAuthority()
            proposal = self.proposal_with_preregistration(
                self.proposal,
                preregistration_resolver=late,
                registered_at="2026-09-03T22:30:00Z",
            )
            with self.assertRaisesRegex(ContractError, "before M10 started"):
                self.assess(
                    ledger, evaluation, proposal=proposal,
                    preregistration_authority_resolver=late,
                )

    def test_backfilled_proposal_time_cannot_replace_preregistration_proof(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            late = SyntheticPreregistrationAuthority()
            proposal = self.proposal_with_preregistration(
                self.proposal,
                preregistration_resolver=late,
                registered_at="2026-09-03T22:30:00Z",
                as_of="2026-09-03",
                created_at="2026-09-03T19:00:00Z",
            )
            with self.assertRaisesRegex(ContractError, "before M10 started"):
                self.assess(
                    ledger, evaluation, proposal=proposal,
                    preregistration_authority_resolver=late,
                )

    def test_preregistration_commit_must_precede_run_commit(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            resolver = RejectingPreregistrationAncestry()
            proposal = self.proposal_with_preregistration(
                self.proposal, preregistration_resolver=resolver,
            )
            with self.assertRaisesRegex(ContractError, "does not precede"):
                self.assess(
                    ledger, evaluation, proposal=proposal,
                    preregistration_authority_resolver=resolver,
                )

    def test_missing_or_mismatched_preregistration_authority_fails_closed(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            with self.assertRaisesRegex(ContractError, "trusted preregistration resolver"):
                self.assess(
                    ledger, evaluation,
                    preregistration_authority_resolver=None,
                )
            criteria = plain(self.prereg["criteria"])
            criteria[0]["expected"] = "pending"
            changed_prereg = build_preregistration(
                required_partitions=["validation"],
                required_result_contracts=["ForwardOutcome"],
                requires_cost_policy=False,
                criteria=criteria,
                evidence_scope=plain(self.prereg["evidence_scope"]),
            )
            forged = plain(self.proposal)
            for field in ("proposal_id", "proposal_content_fingerprint", "strategy_id"):
                forged.pop(field, None)
            forged["preregistration"] = changed_prereg
            forged = build_strategy_proposal(**forged)
            with self.assertRaisesRegex(ContractError, "differs from the proposal"):
                self.assess(ledger, evaluation, proposal=forged)

            untrusted_store = PlaybookShadowStore(
                Path(context.name) / "untrusted-preregistration",
                ledger_store=ledger,
                evaluation_store=evaluation,
                case_authority_resolver=self.case_authority,
            )
            with self.assertRaisesRegex(ContractError, "trusted preregistration resolver"):
                untrusted_store.write_proposal(self.proposal)
            self.assertFalse(list(untrusted_store.root.rglob("*.json")))

    def test_preregistration_freezes_scope_policy_window_and_threshold(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            attacks = []
            for kind in ("window", "partition", "date", "policy", "threshold"):
                prereg = plain(self.prereg)
                for field in ("preregistration_id", "content_fingerprint"):
                    prereg.pop(field)
                if kind == "window":
                    prereg["evidence_scope"]["required_window_sessions"] = [5, 20]
                elif kind == "partition":
                    prereg["required_partitions"] = ["forward", "validation"]
                elif kind == "date":
                    prereg["evidence_scope"]["evidence_window"]["start"] = "2026-09-02"
                elif kind == "policy":
                    prereg["evidence_scope"]["required_policy_refs"][0]["policy_fingerprint"] = "sha256:" + "9" * 64
                else:
                    prereg["criteria"][0]["expected"] = "pending"
                rebuilt = build_preregistration(**prereg)
                forged = plain(self.proposal)
                for field in ("proposal_id", "proposal_content_fingerprint", "strategy_id"):
                    forged.pop(field, None)
                forged["preregistration"] = rebuilt
                attacks.append(build_strategy_proposal(**forged))
            for forged in attacks:
                with self.assertRaisesRegex(ContractError, "differs from the proposal"):
                    self.assess(ledger, evaluation, proposal=forged)

    def test_preregistration_proof_cannot_cross_strategy_version(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            other = self.resign(self.proposal, strategy_version="9.0.0")
            forged = plain(self.proposal)
            for field in ("proposal_id", "proposal_content_fingerprint", "strategy_id"):
                forged.pop(field, None)
            forged["preregistration_authority_ref"] = plain(
                other["preregistration_authority_ref"]
            )
            forged = build_strategy_proposal(**forged)
            with self.assertRaisesRegex(ContractError, "differs from the proposal"):
                self.assess(ledger, evaluation, proposal=forged)

    def test_complete_inventory_rejects_omitted_adverse_run(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            pending, outcome, completed = self.make_forward_run(
                self.third_event,
                attempt_id="attempt-adverse",
                experiment_id="M11-adverse-fixture",
                gross_return=-0.5,
            )
            evaluation.write_run_receipt(pending)
            evaluation.write_result("ForwardOutcome", outcome)
            evaluation.write_run_receipt(completed)
            with self.assertRaisesRegex(ContractError, "complete authoritative scope"):
                self.assess(ledger, evaluation)

            prereg = build_preregistration(
                required_partitions=["validation"],
                required_result_contracts=["ForwardOutcome"],
                requires_cost_policy=False,
                criteria=plain(self.prereg["criteria"]),
                evidence_scope=self.scope_for(
                    self.completed, self.baseline_completed, completed
                ),
            )
            cases = [
                *plain(self.proposal["case_roles"]),
                {
                    "event_id": self.third_event["event_id"],
                    "case_label": "ADVERSE-DISPLAY-ONLY",
                    "role": "validation",
                },
            ]
            proposal = self.resign(
                self.proposal,
                strategy_version="1.3.0",
                preregistration=prereg,
                case_roles=cases,
            )
            complete = self.assess(
                ledger,
                evaluation,
                proposal=proposal,
                run_ids=[
                    self.completed["run_id"], self.baseline_completed["run_id"],
                    completed["run_id"],
                ],
            )
            self.assertEqual("validated", complete["evidence_state"])
            self.assertEqual(3, complete["sample_count"])

    def test_declared_run_replacement_extra_and_duplicate_fail_closed(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            expected = [self.completed["run_id"], self.baseline_completed["run_id"]]
            attacks = (
                [expected[0]],
                [expected[0], expected[0]],
                [*expected, "experiment-run:sha256:" + "f" * 64],
                [expected[0], "experiment-run:sha256:" + "e" * 64],
            )
            for attack in attacks:
                with self.subTest(attack=attack), self.assertRaises(ContractError):
                    self.assess(ledger, evaluation, run_ids=attack)

    def test_cross_policy_run_cannot_be_preregistered_into_scope(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            policies = plain(self.completed["policy_refs"])
            policies.append({
                "policy_kind": "execution", "policy_version": "1.0.0",
                "policy_fingerprint": "sha256:" + "9" * 64,
            })
            policies.sort(key=lambda item: item["policy_kind"])
            pending, outcome, completed = self.make_forward_run(
                self.third_event, attempt_id="attempt-cross-policy",
                experiment_id="M11-cross-policy-fixture", gross_return=0.9,
                policy_refs=policies,
            )
            evaluation.write_run_receipt(pending)
            evaluation.write_result("ForwardOutcome", outcome)
            evaluation.write_run_receipt(completed)
            scope = self.scope_for(self.completed, self.baseline_completed, completed)
            scope["required_policy_refs"] = plain(self.completed["policy_refs"])
            prereg = build_preregistration(
                required_partitions=["validation"],
                required_result_contracts=["ForwardOutcome"],
                requires_cost_policy=False,
                criteria=plain(self.prereg["criteria"]), evidence_scope=scope,
            )
            proposal = self.resign(
                self.proposal, strategy_version="1.5.0", preregistration=prereg,
                case_roles=[
                    *plain(self.proposal["case_roles"]),
                    {
                        "event_id": self.third_event["event_id"],
                        "case_label": "CROSS-POLICY", "role": "validation",
                    },
                ],
            )
            with self.assertRaisesRegex(ContractError, "complete authoritative scope"):
                self.assess(
                    ledger, evaluation, proposal=proposal,
                    run_ids=[
                        self.completed["run_id"], self.baseline_completed["run_id"],
                        completed["run_id"],
                    ],
                )

    def test_missing_preregistered_forward_window_fails_closed(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            scope = plain(self.prereg["evidence_scope"])
            scope["required_window_sessions"] = [5, 20]
            prereg = build_preregistration(
                required_partitions=["validation"],
                required_result_contracts=["ForwardOutcome"],
                requires_cost_policy=False,
                criteria=plain(self.prereg["criteria"]),
                evidence_scope=scope,
            )
            proposal = self.resign(
                self.proposal, strategy_version="1.4.0", preregistration=prereg
            )
            with self.assertRaisesRegex(ContractError, "Forward windows"):
                self.assess(ledger, evaluation, proposal=proposal)

    def test_duplicate_logical_result_across_runs_fails_closed(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            assessment = plain(self.assess(ledger, evaluation))
            for field in (
                "assessment_id", "logical_assessment_id",
                "assessment_content_fingerprint", "gate_policy_version",
            ):
                assessment.pop(field, None)
            assessment["result_refs"][1]["logical_id"] = assessment["result_refs"][0]["logical_id"]
            with self.assertRaisesRegex(ContractError, "logical result"):
                build_strategy_evidence_assessment(**assessment)

    def test_pending_or_failed_run_cannot_support_validated(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            other = EvaluationShadowStore(Path(context.name) / "pending-evaluation")
            other.write_run_receipt(self.pending)
            prereg = build_preregistration(
                required_partitions=["validation"],
                required_result_contracts=["ForwardOutcome"],
                requires_cost_policy=False,
                criteria=plain(self.prereg["criteria"]),
                evidence_scope=self.scope_for(self.pending),
            )
            proposal = self.resign(
                self.proposal, strategy_version="1.0.6", preregistration=prereg
            )
            assessment = self.assess(
                ledger, other, proposal=proposal, run_ids=[self.pending["run_id"]]
            )
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
                prereg = build_preregistration(
                    required_partitions=["validation"],
                    required_result_contracts=["ForwardOutcome"],
                    requires_cost_policy=False,
                    criteria=plain(self.prereg["criteria"]),
                    evidence_scope=self.scope_for(completed, self.baseline_completed),
                )
                proposal = self.resign(
                    self.proposal,
                    strategy_version="1.1.0" if suffix == "comparison" else "1.2.0",
                    preregistration=prereg,
                )
                assessment = self.assess(
                    ledger, evaluation, proposal=proposal,
                    run_ids=[completed["run_id"], self.baseline_completed["run_id"]],
                )
                self.assertEqual("evidence_incomplete", assessment["evidence_state"])

    def test_required_cost_policy_missing_is_evidence_incomplete(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            prereg = build_preregistration(required_partitions=["validation"], required_result_contracts=["ForwardOutcome"], requires_cost_policy=True, criteria=plain(self.prereg["criteria"]), evidence_scope=plain(self.prereg["evidence_scope"]))
            proposal = self.resign(self.proposal, strategy_version="1.0.5", preregistration=prereg)
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
            prereg = build_preregistration(required_partitions=["forward", "validation"], required_result_contracts=["ForwardOutcome"], requires_cost_policy=False, criteria=plain(self.prereg["criteria"]), evidence_scope=plain(self.prereg["evidence_scope"]))
            proposal = self.resign(self.proposal, strategy_version="1.0.1", preregistration=prereg)
            assessment = self.assess(ledger, evaluation, proposal=proposal)
            self.assertEqual("evidence_incomplete", assessment["evidence_state"])

    def test_discovery_only_case_is_evidence_incomplete(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            cases = plain(self.proposal["case_roles"])
            for case in cases:
                case.update({"role": "discovery"})
            proposal = self.resign(self.proposal, strategy_version="1.0.2", case_roles=cases)
            self.assertEqual("evidence_incomplete", self.assess(ledger, evaluation, proposal=proposal)["evidence_state"])

    def test_failed_preregistered_criterion_is_not_validated(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            criteria = plain(self.prereg["criteria"])
            criteria[0]["expected"] = "pending"
            prereg = build_preregistration(required_partitions=["validation"], required_result_contracts=["ForwardOutcome"], requires_cost_policy=False, criteria=criteria, evidence_scope=plain(self.prereg["evidence_scope"]))
            proposal = self.resign(self.proposal, strategy_version="1.0.3", preregistration=prereg)
            self.assertEqual("not_validated", self.assess(ledger, evaluation, proposal=proposal)["evidence_state"])

    def test_current_criterion_cannot_bind_completed_outcome_identity(self):
        criterion = {
            "criterion_id": "forbidden-post-result-selector",
            "result_ref": {
                "id": self.outcome["forward_outcome_id"],
                "content_fingerprint": self.outcome["forward_content_fingerprint"],
            },
            "field": "status", "operator": "eq", "expected": "mature",
        }
        with self.assertRaisesRegex(ContractError, "criterion"):
            build_preregistration(
                required_partitions=["validation"],
                required_result_contracts=["ForwardOutcome"],
                requires_cost_policy=False,
                criteria=[criterion],
                evidence_scope=plain(self.prereg["evidence_scope"]),
            )

    def test_user_approval_changes_decision_not_machine_evidence(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            events = self.lifecycle(assessment)
            approved = record_user_decision(self.proposal, existing_events=events, decision="approved_for_implementation", approval_ref=proof("approval", "d"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="approved intent", authority_resolver=self.lifecycle_authority)
            self.assertEqual("validated", approved["state_after"]["evidence"])
            self.assertEqual("approved_for_implementation", approved["state_after"]["decision"])
            self.assertEqual("inactive", approved["state_after"]["production"])

    def test_approval_before_validation_is_allowed_but_not_active(self):
        events = self.lifecycle()
        approved = record_user_decision(self.proposal, existing_events=events, decision="approved_for_implementation", approval_ref=proof("approval", "d"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="approve candidate implementation", authority_resolver=self.lifecycle_authority)
        self.assertEqual("candidate", approved["state_after"]["evidence"])
        with self.assertRaisesRegex(ContractError, "prerequisites"):
            record_production_activation(self.proposal, existing_events=[*events, approved], m12_manifest_proof=proof("m12-manifest", "e"), deployment_proof=proof("deployment-proof", "6"), online_verification_proof=proof("online-verification", "7"), effective_date="2026-09-05", author_id="system:m12", occurred_at="2026-09-05T12:03:00Z", reason="invalid", authority_resolver=self.lifecycle_authority)

    def test_implemented_in_main_is_not_active(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            events = self.lifecycle(assessment)
            approved = record_user_decision(self.proposal, existing_events=events, decision="approved_for_implementation", approval_ref=proof("approval", "d"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="approved", authority_resolver=self.lifecycle_authority)
            implemented = record_main_implementation(self.proposal, existing_events=[*events, approved], implementation_proof=proof("implementation-proof", "e"), test_proof=proof("test-proof", "f"), code_commit="1" * 40, rule_version="1.0.0", author_id="system:git", occurred_at="2026-09-05T12:03:00Z", reason="merged", authority_resolver=self.lifecycle_authority)
            self.assertEqual("implemented_in_main", implemented["state_after"]["implementation"])
            self.assertEqual("inactive", implemented["state_after"]["production"])

    def test_activation_requires_all_three_axes_and_m12_proof(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            events = self.lifecycle(assessment)
            approved = record_user_decision(self.proposal, existing_events=events, decision="approved_for_implementation", approval_ref=proof("approval", "d"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="approved", authority_resolver=self.lifecycle_authority)
            implemented = record_main_implementation(self.proposal, existing_events=[*events, approved], implementation_proof=proof("implementation-proof", "e"), test_proof=proof("test-proof", "f"), code_commit="1" * 40, rule_version="1.0.0", author_id="system:git", occurred_at="2026-09-05T12:03:00Z", reason="merged", authority_resolver=self.lifecycle_authority)
            active = record_production_activation(self.proposal, existing_events=[*events, approved, implemented], m12_manifest_proof=proof("m12-manifest", "1"), deployment_proof=proof("deployment-proof", "6"), online_verification_proof=proof("online-verification", "7"), effective_date="2026-09-05", author_id="system:m12", occurred_at="2026-09-05T12:04:00Z", reason="synthetic proof", authority_resolver=self.lifecycle_authority)
            self.assertEqual("active", active["state_after"]["production"])

    def test_sensitive_lifecycle_defaults_fail_closed_and_store_has_no_bypass(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            events = self.lifecycle(assessment)
            with self.assertRaisesRegex(ContractError, "trusted evidence resolver"):
                record_user_decision(
                    self.proposal, existing_events=events,
                    decision="approved_for_implementation",
                    approval_ref=proof("approval", "d"), author_id="author:user",
                    occurred_at="2026-09-05T12:02:00Z", reason="untrusted",
                )
            approved = record_user_decision(
                self.proposal, existing_events=events,
                decision="approved_for_implementation",
                approval_ref=proof("approval", "d"), author_id="author:user",
                occurred_at="2026-09-05T12:02:00Z", reason="synthetic",
                authority_resolver=self.lifecycle_authority,
            )
            implemented = record_main_implementation(
                self.proposal, existing_events=[*events, approved],
                implementation_proof=proof("implementation-proof", "e"),
                test_proof=proof("test-proof", "f"), code_commit="1" * 40,
                rule_version="1.0.0", author_id="system:git",
                occurred_at="2026-09-05T12:03:00Z", reason="synthetic",
                authority_resolver=self.lifecycle_authority,
            )
            active = record_production_activation(
                self.proposal, existing_events=[*events, approved, implemented],
                m12_manifest_proof=proof("m12-manifest", "1"),
                deployment_proof=proof("deployment-proof", "6"),
                online_verification_proof=proof("online-verification", "7"),
                effective_date="2026-09-05", author_id="system:m12",
                occurred_at="2026-09-05T12:04:00Z", reason="synthetic",
                authority_resolver=self.lifecycle_authority,
            )
            untrusted = PlaybookShadowStore(
                Path(context.name) / "untrusted-playbook",
                ledger_store=ledger, evaluation_store=evaluation,
                case_authority_resolver=self.case_authority,
                preregistration_authority_resolver=self.prereg_authority,
            )
            untrusted.write_proposal(self.proposal)
            untrusted.write_assessment(assessment)
            for item in events:
                untrusted.write_lifecycle_event(item)
            before = sorted(path.relative_to(untrusted.root) for path in untrusted.root.rglob("*.json"))
            with self.assertRaisesRegex(ContractError, "trusted evidence resolver"):
                untrusted.write_lifecycle_event(approved)
            with self.assertRaisesRegex(ContractError, "trusted evidence resolver"):
                untrusted.write_lifecycle_event(active)
            with self.assertRaisesRegex(ContractError, "trusted evidence resolver"):
                record_retirement(
                    self.proposal,
                    existing_events=[*events, approved, implemented, active],
                    retirement_proof=proof("retirement-proof", "2"),
                    effective_date="2026-09-05", author_id="system:m12",
                    occurred_at="2026-09-05T12:05:00Z", reason="untrusted",
                )
            after = sorted(path.relative_to(untrusted.root) for path in untrusted.root.rglob("*.json"))
            self.assertEqual(before, after)

    def test_trusted_synthetic_lifecycle_can_persist_but_real_default_active_is_zero(self):
        context, ledger, evaluation, store = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            events = self.lifecycle(assessment)
            approved = record_user_decision(
                self.proposal, existing_events=events,
                decision="approved_for_implementation",
                approval_ref=proof("approval", "d"), author_id="author:user",
                occurred_at="2026-09-05T12:02:00Z", reason="synthetic",
                authority_resolver=self.lifecycle_authority,
            )
            implemented = record_main_implementation(
                self.proposal, existing_events=[*events, approved],
                implementation_proof=proof("implementation-proof", "e"),
                test_proof=proof("test-proof", "f"), code_commit="1" * 40,
                rule_version="1.0.0", author_id="system:git",
                occurred_at="2026-09-05T12:03:00Z", reason="synthetic",
                authority_resolver=self.lifecycle_authority,
            )
            active = record_production_activation(
                self.proposal, existing_events=[*events, approved, implemented],
                m12_manifest_proof=proof("m12-manifest", "1"),
                deployment_proof=proof("deployment-proof", "6"),
                online_verification_proof=proof("online-verification", "7"),
                effective_date="2026-09-05", author_id="system:m12",
                occurred_at="2026-09-05T12:04:00Z", reason="synthetic",
                authority_resolver=self.lifecycle_authority,
            )
            store.write_proposal(self.proposal)
            store.write_assessment(assessment)
            for item in [*events, approved, implemented, active]:
                store.write_lifecycle_event(item)
            snapshot, _ = store.derive_and_write_registry_snapshot(
                as_of="2026-09-05", generated_at="2026-09-05T13:00:00Z",
                code_commit="1" * 40,
            )
            self.assertEqual(1, snapshot["active_count"])
        self.assertEqual(
            0,
            empty_current_registry(
                as_of="2026-09-05", generated_at="2026-09-05T13:00:00Z",
                code_commit="1" * 40,
            )["active_count"],
        )

    def test_retirement_preserves_history_and_cannot_reactivate(self):
        context, ledger, evaluation, _ = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            events = self.lifecycle(assessment)
            approved = record_user_decision(self.proposal, existing_events=events, decision="approved_for_implementation", approval_ref=proof("approval", "d"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="approved", authority_resolver=self.lifecycle_authority)
            implemented = record_main_implementation(self.proposal, existing_events=[*events, approved], implementation_proof=proof("implementation-proof", "e"), test_proof=proof("test-proof", "f"), code_commit="1" * 40, rule_version="1.0.0", author_id="system:git", occurred_at="2026-09-05T12:03:00Z", reason="merged", authority_resolver=self.lifecycle_authority)
            active = record_production_activation(self.proposal, existing_events=[*events, approved, implemented], m12_manifest_proof=proof("m12-manifest", "1"), deployment_proof=proof("deployment-proof", "6"), online_verification_proof=proof("online-verification", "7"), effective_date="2026-09-05", author_id="system:m12", occurred_at="2026-09-05T12:04:00Z", reason="synthetic proof", authority_resolver=self.lifecycle_authority)
            chain = [*events, approved, implemented, active]
            retired = record_retirement(self.proposal, existing_events=chain, retirement_proof=proof("retirement-proof", "2"), effective_date="2026-09-05", author_id="system:m12", occurred_at="2026-09-05T12:05:00Z", reason="retired", authority_resolver=self.lifecycle_authority)
            self.assertEqual("retired", retired["state_after"]["production"])
            with self.assertRaisesRegex(ContractError, "retired"):
                record_user_decision(self.proposal, existing_events=[*chain, retired], decision="deferred", approval_ref=proof("approval", "3"), author_id="author:user", occurred_at="2026-09-05T12:06:00Z", reason="cannot revive", authority_resolver=self.lifecycle_authority)

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
        first = record_user_decision(self.proposal, existing_events=[root], decision="deferred", approval_ref=proof("approval", "4"), author_id="author:user", occurred_at="2026-09-05T12:01:00Z", reason="defer", authority_resolver=self.lifecycle_authority)
        second = record_user_decision(self.proposal, existing_events=[root], decision="rejected", approval_ref=proof("approval", "5"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="reject", authority_resolver=self.lifecycle_authority)
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
            first = record_user_decision(self.proposal, existing_events=[root], decision="deferred", approval_ref=proof("approval", "4"), author_id="author:user", occurred_at="2026-09-05T12:01:00Z", reason="defer", authority_resolver=self.lifecycle_authority)
            second = record_user_decision(self.proposal, existing_events=[root], decision="rejected", approval_ref=proof("approval", "5"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="reject", authority_resolver=self.lifecycle_authority)
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
                record_user_decision(self.proposal, existing_events=[root], decision=decision, approval_ref=proof("approval", digit), author_id="author:user", occurred_at=f"2026-09-05T12:0{index}:00Z", reason=decision, authority_resolver=self.lifecycle_authority)
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

    def test_registry_public_store_rejects_resigned_incomplete_inventory(self):
        context, _, _, store = self.seeded()
        with context:
            second = self.resign(self.proposal, strategy_version="2.0.0")
            store.write_proposal(self.proposal)
            store.write_proposal(second)
            omitted = derive_strategy_registry_snapshot(
                [self.proposal], [], [], as_of="2026-09-05",
                generated_at="2026-09-05T13:00:00Z", code_commit="1" * 40,
            )
            before = sorted(path.read_bytes() for path in store.root.rglob("*.json"))
            with self.assertRaisesRegex(ContractError, "complete M11 authority inventory"):
                store.write_registry_snapshot(omitted)
            self.assertEqual(
                before, sorted(path.read_bytes() for path in store.root.rglob("*.json"))
            )
            complete, path = store.derive_and_write_registry_snapshot(
                as_of="2026-09-05", generated_at="2026-09-05T13:00:00Z",
                code_commit="1" * 40,
            )
            replay, replay_path = store.derive_and_write_registry_snapshot(
                as_of="2026-09-05", generated_at="2026-09-05T13:00:00Z",
                code_commit="1" * 40,
            )
            self.assertEqual(2, len(complete["entries"]))
            self.assertEqual((complete, path), (replay, replay_path))

    def test_registry_rejects_omitted_assessment_and_lifecycle_sources(self):
        context, ledger, evaluation, store = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            events = self.lifecycle(assessment)
            store.write_proposal(self.proposal)
            store.write_assessment(assessment)
            for event in events:
                store.write_lifecycle_event(event)
            complete = derive_strategy_registry_snapshot(
                [self.proposal], [assessment], events, as_of="2026-09-05",
                generated_at="2026-09-05T13:00:00Z", code_commit="1" * 40,
            )
            without_assessment = derive_strategy_registry_snapshot(
                [self.proposal], [], events, as_of="2026-09-05",
                generated_at="2026-09-05T13:00:00Z", code_commit="1" * 40,
            )
            without_lifecycle = plain(complete)
            without_lifecycle["source_refs"] = [
                item for item in without_lifecycle["source_refs"]
                if not item["id"].startswith("strategy-lifecycle:")
            ]
            without_lifecycle["entries"][0]["current_lifecycle_ref"] = None
            without_lifecycle = resign_snapshot(without_lifecycle)
            attacks = (without_assessment, without_lifecycle)
            before = {
                str(path.relative_to(store.root)): path.read_bytes()
                for path in store.root.rglob("*.json")
            }
            for attack in attacks:
                with self.subTest(source_count=len(attack["source_refs"])):
                    with self.assertRaisesRegex(ContractError, "complete M11 authority inventory"):
                        store.write_registry_snapshot(attack)
            self.assertEqual(
                before,
                {
                    str(path.relative_to(store.root)): path.read_bytes()
                    for path in store.root.rglob("*.json")
                },
            )

    def test_registry_rejects_each_omitted_lifecycle_transition(self):
        context, ledger, evaluation, store = self.seeded()
        with context:
            assessment = self.assess(ledger, evaluation)
            events = self.lifecycle(assessment)
            approved = record_user_decision(
                self.proposal, existing_events=events,
                decision="approved_for_implementation",
                approval_ref=proof("approval", "d"), author_id="author:user",
                occurred_at="2026-09-05T12:02:00Z", reason="synthetic",
                authority_resolver=self.lifecycle_authority,
            )
            implemented = record_main_implementation(
                self.proposal, existing_events=[*events, approved],
                implementation_proof=proof("implementation-proof", "e"),
                test_proof=proof("test-proof", "f"), code_commit="1" * 40,
                rule_version="1.0.0", author_id="system:git",
                occurred_at="2026-09-05T12:03:00Z", reason="synthetic",
                authority_resolver=self.lifecycle_authority,
            )
            active = record_production_activation(
                self.proposal, existing_events=[*events, approved, implemented],
                m12_manifest_proof=proof("m12-manifest", "1"),
                deployment_proof=proof("deployment-proof", "6"),
                online_verification_proof=proof("online-verification", "7"),
                effective_date="2026-09-05", author_id="system:m12",
                occurred_at="2026-09-05T12:04:00Z", reason="synthetic",
                authority_resolver=self.lifecycle_authority,
            )
            chain = [*events, approved, implemented, active]
            retired = record_retirement(
                self.proposal, existing_events=chain,
                retirement_proof=proof("retirement-proof", "2"),
                effective_date="2026-09-05", author_id="system:m12",
                occurred_at="2026-09-05T12:05:00Z", reason="synthetic",
                authority_resolver=self.lifecycle_authority,
            )
            chain.append(retired)
            store.write_proposal(self.proposal)
            store.write_assessment(assessment)
            for event in chain:
                store.write_lifecycle_event(event)
            complete = derive_strategy_registry_snapshot(
                [self.proposal], [assessment], chain, as_of="2026-09-05",
                generated_at="2026-09-05T13:00:00Z", code_commit="1" * 40,
            )
            before = {
                str(path.relative_to(store.root)): path.read_bytes()
                for path in store.root.rglob("*.json")
            }
            for omitted in (approved, implemented, active, retired):
                attack = plain(complete)
                attack["source_refs"] = [
                    item for item in attack["source_refs"]
                    if item["id"] != omitted["lifecycle_event_id"]
                ]
                attack = resign_snapshot(attack)
                with self.subTest(event_type=omitted["event_type"]), self.assertRaisesRegex(
                    ContractError, "complete M11 authority inventory"
                ):
                    store.write_registry_snapshot(attack)
            self.assertEqual(
                before,
                {
                    str(path.relative_to(store.root)): path.read_bytes()
                    for path in store.root.rglob("*.json")
                },
            )

    def test_concurrent_registry_derivation_has_one_complete_snapshot(self):
        context, _, _, store = self.seeded()
        with context:
            store.write_proposal(self.proposal)

            def derive(_):
                return store.derive_and_write_registry_snapshot(
                    as_of="2026-09-05", generated_at="2026-09-05T13:00:00Z",
                    code_commit="1" * 40,
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(derive, range(2)))
            self.assertEqual(results[0], results[1])
            self.assertEqual(1, len(list((store.root / "registry-snapshots").glob("*.json"))))

    def test_registry_distinguishes_approved_unvalidated_and_validated_unapproved(self):
        approved = record_user_decision(self.proposal, existing_events=self.lifecycle(), decision="approved_for_implementation", approval_ref=proof("approval", "d"), author_id="author:user", occurred_at="2026-09-05T12:02:00Z", reason="approved", authority_resolver=self.lifecycle_authority)
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
        v2 = self.resign(self.proposal, strategy_version="2.0.0")
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
