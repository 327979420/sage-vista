"""The sole M03 creator of immutable GateEvent and GateScanAudit identities."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError, validate_contract
from services.market_data.consumer import ShadowConsumerInput, require_shadow_rows
from services.market_data.storage import atomic_write_validated_json, require_shadow_root

from .baseline import creation_boundary_reason, legacy_long_trend_equivalence
from .local_structure import assess_local_structure
from .long_term_state import assess_long_term

GATE_POLICY_VERSION = "m03-shadow-1.0.0"
SHADOW_FACT_SCHEMA_VERSION = "m03-shadow-facts-1.0.0"
NON_EVENT_REASONS = (
    "data_unavailable", "not_tradable", "insufficient_history",
    "below_price_floor", "below_liquidity_floor", "no_exact_daily_macd_cross",
)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _gate_identity(
    *, instrument_id: str, signal_date: str, path_status: str,
    universe_id: str, market_snapshot_id: str,
) -> dict[str, Any]:
    return {
        "schema_major": 2,
        "instrument_id": instrument_id,
        "signal_date": signal_date,
        "gate_policy_version": GATE_POLICY_VERSION,
        "path_status": path_status,
        "universe_id": universe_id,
        "market_snapshot_id": market_snapshot_id,
        "adjustment_policy": dict(ADJUSTMENT_POLICY),
    }


def _logical_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in identity.items() if key != "market_snapshot_id"}


def _semantic_content(event: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _thaw(value)
        for key, value in event.items()
        if key not in {"generated_at", "event_content_fingerprint"}
    }


def validate_gate_event(event: Mapping[str, Any]) -> None:
    """Validate GateEvent 2.x plus its logical and immutable content bindings."""

    validate_contract("GateEvent", event)
    if not str(event["schema_version"]).startswith("2."):
        return
    if event["gate_policy_version"] != GATE_POLICY_VERSION:
        raise ContractError("unknown M03 gate_policy_version")
    identity = _gate_identity(
        instrument_id=str(event["instrument_id"]),
        signal_date=str(event["signal_date"]),
        path_status=str(event["path_status"]),
        universe_id=str(event["input_identity"]["universe_id"]),
        market_snapshot_id=str(event["input_identity"]["market_snapshot_id"]),
    )
    logical = "gate-signal:" + canonical_fingerprint(_logical_identity(identity))
    if event["logical_signal_id"] != logical:
        raise ContractError("logical_signal_id does not match canonical M03 identity")
    expected_content = canonical_fingerprint(_semantic_content(event))
    if event["event_content_fingerprint"] != expected_content:
        raise ContractError("GateEvent content fingerprint does not match its facts")


def require_gate_event_for_path(event: Mapping[str, Any], *, path_status: str) -> Mapping[str, Any]:
    """Keep 1.x legacy evidence from entering a 2.x formal consumer."""

    validate_contract("GateEvent", event)
    major = int(str(event["schema_version"]).split(".", 1)[0])
    if path_status == "formal":
        if major != 2 or event.get("path_status") != "formal":
            raise ContractError("formal gate consumer requires GateEvent 2.x formal evidence")
        validate_gate_event(event)
    elif path_status == "legacy":
        if major == 2 and event.get("path_status") != "legacy":
            raise ContractError("legacy gate consumer requires explicitly legacy evidence")
    else:
        raise ContractError("gate consumer path must be formal or legacy")
    return event


def _build_event(
    *, prepared: ShadowConsumerInput, symbol: str, rows: tuple[Mapping[str, Any], ...],
    instrument_id: str, generated_at: str, previous_event: Mapping[str, Any] | None,
    market_revision_evidence: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    long_trend = legacy_long_trend_equivalence(rows)
    local = assess_local_structure(rows)
    long_term = assess_long_term(
        rows, as_of=prepared.as_of, baseline_long_trend=long_trend,
        local_structure=local,
    )
    identity = _gate_identity(
        instrument_id=instrument_id,
        signal_date=prepared.as_of,
        path_status=prepared.mode,
        universe_id=prepared.universe_id,
        market_snapshot_id=prepared.market_snapshot_id,
    )
    event_id = "gate:" + canonical_fingerprint(identity)
    logical_id = "gate-signal:" + canonical_fingerprint(_logical_identity(identity))
    previous = _thaw(previous_event) if previous_event is not None else None
    supersedes: str | None = None
    if previous is not None:
        validate_gate_event(previous)
        if previous["logical_signal_id"] != logical_id:
            raise ContractError("revision candidate belongs to a different logical gate signal")
        if previous["gate_event_id"] == event_id:
            supersedes = previous["supersedes_event_id"]
        else:
            evidence = _thaw(market_revision_evidence) if market_revision_evidence else None
            if not isinstance(evidence, Mapping):
                raise ContractError("market snapshot change requires explicit revision evidence")
            if evidence.get("from_market_snapshot_id") != previous["input_identity"]["market_snapshot_id"]:
                raise ContractError("revision evidence has the wrong prior market snapshot")
            if evidence.get("to_market_snapshot_id") != prepared.market_snapshot_id:
                raise ContractError("revision evidence has the wrong replacement market snapshot")
            revision_id = evidence.get("revision_id")
            if not isinstance(revision_id, str) or not revision_id.startswith("sha256:"):
                raise ContractError("revision evidence requires a stable revision_id")
            supersedes = previous["gate_event_id"]
    baseline_checks = {
        "data_integrity": {"status": "passed", "reason_codes": []},
        "tradability_liquidity": {
            "status": "passed", "close": rows[-1]["close"],
            "dollar_volume": rows[-1]["close"] * rows[-1]["volume"],
            "history_sessions": len(rows),
        },
        "exact_daily_macd_cross": {
            "status": "passed", "date": prepared.as_of, "recent_state_used": False,
        },
        "legacy_long_trend_equivalence": {
            "status": "passed" if long_trend else "failed",
            "ema200_ratio_floor": 0.9,
            "ema200_change_60d_floor": -0.03,
        },
    }
    event: dict[str, Any] = {
        "schema_version": "2.0.0",
        "as_of": prepared.as_of,
        "generated_at": generated_at,
        "source_version": {
            "gate_policy": GATE_POLICY_VERSION,
            "market_data_contract": "1.0.0",
            "universe_contract": "3.0.0" if prepared.mode == "formal" else "legacy-explicit",
        },
        "future_data_used": False,
        "gate_event_id": event_id,
        "logical_signal_id": logical_id,
        "supersedes_event_id": supersedes,
        "instrument_id": instrument_id,
        "symbol": symbol,
        "signal_date": prepared.as_of,
        "gate_policy_version": GATE_POLICY_VERSION,
        "path_status": prepared.mode,
        "input_identity": {
            "universe_id": prepared.universe_id,
            "market_snapshot_id": prepared.market_snapshot_id,
            "adjustment_policy": dict(ADJUSTMENT_POLICY),
        },
        "baseline_checks": baseline_checks,
        "baseline_passed": long_trend,
        "passed": long_trend,
        "baseline_reason_codes": [] if long_trend else ["legacy_long_trend_not_met"],
        "shadow_assessment": {
            "status": "observed",
            "suggested_disposition": (
                "shadow_exclusion_candidate"
                if local.get("classification") == "structure_broken"
                else "observe"
            ),
            "production_effect": False,
            "shadow_fact_schema_version": SHADOW_FACT_SCHEMA_VERSION,
            "local_structure": local,
            **long_term,
        },
        "bias_labels": list(prepared.bias_labels),
    }
    if supersedes is not None and previous is not None and previous["gate_event_id"] != event_id:
        event["market_revision_evidence"] = dict(market_revision_evidence or {})
    event["event_content_fingerprint"] = canonical_fingerprint(_semantic_content(event))
    validate_gate_event(event)
    if previous is not None and previous["gate_event_id"] == event_id:
        if previous["event_content_fingerprint"] != event["event_content_fingerprint"]:
            raise ContractError("gate event conflict: identical identity has different content")
        return _freeze(previous)
    return _freeze(event)


@dataclass(frozen=True)
class GateBatch:
    events: tuple[Mapping[str, Any], ...]
    audit: Mapping[str, Any]


def produce_gate_batch(
    prepared: ShadowConsumerInput, *, generated_at: str, scan_batch_id: str,
    previous_events: Iterable[Mapping[str, Any]] = (),
    market_revision_evidence: Mapping[str, Any] | None = None,
) -> GateBatch:
    """Create all boundary-reaching events and one batch-level non-event audit."""

    if not isinstance(prepared, ShadowConsumerInput):
        raise ContractError("M03 gate producer requires M02 ShadowConsumerInput")
    rows_by_symbol = require_shadow_rows(prepared, consumer=prepared.consumer)
    symbols = {item["symbol"]: item["instrument_id"] for item in prepared.market_snapshot["symbols"]}
    previous_by_logical: dict[tuple[str, str], Mapping[str, Any]] = {}
    for event in previous_events:
        validate_gate_event(event)
        previous_by_logical[(str(event["instrument_id"]), str(event["signal_date"]))] = event
    counts = {reason: 0 for reason in NON_EVENT_REASONS}
    events: list[Mapping[str, Any]] = []
    for symbol, rows in sorted(rows_by_symbol.items()):
        reason = creation_boundary_reason(rows, as_of=prepared.as_of)
        if reason is not None:
            counts[reason] += 1
            continue
        instrument_id = symbols[symbol]
        events.append(_build_event(
            prepared=prepared, symbol=symbol, rows=rows, instrument_id=instrument_id,
            generated_at=generated_at,
            previous_event=previous_by_logical.get((instrument_id, prepared.as_of)),
            market_revision_evidence=market_revision_evidence,
        ))
    passed_count = sum(bool(event["baseline_passed"]) for event in events)
    audit_identity = {
        "as_of": prepared.as_of,
        "scan_batch_id": scan_batch_id,
        "gate_policy_version": GATE_POLICY_VERSION,
        "path_status": prepared.mode,
        "universe_id": prepared.universe_id,
        "market_snapshot_id": prepared.market_snapshot_id,
        "adjustment_policy": dict(ADJUSTMENT_POLICY),
    }
    audit: dict[str, Any] = {
        "schema_version": "1.0.0",
        "as_of": prepared.as_of,
        "generated_at": generated_at,
        "source_version": {"gate_policy": GATE_POLICY_VERSION},
        "future_data_used": False,
        "scan_audit_id": "gate-audit:" + canonical_fingerprint(audit_identity),
        "scan_batch_id": scan_batch_id,
        "gate_policy_version": GATE_POLICY_VERSION,
        "path_status": prepared.mode,
        "input_identity": {
            "universe_id": prepared.universe_id,
            "market_snapshot_id": prepared.market_snapshot_id,
            "adjustment_policy": dict(ADJUSTMENT_POLICY),
        },
        "input_count": len(rows_by_symbol),
        "gate_event_created_count": len(events),
        "baseline_passed_count": passed_count,
        "baseline_failed_count": len(events) - passed_count,
        "non_event_reason_counts": counts,
        "audit_status": "complete",
        "reason_codes": [],
    }
    validate_contract("GateScanAudit", audit)
    return GateBatch(tuple(events), _freeze(audit))


class GateEventStore:
    """Append immutable M03 shadow events/audits under temp or repository work/."""

    def __init__(self, root: str | Path, *, workspace_root: str | Path | None = None):
        self.root = require_shadow_root(root, workspace_root=workspace_root)

    def save(self, event: Mapping[str, Any]) -> Path:
        validate_gate_event(event)
        path = self.root / "gate-events" / f"{event['gate_event_id'].split(':')[-1]}.json"
        if path.exists():
            existing = json.loads(path.read_text())
            validate_gate_event(existing)
            if existing["event_content_fingerprint"] != event["event_content_fingerprint"]:
                raise ContractError("gate event conflict: immutable stored event differs")
            return path
        atomic_write_validated_json(path, _thaw(event), validator=validate_gate_event)
        return path

    def save_audit(self, audit: Mapping[str, Any]) -> Path:
        """Persist one batch identity once; changed counts are a real conflict."""

        validate_contract("GateScanAudit", audit)
        path = self.root / "scan-audits" / f"{audit['scan_audit_id'].split(':')[-1]}.json"
        semantic = {
            key: _thaw(value) for key, value in audit.items() if key != "generated_at"
        }
        if path.exists():
            existing = json.loads(path.read_text())
            validate_contract("GateScanAudit", existing)
            existing_semantic = {
                key: value for key, value in existing.items() if key != "generated_at"
            }
            if canonical_fingerprint(existing_semantic) != canonical_fingerprint(semantic):
                raise ContractError("gate scan audit conflict: identical identity has different counts")
            return path
        atomic_write_validated_json(
            path,
            _thaw(audit),
            validator=lambda staged: validate_contract("GateScanAudit", staged),
        )
        return path


def current_gate_event(events: Iterable[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Resolve the unique unsuperseded event without using file or input order."""

    materialized = list(events)
    for event in materialized:
        validate_gate_event(event)
    by_id = {event["gate_event_id"]: event for event in materialized}
    if len(by_id) != len(materialized):
        raise ContractError("gate revision chain contains duplicate event identities")
    superseded = set()
    for event in materialized:
        prior_id = event["supersedes_event_id"]
        if not prior_id:
            continue
        prior = by_id.get(prior_id)
        if prior is None or prior["logical_signal_id"] != event["logical_signal_id"]:
            raise ContractError("gate revision chain has a missing or cross-signal link")
        superseded.add(prior_id)
    current = [event for event in materialized if event["gate_event_id"] not in superseded]
    if len(current) != 1:
        raise ContractError("gate revision chain has no unique current event")
    return current[0]
