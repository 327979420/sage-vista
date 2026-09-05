"""M11 strategy promotion contracts and deterministic lifecycle rules.

This module is pure: it performs no file, market, Git, clock, or network I/O.
"""

from __future__ import annotations

from datetime import date, datetime
import math
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError


SCHEMA_VERSION = "2.0.0"
SOURCE_VERSION = "m11-shadow-1.0.0"
EVIDENCE_GATE_POLICY_VERSION = "1.0.0"

EVIDENCE_STATES = frozenset({
    "candidate", "evidence_incomplete", "not_validated", "validated", "invalidated",
})
DECISION_STATES = frozenset({
    "not_requested", "approved_for_implementation", "rejected", "deferred",
})
IMPLEMENTATION_STATES = frozenset({"not_implemented", "implemented_in_main"})
PRODUCTION_STATES = frozenset({"inactive", "active", "retired"})
CASE_ROLES = frozenset({
    "discovery", "calibration", "validation", "forward", "explanation_only",
})
KNOWN_SEEN_CASES = frozenset({"CGEM", "MRNA", "BTDR", "DLTR", "ADBE", "BABA", "TTD", "AEVA"})

_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID = re.compile(r"^[a-z][a-z0-9-]*:(?:sha256:)?[0-9a-f]{64}$")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    return value


def _exact(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ContractError(f"{label} must contain exactly {', '.join(sorted(fields))}")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ContractError(f"{field} must be stable non-empty text")
    return value


def _date(value: Any, field: str) -> str:
    text = _text(value, field)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise ContractError(f"{field} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != text:
        raise ContractError(f"{field} must be canonical YYYY-MM-DD")
    return text


def _timestamp(value: Any, field: str) -> str:
    text = _text(value, field)
    if not text.endswith("Z"):
        raise ContractError(f"{field} must be UTC ISO-8601")
    try:
        datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{field} must be UTC ISO-8601") from exc
    return text


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ContractError(f"{field} must be sha256:<64 lowercase hex>")
    return value


def _stable_id(value: Any, field: str, prefixes: set[str] | None = None) -> str:
    text = _text(value, field)
    if not _STABLE_ID.fullmatch(text):
        raise ContractError(f"{field} must be a complete content-addressed ID")
    role = text.split(":", 1)[0]
    if prefixes is not None and role not in prefixes:
        raise ContractError(f"{field} has the wrong reference role")
    return text


def _semver(value: Any, field: str) -> str:
    text = _text(value, field)
    if not _SEMVER.fullmatch(text):
        raise ContractError(f"{field} must be strict SemVer")
    return text


def _finite(value: Any, field: str) -> float | int | str | bool | None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError(f"{field} must be finite")
    if value is not None and not isinstance(value, (str, int, float, bool)):
        raise ContractError(f"{field} must be a scalar")
    return value


def _sorted_unique_text(value: Any, field: str, allowed: set[str] | frozenset[str] | None = None) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise ContractError(f"{field} must be a list")
    items = [_text(item, field) for item in value]
    if items != sorted(set(items)):
        raise ContractError(f"{field} must be sorted and unique")
    if allowed is not None and not set(items).issubset(allowed):
        raise ContractError(f"{field} contains an unknown value")
    return items


def _semantic(payload: Mapping[str, Any], fingerprint_field: str) -> dict[str, Any]:
    return {
        key: plain(value)
        for key, value in payload.items()
        if key not in {"generated_at", fingerprint_field}
    }


def _validate_common(payload: Mapping[str, Any], contract: str) -> None:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(f"{contract} requires schema 2.0.0")
    _date(payload.get("as_of"), f"{contract}.as_of")
    _timestamp(payload.get("generated_at"), f"{contract}.generated_at")
    _exact(payload.get("source_version"), {"playbook"}, f"{contract}.source_version")
    if payload["source_version"]["playbook"] != SOURCE_VERSION:
        raise ContractError(f"{contract} source version is unknown")
    if payload.get("future_data_used") is not False:
        raise ContractError(f"{contract} must fail closed on future data")


def _validate_ref(value: Any, field: str, roles: set[str] | None = None) -> Mapping[str, Any]:
    ref = _exact(value, {"id", "content_fingerprint"}, field)
    _stable_id(ref["id"], f"{field}.id", roles)
    _sha(ref["content_fingerprint"], f"{field}.content_fingerprint")
    return ref


def _normalize_refs(values: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    refs = [plain(item) for item in values]
    return sorted(refs, key=lambda item: (item["id"], item["content_fingerprint"]))


def _validate_refs(value: Any, field: str, roles: set[str] | None = None, *, allow_empty: bool = False) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)) or (not value and not allow_empty):
        raise ContractError(f"{field} must be a non-empty reference list")
    refs = [_validate_ref(item, field, roles) for item in value]
    keys = [(str(item["id"]), str(item["content_fingerprint"])) for item in refs]
    if keys != sorted(set(keys)):
        raise ContractError(f"{field} must be sorted and unique")
    return refs


PROPOSAL_FIELDS = {
    "schema_version", "as_of", "generated_at", "source_version", "future_data_used",
    "proposal_id", "proposal_content_fingerprint", "strategy_id", "strategy_key",
    "strategy_version", "proposal_kind", "candidate_version", "baseline_version",
    "definition", "affected_modules", "applicability", "m09_review_refs",
    "case_roles", "preregistration", "created_by", "created_at", "bias_labels",
}


def _proposal_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"strategy_id": payload["strategy_id"], "strategy_version": payload["strategy_version"]}


def _validate_definition(value: Any) -> None:
    item = _exact(value, {"rule_id", "description", "definition_fingerprint"}, "definition")
    _text(item["rule_id"], "definition.rule_id")
    _text(item["description"], "definition.description")
    _sha(item["definition_fingerprint"], "definition.definition_fingerprint")


def _validate_applicability(value: Any) -> None:
    item = _exact(value, {"universe_scope", "market_scope", "timeframes"}, "applicability")
    _text(item["universe_scope"], "applicability.universe_scope")
    _text(item["market_scope"], "applicability.market_scope")
    _sorted_unique_text(item["timeframes"], "applicability.timeframes")


def _validate_preregistration(value: Any) -> None:
    item = _exact(value, {
        "preregistration_id", "content_fingerprint", "required_partitions",
        "required_result_contracts", "requires_cost_policy", "criteria",
    }, "preregistration")
    _stable_id(item["preregistration_id"], "preregistration.id", {"strategy-preregistration"})
    _sha(item["content_fingerprint"], "preregistration.content_fingerprint")
    _sorted_unique_text(item["required_partitions"], "required_partitions", {"development", "validation", "forward"})
    _sorted_unique_text(item["required_result_contracts"], "required_result_contracts", {"ForwardOutcome", "TradeOutcome", "PortfolioRun", "ResearchAggregate"})
    if not isinstance(item["requires_cost_policy"], bool):
        raise ContractError("requires_cost_policy must be boolean")
    criteria = item["criteria"]
    if not isinstance(criteria, (list, tuple)) or not criteria:
        raise ContractError("preregistration requires criteria")
    ids: list[str] = []
    for criterion in criteria:
        criterion = _exact(criterion, {"criterion_id", "result_ref", "field", "operator", "expected"}, "criterion")
        ids.append(_text(criterion["criterion_id"], "criterion_id"))
        _validate_ref(criterion["result_ref"], "criterion.result_ref", {"forward-outcome", "trade-outcome", "portfolio-run", "research-aggregate"})
        _text(criterion["field"], "criterion.field")
        if criterion["operator"] not in {"eq", "gte", "lte"}:
            raise ContractError("criterion operator is unknown")
        _finite(criterion["expected"], "criterion.expected")
    if ids != sorted(set(ids)):
        raise ContractError("criteria must be sorted and unique")
    semantic = {key: plain(child) for key, child in item.items() if key not in {"preregistration_id", "content_fingerprint"}}
    expected_fp = canonical_fingerprint(semantic)
    if item["content_fingerprint"] != expected_fp:
        raise ContractError("preregistration content fingerprint is invalid")
    if item["preregistration_id"] != "strategy-preregistration:" + expected_fp:
        raise ContractError("preregistration identity is invalid")


def validate_strategy_proposal(payload: Mapping[str, Any]) -> None:
    _exact(payload, PROPOSAL_FIELDS, "StrategyProposal")
    _validate_common(payload, "StrategyProposal")
    _stable_id(payload["proposal_id"], "proposal_id", {"strategy-proposal"})
    _stable_id(payload["strategy_id"], "strategy_id", {"strategy"})
    _text(payload["strategy_key"], "strategy_key")
    _semver(payload["strategy_version"], "strategy_version")
    _semver(payload["candidate_version"], "candidate_version")
    _semver(payload["baseline_version"], "baseline_version")
    if payload["proposal_kind"] not in {"playbook_candidate", "alpha_risk_hard_rule_candidate"}:
        raise ContractError("proposal_kind is invalid")
    _validate_definition(payload["definition"])
    _sorted_unique_text(payload["affected_modules"], "affected_modules")
    _validate_applicability(payload["applicability"])
    reviews = payload["m09_review_refs"]
    if not isinstance(reviews, (list, tuple)) or not reviews:
        raise ContractError("StrategyProposal requires persisted M09 review references")
    review_ids: list[str] = []
    for review in reviews:
        review = _exact(review, {"id", "content_fingerprint", "review_type"}, "m09_review_ref")
        review_ids.append(_stable_id(review["id"], "review.id", {"human-review"}))
        _sha(review["content_fingerprint"], "review.content_fingerprint")
        if review["review_type"] not in {"hypothesis", "approved_change"}:
            raise ContractError("only M09 hypothesis or approved_change can source a proposal")
    if review_ids != sorted(set(review_ids)):
        raise ContractError("M09 review references must be sorted and unique")
    case_ids: list[str] = []
    for case in payload["case_roles"]:
        case = _exact(case, {"event_id", "case_label", "role", "seen_before"}, "case_role")
        case_ids.append(_stable_id(case["event_id"], "case.event_id", {"opportunity"}))
        label = _text(case["case_label"], "case_label")
        if case["role"] not in CASE_ROLES or not isinstance(case["seen_before"], bool):
            raise ContractError("case role is invalid")
        if label in KNOWN_SEEN_CASES and (not case["seen_before"] or case["role"] in {"validation", "forward"}):
            raise ContractError("known seen case cannot masquerade as independent evidence")
    if case_ids != sorted(set(case_ids)):
        raise ContractError("case roles must be sorted and unique by event")
    _validate_preregistration(payload["preregistration"])
    _text(payload["created_by"], "created_by")
    created = _timestamp(payload["created_at"], "created_at")
    if created[:10] != payload["as_of"]:
        raise ContractError("proposal as_of must match created_at")
    _sorted_unique_text(payload["bias_labels"], "bias_labels")
    if payload["strategy_id"] != "strategy:" + canonical_fingerprint({"strategy_key": payload["strategy_key"]}):
        raise ContractError("strategy identity is invalid")
    if payload["proposal_id"] != "strategy-proposal:" + canonical_fingerprint(_proposal_identity(payload)):
        raise ContractError("proposal identity is invalid")
    _sha(payload["proposal_content_fingerprint"], "proposal_content_fingerprint")
    if payload["proposal_content_fingerprint"] != canonical_fingerprint(_semantic(payload, "proposal_content_fingerprint")):
        raise ContractError("proposal content fingerprint is invalid")


def build_preregistration(*, required_partitions: Sequence[str], required_result_contracts: Sequence[str], requires_cost_policy: bool, criteria: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    payload = {
        "required_partitions": sorted(set(required_partitions)),
        "required_result_contracts": sorted(set(required_result_contracts)),
        "requires_cost_policy": requires_cost_policy,
        "criteria": sorted((plain(item) for item in criteria), key=lambda item: item["criterion_id"]),
    }
    fingerprint = canonical_fingerprint(payload)
    result = {"preregistration_id": "strategy-preregistration:" + fingerprint, "content_fingerprint": fingerprint, **payload}
    _validate_preregistration(result)
    return freeze(result)


def build_strategy_proposal(**values: Any) -> Mapping[str, Any]:
    payload = plain(values)
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("source_version", {"playbook": SOURCE_VERSION})
    payload.setdefault("future_data_used", False)
    payload["affected_modules"] = sorted(set(payload.get("affected_modules", [])))
    payload["bias_labels"] = sorted(set(payload.get("bias_labels", [])))
    payload["m09_review_refs"] = sorted(payload.get("m09_review_refs", []), key=lambda item: item["id"])
    payload["case_roles"] = sorted(payload.get("case_roles", []), key=lambda item: item["event_id"])
    payload["strategy_id"] = "strategy:" + canonical_fingerprint({"strategy_key": payload["strategy_key"]})
    payload["proposal_id"] = "strategy-proposal:" + canonical_fingerprint(_proposal_identity(payload))
    payload["proposal_content_fingerprint"] = canonical_fingerprint(_semantic(payload, "proposal_content_fingerprint"))
    validate_strategy_proposal(payload)
    return freeze(payload)


ASSESSMENT_FIELDS = {
    "schema_version", "as_of", "generated_at", "source_version", "future_data_used",
    "assessment_id", "logical_assessment_id", "assessment_content_fingerprint",
    "supersedes_assessment_id", "proposal_id", "proposal_content_fingerprint",
    "strategy_id", "strategy_version", "candidate_version", "baseline_version",
    "gate_policy_version", "preregistration_ref", "inventory_fingerprint",
    "run_refs", "result_refs", "partitions", "criteria_results", "case_roles",
    "sample_count", "missing_count", "cost_policy_status", "evidence_state",
    "state_reasons", "bias_labels", "assessed_at",
}


def _assessment_logical(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"proposal_id": payload["proposal_id"], "gate_policy_version": payload["gate_policy_version"]}


def _assessment_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "logical_assessment_id": payload["logical_assessment_id"],
        "inventory_fingerprint": payload["inventory_fingerprint"],
        "run_refs": plain(payload["run_refs"]), "result_refs": plain(payload["result_refs"]),
        "criteria_results": plain(payload["criteria_results"]), "evidence_state": payload["evidence_state"],
        "supersedes_assessment_id": payload["supersedes_assessment_id"], "as_of": payload["as_of"],
    }


def validate_strategy_evidence_assessment(payload: Mapping[str, Any]) -> None:
    _exact(payload, ASSESSMENT_FIELDS, "StrategyEvidenceAssessment")
    _validate_common(payload, "StrategyEvidenceAssessment")
    for field, role in (("assessment_id", "strategy-assessment"), ("logical_assessment_id", "strategy-assessment-root"), ("proposal_id", "strategy-proposal"), ("strategy_id", "strategy")):
        _stable_id(payload[field], field, {role})
    _sha(payload["assessment_content_fingerprint"], "assessment_content_fingerprint")
    _sha(payload["proposal_content_fingerprint"], "proposal_content_fingerprint")
    _semver(payload["strategy_version"], "strategy_version")
    _semver(payload["candidate_version"], "candidate_version")
    _semver(payload["baseline_version"], "baseline_version")
    _semver(payload["gate_policy_version"], "gate_policy_version")
    if payload["gate_policy_version"] != EVIDENCE_GATE_POLICY_VERSION:
        raise ContractError("evidence gate policy is unknown")
    _validate_ref(payload["preregistration_ref"], "preregistration_ref", {"strategy-preregistration"})
    _sha(payload["inventory_fingerprint"], "inventory_fingerprint")
    run_refs = payload["run_refs"]
    if not isinstance(run_refs, (list, tuple)) or not run_refs:
        raise ContractError("assessment requires completed run references")
    run_ids: list[str] = []
    for ref in run_refs:
        ref = _exact(ref, {"run_id", "run_receipt_id", "content_fingerprint", "partition_role"}, "run_ref")
        run_ids.append(_stable_id(ref["run_id"], "run_id", {"experiment-run"}))
        _stable_id(ref["run_receipt_id"], "run_receipt_id", {"experiment-run-receipt"})
        _sha(ref["content_fingerprint"], "run content fingerprint")
        if ref["partition_role"] not in {"development", "validation", "forward"}:
            raise ContractError("run partition role is invalid")
    if run_ids != sorted(set(run_ids)):
        raise ContractError("run references must be sorted and unique")
    result_refs = payload["result_refs"]
    if not isinstance(result_refs, (list, tuple)):
        raise ContractError("assessment result references must be a list")
    if not result_refs and payload["evidence_state"] != "evidence_incomplete":
        raise ContractError("complete evidence assessment requires persisted results")
    result_ids: list[str] = []
    allowed_roles = {"forward-outcome", "trade-outcome", "portfolio-run", "research-aggregate"}
    for ref in result_refs:
        ref = _exact(ref, {"contract", "id", "logical_id", "content_fingerprint", "run_id"}, "result_ref")
        if ref["contract"] not in {"ForwardOutcome", "TradeOutcome", "PortfolioRun", "ResearchAggregate"}:
            raise ContractError("result contract is invalid")
        result_ids.append(_stable_id(ref["id"], "result_ref.id", allowed_roles))
        _stable_id(ref["logical_id"], "result_ref.logical_id")
        _sha(ref["content_fingerprint"], "result_ref.content_fingerprint")
        _stable_id(ref["run_id"], "result_ref.run_id", {"experiment-run"})
    if result_ids != sorted(set(result_ids)):
        raise ContractError("result references must be sorted and unique")
    _sorted_unique_text(payload["partitions"], "partitions", {"development", "validation", "forward"})
    criteria = payload["criteria_results"]
    if not isinstance(criteria, (list, tuple)) or not criteria:
        raise ContractError("assessment requires criterion results")
    criterion_ids: list[str] = []
    statuses: list[str] = []
    for item in criteria:
        item = _exact(item, {"criterion_id", "status", "actual", "evidence_ref"}, "criterion_result")
        criterion_ids.append(_text(item["criterion_id"], "criterion_id"))
        if item["status"] not in {"passed", "failed", "unavailable"}:
            raise ContractError("criterion result status is invalid")
        statuses.append(item["status"])
        _finite(item["actual"], "criterion_result.actual")
        _validate_ref(item["evidence_ref"], "criterion_result.evidence_ref", allowed_roles)
    if criterion_ids != sorted(set(criterion_ids)):
        raise ContractError("criterion results must be sorted and unique")
    case_ids: list[str] = []
    for case in payload["case_roles"]:
        case = _exact(case, {"event_id", "role"}, "assessment.case_role")
        case_ids.append(_stable_id(case["event_id"], "case.event_id", {"opportunity"}))
        if case["role"] not in CASE_ROLES:
            raise ContractError("assessment case role is invalid")
    if case_ids != sorted(set(case_ids)):
        raise ContractError("assessment case roles must be sorted and unique")
    for field in ("sample_count", "missing_count"):
        if isinstance(payload[field], bool) or not isinstance(payload[field], int) or payload[field] < 0:
            raise ContractError(f"{field} must be a non-negative integer")
    if payload["missing_count"] > payload["sample_count"]:
        raise ContractError("missing_count exceeds sample_count")
    if payload["cost_policy_status"] not in {"approved", "not_required", "unavailable"}:
        raise ContractError("cost policy status is invalid")
    state = payload["evidence_state"]
    if state not in EVIDENCE_STATES - {"candidate"}:
        raise ContractError("assessment evidence state is invalid")
    _sorted_unique_text(payload["state_reasons"], "state_reasons")
    _sorted_unique_text(payload["bias_labels"], "bias_labels")
    if state == "validated" and (set(statuses) != {"passed"} or payload["bias_labels"]):
        raise ContractError("validated evidence requires all criteria passed and no bias")
    if state == "evidence_incomplete" and not payload["state_reasons"]:
        raise ContractError("evidence_incomplete requires explicit missing-evidence reasons")
    if state in {"not_validated", "invalidated"} and "failed" not in statuses:
        raise ContractError("failed evidence is required for a negative assessment")
    supersedes = payload["supersedes_assessment_id"]
    if supersedes is not None:
        _stable_id(supersedes, "supersedes_assessment_id", {"strategy-assessment"})
    _timestamp(payload["assessed_at"], "assessed_at")
    if payload["assessed_at"][:10] != payload["as_of"]:
        raise ContractError("assessment as_of must match assessed_at")
    if payload["logical_assessment_id"] != "strategy-assessment-root:" + canonical_fingerprint(_assessment_logical(payload)):
        raise ContractError("logical assessment identity is invalid")
    if payload["assessment_id"] != "strategy-assessment:" + canonical_fingerprint(_assessment_identity(payload)):
        raise ContractError("assessment identity is invalid")
    if payload["assessment_content_fingerprint"] != canonical_fingerprint(_semantic(payload, "assessment_content_fingerprint")):
        raise ContractError("assessment content fingerprint is invalid")


def build_strategy_evidence_assessment(**values: Any) -> Mapping[str, Any]:
    payload = plain(values)
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("source_version", {"playbook": SOURCE_VERSION})
    payload.setdefault("future_data_used", False)
    payload["run_refs"] = sorted(payload["run_refs"], key=lambda item: item["run_id"])
    payload["result_refs"] = sorted(payload["result_refs"], key=lambda item: item["id"])
    payload["partitions"] = sorted(set(payload["partitions"]))
    payload["criteria_results"] = sorted(payload["criteria_results"], key=lambda item: item["criterion_id"])
    payload["case_roles"] = sorted(payload["case_roles"], key=lambda item: item["event_id"])
    payload["state_reasons"] = sorted(set(payload.get("state_reasons", [])))
    payload["bias_labels"] = sorted(set(payload.get("bias_labels", [])))
    payload["gate_policy_version"] = EVIDENCE_GATE_POLICY_VERSION
    payload["logical_assessment_id"] = "strategy-assessment-root:" + canonical_fingerprint(_assessment_logical(payload))
    payload["assessment_id"] = "strategy-assessment:" + canonical_fingerprint(_assessment_identity(payload))
    payload["assessment_content_fingerprint"] = canonical_fingerprint(_semantic(payload, "assessment_content_fingerprint"))
    validate_strategy_evidence_assessment(payload)
    return freeze(payload)


def current_strategy_assessment(items: Iterable[Mapping[str, Any]]) -> Mapping[str, Any]:
    return _current_linear_chain(
        items, validator=validate_strategy_evidence_assessment,
        id_field="assessment_id", prior_field="supersedes_assessment_id",
        root_fields=("logical_assessment_id", "proposal_id", "strategy_version"),
        label="assessment",
    )


AXIS_FIELDS = {"evidence", "decision", "implementation", "production"}
STATE_FIELDS = {"evidence", "decision", "implementation", "production"}
EVENT_TYPES = {
    "proposal_registered": "evidence",
    "evidence_assessed": "evidence",
    "user_decision_recorded": "decision",
    "implementation_recorded": "implementation",
    "production_activation_recorded": "production",
    "retirement_recorded": "production",
}
LIFECYCLE_FIELDS = {
    "schema_version", "as_of", "generated_at", "source_version", "future_data_used",
    "lifecycle_event_id", "lifecycle_content_fingerprint", "proposal_id",
    "proposal_content_fingerprint", "strategy_id", "strategy_version", "event_type",
    "changed_axis", "state_before", "state_after", "supersedes_lifecycle_event_id",
    "assessment_ref", "evidence_refs", "author_id", "occurred_at", "reason",
    "bias_labels",
}


def initial_state() -> dict[str, str]:
    return {"evidence": "candidate", "decision": "not_requested", "implementation": "not_implemented", "production": "inactive"}


def _validate_state(value: Any, field: str) -> Mapping[str, Any]:
    state = _exact(value, STATE_FIELDS, field)
    allowed = {
        "evidence": EVIDENCE_STATES, "decision": DECISION_STATES,
        "implementation": IMPLEMENTATION_STATES, "production": PRODUCTION_STATES,
    }
    for axis, values in allowed.items():
        if state[axis] not in values:
            raise ContractError(f"{field}.{axis} is invalid")
    if state["production"] == "active" and (
        state["evidence"] != "validated"
        or state["decision"] != "approved_for_implementation"
        or state["implementation"] != "implemented_in_main"
    ):
        raise ContractError("active requires validated, approved, and implemented axes")
    return state


def _lifecycle_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: plain(payload[key]) for key in (
        "proposal_id", "strategy_version", "event_type", "changed_axis", "state_before",
        "state_after", "supersedes_lifecycle_event_id", "assessment_ref", "evidence_refs",
        "author_id", "occurred_at", "reason",
    )}


def validate_strategy_lifecycle_event(payload: Mapping[str, Any]) -> None:
    _exact(payload, LIFECYCLE_FIELDS, "StrategyLifecycleEvent")
    _validate_common(payload, "StrategyLifecycleEvent")
    _stable_id(payload["lifecycle_event_id"], "lifecycle_event_id", {"strategy-lifecycle"})
    _sha(payload["lifecycle_content_fingerprint"], "lifecycle_content_fingerprint")
    _stable_id(payload["proposal_id"], "proposal_id", {"strategy-proposal"})
    _sha(payload["proposal_content_fingerprint"], "proposal_content_fingerprint")
    _stable_id(payload["strategy_id"], "strategy_id", {"strategy"})
    _semver(payload["strategy_version"], "strategy_version")
    event_type = payload["event_type"]
    if event_type not in EVENT_TYPES or payload["changed_axis"] != EVENT_TYPES[event_type]:
        raise ContractError("lifecycle event type and changed axis disagree")
    after = _validate_state(payload["state_after"], "state_after")
    before = payload["state_before"]
    if event_type == "proposal_registered":
        if before is not None or plain(after) != initial_state() or payload["supersedes_lifecycle_event_id"] is not None:
            raise ContractError("proposal registration must be the candidate root")
    else:
        before = _validate_state(before, "state_before")
        prior = _stable_id(payload["supersedes_lifecycle_event_id"], "supersedes_lifecycle_event_id", {"strategy-lifecycle"})
        if prior is None:
            raise ContractError("lifecycle revision requires a prior event")
        changed = payload["changed_axis"]
        if any(before[axis] != after[axis] for axis in STATE_FIELDS - {changed}):
            raise ContractError("lifecycle event may change exactly one state axis")
        if before[changed] == after[changed]:
            raise ContractError("lifecycle event must change its declared axis")
        if before["production"] == "retired" or (before["production"] == "active" and after["production"] == "inactive"):
            raise ContractError("retired/active strategy versions cannot be silently reactivated or demoted")
    assessment = payload["assessment_ref"]
    if assessment is not None:
        _validate_ref(assessment, "assessment_ref", {"strategy-assessment"})
    refs = _validate_refs(payload["evidence_refs"], "evidence_refs", allow_empty=event_type == "proposal_registered")
    roles = {str(item["id"]).split(":", 1)[0] for item in refs}
    if event_type == "evidence_assessed" and assessment is None:
        raise ContractError("evidence assessment event requires its assessment")
    if event_type == "user_decision_recorded":
        if after["decision"] not in {"approved_for_implementation", "rejected", "deferred"} or "approval" not in roles:
            raise ContractError("user decision requires an allowed decision and approval evidence")
    if event_type == "implementation_recorded":
        if after["implementation"] != "implemented_in_main" or not {"implementation-proof", "test-proof"}.issubset(roles):
            raise ContractError("implementation requires main code and test proof")
    if event_type == "production_activation_recorded":
        if after["production"] != "active" or "m12-activation" not in roles:
            raise ContractError("production activation requires active state and M12 evidence")
    if event_type == "retirement_recorded":
        if after["production"] != "retired" or "retirement-proof" not in roles:
            raise ContractError("retirement requires retired state and proof")
    _text(payload["author_id"], "author_id")
    occurred = _timestamp(payload["occurred_at"], "occurred_at")
    if occurred[:10] != payload["as_of"]:
        raise ContractError("lifecycle as_of must match occurred_at")
    _text(payload["reason"], "reason")
    _sorted_unique_text(payload["bias_labels"], "bias_labels")
    if payload["lifecycle_event_id"] != "strategy-lifecycle:" + canonical_fingerprint(_lifecycle_identity(payload)):
        raise ContractError("lifecycle event identity is invalid")
    if payload["lifecycle_content_fingerprint"] != canonical_fingerprint(_semantic(payload, "lifecycle_content_fingerprint")):
        raise ContractError("lifecycle content fingerprint is invalid")


def build_strategy_lifecycle_event(**values: Any) -> Mapping[str, Any]:
    payload = plain(values)
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("source_version", {"playbook": SOURCE_VERSION})
    payload.setdefault("future_data_used", False)
    payload["evidence_refs"] = _normalize_refs(payload.get("evidence_refs", []))
    payload["bias_labels"] = sorted(set(payload.get("bias_labels", [])))
    payload["lifecycle_event_id"] = "strategy-lifecycle:" + canonical_fingerprint(_lifecycle_identity(payload))
    payload["lifecycle_content_fingerprint"] = canonical_fingerprint(_semantic(payload, "lifecycle_content_fingerprint"))
    validate_strategy_lifecycle_event(payload)
    return freeze(payload)


def current_strategy_lifecycle(items: Iterable[Mapping[str, Any]]) -> Mapping[str, Any]:
    sequence = list(items)
    leaf = _current_linear_chain(
        sequence, validator=validate_strategy_lifecycle_event,
        id_field="lifecycle_event_id", prior_field="supersedes_lifecycle_event_id",
        root_fields=("proposal_id", "strategy_id", "strategy_version"), label="lifecycle",
    )
    by_id = {str(item["lifecycle_event_id"]): item for item in sequence}
    cursor = leaf
    ordered: list[Mapping[str, Any]] = []
    while cursor is not None:
        ordered.append(cursor)
        prior = cursor["supersedes_lifecycle_event_id"]
        cursor = by_id.get(str(prior)) if prior is not None else None
    ordered.reverse()
    for previous, current in zip(ordered, ordered[1:]):
        if plain(current["state_before"]) != plain(previous["state_after"]):
            raise ContractError("lifecycle state does not continue its direct predecessor")
        if current["occurred_at"] < previous["occurred_at"]:
            raise ContractError("lifecycle timestamps move backwards")
    return leaf


def _current_linear_chain(
    items: Iterable[Mapping[str, Any]], *, validator: Any, id_field: str,
    prior_field: str, root_fields: tuple[str, ...], label: str,
) -> Mapping[str, Any]:
    records = list(items)
    if not records:
        raise ContractError(f"{label} chain is empty")
    by_id: dict[str, Mapping[str, Any]] = {}
    roots: list[str] = []
    children: dict[str, str] = {}
    root_values: set[tuple[Any, ...]] = set()
    for item in records:
        validator(item)
        stable_id = str(item[id_field])
        if stable_id in by_id:
            raise ContractError(f"{label} chain has duplicate identity")
        by_id[stable_id] = item
        root_values.add(tuple(item[field] for field in root_fields))
    if len(root_values) != 1:
        raise ContractError(f"{label} chain crosses strategy roots or versions")
    for stable_id, item in by_id.items():
        prior = item[prior_field]
        if prior is None:
            roots.append(stable_id)
        elif prior not in by_id:
            raise ContractError(f"{label} chain has a dangling predecessor")
        elif prior in children:
            raise ContractError(f"{label} chain forks")
        else:
            children[str(prior)] = stable_id
    if len(roots) != 1:
        raise ContractError(f"{label} chain must have one root")
    seen: set[str] = set()
    cursor = roots[0]
    while cursor in children:
        if cursor in seen:
            raise ContractError(f"{label} chain cycles")
        seen.add(cursor)
        cursor = children[cursor]
    seen.add(cursor)
    if len(seen) != len(by_id):
        raise ContractError(f"{label} chain is disconnected")
    return by_id[cursor]


SNAPSHOT_FIELDS = {
    "schema_version", "as_of", "generated_at", "source_version", "future_data_used",
    "registry_snapshot_id", "registry_content_fingerprint", "source_refs",
    "source_set_fingerprint", "entries", "formal_validated_count", "active_count",
    "alpha_risk_hard_rule_count", "code_commit",
}


def validate_strategy_registry_snapshot(payload: Mapping[str, Any]) -> None:
    _exact(payload, SNAPSHOT_FIELDS, "StrategyRegistrySnapshot")
    _validate_common(payload, "StrategyRegistrySnapshot")
    _stable_id(payload["registry_snapshot_id"], "registry_snapshot_id", {"strategy-registry"})
    _sha(payload["registry_content_fingerprint"], "registry_content_fingerprint")
    refs = _validate_refs(payload["source_refs"], "source_refs", {"strategy-proposal", "strategy-assessment", "strategy-lifecycle"}, allow_empty=True)
    _sha(payload["source_set_fingerprint"], "source_set_fingerprint")
    if payload["source_set_fingerprint"] != canonical_fingerprint(plain(refs)):
        raise ContractError("registry source set fingerprint is invalid")
    entries = payload["entries"]
    if not isinstance(entries, (list, tuple)):
        raise ContractError("registry entries must be a list")
    keys: list[tuple[str, str]] = []
    for entry in entries:
        entry = _exact(entry, {"proposal_ref", "strategy_id", "strategy_version", "proposal_kind", "evidence_state", "decision_state", "implementation_state", "production_state", "current_assessment_ref", "current_lifecycle_ref"}, "registry entry")
        _validate_ref(entry["proposal_ref"], "entry.proposal_ref", {"strategy-proposal"})
        _stable_id(entry["strategy_id"], "entry.strategy_id", {"strategy"})
        _semver(entry["strategy_version"], "entry.strategy_version")
        if entry["proposal_kind"] not in {"playbook_candidate", "alpha_risk_hard_rule_candidate"}:
            raise ContractError("registry proposal kind is invalid")
        _validate_state({"evidence": entry["evidence_state"], "decision": entry["decision_state"], "implementation": entry["implementation_state"], "production": entry["production_state"]}, "registry state")
        if entry["current_assessment_ref"] is not None:
            _validate_ref(entry["current_assessment_ref"], "current_assessment_ref", {"strategy-assessment"})
        if entry["current_lifecycle_ref"] is not None:
            _validate_ref(entry["current_lifecycle_ref"], "current_lifecycle_ref", {"strategy-lifecycle"})
        keys.append((entry["strategy_id"], entry["strategy_version"]))
    if keys != sorted(set(keys)):
        raise ContractError("registry entries must be sorted and unique")
    counts = {
        "formal_validated_count": sum(item["evidence_state"] == "validated" for item in entries),
        "active_count": sum(item["production_state"] == "active" for item in entries),
        "alpha_risk_hard_rule_count": sum(item["proposal_kind"] == "alpha_risk_hard_rule_candidate" and item["production_state"] == "active" for item in entries),
    }
    for field, expected in counts.items():
        if payload[field] != expected:
            raise ContractError(f"registry {field} is inconsistent")
    if not _COMMIT.fullmatch(str(payload["code_commit"])):
        raise ContractError("registry code_commit must be full Git identity")
    identity = {"as_of": payload["as_of"], "source_set_fingerprint": payload["source_set_fingerprint"], "code_commit": payload["code_commit"]}
    if payload["registry_snapshot_id"] != "strategy-registry:" + canonical_fingerprint(identity):
        raise ContractError("registry identity is invalid")
    if payload["registry_content_fingerprint"] != canonical_fingerprint(_semantic(payload, "registry_content_fingerprint")):
        raise ContractError("registry content fingerprint is invalid")


__all__ = [
    "CASE_ROLES", "DECISION_STATES", "EVIDENCE_GATE_POLICY_VERSION", "EVIDENCE_STATES",
    "IMPLEMENTATION_STATES", "KNOWN_SEEN_CASES", "PRODUCTION_STATES", "SCHEMA_VERSION",
    "SOURCE_VERSION", "build_preregistration", "build_strategy_evidence_assessment",
    "build_strategy_lifecycle_event", "build_strategy_proposal", "current_strategy_assessment",
    "current_strategy_lifecycle", "freeze", "initial_state", "plain",
    "validate_strategy_evidence_assessment", "validate_strategy_lifecycle_event",
    "validate_strategy_proposal", "validate_strategy_registry_snapshot",
]
