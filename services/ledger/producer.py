"""Sole M09 producer for immutable events and append-only review records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from types import MappingProxyType
from typing import AbstractSet, Any, Iterable, Mapping, Sequence

from services.context import ContextBatch, validate_context_batch, validate_market_industry_context
from services.contracts.market_data import canonical_fingerprint, require_date
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError, validate_contract
from services.execution import (
    TradePlanBatch,
    validate_exit_state,
    validate_trade_plan_batch,
)
from services.factors import TechnicalEvidenceBatch, validate_technical_evidence_batch
from services.gates import require_gate_event_for_path
from services.ranking import ScoreBatch, validate_ranking_snapshot, validate_score_batch
from services.selectors import ModelAssessmentBatch, validate_model_assessment_batch


OPPORTUNITY_EVENT_SCHEMA_VERSION = "2.0.0"
MACHINE_LINK_SCHEMA_VERSION = "1.0.0"
HUMAN_REVIEW_SCHEMA_VERSION = "1.0.0"
LEDGER_PRODUCER_VERSION = "m09-shadow-1.0.0"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
FORBIDDEN_PERFORMANCE_KEYS = frozenset({
    "return", "returns", "return_pct", "r_return", "mfe", "mae",
    "forward_outcome", "win_rate", "profit_factor", "excel",
})


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _semantic(payload: Mapping[str, Any], fingerprint_field: str) -> dict[str, Any]:
    return {
        key: _plain(value)
        for key, value in payload.items()
        if key not in {"generated_at", fingerprint_field}
    }


def _all_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_all_keys(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            keys.update(_all_keys(child))
    return keys


def _require_timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError(f"{field} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.utcoffset() is None:
        raise ContractError(f"{field} must include UTC evidence")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ContractError(f"{field} must be a stable non-empty string")
    return value


def _opportunity_root(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_major": 2,
        "authority_scope": payload["authority_scope"],
        "instrument_id": payload["instrument_id"],
        "signal_date": payload["signal_date"],
    }


def validate_opportunity_event(payload: Mapping[str, Any]) -> None:
    """Validate the frozen M09 root without recalculating any upstream fact."""

    validate_contract("OpportunityEvent", payload)
    if payload["schema_version"] != OPPORTUNITY_EVENT_SCHEMA_VERSION:
        raise ContractError("formal M09 requires OpportunityEvent 2.0.0")
    if payload["source_version"].get("ledger_producer") != LEDGER_PRODUCER_VERSION:
        raise ContractError("OpportunityEvent has an unknown M09 producer")
    forbidden = FORBIDDEN_PERFORMANCE_KEYS & _all_keys(payload)
    if forbidden:
        raise ContractError(f"OpportunityEvent contains M10 fields: {', '.join(sorted(forbidden))}")
    gate = payload["gate_reference"]
    technical = payload["technical_reference"]
    models = payload["model_assessments"]
    context = payload["context_reference"]
    score = payload["score_reference"]
    frozen = payload["frozen_ranking"]
    if gate.get("gate_event_id") != payload["gate_event_id"]:
        raise ContractError("OpportunityEvent gate reference is inconsistent")
    if not re.fullmatch(r"gate-signal:sha256:[0-9a-f]{64}", str(gate.get("logical_signal_id"))):
        raise ContractError("OpportunityEvent logical GateEvent reference is invalid")
    if not SHA256.fullmatch(str(gate.get("content_fingerprint"))):
        raise ContractError("OpportunityEvent GateEvent content reference is invalid")
    if score.get("score_result_id") != payload["score_result_id"]:
        raise ContractError("OpportunityEvent score reference is inconsistent")
    if frozen.get("rank") != payload["rank"] or frozen.get("selected") != payload["selected"]:
        raise ContractError("OpportunityEvent frozen ranking summary is inconsistent")
    for field, prefix in (
        ("batch_id", "technical-evidence-batch:"),
    ):
        if not _require_text(technical.get(field), f"technical_reference.{field}").startswith(prefix):
            raise ContractError("OpportunityEvent technical batch reference is invalid")
    identity = payload["input_identity"]
    if technical["batch_id"] != identity["technical_evidence_batch_id"]:
        raise ContractError("OpportunityEvent technical batch references disagree")
    if not _require_text(models.get("batch_id"), "model_assessments.batch_id").startswith(
        "model-assessment-batch:"
    ) or models["batch_id"] != identity["model_assessment_batch_id"]:
        raise ContractError("OpportunityEvent model batch references disagree")
    technical_items = technical.get("items")
    model_items = models.get("items")
    if not isinstance(technical_items, (list, tuple)) or not technical_items:
        raise ContractError("OpportunityEvent requires technical evidence references")
    if not isinstance(model_items, (list, tuple)) or not model_items:
        raise ContractError("OpportunityEvent requires model assessment references")
    for items, id_field, fingerprint_field, prefix in (
        (technical_items, "evidence_id", "content_fingerprint", "evidence:sha256:"),
        (model_items, "assessment_id", "content_fingerprint", "assessment:sha256:"),
    ):
        identities = []
        for item in items:
            if not isinstance(item, Mapping):
                raise ContractError("OpportunityEvent evidence reference must be an object")
            stable_id = _require_text(item.get(id_field), id_field)
            if not stable_id.startswith(prefix) or not SHA256.fullmatch(str(item.get(fingerprint_field))):
                raise ContractError("OpportunityEvent evidence reference is invalid")
            identities.append(stable_id)
        if identities != sorted(set(identities)):
            raise ContractError("OpportunityEvent evidence references must be sorted and unique")
    for field, prefix in (
        ("batch_id", "context-batch:"),
        ("context_id", "context:sha256:"),
    ):
        if not _require_text(context.get(field), f"context_reference.{field}").startswith(prefix):
            raise ContractError("OpportunityEvent context reference is invalid")
    if context["batch_id"] != identity["context_batch_id"]:
        raise ContractError("OpportunityEvent context batch references disagree")
    for field in ("content_fingerprint",):
        if not SHA256.fullmatch(str(context.get(field))):
            raise ContractError("OpportunityEvent context content reference is invalid")
    if not SHA256.fullmatch(str(score.get("content_fingerprint"))):
        raise ContractError("OpportunityEvent score content reference is invalid")
    if not SHA256.fullmatch(str(score.get("input_fingerprint"))):
        raise ContractError("OpportunityEvent score input reference is invalid")


@dataclass(frozen=True)
class EventLedgerBatch:
    batch_id: str
    as_of: str
    ranking_snapshot_id: str
    authority_scope: str
    events: tuple[Mapping[str, Any], ...]


def validate_event_ledger_batch(batch: EventLedgerBatch) -> None:
    if not isinstance(batch, EventLedgerBatch):
        raise ContractError("expected an M09 EventLedgerBatch")
    items = list(batch.events)
    seen: set[str] = set()
    for event in items:
        validate_opportunity_event(event)
        if (
            event["signal_date"] != batch.as_of
            or event["ranking_snapshot_id"] != batch.ranking_snapshot_id
            or event["authority_scope"] != batch.authority_scope
        ):
            raise ContractError("EventLedgerBatch contains mixed identities")
        if event["event_id"] in seen:
            raise ContractError("EventLedgerBatch contains a duplicate event root")
        seen.add(str(event["event_id"]))
    if items != sorted(items, key=lambda item: str(item["instrument_id"])):
        raise ContractError("EventLedgerBatch events must use canonical instrument order")
    identity = {
        "as_of": batch.as_of,
        "ranking_snapshot_id": batch.ranking_snapshot_id,
        "authority_scope": batch.authority_scope,
        "events": [
            {"id": item["event_id"], "content": item["event_content_fingerprint"]}
            for item in items
        ],
    }
    if batch.batch_id != "event-ledger-batch:" + canonical_fingerprint(identity):
        raise ContractError("EventLedgerBatch identity does not match its events")


def _single_by_gate(
    items: Iterable[Mapping[str, Any]], *, label: str
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in items:
        gate_id = str(item["gate_event_id"])
        if gate_id in result:
            raise ContractError(f"M09 input contains duplicate {label} for one GateEvent")
        result[gate_id] = item
    return result


def produce_event_ledger_batch(
    *,
    gate_events: Iterable[Mapping[str, Any]],
    technical_evidence: TechnicalEvidenceBatch,
    model_assessments: ModelAssessmentBatch,
    contexts: ContextBatch,
    ranking_snapshot: Mapping[str, Any],
    generated_at: str,
) -> EventLedgerBatch:
    """Freeze every authoritative formal ranked entry into exactly one root event."""

    validate_ranking_snapshot(ranking_snapshot)
    if ranking_snapshot["path_status"] != "formal" or ranking_snapshot["ranking_role"] != "authoritative":
        raise ContractError("M09 formal events require the authoritative formal RankingSnapshot")
    validate_technical_evidence_batch(technical_evidence)
    validate_model_assessment_batch(model_assessments)
    validate_context_batch(contexts)
    as_of = str(ranking_snapshot["as_of"])
    score_batch = ScoreBatch(
        batch_id=str(ranking_snapshot["input_identity"]["score_batch_id"]),
        as_of=as_of,
        path_status=str(ranking_snapshot["path_status"]),
        score_policy_version=str(ranking_snapshot["score_policy_version"]),
        score_policy_fingerprint=str(ranking_snapshot["score_policy_fingerprint"]),
        results=tuple(ranking_snapshot["score_results"]),
    )
    validate_score_batch(score_batch)
    for batch, label in (
        (technical_evidence, "M04"),
        (model_assessments, "M05"),
        (contexts, "M06"),
    ):
        if batch.as_of != as_of or batch.path_status != "formal":
            raise ContractError(f"{label} batch does not match the formal ranking date")

    events_by_id: dict[str, Mapping[str, Any]] = {}
    for event in gate_events:
        require_gate_event_for_path(event, path_status="formal")
        gate_id = str(event["gate_event_id"])
        if gate_id in events_by_id:
            raise ContractError("M09 input contains duplicate GateEvents")
        if event["signal_date"] != as_of:
            raise ContractError("M09 GateEvent date does not match the ranking")
        events_by_id[gate_id] = event

    evidence_by_gate: dict[str, list[Mapping[str, Any]]] = {}
    for item in technical_evidence.evidence:
        evidence_by_gate.setdefault(str(item["gate_event_id"]), []).append(item)
    assessments_by_gate: dict[str, list[Mapping[str, Any]]] = {}
    for item in model_assessments.assessments:
        assessments_by_gate.setdefault(str(item["gate_event_id"]), []).append(item)
    context_by_gate = _single_by_gate(contexts.contexts, label="ContextSnapshot")
    score_by_id = {
        str(item["score_result_id"]): item for item in ranking_snapshot["score_results"]
    }
    selected_ids = {
        str(item["score_result_id"]) for item in ranking_snapshot["selected_entries"]
    }
    produced: list[Mapping[str, Any]] = []
    roots: set[str] = set()
    for entry in ranking_snapshot["ranked_entries"]:
        score = score_by_id[str(entry["score_result_id"])]
        gate = events_by_id.get(str(entry["gate_event_id"]))
        if gate is None:
            raise ContractError("ranked entry has no formal GateEvent")
        instrument_id = str(entry["instrument_id"])
        if gate["instrument_id"] != instrument_id or score["instrument_id"] != instrument_id:
            raise ContractError("ranked entry crosses instrument identities")
        input_identity = score["input_identity"]
        gate_identity = gate["input_identity"]
        if (
            input_identity["universe_id"] != gate_identity["universe_id"]
            or input_identity["market_snapshot_id"] != gate_identity["market_snapshot_id"]
            or _plain(input_identity["adjustment_policy"]) != ADJUSTMENT_POLICY
            or _plain(gate_identity["adjustment_policy"]) != ADJUSTMENT_POLICY
        ):
            raise ContractError("M09 upstream M02 identities do not agree")
        if (
            input_identity["technical_evidence_batch_id"] != technical_evidence.batch_id
            or input_identity["model_assessment_batch_id"] != model_assessments.batch_id
            or input_identity["context_batch_id"] != contexts.batch_id
        ):
            raise ContractError("M09 upstream batch references do not agree")

        technical_items = sorted(
            evidence_by_gate.get(str(gate["gate_event_id"]), ()),
            key=lambda item: str(item["evidence_id"]),
        )
        if [str(item["evidence_id"]) for item in technical_items] != sorted(
            str(item) for item in score["technical_evidence_ids"]
        ):
            raise ContractError("M09 technical evidence references are incomplete")
        if any(item["instrument_id"] != instrument_id for item in technical_items):
            raise ContractError("M09 technical evidence crosses instruments")

        model_items = sorted(
            assessments_by_gate.get(str(gate["gate_event_id"]), ()),
            key=lambda item: str(item["assessment_id"]),
        )
        if not model_items or score["model_assessment_id"] not in {
            item["assessment_id"] for item in model_items
        }:
            raise ContractError("M09 model references omit the scored complex assessment")
        if any(
            item["instrument_id"] != instrument_id
            or item["evidence_batch_id"] != technical_evidence.batch_id
            for item in model_items
        ):
            raise ContractError("M09 model assessments cross their evidence identity")

        context = context_by_gate.get(str(gate["gate_event_id"]))
        if context is None or context["context_id"] != score["context_snapshot_id"]:
            raise ContractError("ranked entry has no matching M06 context")
        if (
            context["instrument_id"] != instrument_id
            or context["technical_evidence_batch_id"] != technical_evidence.batch_id
            or context["model_assessment_batch_id"] != model_assessments.batch_id
            or sorted(context["technical_evidence_ids"])
            != sorted(item["evidence_id"] for item in technical_items)
            or sorted(context["model_assessment_ids"])
            != sorted(item["assessment_id"] for item in model_items)
        ):
            raise ContractError("M06 context does not bind the complete M04/M05 evidence")
        context_identity = context["input_identity"]
        if (
            context_identity["stock_universe_id"] != gate_identity["universe_id"]
            or context_identity["stock_market_snapshot_id"] != gate_identity["market_snapshot_id"]
            or _plain(context_identity["adjustment_policy"]) != ADJUSTMENT_POLICY
        ):
            raise ContractError("M06 context crosses M02 stock identities")

        root = {
            "schema_major": 2,
            "authority_scope": ranking_snapshot["authority_scope"],
            "instrument_id": instrument_id,
            "signal_date": as_of,
        }
        event_id = "opportunity:" + canonical_fingerprint(root)
        if event_id in roots:
            raise ContractError("one authoritative ranking produced a duplicate event root")
        roots.add(event_id)
        selected = str(entry["score_result_id"]) in selected_ids
        payload: dict[str, Any] = {
            "schema_version": OPPORTUNITY_EVENT_SCHEMA_VERSION,
            "as_of": as_of,
            "generated_at": generated_at,
            "source_version": {"ledger_producer": LEDGER_PRODUCER_VERSION},
            "future_data_used": False,
            "event_id": event_id,
            "instrument_id": instrument_id,
            "symbol": gate["symbol"],
            "signal_date": as_of,
            "path_status": "formal",
            "event_role": "authoritative",
            "authority_scope": ranking_snapshot["authority_scope"],
            "gate_event_id": gate["gate_event_id"],
            "ranking_snapshot_id": ranking_snapshot["ranking_snapshot_id"],
            "ranking_content_fingerprint": ranking_snapshot["ranking_content_fingerprint"],
            "score_result_id": score["score_result_id"],
            "rank": entry["rank"],
            "selected": selected,
            "input_identity": {
                "universe_id": gate_identity["universe_id"],
                "market_snapshot_id": gate_identity["market_snapshot_id"],
                "adjustment_policy": dict(ADJUSTMENT_POLICY),
                "technical_evidence_batch_id": technical_evidence.batch_id,
                "model_assessment_batch_id": model_assessments.batch_id,
                "context_batch_id": contexts.batch_id,
                "score_batch_id": ranking_snapshot["input_identity"]["score_batch_id"],
            },
            "gate_reference": {
                "logical_signal_id": gate["logical_signal_id"],
                "gate_event_id": gate["gate_event_id"],
                "supersedes_event_id": gate["supersedes_event_id"],
                "gate_policy_version": gate["gate_policy_version"],
                "content_fingerprint": gate["event_content_fingerprint"],
            },
            "technical_reference": {
                "batch_id": technical_evidence.batch_id,
                "registry_version": technical_evidence.registry_version,
                "items": [
                    {
                        "evidence_id": item["evidence_id"],
                        "factor_id": item["factor_id"],
                        "factor_version": item["factor_version"],
                        "content_fingerprint": item["evidence_content_fingerprint"],
                    }
                    for item in technical_items
                ],
            },
            "model_assessments": {
                "batch_id": model_assessments.batch_id,
                "items": [
                    {
                        "assessment_id": item["assessment_id"],
                        "model_id": item["model_id"],
                        "model_version": item["model_version"],
                        "content_fingerprint": item["assessment_content_fingerprint"],
                    }
                    for item in model_items
                ],
            },
            "context_reference": {
                "batch_id": contexts.batch_id,
                "context_id": context["context_id"],
                "content_fingerprint": context["context_content_fingerprint"],
            },
            "score_reference": {
                "score_result_id": score["score_result_id"],
                "content_fingerprint": score["score_content_fingerprint"],
                "input_fingerprint": score["score_input_fingerprint"],
            },
            "policy_versions": {
                "gate": gate["gate_policy_version"],
                "factor_registry": technical_evidence.registry_version,
                "models": {
                    item["model_id"]: item["model_version"] for item in model_items
                },
                "context": _plain(context["source_version"]),
                "score": {
                    "version": ranking_snapshot["score_policy_version"],
                    "fingerprint": ranking_snapshot["score_policy_fingerprint"],
                },
                "ranking": {
                    "version": ranking_snapshot["ranking_policy_version"],
                    "fingerprint": ranking_snapshot["ranking_policy_fingerprint"],
                },
                "authority": {
                    "version": ranking_snapshot["authority_policy_version"],
                    "fingerprint": ranking_snapshot["authority_policy_fingerprint"],
                    "activation_id": ranking_snapshot["activation"]["activation_id"],
                },
            },
            "frozen_ranking": {
                "rank": entry["rank"],
                "selected": selected,
                "total_score": entry["total_score"],
                "components": _plain(entry["components"]),
                "warnings": list(entry["warnings"]),
                "sort_key": _plain(entry["sort_key"]),
            },
        }
        payload["event_content_fingerprint"] = canonical_fingerprint(
            _semantic(payload, "event_content_fingerprint")
        )
        validate_opportunity_event(payload)
        produced.append(_freeze(payload))

    if len(produced) != len(ranking_snapshot["ranked_entries"]):
        raise ContractError("M09 event count does not conserve authoritative ranked entries")
    produced.sort(key=lambda item: str(item["instrument_id"]))
    identity = {
        "as_of": as_of,
        "ranking_snapshot_id": ranking_snapshot["ranking_snapshot_id"],
        "authority_scope": ranking_snapshot["authority_scope"],
        "events": [
            {"id": item["event_id"], "content": item["event_content_fingerprint"]}
            for item in produced
        ],
    }
    batch = EventLedgerBatch(
        batch_id="event-ledger-batch:" + canonical_fingerprint(identity),
        as_of=as_of,
        ranking_snapshot_id=str(ranking_snapshot["ranking_snapshot_id"]),
        authority_scope=str(ranking_snapshot["authority_scope"]),
        events=tuple(produced),
    )
    validate_event_ledger_batch(batch)
    return batch


def _machine_link_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_id": payload["event_id"],
        "link_type": payload["link_type"],
        "source_identity": _plain(payload["source_identity"]),
    }


def validate_machine_link(payload: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "as_of", "generated_at", "source_version",
        "future_data_used", "link_id", "link_content_fingerprint", "event_id",
        "instrument_id", "signal_date", "link_type", "source_identity",
        "source_reference", "status", "reason",
    }
    if not isinstance(payload, Mapping) or required - payload.keys():
        raise ContractError("M09 machine link is incomplete")
    if payload["schema_version"] != MACHINE_LINK_SCHEMA_VERSION:
        raise ContractError("M09 machine link schema is unknown")
    require_date(payload["as_of"], "as_of")
    require_date(payload["signal_date"], "signal_date")
    _require_timestamp(payload["generated_at"], "generated_at")
    if payload["future_data_used"] is not False or payload["as_of"] != payload["signal_date"]:
        raise ContractError("M09 machine link date evidence is invalid")
    if payload["source_version"].get("ledger_producer") != LEDGER_PRODUCER_VERSION:
        raise ContractError("M09 machine link producer is unknown")
    if not re.fullmatch(r"machine-link:sha256:[0-9a-f]{64}", str(payload["link_id"])):
        raise ContractError("M09 machine link id is invalid")
    if not re.fullmatch(r"opportunity:sha256:[0-9a-f]{64}", str(payload["event_id"])):
        raise ContractError("M09 machine link event id is invalid")
    if not re.fullmatch(r"instrument:sha256:[0-9a-f]{64}", str(payload["instrument_id"])):
        raise ContractError("M09 machine link instrument id is invalid")
    if payload["link_type"] not in {"ranking_evidence_revision", "trade_plan_decision", "exit_state"}:
        raise ContractError("M09 machine link type is invalid")
    if not isinstance(payload["source_identity"], Mapping) or not isinstance(payload["source_reference"], Mapping):
        raise ContractError("M09 machine link source evidence is invalid")
    if payload["status"] not in {"created", "not_created", "unavailable", "recorded"}:
        raise ContractError("M09 machine link status is invalid")
    if payload["status"] in {"not_created", "unavailable"}:
        _require_text(payload["reason"], "reason")
    elif payload["reason"] is not None:
        raise ContractError("successful M09 machine link cannot carry a reason")
    source_identity = payload["source_identity"]
    source_reference = payload["source_reference"]
    if payload["link_type"] == "trade_plan_decision":
        if set(source_identity) != {"trade_plan_batch_id", "score_result_id"}:
            raise ContractError("trade-plan link source identity is invalid")
        if not str(source_identity["trade_plan_batch_id"]).startswith("trade-plan-batch:"):
            raise ContractError("trade-plan link batch identity is invalid")
        if not str(source_identity["score_result_id"]).startswith("score:sha256:"):
            raise ContractError("trade-plan link score identity is invalid")
        if any(
            source_reference.get(field) != source_identity[field]
            for field in ("trade_plan_batch_id", "score_result_id")
        ) or source_reference.get("status") != payload["status"] or source_reference.get("reason") != payload["reason"]:
            raise ContractError("trade-plan link source reference contradicts its identity")
        plan_id = source_reference.get("plan_id")
        plan_fingerprint = source_reference.get("plan_content_fingerprint")
        if payload["status"] == "created":
            if not re.fullmatch(r"plan:sha256:[0-9a-f]{64}", str(plan_id)) or not SHA256.fullmatch(str(plan_fingerprint)):
                raise ContractError("created trade-plan link requires one immutable plan reference")
        elif plan_id is not None or plan_fingerprint is not None:
            raise ContractError("uncreated trade-plan link cannot reference a plan")
    elif payload["link_type"] == "ranking_evidence_revision":
        if set(source_identity) != {"ranking_snapshot_id", "score_result_id"}:
            raise ContractError("ranking revision link source identity is invalid")
        if any(source_reference.get(field) != source_identity[field] for field in source_identity):
            raise ContractError("ranking revision link source reference contradicts its identity")
        if payload["status"] != "recorded" or not SHA256.fullmatch(
            str(source_reference.get("event_content_fingerprint"))
        ):
            raise ContractError("ranking revision link evidence is incomplete")
    else:
        if set(source_identity) != {"exit_state_id"}:
            raise ContractError("exit-state link source identity is invalid")
        if source_reference.get("exit_state_id") != source_identity["exit_state_id"]:
            raise ContractError("exit-state link source reference contradicts its identity")
        if payload["status"] != "recorded" or not SHA256.fullmatch(
            str(source_reference.get("exit_state_content_fingerprint"))
        ):
            raise ContractError("exit-state link evidence is incomplete")
    expected_id = "machine-link:" + canonical_fingerprint(_machine_link_identity(payload))
    if payload["link_id"] != expected_id:
        raise ContractError("M09 machine link id does not match its source identity")
    expected_content = canonical_fingerprint(_semantic(payload, "link_content_fingerprint"))
    if payload["link_content_fingerprint"] != expected_content:
        raise ContractError("M09 machine link content fingerprint is invalid")
    forbidden = FORBIDDEN_PERFORMANCE_KEYS & _all_keys(payload)
    if forbidden:
        raise ContractError(f"M09 machine link contains M10 fields: {', '.join(sorted(forbidden))}")


def produce_trade_plan_links(
    event_batch: EventLedgerBatch,
    trade_plan_batch: TradePlanBatch,
    *,
    generated_at: str,
) -> tuple[Mapping[str, Any], ...]:
    """Append M08 decisions after event creation without changing event bytes."""

    validate_event_ledger_batch(event_batch)
    validate_trade_plan_batch(trade_plan_batch)
    if trade_plan_batch.ranking_snapshot_id != event_batch.ranking_snapshot_id:
        raise ContractError("M08 decision batch belongs to another RankingSnapshot")
    decisions = {str(item["score_result_id"]): item for item in trade_plan_batch.decisions}
    plans = {str(item["plan_id"]): item for item in trade_plan_batch.plans}
    event_score_ids = {str(item["score_result_id"]) for item in event_batch.events}
    if set(decisions) != event_score_ids:
        raise ContractError("M08 decisions do not conserve M09 ranked events")
    links: list[Mapping[str, Any]] = []
    for event in event_batch.events:
        decision = decisions[str(event["score_result_id"])]
        if (
            decision["instrument_id"] != event["instrument_id"]
            or decision["gate_event_id"] != event["gate_event_id"]
        ):
            raise ContractError("M08 decision crosses an M09 event identity")
        plan = plans.get(str(decision["plan_id"])) if decision["plan_id"] is not None else None
        if plan is not None and plan["plan_role"] != "authoritative":
            raise ContractError("non-authoritative M08 plan cannot attach to an authoritative event")
        source_identity = {
            "trade_plan_batch_id": trade_plan_batch.batch_id,
            "score_result_id": event["score_result_id"],
        }
        payload: dict[str, Any] = {
            "schema_version": MACHINE_LINK_SCHEMA_VERSION,
            "as_of": event["signal_date"],
            "generated_at": generated_at,
            "source_version": {"ledger_producer": LEDGER_PRODUCER_VERSION},
            "future_data_used": False,
            "event_id": event["event_id"],
            "instrument_id": event["instrument_id"],
            "signal_date": event["signal_date"],
            "link_type": "trade_plan_decision",
            "source_identity": source_identity,
            "source_reference": {
                "trade_plan_batch_id": trade_plan_batch.batch_id,
                "ranking_snapshot_id": trade_plan_batch.ranking_snapshot_id,
                "score_result_id": event["score_result_id"],
                "status": decision["status"],
                "reason": decision["reason"],
                "plan_id": decision["plan_id"],
                "plan_content_fingerprint": (
                    plan["plan_content_fingerprint"] if plan is not None else None
                ),
            },
            "status": decision["status"],
            "reason": decision["reason"],
        }
        payload["link_id"] = "machine-link:" + canonical_fingerprint(
            _machine_link_identity(payload)
        )
        payload["link_content_fingerprint"] = canonical_fingerprint(
            _semantic(payload, "link_content_fingerprint")
        )
        validate_machine_link(payload)
        links.append(_freeze(payload))
    links.sort(key=lambda item: str(item["instrument_id"]))
    return tuple(links)


def produce_ranking_revision_link(
    event: Mapping[str, Any],
    *,
    gate_events: Iterable[Mapping[str, Any]],
    technical_evidence: TechnicalEvidenceBatch,
    model_assessments: ModelAssessmentBatch,
    contexts: ContextBatch,
    ranking_snapshot: Mapping[str, Any],
    generated_at: str,
) -> Mapping[str, Any]:
    """Re-run the sole batch producer before linking a later authoritative view."""

    validate_opportunity_event(event)
    revised_batch = produce_event_ledger_batch(
        gate_events=gate_events,
        technical_evidence=technical_evidence,
        model_assessments=model_assessments,
        contexts=contexts,
        ranking_snapshot=ranking_snapshot,
        generated_at=generated_at,
    )
    candidates = [item for item in revised_batch.events if item["event_id"] == event["event_id"]]
    if len(candidates) != 1:
        raise ContractError("M09 evidence revision does not contain the existing event root")
    revised_evidence = candidates[0]
    if revised_evidence["event_content_fingerprint"] == event["event_content_fingerprint"]:
        raise ContractError("identical M09 evidence is an idempotent replay, not a revision")
    source_identity = {
        "ranking_snapshot_id": revised_evidence["ranking_snapshot_id"],
        "score_result_id": revised_evidence["score_result_id"],
    }
    payload: dict[str, Any] = {
        "schema_version": MACHINE_LINK_SCHEMA_VERSION,
        "as_of": event["signal_date"],
        "generated_at": generated_at,
        "source_version": {"ledger_producer": LEDGER_PRODUCER_VERSION},
        "future_data_used": False,
        "event_id": event["event_id"],
        "instrument_id": event["instrument_id"],
        "signal_date": event["signal_date"],
        "link_type": "ranking_evidence_revision",
        "source_identity": source_identity,
        "source_reference": {
            "event_content_fingerprint": revised_evidence["event_content_fingerprint"],
            "ranking_snapshot_id": revised_evidence["ranking_snapshot_id"],
            "ranking_content_fingerprint": revised_evidence["ranking_content_fingerprint"],
            "score_result_id": revised_evidence["score_result_id"],
            "gate_reference": _plain(revised_evidence["gate_reference"]),
            "technical_reference": _plain(revised_evidence["technical_reference"]),
            "model_assessments": _plain(revised_evidence["model_assessments"]),
            "context_reference": _plain(revised_evidence["context_reference"]),
            "policy_versions": _plain(revised_evidence["policy_versions"]),
        },
        "status": "recorded",
        "reason": None,
    }
    payload["link_id"] = "machine-link:" + canonical_fingerprint(
        _machine_link_identity(payload)
    )
    payload["link_content_fingerprint"] = canonical_fingerprint(
        _semantic(payload, "link_content_fingerprint")
    )
    validate_machine_link(payload)
    return _freeze(payload)


def produce_exit_state_link(
    event: Mapping[str, Any],
    trade_plan_link: Mapping[str, Any],
    exit_state: Mapping[str, Any],
    *,
    generated_at: str,
) -> Mapping[str, Any]:
    """Reference one immutable M08 exit state without deriving performance."""

    validate_opportunity_event(event)
    validate_machine_link(trade_plan_link)
    validate_exit_state(exit_state)
    if (
        trade_plan_link["event_id"] != event["event_id"]
        or trade_plan_link["link_type"] != "trade_plan_decision"
        or trade_plan_link["source_reference"].get("plan_id") != exit_state["plan_id"]
    ):
        raise ContractError("ExitState does not belong to the event's M08 plan")
    source_identity = {"exit_state_id": exit_state["exit_state_id"]}
    payload: dict[str, Any] = {
        "schema_version": MACHINE_LINK_SCHEMA_VERSION,
        "as_of": event["signal_date"],
        "generated_at": generated_at,
        "source_version": {"ledger_producer": LEDGER_PRODUCER_VERSION},
        "future_data_used": False,
        "event_id": event["event_id"],
        "instrument_id": event["instrument_id"],
        "signal_date": event["signal_date"],
        "link_type": "exit_state",
        "source_identity": source_identity,
        "source_reference": {
            "exit_state_id": exit_state["exit_state_id"],
            "exit_state_content_fingerprint": exit_state["exit_state_content_fingerprint"],
            "plan_id": exit_state["plan_id"],
            "previous_exit_state_id": exit_state["previous_exit_state_id"],
        },
        "status": "recorded",
        "reason": None,
    }
    payload["link_id"] = "machine-link:" + canonical_fingerprint(
        _machine_link_identity(payload)
    )
    payload["link_content_fingerprint"] = canonical_fingerprint(
        _semantic(payload, "link_content_fingerprint")
    )
    validate_machine_link(payload)
    return _freeze(payload)


def _human_review_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "subject_type": payload["subject_type"],
        "subject_reference": _plain(payload["subject_reference"]),
        "review_type": payload["review_type"],
        "author_id": payload["author_id"],
        "authored_at": payload["authored_at"],
        "body": payload["body"],
        "evidence_refs": _plain(payload["evidence_refs"]),
        "tags": list(payload["tags"]),
        "supersedes_review_id": payload["supersedes_review_id"],
        "approval_ref": payload["approval_ref"],
    }


def validate_human_review(
    payload: Mapping[str, Any],
    *,
    known_event_ids: AbstractSet[str] | None = None,
    known_ranking_exclusions: AbstractSet[tuple[str, str]] | None = None,
    known_approval_refs: AbstractSet[str] | None = None,
    require_known_subject: bool = False,
) -> None:
    required = {
        "schema_version", "as_of", "generated_at", "source_version",
        "future_data_used", "review_id", "review_content_fingerprint",
        "subject_type", "subject_reference", "review_type", "author_id",
        "authored_at", "body", "evidence_refs", "tags",
        "supersedes_review_id", "approval_ref",
    }
    if not isinstance(payload, Mapping) or required - payload.keys():
        raise ContractError("HumanReviewRecord is incomplete")
    if payload["schema_version"] != HUMAN_REVIEW_SCHEMA_VERSION:
        raise ContractError("HumanReviewRecord schema is unknown")
    require_date(payload["as_of"], "as_of")
    _require_timestamp(payload["generated_at"], "generated_at")
    authored_at = _require_timestamp(payload["authored_at"], "authored_at")
    if payload["as_of"] != authored_at[:10] or payload["future_data_used"] is not False:
        raise ContractError("HumanReviewRecord date evidence is invalid")
    if payload["source_version"].get("ledger_producer") != LEDGER_PRODUCER_VERSION:
        raise ContractError("HumanReviewRecord producer is unknown")
    if not re.fullmatch(r"human-review:sha256:[0-9a-f]{64}", str(payload["review_id"])):
        raise ContractError("HumanReviewRecord id is invalid")
    subject_type = payload["subject_type"]
    subject = payload["subject_reference"]
    if not isinstance(subject, Mapping):
        raise ContractError("HumanReviewRecord subject_reference must be an object")
    if subject_type == "event":
        if set(subject) != {"event_id"} or not re.fullmatch(
            r"opportunity:sha256:[0-9a-f]{64}", str(subject.get("event_id"))
        ):
            raise ContractError("event review requires exactly one formal event_id")
        if require_known_subject and (
            known_event_ids is None or str(subject["event_id"]) not in known_event_ids
        ):
            raise ContractError("event review subject is not present in injected ledger evidence")
    elif subject_type == "ranking_exclusion":
        if set(subject) != {"ranking_snapshot_id", "score_result_id"}:
            raise ContractError("ranking exclusion review has an invalid subject")
        if not re.fullmatch(r"ranking:sha256:[0-9a-f]{64}", str(subject["ranking_snapshot_id"])):
            raise ContractError("ranking exclusion review has an invalid ranking ID")
        if not re.fullmatch(r"score:sha256:[0-9a-f]{64}", str(subject["score_result_id"])):
            raise ContractError("ranking exclusion review has an invalid score ID")
        exclusion_key = (
            str(subject["ranking_snapshot_id"]), str(subject["score_result_id"])
        )
        if require_known_subject and (
            known_ranking_exclusions is None or exclusion_key not in known_ranking_exclusions
        ):
            raise ContractError("ranking exclusion review subject is not in injected ranking evidence")
    else:
        raise ContractError("HumanReviewRecord subject type is invalid")
    if payload["review_type"] not in {"observation", "hypothesis", "approved_change"}:
        raise ContractError("HumanReviewRecord review type is invalid")
    _require_text(payload["author_id"], "author_id")
    _require_text(payload["body"], "body")
    if not isinstance(payload["evidence_refs"], (list, tuple)) or any(
        not isinstance(item, Mapping) for item in payload["evidence_refs"]
    ):
        raise ContractError("HumanReviewRecord evidence_refs must contain objects")
    tags = payload["tags"]
    if (
        not isinstance(tags, (list, tuple))
        or any(not isinstance(item, str) or not item for item in tags)
        or list(tags) != sorted(set(tags))
    ):
        raise ContractError("HumanReviewRecord tags must be sorted unique text")
    supersedes = payload["supersedes_review_id"]
    if supersedes is not None and not re.fullmatch(r"human-review:sha256:[0-9a-f]{64}", str(supersedes)):
        raise ContractError("HumanReviewRecord supersedes_review_id is invalid")
    approval = payload["approval_ref"]
    if payload["review_type"] == "approved_change":
        _require_text(approval, "approval_ref")
        if known_approval_refs is None or str(approval) not in known_approval_refs:
            raise ContractError("approved_change lacks an injected approved governance reference")
    elif approval is not None:
        raise ContractError("only approved_change may carry approval_ref")
    expected_id = "human-review:" + canonical_fingerprint(_human_review_identity(payload))
    if payload["review_id"] != expected_id:
        raise ContractError("HumanReviewRecord id does not match its content identity")
    if payload["review_content_fingerprint"] != canonical_fingerprint(
        _semantic(payload, "review_content_fingerprint")
    ):
        raise ContractError("HumanReviewRecord content fingerprint is invalid")
    forbidden = FORBIDDEN_PERFORMANCE_KEYS & _all_keys(payload)
    if forbidden:
        raise ContractError(f"HumanReviewRecord contains M10 fields: {', '.join(sorted(forbidden))}")


def create_human_review(
    *,
    subject_type: str,
    subject_reference: Mapping[str, Any],
    review_type: str,
    author_id: str,
    authored_at: str,
    body: str,
    evidence_refs: Sequence[Mapping[str, Any]] = (),
    tags: Sequence[str] = (),
    supersedes_review: Mapping[str, Any] | None = None,
    approval_ref: str | None = None,
    known_event_ids: AbstractSet[str] = frozenset(),
    known_ranking_exclusions: AbstractSet[tuple[str, str]] = frozenset(),
    known_approval_refs: AbstractSet[str] = frozenset(),
) -> Mapping[str, Any]:
    """Create an immutable human note; corrections append and reference the old note."""

    if supersedes_review is not None:
        validate_human_review(
            supersedes_review,
            known_event_ids=known_event_ids,
            known_ranking_exclusions=known_ranking_exclusions,
            known_approval_refs=known_approval_refs,
            require_known_subject=True,
        )
        if (
            supersedes_review["subject_type"] != subject_type
            or _plain(supersedes_review["subject_reference"]) != _plain(subject_reference)
        ):
            raise ContractError("human review correction crosses subjects")
    evidence = sorted(
        (_plain(item) for item in evidence_refs), key=canonical_fingerprint
    )
    payload: dict[str, Any] = {
        "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
        "as_of": _require_timestamp(authored_at, "authored_at")[:10],
        "generated_at": authored_at,
        "source_version": {"ledger_producer": LEDGER_PRODUCER_VERSION},
        "future_data_used": False,
        "subject_type": subject_type,
        "subject_reference": _plain(subject_reference),
        "review_type": review_type,
        "author_id": author_id,
        "authored_at": authored_at,
        "body": body,
        "evidence_refs": evidence,
        "tags": sorted(set(tags)),
        "supersedes_review_id": (
            supersedes_review["review_id"] if supersedes_review is not None else None
        ),
        "approval_ref": approval_ref,
    }
    payload["review_id"] = "human-review:" + canonical_fingerprint(
        _human_review_identity(payload)
    )
    payload["review_content_fingerprint"] = canonical_fingerprint(
        _semantic(payload, "review_content_fingerprint")
    )
    validate_human_review(
        payload,
        known_event_ids=known_event_ids,
        known_ranking_exclusions=known_ranking_exclusions,
        known_approval_refs=known_approval_refs,
        require_known_subject=True,
    )
    return _freeze(payload)


def ranking_exclusion_subjects(
    ranking_snapshot: Mapping[str, Any],
) -> frozenset[tuple[str, str]]:
    """Derive reviewable exclusions only from one validated M07 snapshot."""

    validate_ranking_snapshot(ranking_snapshot)
    return frozenset(
        (
            str(ranking_snapshot["ranking_snapshot_id"]),
            str(item["score_result_id"]),
        )
        for item in ranking_snapshot["excluded_entries"]
    )


def query_events(
    events: Iterable[Mapping[str, Any]],
    *,
    instrument_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    selected: bool | None = None,
    rank: int | None = None,
    score_policy_version: str | None = None,
) -> tuple[Mapping[str, Any], ...]:
    """Build a disposable query view; the immutable events remain the authority."""

    if date_from is not None:
        require_date(date_from, "date_from")
    if date_to is not None:
        require_date(date_to, "date_to")
    result: list[Mapping[str, Any]] = []
    for event in events:
        validate_opportunity_event(event)
        if instrument_id is not None and event["instrument_id"] != instrument_id:
            continue
        if date_from is not None and event["signal_date"] < date_from:
            continue
        if date_to is not None and event["signal_date"] > date_to:
            continue
        if selected is not None and event["selected"] is not selected:
            continue
        if rank is not None and event["rank"] != rank:
            continue
        if score_policy_version is not None and event["policy_versions"]["score"]["version"] != score_policy_version:
            continue
        result.append(event)
    return tuple(sorted(result, key=lambda item: (str(item["signal_date"]), str(item["instrument_id"]))))


__all__ = [
    "EventLedgerBatch",
    "HUMAN_REVIEW_SCHEMA_VERSION",
    "LEDGER_PRODUCER_VERSION",
    "MACHINE_LINK_SCHEMA_VERSION",
    "OPPORTUNITY_EVENT_SCHEMA_VERSION",
    "create_human_review",
    "produce_event_ledger_batch",
    "produce_exit_state_link",
    "produce_ranking_revision_link",
    "produce_trade_plan_links",
    "query_events",
    "ranking_exclusion_subjects",
    "validate_event_ledger_batch",
    "validate_human_review",
    "validate_machine_link",
    "validate_opportunity_event",
]
