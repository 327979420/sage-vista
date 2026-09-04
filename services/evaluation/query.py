"""M10-D deterministic read-only queries over one atomic evaluation inventory.

This module never reads market data and never recalculates an outcome.  It
validates immutable M10 records, selects revisions, applies direct-field
filters, and returns a reproducible in-memory result set for audit exports.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Sequence

from services.contracts.market_data import canonical_fingerprint, require_date
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError, SEMVER

from .contracts import (
    RESULT_TYPES,
    current_experiment_run,
    current_result,
    validate_experiment_run,
    validate_result,
)
from .policies import FORWARD_WINDOW_POLICY
from .storage import EvaluationInventorySnapshot, EvaluationShadowStore


EVALUATION_QUERY_SCHEMA_VERSION = "2.0.0"
QUERY_RESULT_SET_SCHEMA_VERSION = "2.0.0"
M10_D_SOURCE_VERSION = "m10-d-query-export-1.0.0"
QUERY_SORT_POLICY_VERSION = "m10-d-result-sort-1.0.0"

_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
_STABLE_ID = re.compile(r"^[a-z][a-z0-9-]*:sha256:[0-9a-f]{64}$")
_QUERY_ID = re.compile(r"^evaluation-query:sha256:[0-9a-f]{64}$")
_RESULT_SET_ID = re.compile(r"^query-result-set:sha256:[0-9a-f]{64}$")
_INVENTORY_ID = re.compile(r"^source-inventory:sha256:[0-9a-f]{64}$")

_FILTER_FIELDS = {
    "result_contracts",
    "result_schema_versions",
    "result_source_versions",
    "run_ids",
    "event_ids",
    "instrument_ids",
    "signal_date_from",
    "signal_date_to",
    "as_of_from",
    "as_of_to",
    "window_sessions",
    "statuses",
    "path_statuses",
    "result_roles",
    "partition_roles",
    "policy_refs",
    "bias_labels",
}
_LIST_FILTERS = {
    "result_contracts",
    "result_schema_versions",
    "result_source_versions",
    "run_ids",
    "event_ids",
    "instrument_ids",
    "window_sessions",
    "statuses",
    "path_statuses",
    "result_roles",
    "partition_roles",
    "bias_labels",
}
_POLICY_KINDS = {
    "evaluation",
    "forward_window",
    "execution",
    "cost_slippage",
    "adjustment",
    "aggregation",
    "partition",
}
_POLICY_FIELDS = {
    "evaluation": "evaluation_policy",
    "forward_window": "window_policy",
    "execution": "execution_policy",
    "cost_slippage": "cost_policy",
    "adjustment": "adjustment_policy",
    "aggregation": "aggregation_policy",
    "partition": "partition_policy",
}
_RESULT_STATUSES = {
    "pending", "mature", "partial", "unavailable", "completed", "no_trade",
}
_PATH_STATUSES = {"formal", "legacy"}
_RESULT_ROLES = {"authoritative", "comparison", "legacy_readonly"}
_PARTITION_ROLES = {"development", "validation", "forward"}


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


def _exact_fields(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    missing = sorted(expected - value.keys())
    unknown = sorted(value.keys() - expected)
    if missing:
        raise ContractError(f"{label} missing required fields: {', '.join(missing)}")
    if unknown:
        raise ContractError(f"{label} contains unknown fields: {', '.join(unknown)}")


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _require_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ContractError(f"{field} must be sha256:<64 lowercase hex>")
    return value


def _require_stable_id(value: Any, field: str, prefix: str | None = None) -> str:
    if not isinstance(value, str) or not _STABLE_ID.fullmatch(value):
        raise ContractError(f"{field} must be a content-addressed stable ID")
    if prefix is not None and not value.startswith(prefix + ":sha256:"):
        raise ContractError(f"{field} has the wrong stable ID role")
    return value


def _source_version(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ContractError("M10-D source_version must be an object")
    _exact_fields(value, {"evaluation_contracts"}, "M10-D source_version")
    if value.get("evaluation_contracts") != M10_D_SOURCE_VERSION:
        raise ContractError("M10-D source_version is not approved")
    return {"evaluation_contracts": M10_D_SOURCE_VERSION}


def _normalize_scalar_list(value: Any, field: str) -> list[Any] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or not value:
        raise ContractError(f"EvaluationQuery {field} must be null or a non-empty list")
    normalized: list[Any] = []
    for item in value:
        if field == "window_sessions":
            if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
                raise ContractError("window_sessions must contain positive integers")
        else:
            item = _require_text(item, field)
        normalized.append(item)
    return sorted(set(normalized))


def _normalize_policy_refs(value: Any) -> list[dict[str, Any]] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or not value:
        raise ContractError("EvaluationQuery policy_refs must be null or non-empty")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, str, str]] = set()
    fields = {"policy_kind", "status", "policy_version", "policy_fingerprint"}
    for item in value:
        if not isinstance(item, Mapping):
            raise ContractError("EvaluationQuery policy_refs entries must be objects")
        _exact_fields(item, fields, "EvaluationQuery policy_ref")
        kind = _require_text(item["policy_kind"], "policy_kind")
        if kind not in _POLICY_KINDS:
            raise ContractError("EvaluationQuery policy_kind is unknown")
        status = item["status"]
        if status is not None:
            status = _require_text(status, "policy status")
        version = _require_text(item["policy_version"], "policy_version")
        if not SEMVER.fullmatch(version):
            raise ContractError("policy_version must be semantic version")
        fingerprint = _require_sha(item["policy_fingerprint"], "policy_fingerprint")
        key = (kind, status, version, fingerprint)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({
            "policy_kind": kind,
            "status": status,
            "policy_version": version,
            "policy_fingerprint": fingerprint,
        })
    return sorted(
        normalized,
        key=lambda item: (
            item["policy_kind"], item["status"] or "", item["policy_version"],
            item["policy_fingerprint"],
        ),
    )


def _normalize_filters(value: Mapping[str, Any] | None) -> dict[str, Any]:
    supplied = {} if value is None else _plain(value)
    if not isinstance(supplied, Mapping):
        raise ContractError("EvaluationQuery filters must be an object")
    unknown = sorted(set(supplied) - _FILTER_FIELDS)
    if unknown:
        raise ContractError(f"EvaluationQuery filters contain unknown fields: {', '.join(unknown)}")
    normalized = {field: None for field in sorted(_FILTER_FIELDS)}
    for field in _LIST_FILTERS:
        normalized[field] = _normalize_scalar_list(supplied.get(field), field)
    normalized["policy_refs"] = _normalize_policy_refs(supplied.get("policy_refs"))
    for field in ("signal_date_from", "signal_date_to", "as_of_from", "as_of_to"):
        item = supplied.get(field)
        normalized[field] = None if item is None else require_date(item, field)

    if normalized["result_contracts"] is not None:
        unknown_contracts = set(normalized["result_contracts"]) - set(RESULT_TYPES)
        if unknown_contracts:
            raise ContractError("EvaluationQuery contains an unknown result contract")
    if normalized["result_schema_versions"] is not None:
        if any(not SEMVER.fullmatch(item) for item in normalized["result_schema_versions"]):
            raise ContractError("result_schema_versions must contain semantic versions")
    for field, pattern, prefix in (
        ("run_ids", _STABLE_ID, "experiment-run"),
        ("event_ids", _STABLE_ID, "opportunity"),
        ("instrument_ids", _STABLE_ID, "instrument"),
    ):
        if normalized[field] is not None:
            for item in normalized[field]:
                _require_stable_id(item, field, prefix)
    if normalized["statuses"] is not None and not set(normalized["statuses"]) <= _RESULT_STATUSES:
        raise ContractError("EvaluationQuery contains an unknown result status")
    if normalized["path_statuses"] is not None and not set(normalized["path_statuses"]) <= _PATH_STATUSES:
        raise ContractError("EvaluationQuery contains an unknown path status")
    if normalized["result_roles"] is not None and not set(normalized["result_roles"]) <= _RESULT_ROLES:
        raise ContractError("EvaluationQuery contains an unknown result role")
    if normalized["partition_roles"] is not None and not set(normalized["partition_roles"]) <= _PARTITION_ROLES:
        raise ContractError("EvaluationQuery contains an unknown partition role")
    for start_field, end_field in (
        ("signal_date_from", "signal_date_to"), ("as_of_from", "as_of_to")
    ):
        if (
            normalized[start_field] is not None
            and normalized[end_field] is not None
            and normalized[start_field] > normalized[end_field]
        ):
            raise ContractError(f"{start_field} cannot be after {end_field}")
    return normalized


def _query_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": payload["schema_version"],
        "source_version": _plain(payload["source_version"]),
        "filters": _plain(payload["filters"]),
        "revision_mode": payload["revision_mode"],
        "sort_policy_version": payload["sort_policy_version"],
        "inventory_as_of": payload["inventory_as_of"],
    }


def build_evaluation_query(
    *,
    filters: Mapping[str, Any] | None,
    revision_mode: str,
    inventory_as_of: str | None = None,
    sort_policy_version: str = QUERY_SORT_POLICY_VERSION,
) -> Mapping[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": EVALUATION_QUERY_SCHEMA_VERSION,
        "source_version": {"evaluation_contracts": M10_D_SOURCE_VERSION},
        "filters": _normalize_filters(filters),
        "revision_mode": revision_mode,
        "sort_policy_version": sort_policy_version,
        "inventory_as_of": (
            None if inventory_as_of is None
            else require_date(inventory_as_of, "inventory_as_of")
        ),
    }
    identity = _query_identity(payload)
    payload["query_id"] = "evaluation-query:" + canonical_fingerprint(identity)
    payload["query_content_fingerprint"] = canonical_fingerprint(identity)
    validate_evaluation_query(payload)
    return _freeze(payload)


def validate_evaluation_query(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise ContractError("EvaluationQuery must be an object")
    fields = {
        "schema_version", "source_version", "query_id",
        "query_content_fingerprint", "filters", "revision_mode",
        "sort_policy_version", "inventory_as_of",
    }
    _exact_fields(payload, fields, "EvaluationQuery 2.0.0")
    if payload["schema_version"] != EVALUATION_QUERY_SCHEMA_VERSION:
        raise ContractError("unknown EvaluationQuery schema version")
    _source_version(payload["source_version"])
    if payload["revision_mode"] not in {"all", "current"}:
        raise ContractError("revision_mode must be explicitly all or current")
    if payload["sort_policy_version"] != QUERY_SORT_POLICY_VERSION:
        raise ContractError("EvaluationQuery sort policy is not approved")
    if payload["inventory_as_of"] is not None:
        require_date(payload["inventory_as_of"], "inventory_as_of")
    normalized_filters = _normalize_filters(payload["filters"])
    if _plain(payload["filters"]) != normalized_filters:
        raise ContractError("EvaluationQuery filters are not canonical")
    expected = canonical_fingerprint(_query_identity(payload))
    if payload["query_id"] != "evaluation-query:" + expected:
        raise ContractError("EvaluationQuery ID does not match its inputs")
    if payload["query_content_fingerprint"] != expected:
        raise ContractError("EvaluationQuery content fingerprint is invalid")


def validate_source_inventory(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise ContractError("source_inventory must be an object")
    _exact_fields(
        value,
        {"source_inventory_id", "source_inventory_fingerprint", "entries"},
        "source_inventory",
    )
    if not isinstance(value["source_inventory_id"], str) or not _INVENTORY_ID.fullmatch(value["source_inventory_id"]):
        raise ContractError("source_inventory_id is invalid")
    fingerprint = _require_sha(
        value["source_inventory_fingerprint"], "source_inventory_fingerprint"
    )
    entries = value["entries"]
    if not isinstance(entries, (list, tuple)):
        raise ContractError("source_inventory.entries must be a list")
    entry_fields = {
        "relative_path", "record_kind", "contract_name", "schema_version",
        "stable_id", "logical_id", "supersedes_id", "run_id",
        "content_fingerprint", "file_sha256", "byte_count", "payload",
    }
    normalized: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ContractError("source_inventory entry must be an object")
        if "payload" not in entry:
            raise ContractError("inventory_evidence_unavailable")
        _exact_fields(entry, entry_fields, "source_inventory entry")
        path = _require_text(entry["relative_path"], "relative_path")
        parts = path.split("/")
        if path.startswith("/") or "\\" in path or any(part in {"", ".", ".."} for part in parts):
            raise ContractError("source_inventory relative_path is unsafe")
        if path in seen_paths:
            raise ContractError("source_inventory contains a duplicate path")
        seen_paths.add(path)
        if entry["record_kind"] not in {"result", "run_receipt"}:
            raise ContractError("source_inventory record_kind is invalid")
        if not SEMVER.fullmatch(str(entry["schema_version"])):
            raise ContractError("source_inventory schema_version is invalid")
        if entry["record_kind"] == "result":
            if entry["contract_name"] not in RESULT_TYPES:
                raise ContractError("source_inventory result contract is unknown")
            _, _, stable_prefix, logical_prefix = RESULT_TYPES[entry["contract_name"]]
        else:
            if entry["contract_name"] != "ExperimentRun":
                raise ContractError("source_inventory receipt contract is invalid")
            stable_prefix, logical_prefix = "experiment-run-receipt", "experiment-run"
        stable_id = _require_stable_id(
            entry["stable_id"], "stable_id", stable_prefix
        )
        if stable_id in seen_ids:
            raise ContractError("source_inventory contains a duplicate stable ID")
        seen_ids.add(stable_id)
        _require_stable_id(entry["logical_id"], "logical_id", logical_prefix)
        if entry["supersedes_id"] is not None:
            _require_stable_id(
                entry["supersedes_id"], "supersedes_id", stable_prefix
            )
        _require_stable_id(entry["run_id"], "run_id", "experiment-run")
        _require_sha(entry["content_fingerprint"], "content_fingerprint")
        _require_sha(entry["file_sha256"], "file_sha256")
        if isinstance(entry["byte_count"], bool) or not isinstance(entry["byte_count"], int) or entry["byte_count"] <= 0:
            raise ContractError("source_inventory byte_count must be positive")
        payload = entry["payload"]
        if not isinstance(payload, Mapping):
            raise ContractError("source_inventory payload must be an object")
        if entry["record_kind"] == "result":
            validate_result(str(entry["contract_name"]), payload)
            id_field, fingerprint_field, _, _ = RESULT_TYPES[str(entry["contract_name"])]
            expected_path = (
                f"results/{entry['contract_name']}/"
                f"{str(payload[id_field]).rsplit(':', 1)[-1]}.json"
            )
            metadata = {
                "schema_version": str(payload["schema_version"]),
                "stable_id": str(payload[id_field]),
                "logical_id": str(payload["logical_result_id"]),
                "supersedes_id": payload["supersedes_result_id"],
                "run_id": str(payload["run_id"]),
                "content_fingerprint": str(payload[fingerprint_field]),
            }
        else:
            validate_experiment_run(payload)
            expected_path = f"runs/{str(payload['run_receipt_id']).rsplit(':', 1)[-1]}.json"
            metadata = {
                "schema_version": str(payload["schema_version"]),
                "stable_id": str(payload["run_receipt_id"]),
                "logical_id": str(payload["run_id"]),
                "supersedes_id": payload["supersedes_run_receipt_id"],
                "run_id": str(payload["run_id"]),
                "content_fingerprint": str(payload["run_content_fingerprint"]),
            }
        if path != expected_path or any(entry[key] != item for key, item in metadata.items()):
            raise ContractError("source_inventory payload differs from its frozen index")
        canonical_bytes = (
            json.dumps(
                _plain(payload), ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        if (
            entry["byte_count"] != len(canonical_bytes)
            or entry["file_sha256"]
            != "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
        ):
            raise ContractError("source_inventory payload bytes do not match its evidence")
        normalized.append(_plain(entry))
    ordered = sorted(
        normalized,
        key=lambda item: (
            item["record_kind"], item["contract_name"], item["stable_id"],
            item["relative_path"],
        ),
    )
    if normalized != ordered:
        raise ContractError("source_inventory entries are not canonically sorted")
    expected = canonical_fingerprint({"entries": ordered})
    if fingerprint != expected or value["source_inventory_id"] != "source-inventory:" + expected:
        raise ContractError("source_inventory identity does not match its entries")


def _result_ref(contract_name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
    return {
        "result_contract": contract_name,
        "schema_version": str(payload["schema_version"]),
        "result_id": str(payload[id_field]),
        "logical_result_id": str(payload["logical_result_id"]),
        "run_id": str(payload["run_id"]),
        "content_fingerprint": str(payload[fingerprint_field]),
    }


def _receipt_ref(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(payload["run_id"]),
        "run_receipt_id": str(payload["run_receipt_id"]),
        "run_content_fingerprint": str(payload["run_content_fingerprint"]),
        "supersedes_run_receipt_id": payload["supersedes_run_receipt_id"],
        "status": str(payload["status"]),
    }


def _result_sort_key(item: tuple[str, Mapping[str, Any]]) -> tuple[Any, ...]:
    contract_name, payload = item
    id_field = RESULT_TYPES[contract_name][0]
    return (
        list(RESULT_TYPES).index(contract_name),
        str(payload[id_field]),
    )


def _policy_value(payload: Mapping[str, Any], kind: str) -> Mapping[str, Any] | None:
    value = payload.get(_POLICY_FIELDS[kind])
    if isinstance(value, Mapping):
        return value
    scope = payload.get("aggregate_scope", payload.get("portfolio_scope"))
    if not isinstance(scope, Mapping):
        return None
    if kind == "adjustment" and scope.get("adjustment_policy_fingerprint"):
        return {
            "policy_version": ADJUSTMENT_POLICY["version"],
            "policy_fingerprint": scope["adjustment_policy_fingerprint"],
        }
    scoped_fields = {
        "execution": ("execution_policy_version", "execution_policy_fingerprint"),
        "cost_slippage": ("cost_policy_version", "cost_policy_fingerprint"),
    }
    if kind == "forward_window" and scope.get("window_policy_fingerprint"):
        return {
            "policy_version": FORWARD_WINDOW_POLICY["policy_version"],
            "policy_fingerprint": scope["window_policy_fingerprint"],
        }
    fields = scoped_fields.get(kind)
    if fields is None or scope.get(fields[1]) is None:
        return None
    return {
        "status": scope.get("cost_policy_status") if kind == "cost_slippage" else None,
        "policy_version": scope.get(fields[0]),
        "policy_fingerprint": scope.get(fields[1]),
    }


def _policy_matches(payload: Mapping[str, Any], requested: Mapping[str, Any]) -> bool:
    policy = _policy_value(payload, str(requested["policy_kind"]))
    if policy is None:
        return False
    version = policy.get("policy_version", policy.get("version"))
    fingerprint = policy.get("policy_fingerprint")
    if fingerprint is None:
        fingerprint = canonical_fingerprint(_plain(policy))
    status = policy.get("status")
    return (
        version == requested["policy_version"]
        and fingerprint == requested["policy_fingerprint"]
        and (requested["status"] is None or status == requested["status"])
    )


def _record_matches(contract_name: str, payload: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
    scalar_lists = {
        "result_contracts": contract_name,
        "result_schema_versions": payload.get("schema_version"),
        "result_source_versions": (
            payload.get("source_version", {}).get("evaluation_contracts")
            if isinstance(payload.get("source_version"), Mapping) else None
        ),
        "run_ids": payload.get("run_id"),
        "event_ids": payload.get("event_id"),
        "instrument_ids": payload.get("instrument_id"),
        "window_sessions": payload.get("window_sessions"),
        "statuses": payload.get("status"),
        "path_statuses": payload.get("path_status"),
        "result_roles": payload.get("result_role"),
        "partition_roles": payload.get("partition_role"),
    }
    for filter_name, actual in scalar_lists.items():
        requested = filters[filter_name]
        if requested is not None and actual not in requested:
            return False
    for start_field, end_field, actual_field in (
        ("signal_date_from", "signal_date_to", "signal_date"),
        ("as_of_from", "as_of_to", "as_of"),
    ):
        lower, upper = filters[start_field], filters[end_field]
        if lower is not None or upper is not None:
            actual = payload.get(actual_field)
            if not isinstance(actual, str):
                return False
            if lower is not None and actual < lower:
                return False
            if upper is not None and actual > upper:
                return False
    if filters["bias_labels"] is not None:
        actual_biases = payload.get("bias_labels")
        if not isinstance(actual_biases, (list, tuple)) or not set(filters["bias_labels"]) <= set(actual_biases):
            return False
    if filters["policy_refs"] is not None:
        if not all(_policy_matches(payload, item) for item in filters["policy_refs"]):
            return False
    return True


def resolve_ticker_instrument_id(
    ticker: str,
    resolver: Callable[[str], Iterable[str]],
) -> str:
    """Resolve a display ticker without guessing a listing identity."""

    symbol = _require_text(ticker, "ticker").upper()
    matches = sorted(set(resolver(symbol)))
    for item in matches:
        _require_stable_id(item, "resolved instrument_id", "instrument")
    if not matches:
        raise ContractError("ticker_resolution_unavailable")
    if len(matches) != 1:
        raise ContractError("ticker_resolution_ambiguous")
    return matches[0]


@dataclass(frozen=True)
class EvaluationQueryResult:
    query: Mapping[str, Any]
    result_set: Mapping[str, Any]
    results: tuple[tuple[str, Mapping[str, Any]], ...]
    run_receipts: tuple[Mapping[str, Any], ...]


def _derive_query_records(
    query: Mapping[str, Any], source_inventory: Mapping[str, Any]
) -> tuple[
    tuple[tuple[str, Mapping[str, Any]], ...],
    tuple[Mapping[str, Any], ...],
]:
    """Deterministically re-run one query from its complete frozen inventory."""

    validate_evaluation_query(query)
    validate_source_inventory(source_inventory)
    all_records: list[tuple[str, Mapping[str, Any]]] = []
    all_receipts: list[Mapping[str, Any]] = []
    for entry in source_inventory["entries"]:
        payload = _freeze(_plain(entry["payload"]))
        if entry["record_kind"] == "result":
            all_records.append((str(entry["contract_name"]), payload))
        else:
            all_receipts.append(payload)

    grouped_results: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for contract_name, payload in all_records:
        grouped_results.setdefault(
            (contract_name, str(payload["logical_result_id"])), []
        ).append(payload)
    current_results: dict[tuple[str, str], Mapping[str, Any]] = {
        key: current_result(key[0], chain)
        for key, chain in grouped_results.items()
    }
    candidates = (
        [(contract_name, payload) for (contract_name, _), payload in current_results.items()]
        if query["revision_mode"] == "current"
        else all_records
    )
    selected = [
        item for item in candidates
        if _record_matches(item[0], item[1], query["filters"])
    ]
    selected.sort(key=_result_sort_key)

    grouped_receipts: dict[str, list[Mapping[str, Any]]] = {}
    for receipt in all_receipts:
        grouped_receipts.setdefault(str(receipt["run_id"]), []).append(receipt)
    current_receipts = {
        run_id: current_experiment_run(chain)
        for run_id, chain in grouped_receipts.items()
    }
    selected_receipts: list[Mapping[str, Any]] = []
    for run_id in sorted({str(payload["run_id"]) for _, payload in selected}):
        chain = grouped_receipts.get(run_id)
        if not chain:
            raise ContractError("selected M10 result has no ExperimentRun receipt")
        selected_receipts.extend(
            chain if query["revision_mode"] == "all" else [current_receipts[run_id]]
        )
    selected_receipts.sort(
        key=lambda item: (str(item["run_id"]), str(item["run_receipt_id"]))
    )
    return tuple(selected), tuple(selected_receipts)


def validate_query_execution(execution: EvaluationQueryResult) -> None:
    """Bind the public in-memory objects to the signed query result contract."""

    if not isinstance(execution, EvaluationQueryResult):
        raise ContractError("M10-D export requires an EvaluationQueryResult")
    validate_evaluation_query(execution.query)
    validate_query_result_set(execution.result_set)
    result_set = execution.result_set
    if (
        result_set["query_id"] != execution.query["query_id"]
        or result_set["query_content_fingerprint"]
        != execution.query["query_content_fingerprint"]
        or result_set["revision_mode"] != execution.query["revision_mode"]
        or result_set["sort_policy_version"]
        != execution.query["sort_policy_version"]
    ):
        raise ContractError("QueryResultSet is not bound to its EvaluationQuery")

    actual_results: list[tuple[str, Mapping[str, Any]]] = []
    for item in execution.results:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or item[0] not in RESULT_TYPES
            or not isinstance(item[1], Mapping)
        ):
            raise ContractError("EvaluationQueryResult contains an invalid result")
        validate_result(item[0], item[1])
        actual_results.append(item)
    if any(
        not _record_matches(contract_name, payload, execution.query["filters"])
        for contract_name, payload in actual_results
    ):
        raise ContractError("EvaluationQueryResult contains a result outside its filters")
    if execution.query["revision_mode"] == "current" and len({
        (contract_name, str(payload["logical_result_id"]))
        for contract_name, payload in actual_results
    }) != len(actual_results):
        raise ContractError("current query contains more than one logical revision")
    if actual_results != sorted(actual_results, key=_result_sort_key):
        raise ContractError("EvaluationQueryResult results are not canonically sorted")
    actual_result_refs = [
        _result_ref(contract_name, payload)
        for contract_name, payload in actual_results
    ]
    if actual_result_refs != _plain(result_set["result_refs"]):
        raise ContractError("QueryResultSet references do not match actual results")

    actual_receipts: list[Mapping[str, Any]] = []
    for receipt in execution.run_receipts:
        if not isinstance(receipt, Mapping):
            raise ContractError("EvaluationQueryResult contains an invalid run receipt")
        validate_experiment_run(receipt)
        actual_receipts.append(receipt)
    if actual_receipts != sorted(
        actual_receipts,
        key=lambda item: (str(item["run_id"]), str(item["run_receipt_id"])),
    ):
        raise ContractError("EvaluationQueryResult receipts are not canonically sorted")
    actual_receipt_refs = [_receipt_ref(item) for item in actual_receipts]
    if actual_receipt_refs != _plain(result_set["run_receipt_refs"]):
        raise ContractError("QueryResultSet references do not match actual receipts")

    inventory = result_set["source_inventory"]
    if inventory is None:
        if execution.results or execution.run_receipts:
            raise ContractError("unavailable query cannot carry inventory records")
        return
    expected_results, expected_receipts = _derive_query_records(
        execution.query, inventory
    )
    if tuple(actual_results) != expected_results:
        raise ContractError("QueryResultSet is not the complete deterministic query result")
    if tuple(actual_receipts) != expected_receipts:
        raise ContractError("QueryResultSet receipts are not the complete deterministic query evidence")


def _result_set_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _plain(value)
        for key, value in payload.items()
        if key not in {"query_result_set_id", "query_result_set_content_fingerprint"}
    }


def _build_unavailable_result_set(
    query: Mapping[str, Any], *, code_commit: str, reason: str
) -> Mapping[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": QUERY_RESULT_SET_SCHEMA_VERSION,
        "source_version": {"evaluation_contracts": M10_D_SOURCE_VERSION},
        "query_id": query["query_id"],
        "query_content_fingerprint": query["query_content_fingerprint"],
        "source_inventory": None,
        "result_refs": [],
        "result_set_fingerprint": canonical_fingerprint([]),
        "run_receipt_refs": [],
        "run_receipt_set_fingerprint": canonical_fingerprint([]),
        "row_count": 0,
        "revision_mode": query["revision_mode"],
        "sort_policy_version": query["sort_policy_version"],
        "code_commit": code_commit,
        "status": "unavailable",
        "diagnostics": [reason],
    }
    identity = _result_set_identity(payload)
    payload["query_result_set_id"] = "query-result-set:" + canonical_fingerprint(identity)
    payload["query_result_set_content_fingerprint"] = canonical_fingerprint(identity)
    validate_query_result_set(payload)
    return _freeze(payload)


def execute_evaluation_query(
    store: EvaluationShadowStore,
    query: Mapping[str, Any],
    *,
    code_commit: str,
) -> EvaluationQueryResult:
    validate_evaluation_query(query)
    if not re.fullmatch(r"[0-9a-f]{40}", code_commit):
        raise ContractError("QueryResultSet code_commit must be full 40-hex")
    if query["inventory_as_of"] is not None:
        result_set = _build_unavailable_result_set(
            query, code_commit=code_commit,
            reason="historical_inventory_unavailable",
        )
        return EvaluationQueryResult(query, result_set, (), ())

    inventory = store.capture_inventory()
    selected, selected_receipts = _derive_query_records(query, inventory.evidence)

    result_refs = [_result_ref(contract_name, payload) for contract_name, payload in selected]
    receipt_refs = [_receipt_ref(payload) for payload in selected_receipts]
    payload: dict[str, Any] = {
        "schema_version": QUERY_RESULT_SET_SCHEMA_VERSION,
        "source_version": {"evaluation_contracts": M10_D_SOURCE_VERSION},
        "query_id": query["query_id"],
        "query_content_fingerprint": query["query_content_fingerprint"],
        "source_inventory": _plain(inventory.evidence),
        "result_refs": result_refs,
        "result_set_fingerprint": canonical_fingerprint(result_refs),
        "run_receipt_refs": receipt_refs,
        "run_receipt_set_fingerprint": canonical_fingerprint(receipt_refs),
        "row_count": len(result_refs),
        "revision_mode": query["revision_mode"],
        "sort_policy_version": query["sort_policy_version"],
        "code_commit": code_commit,
        "status": "complete" if result_refs else "empty",
        "diagnostics": [],
    }
    identity = _result_set_identity(payload)
    payload["query_result_set_id"] = "query-result-set:" + canonical_fingerprint(identity)
    payload["query_result_set_content_fingerprint"] = canonical_fingerprint(identity)
    validate_query_result_set(payload)
    return EvaluationQueryResult(query, _freeze(payload), selected, selected_receipts)


def validate_query_result_set(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise ContractError("QueryResultSet must be an object")
    fields = {
        "schema_version", "source_version", "query_result_set_id",
        "query_result_set_content_fingerprint", "query_id",
        "query_content_fingerprint", "source_inventory", "result_refs",
        "result_set_fingerprint", "run_receipt_refs",
        "run_receipt_set_fingerprint", "row_count", "revision_mode",
        "sort_policy_version", "code_commit", "status", "diagnostics",
    }
    _exact_fields(payload, fields, "QueryResultSet 2.0.0")
    if payload["schema_version"] != QUERY_RESULT_SET_SCHEMA_VERSION:
        raise ContractError("unknown QueryResultSet schema version")
    _source_version(payload["source_version"])
    if not isinstance(payload["query_result_set_id"], str) or not _RESULT_SET_ID.fullmatch(payload["query_result_set_id"]):
        raise ContractError("query_result_set_id is invalid")
    if not isinstance(payload["query_id"], str) or not _QUERY_ID.fullmatch(payload["query_id"]):
        raise ContractError("QueryResultSet query_id is invalid")
    _require_sha(payload["query_content_fingerprint"], "query_content_fingerprint")
    if payload["revision_mode"] not in {"all", "current"}:
        raise ContractError("QueryResultSet revision_mode is invalid")
    if payload["sort_policy_version"] != QUERY_SORT_POLICY_VERSION:
        raise ContractError("QueryResultSet sort policy is invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", str(payload["code_commit"])):
        raise ContractError("QueryResultSet code_commit must be full 40-hex")
    if payload["status"] not in {"complete", "empty", "unavailable"}:
        raise ContractError("QueryResultSet status is invalid")
    diagnostics = payload["diagnostics"]
    if not isinstance(diagnostics, (list, tuple)) or any(
        not isinstance(item, str) or not item for item in diagnostics
    ):
        raise ContractError("QueryResultSet diagnostics must be a string list")
    result_refs = payload["result_refs"]
    receipt_refs = payload["run_receipt_refs"]
    if not isinstance(result_refs, (list, tuple)) or not isinstance(receipt_refs, (list, tuple)):
        raise ContractError("QueryResultSet references must be lists")
    result_fields = {
        "result_contract", "schema_version", "result_id", "logical_result_id",
        "run_id", "content_fingerprint",
    }
    seen_result_ids: set[str] = set()
    for item in result_refs:
        if not isinstance(item, Mapping):
            raise ContractError("QueryResultSet result ref must be an object")
        _exact_fields(item, result_fields, "QueryResultSet result ref")
        if item["result_contract"] not in RESULT_TYPES:
            raise ContractError("QueryResultSet result contract is unknown")
        if not SEMVER.fullmatch(str(item["schema_version"])):
            raise ContractError("QueryResultSet result schema is invalid")
        _require_stable_id(item["result_id"], "result_id")
        _require_stable_id(item["logical_result_id"], "logical_result_id")
        _require_stable_id(item["run_id"], "run_id", "experiment-run")
        _require_sha(item["content_fingerprint"], "content_fingerprint")
        if item["result_id"] in seen_result_ids:
            raise ContractError("QueryResultSet contains duplicate result IDs")
        seen_result_ids.add(str(item["result_id"]))
    receipt_fields = {
        "run_id", "run_receipt_id", "run_content_fingerprint",
        "supersedes_run_receipt_id", "status",
    }
    seen_receipt_ids: set[str] = set()
    for item in receipt_refs:
        if not isinstance(item, Mapping):
            raise ContractError("QueryResultSet run receipt ref must be an object")
        _exact_fields(item, receipt_fields, "QueryResultSet run receipt ref")
        _require_stable_id(item["run_id"], "run_id", "experiment-run")
        _require_stable_id(
            item["run_receipt_id"], "run_receipt_id", "experiment-run-receipt"
        )
        if item["supersedes_run_receipt_id"] is not None:
            _require_stable_id(
                item["supersedes_run_receipt_id"],
                "supersedes_run_receipt_id", "experiment-run-receipt",
            )
        _require_sha(item["run_content_fingerprint"], "run_content_fingerprint")
        _require_text(item["status"], "run receipt status")
        if item["run_receipt_id"] in seen_receipt_ids:
            raise ContractError("QueryResultSet contains duplicate run receipt IDs")
        seen_receipt_ids.add(str(item["run_receipt_id"]))
    if list(result_refs) != sorted(
        (_plain(item) for item in result_refs),
        key=lambda item: (
            list(RESULT_TYPES).index(item["result_contract"]), item["result_id"]
        ),
    ):
        # Full business ordering is validated by the builder; this check catches
        # arbitrary caller order while keeping the compact reference contract.
        raise ContractError("QueryResultSet result refs are not canonical")
    if list(receipt_refs) != sorted(
        (_plain(item) for item in receipt_refs),
        key=lambda item: (item["run_id"], item["run_receipt_id"]),
    ):
        raise ContractError("QueryResultSet run receipt refs are not canonical")
    if payload["result_set_fingerprint"] != canonical_fingerprint(_plain(result_refs)):
        raise ContractError("QueryResultSet result set fingerprint is invalid")
    if payload["run_receipt_set_fingerprint"] != canonical_fingerprint(_plain(receipt_refs)):
        raise ContractError("QueryResultSet receipt set fingerprint is invalid")
    if isinstance(payload["row_count"], bool) or payload["row_count"] != len(result_refs):
        raise ContractError("QueryResultSet row_count is invalid")
    if payload["status"] == "complete":
        if not result_refs or payload["source_inventory"] is None or diagnostics:
            raise ContractError("complete QueryResultSet is inconsistent")
    elif payload["status"] == "empty":
        if result_refs or receipt_refs or payload["source_inventory"] is None or diagnostics:
            raise ContractError("empty QueryResultSet is inconsistent")
    else:
        if result_refs or receipt_refs or payload["source_inventory"] is not None or not diagnostics:
            raise ContractError("unavailable QueryResultSet is inconsistent")
    if payload["source_inventory"] is not None:
        validate_source_inventory(payload["source_inventory"])
        result_run_ids = {item["run_id"] for item in result_refs}
        receipt_run_ids = {item["run_id"] for item in receipt_refs}
        if result_run_ids != receipt_run_ids:
            raise ContractError("QueryResultSet result and receipt runs are not conserved")
        inventory_entries = {
            (item["record_kind"], item["stable_id"]): item
            for item in payload["source_inventory"]["entries"]
        }
        for item in result_refs:
            source = inventory_entries.get(("result", item["result_id"]))
            if source is None or any((
                source["contract_name"] != item["result_contract"],
                source["schema_version"] != item["schema_version"],
                source["logical_id"] != item["logical_result_id"],
                source["run_id"] != item["run_id"],
                source["content_fingerprint"] != item["content_fingerprint"],
            )):
                raise ContractError("QueryResultSet result ref is absent from inventory")
        for item in receipt_refs:
            source = inventory_entries.get(("run_receipt", item["run_receipt_id"]))
            if source is None or any((
                source["run_id"] != item["run_id"],
                source["content_fingerprint"] != item["run_content_fingerprint"],
                source["supersedes_id"] != item["supersedes_run_receipt_id"],
            )):
                raise ContractError("QueryResultSet receipt ref is absent from inventory")
    expected = canonical_fingerprint(_result_set_identity(payload))
    if payload["query_result_set_id"] != "query-result-set:" + expected:
        raise ContractError("QueryResultSet ID is invalid")
    if payload["query_result_set_content_fingerprint"] != expected:
        raise ContractError("QueryResultSet content fingerprint is invalid")


__all__ = [
    "EVALUATION_QUERY_SCHEMA_VERSION",
    "EvaluationQueryResult",
    "M10_D_SOURCE_VERSION",
    "QUERY_RESULT_SET_SCHEMA_VERSION",
    "QUERY_SORT_POLICY_VERSION",
    "build_evaluation_query",
    "execute_evaluation_query",
    "resolve_ticker_instrument_id",
    "validate_evaluation_query",
    "validate_query_execution",
    "validate_query_result_set",
    "validate_source_inventory",
]
