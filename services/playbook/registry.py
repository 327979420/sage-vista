"""Deterministic read-only StrategyRegistrySnapshot derivation."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError

from .contracts import (
    SCHEMA_VERSION,
    SOURCE_VERSION,
    current_strategy_assessment,
    current_strategy_lifecycle,
    freeze,
    initial_state,
    plain,
    validate_strategy_evidence_assessment,
    validate_strategy_lifecycle_event,
    validate_strategy_proposal,
    validate_strategy_registry_snapshot,
)


def derive_strategy_registry_snapshot(
    proposals: Iterable[Mapping[str, Any]],
    assessments: Iterable[Mapping[str, Any]],
    lifecycle_events: Iterable[Mapping[str, Any]],
    *,
    as_of: str,
    generated_at: str,
    code_commit: str,
) -> Mapping[str, Any]:
    """Rebuild current axes from the three immutable authority record types."""

    proposal_items = list(proposals)
    assessment_items = list(assessments)
    event_items = list(lifecycle_events)
    by_proposal: dict[str, Mapping[str, Any]] = {}
    for proposal in proposal_items:
        validate_strategy_proposal(proposal)
        proposal_id = str(proposal["proposal_id"])
        if proposal_id in by_proposal:
            raise ContractError("registry source contains duplicate proposals")
        by_proposal[proposal_id] = proposal
    assessment_groups: dict[str, list[Mapping[str, Any]]] = {}
    for assessment in assessment_items:
        validate_strategy_evidence_assessment(assessment)
        proposal_id = str(assessment["proposal_id"])
        if proposal_id not in by_proposal:
            raise ContractError("registry assessment lacks its proposal")
        if assessment["proposal_content_fingerprint"] != by_proposal[proposal_id]["proposal_content_fingerprint"]:
            raise ContractError("registry assessment proposal fingerprint is stale")
        assessment_groups.setdefault(proposal_id, []).append(assessment)
    event_groups: dict[str, list[Mapping[str, Any]]] = {}
    for event in event_items:
        validate_strategy_lifecycle_event(event)
        proposal_id = str(event["proposal_id"])
        if proposal_id not in by_proposal:
            raise ContractError("registry lifecycle lacks its proposal")
        if event["proposal_content_fingerprint"] != by_proposal[proposal_id]["proposal_content_fingerprint"]:
            raise ContractError("registry lifecycle proposal fingerprint is stale")
        event_groups.setdefault(proposal_id, []).append(event)

    entries: list[dict[str, Any]] = []
    source_refs: list[dict[str, str]] = []
    for proposal_id, proposal in by_proposal.items():
        source_refs.append({"id": proposal_id, "content_fingerprint": proposal["proposal_content_fingerprint"]})
        assessment_ref = None
        assessment_leaf = None
        if proposal_id in assessment_groups:
            assessment_leaf = current_strategy_assessment(assessment_groups[proposal_id])
            for assessment in assessment_groups[proposal_id]:
                source_refs.append({"id": assessment["assessment_id"], "content_fingerprint": assessment["assessment_content_fingerprint"]})
            assessment_ref = {"id": assessment_leaf["assessment_id"], "content_fingerprint": assessment_leaf["assessment_content_fingerprint"]}
        state = initial_state()
        lifecycle_ref = None
        if proposal_id in event_groups:
            lifecycle_leaf = current_strategy_lifecycle(event_groups[proposal_id])
            for event in event_groups[proposal_id]:
                source_refs.append({"id": event["lifecycle_event_id"], "content_fingerprint": event["lifecycle_content_fingerprint"]})
            state = plain(lifecycle_leaf["state_after"])
            lifecycle_ref = {"id": lifecycle_leaf["lifecycle_event_id"], "content_fingerprint": lifecycle_leaf["lifecycle_content_fingerprint"]}
        if assessment_leaf is not None and state["evidence"] != assessment_leaf["evidence_state"]:
            raise ContractError("registry lifecycle does not reflect current assessment")
        entries.append({
            "proposal_ref": {"id": proposal_id, "content_fingerprint": proposal["proposal_content_fingerprint"]},
            "strategy_id": proposal["strategy_id"], "strategy_version": proposal["strategy_version"],
            "proposal_kind": proposal["proposal_kind"],
            "evidence_state": state["evidence"], "decision_state": state["decision"],
            "implementation_state": state["implementation"], "production_state": state["production"],
            "current_assessment_ref": assessment_ref, "current_lifecycle_ref": lifecycle_ref,
        })
    entries.sort(key=lambda item: (item["strategy_id"], item["strategy_version"]))
    source_refs.sort(key=lambda item: (item["id"], item["content_fingerprint"]))
    source_set_fingerprint = canonical_fingerprint(source_refs)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "as_of": as_of, "generated_at": generated_at,
        "source_version": {"playbook": SOURCE_VERSION}, "future_data_used": False,
        "source_refs": source_refs, "source_set_fingerprint": source_set_fingerprint,
        "entries": entries,
        "formal_validated_count": sum(item["evidence_state"] == "validated" for item in entries),
        "active_count": sum(item["production_state"] == "active" for item in entries),
        "alpha_risk_hard_rule_count": sum(item["proposal_kind"] == "alpha_risk_hard_rule_candidate" and item["production_state"] == "active" for item in entries),
        "code_commit": code_commit,
    }
    payload["registry_snapshot_id"] = "strategy-registry:" + canonical_fingerprint({"as_of": as_of, "source_set_fingerprint": source_set_fingerprint, "code_commit": code_commit})
    payload["registry_content_fingerprint"] = canonical_fingerprint({key: plain(value) for key, value in payload.items() if key not in {"generated_at", "registry_content_fingerprint"}})
    validate_strategy_registry_snapshot(payload)
    return freeze(payload)


def empty_current_registry(*, as_of: str, generated_at: str, code_commit: str) -> Mapping[str, Any]:
    """Truthful current-repository view: no records means no promoted strategies."""

    return derive_strategy_registry_snapshot((), (), (), as_of=as_of, generated_at=generated_at, code_commit=code_commit)


__all__ = ["derive_strategy_registry_snapshot", "empty_current_registry"]
