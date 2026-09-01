"""One explicit read-only adapter for legacy selector outputs."""

from __future__ import annotations

from typing import Any, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError, validate_contract


LEGACY_ADAPTER_VERSION = "legacy-adapter-m05-model-assessment-1.0.0"
LEGACY_BIAS = "legacy_selector_without_formal_m02_m03_m04_identity"


def adapt_legacy_model_assessment(
    source: Mapping[str, Any],
    *,
    model_id: str,
    model_version: str,
    symbol: str,
    as_of: str,
    generated_at: str,
) -> dict[str, Any]:
    """Preserve an old selector result without inventing formal evidence."""

    if not isinstance(source, Mapping) or not source:
        raise ContractError("legacy selector source must be a non-empty object")
    if not all(isinstance(value, str) and value for value in (model_id, model_version, symbol)):
        raise ContractError("legacy selector identity is incomplete")
    identity = {
        "adapter_version": LEGACY_ADAPTER_VERSION,
        "model_id": model_id,
        "model_version": model_version,
        "symbol": symbol,
        "as_of": as_of,
        "source_fingerprint": canonical_fingerprint(source),
    }
    payload = {
        "schema_version": "1.0.0",
        "as_of": as_of,
        "generated_at": generated_at,
        "source_version": {"adapter": LEGACY_ADAPTER_VERSION},
        "future_data_used": False,
        "assessment_id": "assessment:legacy:" + canonical_fingerprint(identity),
        "gate_event_id": "gate:legacy-reference:" + canonical_fingerprint(
            {"symbol": symbol, "as_of": as_of}
        ),
        "model_id": model_id,
        "model_version": model_version,
        "eligible": bool(source.get("eligible", source.get("stage") == "entry_ready")),
        "path_status": "legacy",
        "adapter_version": LEGACY_ADAPTER_VERSION,
        "bias_labels": [LEGACY_BIAS],
        "legacy_source": dict(source),
    }
    validate_contract("ModelAssessment", payload)
    return payload
