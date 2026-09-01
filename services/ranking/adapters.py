"""The only read-only view of legacy Unified V2 ranking archives."""

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
class LegacyRankingArchive:
    path_status: str
    adapter_version: str
    source_sha256: str
    bias_labels: tuple[str, ...]
    payload: Mapping[str, Any]


def adapt_legacy_ranking_bytes(raw: bytes) -> LegacyRankingArchive:
    """Parse old JSON as evidence without inventing formal M03-M07 identities."""

    before = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("legacy ranking archive is not valid JSON") from exc
    if not isinstance(payload, Mapping) or not isinstance(payload.get("days"), list):
        raise ContractError("legacy ranking archive lacks its historical days")
    after = hashlib.sha256(raw).hexdigest()
    if before != after:
        raise ContractError("legacy ranking adapter modified source bytes")
    return LegacyRankingArchive(
        path_status="legacy",
        adapter_version="legacy-adapter-m07-1.0.0",
        source_sha256="sha256:" + before,
        bias_labels=("legacy_missing_formal_m03_m07_identities",),
        payload=_freeze(payload),
    )


__all__ = ["LegacyRankingArchive", "adapt_legacy_ranking_bytes"]
