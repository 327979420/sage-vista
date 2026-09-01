"""The only read-only view of legacy support-plan evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

from services.contracts.validation import ContractError


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class LegacyExecutionEvidence:
    path_status: str
    adapter_version: str
    source_sha256: str
    bias_labels: tuple[str, ...]
    payload: Mapping[str, Any]


def adapt_legacy_support_plan_bytes(raw: bytes) -> LegacyExecutionEvidence:
    before = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("legacy support-plan evidence is not valid JSON") from exc
    if not isinstance(payload, Mapping) or not isinstance(payload.get("available"), bool):
        raise ContractError("legacy support-plan evidence is incomplete")
    if hashlib.sha256(raw).hexdigest() != before:
        raise ContractError("legacy support-plan adapter modified source bytes")
    return LegacyExecutionEvidence(
        path_status="legacy",
        adapter_version="legacy-adapter-m08-1.0.0",
        source_sha256="sha256:" + before,
        bias_labels=("legacy_missing_m02_m04_m07_execution_identities",),
        payload=_freeze(payload),
    )


__all__ = ["LegacyExecutionEvidence", "adapt_legacy_support_plan_bytes"]
