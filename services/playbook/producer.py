"""Sole M11 producer for proposals and append-only lifecycle facts."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from services.contracts.validation import ContractError
from services.ledger import validate_opportunity_event

from .authority import (
    CaseAuthorityResolver,
    LifecycleAuthorityResolver,
    PreregistrationAuthorityResolver,
    resolve_case_authority,
    validate_case_authority,
    validate_preregistration_authority,
    validate_sensitive_lifecycle_authority,
)

from .contracts import (
    build_strategy_lifecycle_event,
    build_strategy_proposal,
    current_strategy_lifecycle,
    initial_state,
    plain,
    validate_strategy_evidence_assessment,
    validate_strategy_proposal,
)


def produce_strategy_proposal(
    *, persisted_case_events: Sequence[Mapping[str, Any]],
    case_authority_resolver: CaseAuthorityResolver | None,
    preregistration_authority_resolver: PreregistrationAuthorityResolver | None = None,
    **values: Any,
) -> Mapping[str, Any]:
    """Create a candidate proposal; this never claims validation or activation."""

    events: dict[str, Mapping[str, Any]] = {}
    for event in persisted_case_events:
        validate_opportunity_event(event)
        event_id = str(event["event_id"])
        if event_id in events:
            raise ContractError("proposal case authority contains duplicate M09 events")
        events[event_id] = event
    resolved_cases: list[dict[str, Any]] = []
    for declared in values.get("case_roles", []):
        if not isinstance(declared, Mapping) or set(declared) != {
            "event_id", "case_label", "role",
        }:
            raise ContractError(
                "proposal producer accepts only event_id, case_label, and role; "
                "stable case identity is authority-derived"
            )
        event = events.get(str(declared["event_id"]))
        if event is None:
            raise ContractError("proposal case event is not in persisted authority input")
        authority = resolve_case_authority(event, case_authority_resolver)
        resolved_case = {
            **authority,
            "case_label": declared["case_label"],
            "role": declared["role"],
        }
        validate_case_authority(resolved_case, event, case_authority_resolver)
        resolved_cases.append(resolved_case)
    values["case_roles"] = resolved_cases
    proposal = build_strategy_proposal(**values)
    validate_preregistration_authority(
        proposal, preregistration_authority_resolver
    )
    return proposal


def _ref(item: Mapping[str, Any], id_field: str, fingerprint_field: str) -> dict[str, str]:
    return {"id": str(item[id_field]), "content_fingerprint": str(item[fingerprint_field])}


def _next_event(
    proposal: Mapping[str, Any],
    *,
    existing_events: Sequence[Mapping[str, Any]],
    event_type: str,
    new_value: str,
    author_id: str,
    occurred_at: str,
    reason: str,
    evidence_refs: Sequence[Mapping[str, Any]] = (),
    assessment: Mapping[str, Any] | None = None,
    implementation_evidence: Mapping[str, Any] | None = None,
    activation_evidence: Mapping[str, Any] | None = None,
    retirement_evidence: Mapping[str, Any] | None = None,
    authority_resolver: LifecycleAuthorityResolver | None = None,
) -> Mapping[str, Any]:
    validate_strategy_proposal(proposal)
    for existing in existing_events:
        validate_sensitive_lifecycle_authority(
            proposal, existing, authority_resolver
        )
    if existing_events:
        leaf = current_strategy_lifecycle(existing_events)
        if leaf["proposal_id"] != proposal["proposal_id"]:
            raise ContractError("lifecycle event crosses proposals")
        before = plain(leaf["state_after"])
        prior = leaf["lifecycle_event_id"]
    else:
        if event_type != "proposal_registered":
            raise ContractError("lifecycle must begin with proposal registration")
        before = None
        prior = None
    axis = {
        "proposal_registered": "evidence",
        "evidence_assessed": "evidence",
        "user_decision_recorded": "decision",
        "implementation_recorded": "implementation",
        "production_activation_recorded": "production",
        "retirement_recorded": "production",
    }[event_type]
    after = initial_state() if before is None else dict(before)
    after[axis] = new_value
    if before is not None and before["production"] == "retired":
        raise ContractError("retired strategy version cannot be changed or reactivated")
    if event_type == "production_activation_recorded" and (
        after["evidence"] != "validated"
        or after["decision"] != "approved_for_implementation"
        or after["implementation"] != "implemented_in_main"
    ):
        raise ContractError("production activation prerequisites are not met")
    assessment_ref = None
    if assessment is not None:
        validate_strategy_evidence_assessment(assessment)
        if (
            assessment["proposal_id"] != proposal["proposal_id"]
            or assessment["proposal_content_fingerprint"] != proposal["proposal_content_fingerprint"]
            or assessment["strategy_id"] != proposal["strategy_id"]
            or assessment["strategy_version"] != proposal["strategy_version"]
        ):
            raise ContractError("lifecycle assessment crosses proposals")
        assessment_ref = _ref(assessment, "assessment_id", "assessment_content_fingerprint")
    event = build_strategy_lifecycle_event(
        as_of=occurred_at[:10], generated_at=occurred_at,
        proposal_id=proposal["proposal_id"],
        proposal_content_fingerprint=proposal["proposal_content_fingerprint"],
        strategy_id=proposal["strategy_id"], strategy_version=proposal["strategy_version"],
        event_type=event_type, changed_axis=axis,
        state_before=before, state_after=after,
        supersedes_lifecycle_event_id=prior, assessment_ref=assessment_ref,
        evidence_refs=evidence_refs,
        implementation_evidence=implementation_evidence,
        activation_evidence=activation_evidence,
        retirement_evidence=retirement_evidence,
        author_id=author_id,
        occurred_at=occurred_at, reason=reason, bias_labels=[],
    )
    validate_sensitive_lifecycle_authority(proposal, event, authority_resolver)
    return event


def register_strategy_proposal(
    proposal: Mapping[str, Any], *, author_id: str, occurred_at: str
) -> Mapping[str, Any]:
    return _next_event(
        proposal, existing_events=(), event_type="proposal_registered",
        new_value="candidate", author_id=author_id, occurred_at=occurred_at,
        reason="proposal_registered",
    )


def record_evidence_assessment(
    proposal: Mapping[str, Any], assessment: Mapping[str, Any], *,
    existing_events: Sequence[Mapping[str, Any]], author_id: str, occurred_at: str,
    authority_resolver: LifecycleAuthorityResolver | None = None,
) -> Mapping[str, Any]:
    return _next_event(
        proposal, existing_events=existing_events, event_type="evidence_assessed",
        new_value=str(assessment["evidence_state"]), author_id=author_id,
        occurred_at=occurred_at, reason="machine_evidence_assessed", assessment=assessment,
        evidence_refs=[_ref(assessment, "assessment_id", "assessment_content_fingerprint")],
        authority_resolver=authority_resolver,
    )


def record_user_decision(
    proposal: Mapping[str, Any], *, existing_events: Sequence[Mapping[str, Any]],
    decision: str, approval_ref: Mapping[str, Any], author_id: str,
    occurred_at: str, reason: str,
    authority_resolver: LifecycleAuthorityResolver | None = None,
) -> Mapping[str, Any]:
    if decision not in {"approved_for_implementation", "rejected", "deferred"}:
        raise ContractError("user decision is invalid")
    return _next_event(
        proposal, existing_events=existing_events, event_type="user_decision_recorded",
        new_value=decision, author_id=author_id, occurred_at=occurred_at,
        reason=reason, evidence_refs=[approval_ref],
        authority_resolver=authority_resolver,
    )


def record_main_implementation(
    proposal: Mapping[str, Any], *, existing_events: Sequence[Mapping[str, Any]],
    implementation_proof: Mapping[str, Any], test_proof: Mapping[str, Any],
    code_commit: str, rule_version: str,
    author_id: str, occurred_at: str, reason: str,
    authority_resolver: LifecycleAuthorityResolver | None = None,
) -> Mapping[str, Any]:
    leaf = current_strategy_lifecycle(existing_events)
    if leaf["state_after"]["decision"] != "approved_for_implementation":
        raise ContractError("main implementation requires explicit user approval")
    return _next_event(
        proposal, existing_events=existing_events, event_type="implementation_recorded",
        new_value="implemented_in_main", author_id=author_id, occurred_at=occurred_at,
        reason=reason, evidence_refs=[implementation_proof, test_proof],
        implementation_evidence={
            "code_commit": code_commit,
            "rule_version": rule_version,
            "implementation_ref": implementation_proof,
            "test_ref": test_proof,
        },
        authority_resolver=authority_resolver,
    )


def record_production_activation(
    proposal: Mapping[str, Any], *, existing_events: Sequence[Mapping[str, Any]],
    m12_manifest_proof: Mapping[str, Any], deployment_proof: Mapping[str, Any],
    online_verification_proof: Mapping[str, Any], effective_date: str,
    author_id: str, occurred_at: str, reason: str,
    authority_resolver: LifecycleAuthorityResolver | None = None,
) -> Mapping[str, Any]:
    """Consume an M12 proof; M11 never creates that proof itself."""

    return _next_event(
        proposal, existing_events=existing_events,
        event_type="production_activation_recorded", new_value="active",
        author_id=author_id, occurred_at=occurred_at, reason=reason,
        evidence_refs=[m12_manifest_proof, deployment_proof, online_verification_proof],
        activation_evidence={
            "manifest_ref": m12_manifest_proof,
            "deployment_ref": deployment_proof,
            "online_verification_ref": online_verification_proof,
            "effective_date": effective_date,
        },
        authority_resolver=authority_resolver,
    )


def record_retirement(
    proposal: Mapping[str, Any], *, existing_events: Sequence[Mapping[str, Any]],
    retirement_proof: Mapping[str, Any], effective_date: str,
    replacement_strategy_version: str | None = None,
    author_id: str, occurred_at: str, reason: str,
    authority_resolver: LifecycleAuthorityResolver | None = None,
) -> Mapping[str, Any]:
    leaf = current_strategy_lifecycle(existing_events)
    if leaf["state_after"]["production"] != "active":
        raise ContractError("only an active strategy version can be retired")
    return _next_event(
        proposal, existing_events=existing_events, event_type="retirement_recorded",
        new_value="retired", author_id=author_id, occurred_at=occurred_at,
        reason=reason, evidence_refs=[retirement_proof],
        retirement_evidence={
            "retirement_ref": retirement_proof,
            "effective_date": effective_date,
            "replacement_strategy_version": replacement_strategy_version,
        },
        authority_resolver=authority_resolver,
    )


__all__ = [
    "produce_strategy_proposal", "record_evidence_assessment",
    "record_main_implementation", "record_production_activation",
    "record_retirement", "record_user_decision", "register_strategy_proposal",
]
