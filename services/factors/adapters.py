"""One-way, explicit legacy adapter for old nested factor states."""

from __future__ import annotations

from typing import Any, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError, validate_contract
from services.scanner.factor_registry import FACTORS_BY_ID


LEGACY_ADAPTER_VERSION = "legacy-adapter-m04-factor-state-1.0.0"
LEGACY_BIAS = "legacy_factor_state_without_formal_m02_m03_identity"


def adapt_legacy_factor_state(
    state: Mapping[str, Any],
    *,
    symbol: str,
    as_of: str,
    generated_at: str,
    registry_version: str,
) -> dict[str, Any]:
    """Expose an old state as legacy without inventing formal identities."""

    if not isinstance(state, Mapping):
        raise ContractError("legacy factor state must be an object")
    factor_id = state.get("factor_id")
    factor = FACTORS_BY_ID.get(str(factor_id))
    if factor is None:
        raise ContractError("legacy factor state references an unknown factor")
    required = {"factor_version", "available", "lookahead_audit"}
    missing = sorted(required - state.keys())
    if missing:
        raise ContractError(
            f"legacy factor state missing evidence: {', '.join(missing)}"
        )
    audit = state["lookahead_audit"]
    if not isinstance(audit, Mapping) or audit.get("future_data_used") is not False:
        raise ContractError("legacy factor state lacks explicit no-future evidence")
    evidence_date = state.get("latest_hit_date") or as_of
    identity = {
        "adapter_version": LEGACY_ADAPTER_VERSION,
        "symbol": symbol,
        "as_of": as_of,
        "factor_id": factor.id,
        "factor_version": state["factor_version"],
    }
    payload = {
        "schema_version": "1.0.0",
        "as_of": as_of,
        "generated_at": generated_at,
        "source_version": {"registry": registry_version, "source": "legacy-factor-snapshot"},
        "future_data_used": False,
        "adapter_version": LEGACY_ADAPTER_VERSION,
        "evidence_id": "evidence:legacy:" + canonical_fingerprint(identity),
        "factor_id": factor.id,
        "factor_version": state["factor_version"],
        "timeframe": factor.timeframe,
        "evidence_date": evidence_date,
        "available": state["available"],
        "path_status": "legacy",
        "bias_labels": [LEGACY_BIAS],
        "legacy_state": dict(state),
    }
    validate_contract("TechnicalEvidence", payload)
    return payload
