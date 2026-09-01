"""Sole M05 producer for immutable, score-free model assessments."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError, validate_contract
from services.factors.producer import (
    TechnicalEvidenceBatch,
    validate_technical_evidence,
    validate_technical_evidence_batch,
)
from services.gates.producer import require_gate_event_for_path
from services.market_data.consumer import ShadowConsumerInput, require_shadow_rows
from services.scanner.favorite_pattern_tracker import (
    PATTERN_VERSION,
    evaluate_v3_model_facts,
)
from services.scanner.factor_registry import FACTORS_BY_ID


MODEL_ASSESSMENT_SCHEMA_VERSION = "2.0.0"
SELECTOR_POLICY_VERSION = "m05-selector-assessment-1.0.0"
MODEL_VERSIONS = {
    "complex_multifactor": "1.0.0",
    "favorite_pattern": "3.0.0",
}
FAVORITE_FACT_IDS = frozenset({
    "favorite_pattern.v3.objective_pullback",
    "favorite_pattern.v3.broad_double_bottom",
    "favorite_pattern.v3.three_push_close_breakout",
    "favorite_pattern.v3.golden_pocket_or_ema",
})
FORBIDDEN_OUTPUT_KEYS = frozenset({
    "score", "technical_score", "weight", "rank", "ranking",
    "market_adjustment", "industry_adjustment", "trade_plan",
    "entry", "stop", "target",
})


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _all_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.add(str(key))
            keys.update(_all_keys(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys.update(_all_keys(item))
    return keys


def _identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "gate_event_id": payload["gate_event_id"],
        "instrument_id": payload["instrument_id"],
        "as_of": payload["as_of"],
        "path_status": payload["path_status"],
        "input_identity": _plain(payload["input_identity"]),
        "model_id": payload["model_id"],
        "model_version": payload["model_version"],
        "evidence_batch_id": payload["evidence_batch_id"],
        "technical_evidence_ids": list(payload["technical_evidence_ids"]),
        "model_specific_facts_fingerprint": payload["model_specific_facts_fingerprint"],
    }


def _semantic_content(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _plain(value)
        for key, value in payload.items()
        if key not in {"generated_at", "assessment_content_fingerprint"}
    }


def validate_model_assessment(payload: Mapping[str, Any]) -> None:
    """Validate formal M05 policy without creating a second contract parser."""

    validate_contract("ModelAssessment", payload)
    if not str(payload["schema_version"]).startswith("2."):
        raise ContractError("formal M05 consumers require ModelAssessment 2.x")
    expected_version = MODEL_VERSIONS.get(str(payload["model_id"]))
    if expected_version is None or payload["model_version"] != expected_version:
        raise ContractError("ModelAssessment model identity is not registered by M05")
    if payload["source_version"].get("selector_policy") != SELECTOR_POLICY_VERSION:
        raise ContractError("ModelAssessment selector policy is not current")
    forbidden = sorted(FORBIDDEN_OUTPUT_KEYS & _all_keys(payload))
    if forbidden:
        raise ContractError(
            f"ModelAssessment contains out-of-scope fields: {', '.join(forbidden)}"
        )


@dataclass(frozen=True)
class ModelAssessmentBatch:
    """Both selector views for one immutable M03/M04 input batch."""

    batch_id: str
    as_of: str
    path_status: str
    assessments: tuple[Mapping[str, Any], ...]


def validate_model_assessment_batch(batch: ModelAssessmentBatch) -> None:
    """Validate the immutable M05 batch before a later module trusts its ID."""

    if not isinstance(batch, ModelAssessmentBatch):
        raise ContractError("expected an M05 ModelAssessmentBatch")
    items = list(batch.assessments)
    for item in items:
        validate_model_assessment(item)
        if item["as_of"] != batch.as_of or item["path_status"] != batch.path_status:
            raise ContractError("ModelAssessmentBatch contains mixed identities")
    if items != sorted(
        items, key=lambda item: (str(item["instrument_id"]), str(item["model_id"]))
    ):
        raise ContractError("ModelAssessmentBatch assessments must use canonical order")
    identities = [str(item["assessment_id"]) for item in items]
    if len(identities) != len(set(identities)):
        raise ContractError("ModelAssessmentBatch contains duplicate assessments")
    logical_keys = [
        (
            str(item["gate_event_id"]),
            str(item["instrument_id"]),
            str(item["model_id"]),
        )
        for item in items
    ]
    if len(logical_keys) != len(set(logical_keys)):
        raise ContractError(
            "ModelAssessmentBatch contains duplicate model assessments for one GateEvent"
        )
    batch_identity = {
        "as_of": batch.as_of,
        "path_status": batch.path_status,
        "selector_policy": SELECTOR_POLICY_VERSION,
        "assessments": [
            {
                "assessment_id": item["assessment_id"],
                "content": item["assessment_content_fingerprint"],
            }
            for item in items
        ],
    }
    if batch.batch_id != "model-assessment-batch:" + canonical_fingerprint(batch_identity):
        raise ContractError("ModelAssessmentBatch identity does not match its assessments")


def _fact_reference(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "evidence_id": item["evidence_id"],
        "factor_id": item["factor_id"],
        "factor_version": item["factor_version"],
        "family": item["family"],
        "timeframe": item["timeframe"],
        "available": item["available"],
        "raw_hit": item["raw_hit"],
        "qualified_hit": item["qualified_hit"],
        "blocked_by": list(item["blocked_by"]),
        "evidence_date": item["evidence_date"],
    }


def _validate_favorite_facts(facts: Mapping[str, Any]) -> None:
    """Keep personal-only facts named, versioned and distinct from M04 IDs."""

    if facts.get("definition_version") != PATTERN_VERSION:
        raise ContractError("favorite pattern facts use an unknown definition version")
    items = facts.get("facts")
    if not isinstance(items, (list, tuple)):
        raise ContractError("favorite pattern facts must be a list")
    ids: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ContractError("favorite pattern fact must be an object")
        fact_id = str(item.get("fact_id") or "")
        if fact_id not in FAVORITE_FACT_IDS:
            raise ContractError("favorite pattern fact is not namespaced by M05")
        if item.get("definition_version") != PATTERN_VERSION:
            raise ContractError("favorite pattern fact version is inconsistent")
        if not isinstance(item.get("available"), bool) or not isinstance(item.get("hit"), bool):
            raise ContractError("favorite pattern fact availability and hit must be explicit")
        if not isinstance(item.get("evidence"), Mapping):
            raise ContractError("favorite pattern fact requires objective evidence")
        ids.append(fact_id)
    if len(ids) != len(set(ids)):
        raise ContractError("favorite pattern facts contain duplicate identities")
    if facts.get("available") is True and set(ids) != FAVORITE_FACT_IDS:
        raise ContractError("available favorite pattern assessment requires all four facts")
    risk = facts.get("risk")
    if (
        not isinstance(risk, Mapping)
        or risk.get("fact_id") != "favorite_pattern.v3.supply_risk"
        or risk.get("definition_version") != PATTERN_VERSION
        or not isinstance(risk.get("available"), bool)
        or not isinstance(risk.get("blocked"), bool)
        or not isinstance(risk.get("evidence"), Mapping)
    ):
        raise ContractError("favorite pattern risk fact is not explicit and versioned")


def _build_assessment(
    *,
    prepared: ShadowConsumerInput,
    event: Mapping[str, Any],
    batch: TechnicalEvidenceBatch,
    evidence: tuple[Mapping[str, Any], ...],
    model_id: str,
    status: str,
    eligible: bool,
    matched: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    warnings: list[str],
    model_facts: Mapping[str, Any],
    generated_at: str,
) -> Mapping[str, Any]:
    evidence_ids = sorted(str(item["evidence_id"]) for item in evidence)
    facts = _plain(model_facts)
    payload: dict[str, Any] = {
        "schema_version": MODEL_ASSESSMENT_SCHEMA_VERSION,
        "as_of": prepared.as_of,
        "generated_at": generated_at,
        "source_version": {"selector_policy": SELECTOR_POLICY_VERSION},
        "future_data_used": False,
        "gate_event_id": event["gate_event_id"],
        "instrument_id": event["instrument_id"],
        "path_status": prepared.mode,
        "input_identity": {
            "universe_id": prepared.universe_id,
            "market_snapshot_id": prepared.market_snapshot_id,
            "adjustment_policy": dict(ADJUSTMENT_POLICY),
        },
        "evidence_batch_id": batch.batch_id,
        "technical_evidence_ids": evidence_ids,
        "model_id": model_id,
        "model_version": MODEL_VERSIONS[model_id],
        "eligible": eligible,
        "status": status,
        "matched_facts": matched,
        "missing_facts": missing,
        "risk_facts": risks,
        "warnings": sorted(set(warnings)),
        "model_specific_facts": facts,
        "model_specific_facts_fingerprint": canonical_fingerprint(facts),
        "production_effect": False,
        "bias_labels": list(prepared.bias_labels),
    }
    payload["assessment_id"] = "assessment:" + canonical_fingerprint(_identity(payload))
    payload["assessment_content_fingerprint"] = canonical_fingerprint(
        _semantic_content(payload)
    )
    validate_model_assessment(payload)
    return _freeze(payload)


def produce_model_assessments(
    prepared: ShadowConsumerInput,
    *,
    gate_events: Iterable[Mapping[str, Any]],
    technical_evidence: TechnicalEvidenceBatch,
    generated_at: str,
    favorite_fact_evaluator: Callable[[tuple[Mapping[str, Any], ...]], Mapping[str, Any]] = evaluate_v3_model_facts,
) -> ModelAssessmentBatch:
    """Create both formal selector interpretations without rescanning shared facts."""

    if not isinstance(prepared, ShadowConsumerInput):
        raise ContractError("M05 producer requires M02 ShadowConsumerInput")
    if prepared.mode != "formal":
        raise ContractError("formal M05 producer does not accept legacy input")
    if not isinstance(technical_evidence, TechnicalEvidenceBatch):
        raise ContractError("M05 producer requires the M04 TechnicalEvidenceBatch")
    validate_technical_evidence_batch(technical_evidence)
    if technical_evidence.as_of != prepared.as_of or technical_evidence.path_status != prepared.mode:
        raise ContractError("M04 evidence batch does not match M05 input")
    rows_by_symbol = require_shadow_rows(prepared, consumer=prepared.consumer)
    events = tuple(gate_events)
    event_ids: set[str] = set()
    by_event: dict[str, list[Mapping[str, Any]]] = {}
    for item in technical_evidence.evidence:
        validate_technical_evidence(item)
        by_event.setdefault(str(item["gate_event_id"]), []).append(item)
    assessments: list[Mapping[str, Any]] = []
    for event in sorted(events, key=lambda item: str(item.get("gate_event_id"))):
        require_gate_event_for_path(event, path_status="formal")
        event_id = str(event["gate_event_id"])
        if event_id in event_ids:
            raise ContractError("M05 input contains a duplicate GateEvent")
        event_ids.add(event_id)
        if event["signal_date"] != prepared.as_of:
            raise ContractError("GateEvent date does not match M05 input")
        identity = event["input_identity"]
        if (
            identity["universe_id"] != prepared.universe_id
            or identity["market_snapshot_id"] != prepared.market_snapshot_id
            or _plain(identity["adjustment_policy"]) != ADJUSTMENT_POLICY
        ):
            raise ContractError("GateEvent identity does not match M05 input")
        evidence = tuple(sorted(by_event.pop(event_id, []), key=lambda item: str(item["factor_id"])))
        if not evidence:
            raise ContractError("GateEvent has no TechnicalEvidence")
        factor_ids = [str(item["factor_id"]) for item in evidence]
        if len(factor_ids) != len(set(factor_ids)) or set(factor_ids) != set(FACTORS_BY_ID):
            raise ContractError("GateEvent does not have one complete M04 evidence set")
        if any(item["instrument_id"] != event["instrument_id"] for item in evidence):
            raise ContractError("TechnicalEvidence instrument does not match GateEvent")
        refs = [_fact_reference(item) for item in evidence]
        matched = [item for item in refs if item["qualified_hit"] and item["family"] != "risk"]
        missing = [item for item in refs if not item["available"]]
        risks = [item for item in refs if item["raw_hit"] and item["family"] == "risk"]
        blocked = [
            f"{item['factor_id']} blocked by {','.join(item['blocked_by'])}"
            for item in refs if item["raw_hit"] and item["blocked_by"]
        ]
        assessments.append(_build_assessment(
            prepared=prepared,
            event=event,
            batch=technical_evidence,
            evidence=evidence,
            model_id="complex_multifactor",
            status="eligible" if event["baseline_passed"] else "baseline_not_eligible",
            eligible=bool(event["baseline_passed"]),
            matched=matched,
            missing=missing,
            risks=risks,
            warnings=blocked,
            model_facts={"assessment_kind": "technical_fact_inventory"},
            generated_at=generated_at,
        ))
        rows = rows_by_symbol.get(str(event["symbol"]))
        if rows is None:
            raise ContractError("GateEvent has no immutable M02 rows for personal pattern")
        favorite_facts = favorite_fact_evaluator(rows)
        if not isinstance(favorite_facts, Mapping):
            raise ContractError("favorite pattern evaluator returned invalid facts")
        _validate_favorite_facts(favorite_facts)
        audit = favorite_facts.get("lookahead_audit")
        if not isinstance(audit, Mapping) or audit.get("future_data_used") is not False:
            raise ContractError("favorite pattern facts lack no-future evidence")
        status = str(favorite_facts.get("status") or "unavailable")
        favorite_warnings = list(favorite_facts.get("risk", {}).get("reasons") or [])
        if not favorite_facts.get("available"):
            favorite_warnings.append("favorite_pattern_facts_unavailable")
        assessments.append(_build_assessment(
            prepared=prepared,
            event=event,
            batch=technical_evidence,
            evidence=evidence,
            model_id="favorite_pattern",
            status=status,
            eligible=status == "entry_ready",
            matched=[item for item in matched if item["factor_id"] in {
                "macd.daily_bull_cross", "qualification.long_trend"
            }],
            missing=missing,
            risks=risks,
            warnings=favorite_warnings,
            model_facts=favorite_facts,
            generated_at=generated_at,
        ))
    if by_event:
        raise ContractError("TechnicalEvidence contains an unknown GateEvent")
    assessments.sort(key=lambda item: (str(item["instrument_id"]), str(item["model_id"])))
    batch_identity = {
        "as_of": prepared.as_of,
        "path_status": prepared.mode,
        "selector_policy": SELECTOR_POLICY_VERSION,
        "assessments": [
            {
                "assessment_id": item["assessment_id"],
                "content": item["assessment_content_fingerprint"],
            }
            for item in assessments
        ],
    }
    batch = ModelAssessmentBatch(
        batch_id="model-assessment-batch:" + canonical_fingerprint(batch_identity),
        as_of=prepared.as_of,
        path_status=prepared.mode,
        assessments=tuple(assessments),
    )
    validate_model_assessment_batch(batch)
    return batch
