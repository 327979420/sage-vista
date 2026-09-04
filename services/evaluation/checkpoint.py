"""Immutable M10-E orchestration checkpoints.

Checkpoints contain progress and references only.  They never contain market
rows or reinterpret an M10 result.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Iterable, Mapping
import re

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError


RESEARCH_RUN_CHECKPOINT_SCHEMA_VERSION = "2.0.0"
CHECKPOINT_SOURCE_VERSION = "m10-e-cli-1.0.0"
_CHECKPOINT_ID = re.compile(r"^research-run-checkpoint:sha256:[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^experiment-run:sha256:[0-9a-f]{64}$")
_CONFIG_ID = re.compile(r"^research-run-config:sha256:[0-9a-f]{64}$")
_RESULT_ID = re.compile(
    r"^(?:forward-outcome|trade-outcome|portfolio-run|research-aggregate):sha256:[0-9a-f]{64}$"
)
_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")

_FIELDS = {
    "schema_version", "source_version", "checkpoint_id",
    "checkpoint_content_fingerprint", "run_id", "config_id",
    "config_content_fingerprint", "config_scope_fingerprint", "result_family",
    "path_status", "result_role", "partition_role", "code_commit",
    "input_set_fingerprint", "expected_work_units", "completed_work_units",
    "remaining_work_units", "result_refs", "supersedes_checkpoint_id",
    "status", "generated_at",
}


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


def _exact(payload: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ContractError(f"{label} must be an object")
    if set(payload) != fields:
        raise ContractError(f"{label} fields are incomplete or unknown")
    return _plain(payload)


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ContractError(f"{field} must be sha256:<64 lowercase hex>")
    return value


def _semantic(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _plain(value) for key, value in payload.items()
        if key not in {"checkpoint_id", "checkpoint_content_fingerprint"}
    }


def _result_refs(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, (list, tuple)):
        raise ContractError("checkpoint result_refs must be a list")
    normalized: list[dict[str, str]] = []
    for raw in value:
        item = _exact(raw, {"work_unit_id", "id", "content_fingerprint"}, "checkpoint result_ref")
        if not isinstance(item["work_unit_id"], str) or not item["work_unit_id"]:
            raise ContractError("checkpoint result_ref work_unit_id is required")
        if not isinstance(item["id"], str) or not _RESULT_ID.fullmatch(item["id"]):
            raise ContractError("checkpoint result_ref ID is invalid")
        _sha(item["content_fingerprint"], "checkpoint result fingerprint")
        normalized.append(item)
    ordered = sorted(normalized, key=lambda item: (item["work_unit_id"], item["id"]))
    if normalized != ordered or len({item["id"] for item in ordered}) != len(ordered):
        raise ContractError("checkpoint result_refs must be sorted and unique")
    return ordered


def build_research_run_checkpoint(**values: Any) -> Mapping[str, Any]:
    payload = _plain(values)
    payload.setdefault("schema_version", RESEARCH_RUN_CHECKPOINT_SCHEMA_VERSION)
    payload.setdefault("source_version", {"evaluation_contracts": CHECKPOINT_SOURCE_VERSION})
    payload.setdefault("supersedes_checkpoint_id", None)
    payload.pop("checkpoint_id", None)
    payload.pop("checkpoint_content_fingerprint", None)
    required = _FIELDS - {"checkpoint_id", "checkpoint_content_fingerprint"}
    _exact(payload, required, "ResearchRunCheckpoint builder")
    payload["result_refs"] = sorted(
        [_plain(item) for item in payload["result_refs"]],
        key=lambda item: (item["work_unit_id"], item["id"]),
    )
    fingerprint = canonical_fingerprint(_semantic(payload))
    payload["checkpoint_id"] = "research-run-checkpoint:" + fingerprint
    payload["checkpoint_content_fingerprint"] = fingerprint
    validate_research_run_checkpoint(payload)
    return _freeze(payload)


def validate_research_run_checkpoint(payload: Mapping[str, Any]) -> None:
    item = _exact(payload, _FIELDS, "ResearchRunCheckpoint 2.0.0")
    if item["schema_version"] != RESEARCH_RUN_CHECKPOINT_SCHEMA_VERSION:
        raise ContractError("ResearchRunCheckpoint schema version is unknown")
    if item["source_version"] != {"evaluation_contracts": CHECKPOINT_SOURCE_VERSION}:
        raise ContractError("ResearchRunCheckpoint source version is invalid")
    if not isinstance(item["checkpoint_id"], str) or not _CHECKPOINT_ID.fullmatch(item["checkpoint_id"]):
        raise ContractError("ResearchRunCheckpoint ID is invalid")
    if not isinstance(item["run_id"], str) or not _RUN_ID.fullmatch(item["run_id"]):
        raise ContractError("ResearchRunCheckpoint run_id is invalid")
    if not isinstance(item["config_id"], str) or not _CONFIG_ID.fullmatch(item["config_id"]):
        raise ContractError("ResearchRunCheckpoint config_id is invalid")
    for field in (
        "checkpoint_content_fingerprint", "config_content_fingerprint",
        "config_scope_fingerprint", "input_set_fingerprint",
    ):
        _sha(item[field], field)
    if item["result_family"] not in {
        "ForwardOutcome", "TradeOutcome", "PortfolioRun", "ResearchAggregate"
    }:
        raise ContractError("ResearchRunCheckpoint result family is invalid")
    if item["path_status"] != "formal" or item["result_role"] != "authoritative":
        raise ContractError("ResearchRunCheckpoint is not formal authoritative")
    if item["partition_role"] not in {"development", "validation", "forward"}:
        raise ContractError("ResearchRunCheckpoint partition is invalid")
    if not isinstance(item["code_commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", item["code_commit"]):
        raise ContractError("ResearchRunCheckpoint code_commit is invalid")
    expected = item["expected_work_units"]
    completed = item["completed_work_units"]
    remaining = item["remaining_work_units"]
    if any(
        not isinstance(value, list)
        or len(value) != len(set(value))
        or any(not isinstance(unit, str) or not unit for unit in value)
        for value in (expected, completed, remaining)
    ):
        raise ContractError("checkpoint work-unit lists must be unique string lists")
    if completed != [unit for unit in expected if unit in set(completed)] or remaining != [unit for unit in expected if unit in set(remaining)]:
        raise ContractError("checkpoint work-unit order must follow the expected set")
    if set(completed) & set(remaining) or set(completed) | set(remaining) != set(expected):
        raise ContractError("checkpoint completed and remaining units do not conserve expected work")
    refs = _result_refs(item["result_refs"])
    if any(ref["work_unit_id"] not in set(completed) for ref in refs):
        raise ContractError("checkpoint references a result for unfinished work")
    if item["status"] not in {"in_progress", "interrupted", "failed", "completed"}:
        raise ContractError("ResearchRunCheckpoint status is invalid")
    if item["status"] == "completed" and remaining:
        raise ContractError("completed checkpoint cannot have remaining work")
    prior = item["supersedes_checkpoint_id"]
    if prior is not None and (not isinstance(prior, str) or not _CHECKPOINT_ID.fullmatch(prior)):
        raise ContractError("ResearchRunCheckpoint predecessor is invalid")
    if not isinstance(item["generated_at"], str) or not item["generated_at"].endswith("Z"):
        raise ContractError("ResearchRunCheckpoint generated_at is invalid")
    fingerprint = canonical_fingerprint(_semantic(item))
    if item["checkpoint_content_fingerprint"] != fingerprint or item["checkpoint_id"] != "research-run-checkpoint:" + fingerprint:
        raise ContractError("ResearchRunCheckpoint identity does not match its content")


def current_research_run_checkpoint(
    checkpoints: Iterable[Mapping[str, Any]],
) -> Mapping[str, Any]:
    items = list(checkpoints)
    if not items:
        raise ContractError("ResearchRunCheckpoint chain is empty")
    by_id: dict[str, Mapping[str, Any]] = {}
    run_ids: set[str] = set()
    children: dict[str, str] = {}
    roots: list[str] = []
    for item in items:
        validate_research_run_checkpoint(item)
        checkpoint_id = str(item["checkpoint_id"])
        if checkpoint_id in by_id:
            raise ContractError("checkpoint chain contains a duplicate identity")
        by_id[checkpoint_id] = item
        run_ids.add(str(item["run_id"]))
    if len(run_ids) != 1:
        raise ContractError("checkpoint chain crosses runs")
    for checkpoint_id, item in by_id.items():
        prior = item["supersedes_checkpoint_id"]
        if prior is None:
            roots.append(checkpoint_id)
        elif prior not in by_id:
            raise ContractError("checkpoint chain has a missing predecessor")
        elif prior in children:
            raise ContractError("checkpoint chain forks")
        else:
            children[prior] = checkpoint_id
    if len(roots) != 1:
        raise ContractError("checkpoint chain must have one root")
    visited: set[str] = set()
    cursor = roots[0]
    while cursor not in visited:
        visited.add(cursor)
        if cursor not in children:
            break
        cursor = children[cursor]
    if cursor in children or visited != set(by_id):
        raise ContractError("checkpoint chain is cyclic or disconnected")
    return by_id[cursor]


__all__ = [
    "CHECKPOINT_SOURCE_VERSION", "RESEARCH_RUN_CHECKPOINT_SCHEMA_VERSION",
    "build_research_run_checkpoint", "current_research_run_checkpoint",
    "validate_research_run_checkpoint",
]
