"""Sole M04 producer for immutable, score-free factor evidence.

The producer accepts only identities already validated by M02 and M03.  It
does not discover files, read Git, access the network, score a stock, or write
an artifact.  Daily and replay shadows call this same function.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError, validate_contract
from services.gates.producer import require_gate_event_for_path
from services.market_data.consumer import ShadowConsumerInput, require_shadow_rows
from services.scanner.factor_detectors import FactorState, evaluate_all_factors
from services.scanner.factor_registry import FACTORS, FACTORS_BY_ID, REGISTRY_VERSION


TECHNICAL_EVIDENCE_SCHEMA_VERSION = "2.0.0"
DETECTOR_POLICY_VERSION = "m04-factor-evidence-1.0.0"
GATE_REFERENCE_FACTOR_IDS = frozenset({
    "qualification.long_trend",
    "macd.daily_bull_cross",
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


def _identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "gate_event_id": payload["gate_event_id"],
        "instrument_id": payload["instrument_id"],
        "as_of": payload["as_of"],
        "path_status": payload["path_status"],
        "universe_id": payload["universe_id"],
        "market_snapshot_id": payload["market_snapshot_id"],
        "adjustment_policy": _plain(payload["adjustment_policy"]),
        "registry_version": payload["registry_version"],
        "detector_policy_version": payload["detector_policy_version"],
        "factor_id": payload["factor_id"],
        "factor_version": payload["factor_version"],
    }


def _semantic_content(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _plain(value)
        for key, value in payload.items()
        if key not in {"generated_at", "evidence_content_fingerprint"}
    }


def validate_technical_evidence(payload: Mapping[str, Any]) -> None:
    """Validate the shared contract and its current registry binding."""

    validate_contract("TechnicalEvidence", payload)
    if not str(payload["schema_version"]).startswith("2."):
        raise ContractError("formal M04 consumers require TechnicalEvidence 2.x")
    factor = FACTORS_BY_ID.get(str(payload["factor_id"]))
    if factor is None:
        raise ContractError("TechnicalEvidence references an unknown factor")
    expected = {
        "factor_version": factor.version,
        "timeframe": factor.timeframe,
        "family": factor.evidence_family,
        "registry_version": REGISTRY_VERSION,
        "detector_policy_version": DETECTOR_POLICY_VERSION,
    }
    for field, value in expected.items():
        if payload[field] != value:
            raise ContractError(f"TechnicalEvidence {field} does not match its authority")
    expected_source = (
        "gate_reference"
        if factor.id in GATE_REFERENCE_FACTOR_IDS
        else "factor_detector"
    )
    if payload["source_kind"] != expected_source:
        raise ContractError("TechnicalEvidence source_kind does not match factor ownership")


@dataclass(frozen=True)
class TechnicalEvidenceBatch:
    """One immutable evidence collection for explicitly supplied GateEvents."""

    batch_id: str
    as_of: str
    path_status: str
    registry_version: str
    evidence: tuple[Mapping[str, Any], ...]


def _gate_references(event: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    checks = event["baseline_checks"]
    return {
        "qualification.long_trend": {
            "hit": bool(event["baseline_passed"]),
            "evidence": {
                "gate_event_id": event["gate_event_id"],
                "baseline_check": _plain(checks["legacy_long_trend_equivalence"]),
            },
        },
        "macd.daily_bull_cross": {
            "hit": checks["exact_daily_macd_cross"]["status"] == "passed",
            "evidence": {
                "gate_event_id": event["gate_event_id"],
                "baseline_check": _plain(checks["exact_daily_macd_cross"]),
            },
        },
    }


def _qualified_hits(states: Mapping[str, FactorState]) -> dict[str, tuple[bool, tuple[str, ...]]]:
    """Resolve parent requirements once without turning them into scores."""

    results: dict[str, tuple[bool, tuple[str, ...]]] = {}
    visiting: set[str] = set()

    def resolve(factor_id: str) -> tuple[bool, tuple[str, ...]]:
        if factor_id in results:
            return results[factor_id]
        if factor_id in visiting:
            raise ContractError("factor registry dependency graph contains a cycle")
        state = states.get(factor_id)
        factor = FACTORS_BY_ID.get(factor_id)
        if state is None or factor is None:
            raise ContractError("factor registry and detector output are inconsistent")
        visiting.add(factor_id)
        parents = list(factor.depends_on)
        parent_results = {parent: resolve(parent)[0] for parent in parents}
        if not parents:
            dependency_ok = True
            blocked = ()
        elif factor.dependency_policy == "any":
            dependency_ok = not parents or any(parent_results.values())
            blocked = tuple(sorted(parents)) if parents and not dependency_ok else ()
        elif factor.dependency_policy == "all":
            blocked = tuple(sorted(parent for parent, passed in parent_results.items() if not passed))
            dependency_ok = not blocked
        else:
            raise ContractError("factor registry has an unknown dependency policy")
        result = (bool(state.available and state.hit and dependency_ok), blocked)
        results[factor_id] = result
        visiting.remove(factor_id)
        return result

    for factor in FACTORS:
        resolve(factor.id)
    return results


def _event_matches_input(event: Mapping[str, Any], prepared: ShadowConsumerInput) -> None:
    if event["signal_date"] != prepared.as_of or event["as_of"] != prepared.as_of:
        raise ContractError("GateEvent date does not match M02 point-in-time input")
    identity = event["input_identity"]
    if identity["universe_id"] != prepared.universe_id:
        raise ContractError("GateEvent universe does not match M02 input")
    if identity["market_snapshot_id"] != prepared.market_snapshot_id:
        raise ContractError("GateEvent market snapshot does not match M02 input")
    if _plain(identity["adjustment_policy"]) != ADJUSTMENT_POLICY:
        raise ContractError("GateEvent adjustment policy does not match M02")


def produce_technical_evidence(
    prepared: ShadowConsumerInput,
    *,
    gate_events: Iterable[Mapping[str, Any]],
    generated_at: str,
    detector: Callable[..., list[FactorState]] = evaluate_all_factors,
) -> TechnicalEvidenceBatch:
    """Produce every registered objective factor exactly once per GateEvent."""

    if not isinstance(prepared, ShadowConsumerInput):
        raise ContractError("M04 producer requires M02 ShadowConsumerInput")
    rows_by_symbol = require_shadow_rows(prepared, consumer=prepared.consumer)
    events = tuple(gate_events)
    if prepared.mode == "formal" and events and prepared.market_snapshot is None:
        raise ContractError("formal TechnicalEvidence requires an M02 market snapshot")
    seen_events: set[str] = set()
    output: list[Mapping[str, Any]] = []
    for event in sorted(events, key=lambda item: str(item.get("gate_event_id"))):
        require_gate_event_for_path(event, path_status=prepared.mode)
        if not str(event["schema_version"]).startswith("2."):
            raise ContractError(
                "M04 producer requires GateEvent 2.x; use the explicit legacy adapter"
            )
        _event_matches_input(event, prepared)
        event_id = str(event["gate_event_id"])
        if event_id in seen_events:
            raise ContractError("M04 input contains a duplicate GateEvent")
        seen_events.add(event_id)
        symbol = str(event["symbol"])
        rows = rows_by_symbol.get(symbol)
        if rows is None:
            raise ContractError("GateEvent has no immutable M02 rows")
        references = _gate_references(event)
        states_list = detector(rows, prepared.as_of, fact_references=references)
        states: dict[str, FactorState] = {}
        for state in states_list:
            if state.factor_id in states:
                raise ContractError("factor detector returned duplicate factor states")
            states[state.factor_id] = state
        if set(states) != set(FACTORS_BY_ID):
            raise ContractError("factor detector output does not match the active registry")
        qualified = _qualified_hits(states)
        for factor in FACTORS:
            state = states[factor.id]
            qualified_hit, blocked_by = qualified[factor.id]
            source_kind = (
                "gate_reference"
                if factor.id in GATE_REFERENCE_FACTOR_IDS
                else "factor_detector"
            )
            evidence_date = state.latest_hit_date or prepared.as_of
            payload: dict[str, Any] = {
                "schema_version": TECHNICAL_EVIDENCE_SCHEMA_VERSION,
                "as_of": prepared.as_of,
                "generated_at": generated_at,
                "source_version": {
                    "producer": DETECTOR_POLICY_VERSION,
                    "registry": REGISTRY_VERSION,
                },
                "future_data_used": False,
                "gate_event_id": event["gate_event_id"],
                "instrument_id": event["instrument_id"],
                "path_status": prepared.mode,
                "universe_id": prepared.universe_id,
                "market_snapshot_id": prepared.market_snapshot_id,
                "adjustment_policy": dict(ADJUSTMENT_POLICY),
                "registry_version": REGISTRY_VERSION,
                "detector_policy_version": DETECTOR_POLICY_VERSION,
                "factor_id": factor.id,
                "factor_version": factor.version,
                "family": factor.evidence_family,
                "timeframe": factor.timeframe,
                "source_kind": source_kind,
                "evidence_date": evidence_date,
                "available": bool(state.available),
                "raw_hit": bool(state.hit),
                "qualified_hit": qualified_hit,
                "blocked_by": list(blocked_by),
                "recent_hit": bool(state.recent_hit),
                "latest_hit_date": state.latest_hit_date,
                "bars_since_hit": state.bars_since_hit,
                "value": _plain(state.value),
                "evidence": _plain(state.evidence),
                "lookahead_audit": _plain(state.lookahead_audit),
                "bias_labels": list(prepared.bias_labels),
            }
            payload["evidence_id"] = "evidence:" + canonical_fingerprint(_identity(payload))
            payload["evidence_content_fingerprint"] = canonical_fingerprint(
                _semantic_content(payload)
            )
            validate_technical_evidence(payload)
            output.append(_freeze(payload))
    output.sort(key=lambda item: (str(item["instrument_id"]), str(item["factor_id"])))
    batch_identity = {
        "as_of": prepared.as_of,
        "path_status": prepared.mode,
        "registry_version": REGISTRY_VERSION,
        "evidence": [
            {
                "evidence_id": item["evidence_id"],
                "content": item["evidence_content_fingerprint"],
            }
            for item in output
        ],
    }
    return TechnicalEvidenceBatch(
        batch_id="technical-evidence-batch:" + canonical_fingerprint(batch_identity),
        as_of=prepared.as_of,
        path_status=prepared.mode,
        registry_version=REGISTRY_VERSION,
        evidence=tuple(output),
    )
