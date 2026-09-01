"""M04-owned immutable support evidence for downstream execution planning.

The existing support calculation remains the sole calculation. This module
binds its point-in-time result to stable M02/M03/M04 identities so M08 can
consume evidence instead of recalculating indicators or reading ranking prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError
from services.gates.producer import require_gate_event_for_path
from services.market_data.consumer import ShadowConsumerInput, require_shadow_rows
from services.scanner.support_risk import EXECUTION_POLICY_VERSION, signal_support_plan

from .producer import TechnicalEvidenceBatch, validate_technical_evidence_batch


SUPPORT_EVIDENCE_SCHEMA_VERSION = "2.0.0"
SUPPORT_EVIDENCE_PRODUCER_VERSION = "m04-execution-support-1.0.0"
SUPPORT_FACTOR_IDS = (
    "structure.higher_low",
    "support.ema_proximity",
    "support.volume_profile_proxy",
)


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


def _identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_major": 2,
        "as_of": payload["as_of"],
        "instrument_id": payload["instrument_id"],
        "gate_event_id": payload["gate_event_id"],
        "universe_id": payload["universe_id"],
        "market_snapshot_id": payload["market_snapshot_id"],
        "adjustment_policy": _plain(payload["adjustment_policy"]),
        "technical_evidence_batch_id": payload["technical_evidence_batch_id"],
        "technical_evidence_ids": list(payload["technical_evidence_ids"]),
        "support_policy_version": payload["support_policy_version"],
    }


def validate_support_evidence(payload: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "support_evidence_id", "support_content_fingerprint",
        "as_of", "generated_at", "future_data_used", "source_version",
        "instrument_id", "gate_event_id", "path_status", "universe_id",
        "market_snapshot_id", "adjustment_policy", "technical_evidence_batch_id",
        "technical_evidence_ids", "support_policy_version", "support_plan",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise ContractError(f"SupportEvidence missing required fields: {', '.join(missing)}")
    if payload["schema_version"] != SUPPORT_EVIDENCE_SCHEMA_VERSION:
        raise ContractError("formal support evidence requires schema 2.0.0")
    if payload["path_status"] != "formal" or payload["future_data_used"] is not False:
        raise ContractError("formal support evidence must be point-in-time and formal")
    if _plain(payload["adjustment_policy"]) != ADJUSTMENT_POLICY:
        raise ContractError("support evidence must use the M02 adjustment policy")
    ids = list(payload["technical_evidence_ids"])
    if ids != sorted(set(ids)) or not ids:
        raise ContractError("support evidence requires sorted unique M04 evidence IDs")
    plan = payload["support_plan"]
    if not isinstance(plan, Mapping) or not isinstance(plan.get("available"), bool):
        raise ContractError("support evidence requires an explicit support plan fact")
    if plan["available"]:
        level = plan.get("level")
        if isinstance(level, bool) or not isinstance(level, (int, float)) or level <= 0:
            raise ContractError("available support evidence requires a positive level")
        if not isinstance(plan.get("source"), str) or not plan["source"]:
            raise ContractError("available support evidence requires a source")
    expected = "support-evidence:" + canonical_fingerprint(_identity(payload))
    if payload["support_evidence_id"] != expected:
        raise ContractError("SupportEvidence id does not match its inputs")
    semantic = {
        key: _plain(value)
        for key, value in payload.items()
        if key not in {"generated_at", "support_content_fingerprint"}
    }
    if payload["support_content_fingerprint"] != canonical_fingerprint(semantic):
        raise ContractError("SupportEvidence content fingerprint is invalid")


@dataclass(frozen=True)
class SupportEvidenceBatch:
    batch_id: str
    as_of: str
    path_status: str
    technical_evidence_batch_id: str
    evidence: tuple[Mapping[str, Any], ...]


def validate_support_evidence_batch(batch: SupportEvidenceBatch) -> None:
    if not isinstance(batch, SupportEvidenceBatch):
        raise ContractError("expected an M04 SupportEvidenceBatch")
    seen: set[str] = set()
    for item in batch.evidence:
        validate_support_evidence(item)
        if item["as_of"] != batch.as_of or item["path_status"] != batch.path_status:
            raise ContractError("SupportEvidenceBatch contains mixed dates or paths")
        if item["technical_evidence_batch_id"] != batch.technical_evidence_batch_id:
            raise ContractError("SupportEvidenceBatch references mixed M04 batches")
        if item["support_evidence_id"] in seen:
            raise ContractError("SupportEvidenceBatch contains duplicate evidence")
        seen.add(str(item["support_evidence_id"]))
    identity = {
        "as_of": batch.as_of,
        "path_status": batch.path_status,
        "technical_evidence_batch_id": batch.technical_evidence_batch_id,
        "evidence": [
            {"id": item["support_evidence_id"], "content": item["support_content_fingerprint"]}
            for item in batch.evidence
        ],
    }
    if batch.batch_id != "support-evidence-batch:" + canonical_fingerprint(identity):
        raise ContractError("SupportEvidenceBatch identity does not match its contents")


def produce_support_evidence(
    prepared: ShadowConsumerInput,
    *,
    gate_events: Iterable[Mapping[str, Any]],
    technical_evidence: TechnicalEvidenceBatch,
    generated_at: str,
) -> SupportEvidenceBatch:
    """Bind the unchanged signal-time support result to upstream evidence IDs."""

    if prepared.mode != "formal":
        raise ContractError("formal support evidence does not accept legacy input")
    validate_technical_evidence_batch(technical_evidence)
    if technical_evidence.as_of != prepared.as_of or technical_evidence.path_status != "formal":
        raise ContractError("M04 support evidence input identities do not match")
    rows_by_symbol = require_shadow_rows(prepared, consumer=prepared.consumer)
    evidence_by_event: dict[str, dict[str, Mapping[str, Any]]] = {}
    for item in technical_evidence.evidence:
        evidence_by_event.setdefault(str(item["gate_event_id"]), {})[str(item["factor_id"])] = item
    output: list[Mapping[str, Any]] = []
    for event in sorted(gate_events, key=lambda item: str(item.get("gate_event_id"))):
        require_gate_event_for_path(event, path_status="formal")
        if event["signal_date"] != prepared.as_of:
            raise ContractError("support evidence date does not match GateEvent")
        rows = rows_by_symbol.get(str(event["symbol"]))
        if rows is None:
            raise ContractError("GateEvent has no immutable M02 rows for support evidence")
        sources = evidence_by_event.get(str(event["gate_event_id"]), {})
        if any(factor_id not in sources for factor_id in SUPPORT_FACTOR_IDS):
            raise ContractError("support evidence requires the complete M04 support source set")
        source_ids = sorted(str(sources[factor_id]["evidence_id"]) for factor_id in SUPPORT_FACTOR_IDS)
        payload: dict[str, Any] = {
            "schema_version": SUPPORT_EVIDENCE_SCHEMA_VERSION,
            "as_of": prepared.as_of,
            "generated_at": generated_at,
            "source_version": {"producer": SUPPORT_EVIDENCE_PRODUCER_VERSION},
            "future_data_used": False,
            "instrument_id": event["instrument_id"],
            "gate_event_id": event["gate_event_id"],
            "path_status": "formal",
            "universe_id": prepared.universe_id,
            "market_snapshot_id": prepared.market_snapshot_id,
            "adjustment_policy": dict(ADJUSTMENT_POLICY),
            "technical_evidence_batch_id": technical_evidence.batch_id,
            "technical_evidence_ids": source_ids,
            "support_policy_version": EXECUTION_POLICY_VERSION,
            "support_plan": signal_support_plan(rows),
        }
        payload["support_evidence_id"] = "support-evidence:" + canonical_fingerprint(_identity(payload))
        semantic = {key: _plain(value) for key, value in payload.items() if key != "generated_at"}
        payload["support_content_fingerprint"] = canonical_fingerprint(semantic)
        validate_support_evidence(payload)
        output.append(_freeze(payload))
    output.sort(key=lambda item: str(item["instrument_id"]))
    identity = {
        "as_of": prepared.as_of,
        "path_status": "formal",
        "technical_evidence_batch_id": technical_evidence.batch_id,
        "evidence": [
            {"id": item["support_evidence_id"], "content": item["support_content_fingerprint"]}
            for item in output
        ],
    }
    batch = SupportEvidenceBatch(
        batch_id="support-evidence-batch:" + canonical_fingerprint(identity),
        as_of=prepared.as_of,
        path_status="formal",
        technical_evidence_batch_id=technical_evidence.batch_id,
        evidence=tuple(output),
    )
    validate_support_evidence_batch(batch)
    return batch


__all__ = [
    "SUPPORT_EVIDENCE_SCHEMA_VERSION",
    "SupportEvidenceBatch",
    "produce_support_evidence",
    "validate_support_evidence",
    "validate_support_evidence_batch",
]
