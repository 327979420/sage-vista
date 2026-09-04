"""M10-D deterministic CSV/XLSX audit-package contracts and publication.

Exports are disposable, one-way audit copies.  All values come from an
already validated :class:`EvaluationQueryResult`; this module never reads
market data or recalculates an M10 outcome.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Sequence

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError
from services.market_data.storage import require_shadow_root

from .contracts import RESULT_TYPES
from .query import (
    EvaluationQueryResult,
    M10_D_SOURCE_VERSION,
    QUERY_SORT_POLICY_VERSION,
    validate_evaluation_query,
    validate_query_execution,
    validate_query_result_set,
)
from .storage import _chain_lock


EXPORT_CONFIG_SCHEMA_VERSION = "1.0.0"
EXPORT_MANIFEST_SCHEMA_VERSION = "2.0.0"
AUDIT_CELL_CODEC_VERSION = "audit_cell_codec_v1"
PARTITION_POLICY_VERSION = "m10-d-partition-1.0.0"
CSV_POLICY_VERSION = "m10-d-csv-1.0.0"
XLSX_POLICY_VERSION = "m10-d-xlsx-1.0.0"
ARTIFACT_NAMING_POLICY_VERSION = "m10-d-artifacts-1.0.0"
TEXT_SAFETY_POLICY_VERSION = "m10-d-safe-text-1.0.0"
DECIMAL_RENDER_POLICY_VERSION = "m10-d-decimal-dual-1.0.0"
MAX_DATA_ROWS_PER_PART = 1_000_000
AUDIT_NOTICE = (
    "Non-authoritative audit copy. Any manual edit invalidates the file SHA-256; "
    "this package cannot be imported into the M10 machine ledger."
)

_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXPORT_CONFIG_ID = re.compile(r"^export-config:sha256:[0-9a-f]{64}$")
_QUERY_RESULT_SET_ID = re.compile(r"^query-result-set:sha256:[0-9a-f]{64}$")
_SOURCE_INVENTORY_ID = re.compile(r"^source-inventory:sha256:[0-9a-f]{64}$")
_EXPORT_ID = re.compile(r"^export:sha256:[0-9a-f]{64}$")
_EXPORT_RECEIPT_ID = re.compile(r"^export-receipt:sha256:[0-9a-f]{64}$")
_DANGEROUS_TEXT = frozenset("=+-@")


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Decimal):
        return canonical_decimal(value)
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


def _require_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ContractError(f"{field} must be sha256:<64 lowercase hex>")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            _plain(value), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ContractError("audit value must be canonical JSON") from exc


def canonical_decimal(value: Decimal | int | float | str) -> str:
    if isinstance(value, bool):
        raise ContractError("boolean is not a Decimal audit value")
    try:
        decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ContractError("audit Decimal value is invalid") from exc
    if not decimal.is_finite():
        raise ContractError("audit Decimal value must be finite")
    if decimal == 0:
        return "0"
    text = format(decimal, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def excel_safe_decimal(value: Any) -> Decimal | None:
    """Return a numeric display value only when binary-float round-trip is exact.

    The adjacent canonical text column always remains the audit authority.
    """

    decimal = Decimal(canonical_decimal(value))
    if len(decimal.normalize().as_tuple().digits) > 15:
        return None
    number = float(decimal)
    if not math.isfinite(number) or Decimal(format(number, ".16g")) != decimal:
        return None
    return decimal


def encode_audit_cell(value: Any, kind: str) -> str:
    """Encode one typed cell without collapsing null, empty, zero, or text."""

    if value is None:
        return r"\N"
    if kind == "bool":
        if not isinstance(value, bool):
            raise ContractError("audit bool cell has the wrong type")
        return "true" if value else "false"
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ContractError("audit integer cell has the wrong type")
        return str(value)
    if kind == "decimal":
        return canonical_decimal(value)
    if kind == "json":
        text = _canonical_json(value)
    elif kind == "text":
        if not isinstance(value, str):
            raise ContractError("audit text cell has the wrong type")
        text = value
    else:
        raise ContractError("unknown audit cell kind")
    if text.startswith("\\"):
        text = "\\" + text
    if text.startswith("'") or (text and text[0] in _DANGEROUS_TEXT):
        text = "'" + text
    return text


def decode_audit_cell(value: str, kind: str) -> Any:
    if not isinstance(value, str):
        raise ContractError("encoded audit cell must be text")
    if value == r"\N":
        return None
    if kind in {"text", "json"}:
        decoded = value
        if decoded.startswith("\\\\"):
            decoded = decoded[1:]
        elif decoded.startswith("''") or (
            len(decoded) >= 2 and decoded[0] == "'" and decoded[1] in _DANGEROUS_TEXT
        ):
            decoded = decoded[1:]
        if encode_audit_cell(
            json.loads(decoded) if kind == "json" else decoded, kind
        ) != value:
            raise ContractError("audit cell is not canonically encoded")
        return json.loads(decoded) if kind == "json" else decoded
    if kind == "bool":
        if value not in {"true", "false"}:
            raise ContractError("audit bool encoding is invalid")
        return value == "true"
    if kind == "int":
        if not re.fullmatch(r"0|-?[1-9][0-9]*", value):
            raise ContractError("audit integer encoding is invalid")
        return int(value)
    if kind == "decimal":
        try:
            decimal = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ContractError("audit Decimal encoding is invalid") from exc
        if canonical_decimal(decimal) != value:
            raise ContractError("audit Decimal encoding is not canonical")
        return decimal
    raise ContractError("unknown audit cell kind")


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    kind: str = "text"


@dataclass(frozen=True)
class AuditDataset:
    name: str
    columns: tuple[ColumnSpec, ...]
    rows: tuple[Mapping[str, Any], ...]
    sort_key_columns: tuple[str, ...]


_COMMON_RESULT_COLUMNS = (
    ColumnSpec("result_contract"), ColumnSpec("schema_version"),
    ColumnSpec("source_version"), ColumnSpec("result_id"),
    ColumnSpec("content_fingerprint"), ColumnSpec("logical_result_id"),
    ColumnSpec("supersedes_result_id"), ColumnSpec("run_id"),
    ColumnSpec("event_id"), ColumnSpec("instrument_id"),
    ColumnSpec("signal_date"), ColumnSpec("as_of"), ColumnSpec("generated_at"),
    ColumnSpec("path_status"), ColumnSpec("result_role"),
    ColumnSpec("partition_role"), ColumnSpec("status"),
    ColumnSpec("status_reason"), ColumnSpec("input_fingerprint"),
    ColumnSpec("bias_labels", "json"), ColumnSpec("future_data_used", "bool"),
)
_DECIMAL_COLUMNS = (
    "gross_return", "gross_r_multiple", "net_return", "mfe", "mae",
    "missing_rate", "win_rate", "mean_gross_return", "median_gross_return",
    "gross_profit", "gross_loss_abs", "profit_factor", "gross_expectancy",
)


def _decimal_specs(*names: str) -> tuple[ColumnSpec, ...]:
    specs: list[ColumnSpec] = []
    for name in names:
        specs.extend((ColumnSpec(name, "decimal"), ColumnSpec(name + "_canonical")))
    return tuple(specs)


DATASET_COLUMNS: dict[str, tuple[ColumnSpec, ...]] = {
    "RunSummary": (
        ColumnSpec("query_result_set_id"), ColumnSpec("query_id"),
        ColumnSpec("revision_mode"), ColumnSpec("inventory_id"),
        ColumnSpec("inventory_fingerprint"), ColumnSpec("query_row_count", "int"),
        ColumnSpec("run_receipt_count", "int"), ColumnSpec("status_counts", "json"),
        ColumnSpec("evaluated_count", "int"), ColumnSpec("missing_count", "int"),
        ColumnSpec("coverage", "json"), ColumnSpec("notice"),
    ),
    "ForwardOutcomes": _COMMON_RESULT_COLUMNS + (
        ColumnSpec("window_sessions", "int"), ColumnSpec("target_session_date"),
        ColumnSpec("session_calendar_id"), ColumnSpec("session_calendar_fingerprint"),
        ColumnSpec("market_snapshot_id"), ColumnSpec("market_snapshot_fingerprint"),
        ColumnSpec("universe_id"), ColumnSpec("universe_content_fingerprint"),
        ColumnSpec("entry", "json"), ColumnSpec("endpoint", "json"),
    ) + _decimal_specs("gross_return", "mfe", "mae") + (
        ColumnSpec("policy_evidence", "json"), ColumnSpec("payload_json", "json"),
    ),
    "TradeOutcomes": _COMMON_RESULT_COLUMNS + (
        ColumnSpec("trade_plan_id"), ColumnSpec("trade_plan_link_id"),
        ColumnSpec("exit_state_id"), ColumnSpec("exit_reason"),
        ColumnSpec("holding_sessions", "int"), ColumnSpec("entry", "json"),
        ColumnSpec("exit", "json"),
    ) + _decimal_specs("gross_return", "gross_r_multiple", "net_return", "mfe", "mae") + (
        ColumnSpec("net_return_status"), ColumnSpec("mfe_status"),
        ColumnSpec("mae_status"), ColumnSpec("policy_evidence", "json"),
        ColumnSpec("payload_json", "json"),
    ),
    "PortfolioStatus": _COMMON_RESULT_COLUMNS + (
        ColumnSpec("result_set_fingerprint"), ColumnSpec("aggregation_policy", "json"),
        ColumnSpec("portfolio_scope", "json"), ColumnSpec("payload_json", "json"),
    ),
    "ResearchAggregates": _COMMON_RESULT_COLUMNS + (
        ColumnSpec("source_result_type"), ColumnSpec("window_sessions", "int"),
        ColumnSpec("result_set_fingerprint"), ColumnSpec("status_counts", "json"),
        ColumnSpec("total_count", "int"), ColumnSpec("evaluated_count", "int"),
        ColumnSpec("missing_count", "int"), ColumnSpec("win_count", "int"),
        ColumnSpec("loss_count", "int"), ColumnSpec("flat_count", "int"),
    ) + _decimal_specs(
        "missing_rate", "win_rate", "mean_gross_return", "median_gross_return",
        "gross_profit", "gross_loss_abs", "profit_factor", "gross_expectancy",
    ) + (
        ColumnSpec("metric_status"), ColumnSpec("metric_reason"),
        ColumnSpec("aggregate_scope", "json"), ColumnSpec("aggregation_policy", "json"),
        ColumnSpec("payload_json", "json"),
    ),
    "ExperimentRuns": (
        ColumnSpec("run_id"), ColumnSpec("run_receipt_id"),
        ColumnSpec("supersedes_run_receipt_id"), ColumnSpec("run_content_fingerprint"),
        ColumnSpec("schema_version"), ColumnSpec("source_version"),
        ColumnSpec("experiment_id"), ColumnSpec("attempt_id"), ColumnSpec("status"),
        ColumnSpec("as_of"), ColumnSpec("generated_at"), ColumnSpec("path_status"),
        ColumnSpec("result_role"), ColumnSpec("partition_role"),
        ColumnSpec("bias_labels", "json"), ColumnSpec("code_commit"),
        ColumnSpec("evidence_window", "json"), ColumnSpec("config_ref", "json"),
        ColumnSpec("engine", "json"), ColumnSpec("input_set_fingerprint"),
        ColumnSpec("result_set_fingerprint"), ColumnSpec("started_at"),
        ColumnSpec("finished_at"), ColumnSpec("error", "json"),
        ColumnSpec("future_data_used", "bool"), ColumnSpec("payload_json", "json"),
    ),
    "PortfolioRunRefs": (
        ColumnSpec("parent_id"), ColumnSpec("ordinal", "int"),
        ColumnSpec("reference_role"), ColumnSpec("referenced_id"),
        ColumnSpec("content_fingerprint"),
    ),
    "ResearchAggregateRefs": (
        ColumnSpec("parent_id"), ColumnSpec("ordinal", "int"),
        ColumnSpec("reference_role"), ColumnSpec("referenced_id"),
        ColumnSpec("content_fingerprint"),
    ),
    "RunPolicyRefs": (
        ColumnSpec("parent_id"), ColumnSpec("ordinal", "int"),
        ColumnSpec("policy_kind"), ColumnSpec("policy_version"),
        ColumnSpec("policy_fingerprint"),
    ),
    "RunInputRefs": (
        ColumnSpec("parent_id"), ColumnSpec("ordinal", "int"),
        ColumnSpec("reference_role"), ColumnSpec("referenced_id"),
        ColumnSpec("content_fingerprint"),
    ),
    "RunResultRefs": (
        ColumnSpec("parent_id"), ColumnSpec("ordinal", "int"),
        ColumnSpec("reference_role"), ColumnSpec("referenced_id"),
        ColumnSpec("content_fingerprint"),
    ),
    "BiasMissingData": (
        ColumnSpec("result_contract"), ColumnSpec("result_id"),
        ColumnSpec("run_id"), ColumnSpec("event_id"), ColumnSpec("instrument_id"),
        ColumnSpec("status"), ColumnSpec("status_reason"),
        ColumnSpec("bias_labels", "json"),
    ),
    "VersionEvidence": (
        ColumnSpec("record_kind"), ColumnSpec("contract_name"),
        ColumnSpec("stable_id"), ColumnSpec("run_id"), ColumnSpec("schema_version"),
        ColumnSpec("source_version"), ColumnSpec("content_fingerprint"),
        ColumnSpec("code_commit"),
    ),
    "HumanReview": (
        ColumnSpec("result_contract"), ColumnSpec("result_id"),
        ColumnSpec("content_fingerprint"), ColumnSpec("event_id"),
        ColumnSpec("instrument_id"), ColumnSpec("signal_date"), ColumnSpec("run_id"),
        ColumnSpec("reviewer"), ColumnSpec("reviewed_at"),
        ColumnSpec("decision"), ColumnSpec("issue_type"), ColumnSpec("notes"),
        ColumnSpec("hypothesis"), ColumnSpec("notice"),
    ),
}


_RESULT_DATASET = {
    "ForwardOutcome": "ForwardOutcomes",
    "TradeOutcome": "TradeOutcomes",
    "PortfolioRun": "PortfolioStatus",
    "ResearchAggregate": "ResearchAggregates",
}

DATASET_SORT_KEYS: dict[str, tuple[str, ...]] = {
    "RunSummary": ("query_result_set_id",),
    "ForwardOutcomes": ("result_id",),
    "TradeOutcomes": ("result_id",),
    "ResearchAggregates": ("result_id",),
    "PortfolioStatus": ("result_id",),
    "ExperimentRuns": ("run_id", "run_receipt_id"),
    "PortfolioRunRefs": ("parent_id", "ordinal"),
    "ResearchAggregateRefs": ("parent_id", "ordinal"),
    "RunPolicyRefs": ("parent_id", "ordinal"),
    "RunInputRefs": ("parent_id", "ordinal"),
    "RunResultRefs": ("parent_id", "ordinal"),
    "BiasMissingData": ("result_contract", "result_id"),
    "VersionEvidence": ("record_kind", "stable_id"),
    "HumanReview": ("result_contract", "result_id"),
}


def _reference_role(stable_id: str) -> str:
    return stable_id.split(":sha256:", 1)[0]


def _status_counts(
    records: Iterable[tuple[str, Mapping[str, Any]]]
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for contract_name, payload in records:
        status = str(payload["status"])
        if (
            contract_name == "TradeOutcome"
            and status == "pending"
            and payload.get("status_reason") == "trade_open"
        ):
            status = "open"
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _date_range(values: Iterable[Any]) -> Mapping[str, str | None]:
    dates = sorted(str(value) for value in values if value is not None)
    return {"from": dates[0] if dates else None, "to": dates[-1] if dates else None}


def _result_row(contract_name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
    row: dict[str, Any] = {
        "result_contract": contract_name,
        "schema_version": payload.get("schema_version"),
        "source_version": payload.get("source_version", {}).get("evaluation_contracts"),
        "result_id": payload.get(id_field),
        "content_fingerprint": payload.get(fingerprint_field),
        "logical_result_id": payload.get("logical_result_id"),
        "supersedes_result_id": payload.get("supersedes_result_id"),
        "run_id": payload.get("run_id"),
        "event_id": payload.get("event_id"),
        "instrument_id": payload.get("instrument_id"),
        "signal_date": payload.get("signal_date"),
        "as_of": payload.get("as_of"),
        "generated_at": payload.get("generated_at"),
        "path_status": payload.get("path_status"),
        "result_role": payload.get("result_role"),
        "partition_role": payload.get("partition_role"),
        "status": payload.get("status"),
        "status_reason": payload.get("status_reason"),
        "input_fingerprint": payload.get("input_fingerprint"),
        "bias_labels": _plain(payload.get("bias_labels", [])),
        "future_data_used": payload.get("future_data_used"),
    }
    if contract_name == "ForwardOutcome":
        row.update({
            "window_sessions": payload.get("window_sessions"),
            "target_session_date": payload.get("target_session_date"),
            "session_calendar_id": payload.get("session_calendar_id"),
            "session_calendar_fingerprint": payload.get("session_calendar_fingerprint"),
            "market_snapshot_id": payload.get("evaluation_market_snapshot_id"),
            "market_snapshot_fingerprint": payload.get("evaluation_market_snapshot_fingerprint"),
            "universe_id": payload.get("universe_id"),
            "universe_content_fingerprint": payload.get("universe_content_fingerprint"),
            "entry": _plain(payload.get("entry")), "endpoint": _plain(payload.get("endpoint")),
            "policy_evidence": {
                key: _plain(payload.get(key)) for key in (
                    "evaluation_policy", "partition_policy", "window_policy", "adjustment_policy"
                )
            },
        })
    elif contract_name == "TradeOutcome":
        row.update({
            "trade_plan_id": payload.get("trade_plan_id"),
            "trade_plan_link_id": payload.get("trade_plan_link_id"),
            "exit_state_id": payload.get("exit_state_id"),
            "exit_reason": payload.get("exit_reason"),
            "holding_sessions": payload.get("holding_sessions"),
            "entry": _plain(payload.get("entry")), "exit": _plain(payload.get("exit")),
            "net_return_status": payload.get("net_return_status"),
            "mfe_status": payload.get("mfe_status"), "mae_status": payload.get("mae_status"),
            "policy_evidence": {
                key: _plain(payload.get(key)) for key in (
                    "evaluation_policy", "partition_policy", "execution_policy",
                    "cost_policy", "adjustment_policy",
                )
            },
        })
    elif contract_name == "PortfolioRun":
        row.update({
            "result_set_fingerprint": payload.get("result_set_fingerprint"),
            "aggregation_policy": _plain(payload.get("aggregation_policy")),
            "portfolio_scope": _plain(payload.get("portfolio_scope")),
        })
    else:
        for field in (
            "source_result_type", "window_sessions", "result_set_fingerprint",
            "status_counts", "total_count", "evaluated_count", "missing_count",
            "win_count", "loss_count", "flat_count", "metric_status", "metric_reason",
        ):
            row[field] = _plain(payload.get(field))
        row.update({
            "aggregate_scope": _plain(payload.get("aggregate_scope")),
            "aggregation_policy": _plain(payload.get("aggregation_policy")),
        })
    decimal_fields = {
        "ForwardOutcome": ("gross_return", "mfe", "mae"),
        "TradeOutcome": ("gross_return", "gross_r_multiple", "net_return", "mfe", "mae"),
        "PortfolioRun": (),
        "ResearchAggregate": (
            "missing_rate", "win_rate", "mean_gross_return", "median_gross_return",
            "gross_profit", "gross_loss_abs", "profit_factor", "gross_expectancy",
        ),
    }[contract_name]
    for field in decimal_fields:
        value = payload.get(field)
        row[field] = None if value is None else excel_safe_decimal(value)
        row[field + "_canonical"] = (
            None if value is None else canonical_decimal(Decimal(str(value)))
        )
    excluded_refs = {"trade_outcome_refs", "result_refs"}
    row["payload_json"] = {
        key: _plain(value) for key, value in payload.items() if key not in excluded_refs
    }
    return row


def _run_row(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": payload["run_id"], "run_receipt_id": payload["run_receipt_id"],
        "supersedes_run_receipt_id": payload["supersedes_run_receipt_id"],
        "run_content_fingerprint": payload["run_content_fingerprint"],
        "schema_version": payload["schema_version"],
        "source_version": payload["source_version"]["evaluation_contracts"],
        "experiment_id": payload["experiment_id"], "attempt_id": payload["attempt_id"],
        "status": payload["status"], "as_of": payload["as_of"],
        "generated_at": payload["generated_at"], "path_status": payload["path_status"],
        "result_role": payload["result_role"], "partition_role": payload["partition_role"],
        "bias_labels": _plain(payload["bias_labels"]), "code_commit": payload["code_commit"],
        "evidence_window": _plain(payload["evidence_window"]),
        "config_ref": _plain(payload["config_ref"]), "engine": _plain(payload["engine"]),
        "input_set_fingerprint": payload["input_set_fingerprint"],
        "result_set_fingerprint": payload["result_set_fingerprint"],
        "started_at": payload["started_at"], "finished_at": payload["finished_at"],
        "error": _plain(payload["error"]), "future_data_used": payload["future_data_used"],
        "payload_json": {
            key: _plain(value) for key, value in payload.items()
            if key not in {"policy_refs", "input_refs", "result_refs"}
        },
    }


def _dataset(name: str, rows: Iterable[Mapping[str, Any]], keys: Sequence[str]) -> AuditDataset:
    columns = DATASET_COLUMNS[name]
    names = {column.name for column in columns}
    normalized: list[dict[str, Any]] = []
    for source in rows:
        unknown = set(source) - names
        if unknown:
            raise ContractError(f"{name} row contains unknown columns")
        normalized.append({column.name: source.get(column.name) for column in columns})
    column_kinds = {column.name: column.kind for column in columns}
    def typed_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
        values: list[Any] = []
        for key in keys:
            value = row.get(key)
            if value is None:
                values.append((1, 0 if column_kinds[key] == "int" else ""))
            elif column_kinds[key] == "int":
                values.append((0, int(value)))
            else:
                values.append((0, str(value)))
        return tuple(values)
    normalized.sort(key=typed_key)
    return AuditDataset(name, columns, tuple(_freeze(row) for row in normalized), tuple(keys))


def build_audit_datasets(execution: EvaluationQueryResult) -> Mapping[str, AuditDataset]:
    validate_query_execution(execution)
    if execution.result_set["status"] == "unavailable":
        raise ContractError("unavailable query result cannot be exported")

    result_rows: dict[str, list[dict[str, Any]]] = {
        name: [] for name in _RESULT_DATASET.values()
    }
    portfolio_refs: list[dict[str, Any]] = []
    aggregate_refs: list[dict[str, Any]] = []
    bias_rows: list[dict[str, Any]] = []
    version_rows: list[dict[str, Any]] = []
    human_rows: list[dict[str, Any]] = []
    status_counts = _status_counts(execution.results)
    evaluated_count = sum(
        1 for _, payload in execution.results if payload.get("gross_return") is not None
    )
    for contract_name, payload in execution.results:
        row = _result_row(contract_name, payload)
        result_rows[_RESULT_DATASET[contract_name]].append(row)
        id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
        result_id = str(payload[id_field])
        status = str(payload["status"])
        bias_rows.append({
            "result_contract": contract_name, "result_id": result_id,
            "run_id": payload["run_id"], "event_id": payload.get("event_id"),
            "instrument_id": payload.get("instrument_id"), "status": status,
            "status_reason": payload.get("status_reason"),
            "bias_labels": _plain(payload.get("bias_labels", [])),
        })
        version_rows.append({
            "record_kind": "result", "contract_name": contract_name,
            "stable_id": result_id, "run_id": payload["run_id"],
            "schema_version": payload["schema_version"],
            "source_version": payload["source_version"]["evaluation_contracts"],
            "content_fingerprint": payload[fingerprint_field], "code_commit": None,
        })
        human_rows.append({
            "result_contract": contract_name, "result_id": result_id,
            "content_fingerprint": payload[fingerprint_field],
            "event_id": payload.get("event_id"), "instrument_id": payload.get("instrument_id"),
            "signal_date": payload.get("signal_date"), "run_id": payload["run_id"],
            "reviewer": "", "reviewed_at": "", "decision": "",
            "issue_type": "", "notes": "", "hypothesis": "", "notice": AUDIT_NOTICE,
        })
        refs = payload.get("trade_outcome_refs") if contract_name == "PortfolioRun" else (
            payload.get("result_refs") if contract_name == "ResearchAggregate" else None
        )
        target = portfolio_refs if contract_name == "PortfolioRun" else aggregate_refs
        if refs is not None:
            for ordinal, ref in enumerate(refs, 1):
                target.append({
                    "parent_id": result_id, "ordinal": ordinal,
                    "reference_role": _reference_role(str(ref["id"])),
                    "referenced_id": ref["id"],
                    "content_fingerprint": ref["content_fingerprint"],
                })

    run_rows: list[dict[str, Any]] = []
    policy_rows: list[dict[str, Any]] = []
    input_rows: list[dict[str, Any]] = []
    output_rows: list[dict[str, Any]] = []
    for receipt in execution.run_receipts:
        run_rows.append(_run_row(receipt))
        receipt_id = str(receipt["run_receipt_id"])
        version_rows.append({
            "record_kind": "run_receipt", "contract_name": "ExperimentRun",
            "stable_id": receipt_id, "run_id": receipt["run_id"],
            "schema_version": receipt["schema_version"],
            "source_version": receipt["source_version"]["evaluation_contracts"],
            "content_fingerprint": receipt["run_content_fingerprint"],
            "code_commit": receipt["code_commit"],
        })
        for ordinal, policy in enumerate(receipt["policy_refs"], 1):
            policy_rows.append({
                "parent_id": receipt_id, "ordinal": ordinal,
                "policy_kind": policy["policy_kind"],
                "policy_version": policy["policy_version"],
                "policy_fingerprint": policy["policy_fingerprint"],
            })
        for collection, target in (
            (receipt["input_refs"], input_rows), (receipt["result_refs"], output_rows)
        ):
            for ordinal, ref in enumerate(collection, 1):
                target.append({
                    "parent_id": receipt_id, "ordinal": ordinal,
                    "reference_role": _reference_role(str(ref["id"])),
                    "referenced_id": ref["id"],
                    "content_fingerprint": ref["content_fingerprint"],
                })

    coverage = {
        name: ("available" if rows else "no_source_rows")
        for name, rows in result_rows.items()
    }
    coverage.update({
        "Score Analysis": "not_implemented",
        "Factor Analysis": "not_implemented",
        "Pair Matrix": "not_implemented",
    })
    summary = [{
        "query_result_set_id": execution.result_set["query_result_set_id"],
        "query_id": execution.query["query_id"],
        "revision_mode": execution.query["revision_mode"],
        "inventory_id": execution.result_set["source_inventory"]["source_inventory_id"],
        "inventory_fingerprint": execution.result_set["source_inventory"]["source_inventory_fingerprint"],
        "query_row_count": execution.result_set["row_count"],
        "run_receipt_count": len(execution.run_receipts),
        "status_counts": status_counts,
        "evaluated_count": evaluated_count,
        "missing_count": len(execution.results) - evaluated_count,
        "coverage": coverage,
        "notice": AUDIT_NOTICE,
    }]

    datasets = {
        name: _dataset(name, rows, DATASET_SORT_KEYS[name])
        for name, rows in {
            "RunSummary": summary,
            "ForwardOutcomes": result_rows["ForwardOutcomes"],
            "TradeOutcomes": result_rows["TradeOutcomes"],
            "ResearchAggregates": result_rows["ResearchAggregates"],
            "PortfolioStatus": result_rows["PortfolioStatus"],
            "ExperimentRuns": run_rows,
            "PortfolioRunRefs": portfolio_refs,
            "ResearchAggregateRefs": aggregate_refs,
            "RunPolicyRefs": policy_rows,
            "RunInputRefs": input_rows,
            "RunResultRefs": output_rows,
            "BiasMissingData": bias_rows,
            "VersionEvidence": version_rows,
            "HumanReview": human_rows,
        }.items()
    }
    return MappingProxyType(datasets)


def _export_config_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _plain(value) for key, value in payload.items()
        if key not in {"export_config_id", "export_config_content_fingerprint"}
    }


def build_export_config(
    *,
    formats: Sequence[str] = ("csv",),
    max_data_rows: int = MAX_DATA_ROWS_PER_PART,
) -> Mapping[str, Any]:
    normalized_formats = sorted(set(formats))
    if not normalized_formats or "csv" not in normalized_formats:
        raise ContractError("M10-D audit export must include CSV")
    payload: dict[str, Any] = {
        "schema_version": EXPORT_CONFIG_SCHEMA_VERSION,
        "source_version": {"evaluation_contracts": M10_D_SOURCE_VERSION},
        "formats": normalized_formats,
        "dataset_columns": {
            name: [{"name": item.name, "kind": item.kind} for item in columns]
            for name, columns in DATASET_COLUMNS.items()
        },
        "cell_codec_version": AUDIT_CELL_CODEC_VERSION,
        "csv_policy": {
            "policy_version": CSV_POLICY_VERSION,
            "encoding": "utf-8",
            "bom": False,
            "dialect": "rfc4180",
            "delimiter": ",",
            "line_ending": "crlf",
        },
        "xlsx_policy": (
            {
                "policy_version": XLSX_POLICY_VERSION,
                "dependency": "XlsxWriter",
                "dependency_version": "3.2.9",
                "constant_memory": True,
                "strings_to_formulas": False,
                "strings_to_urls": False,
                "strings_to_numbers": False,
                "fixed_created_utc": "2000-01-01T00:00:00Z",
            }
            if "xlsx" in normalized_formats else None
        ),
        "partition_policy": {
            "policy_version": PARTITION_POLICY_VERSION,
            "max_data_rows": max_data_rows,
            "header_rows": 1,
        },
        "sort_policy_version": QUERY_SORT_POLICY_VERSION,
        "artifact_naming_policy_version": ARTIFACT_NAMING_POLICY_VERSION,
        "text_safety_policy_version": TEXT_SAFETY_POLICY_VERSION,
        "decimal_render_policy_version": DECIMAL_RENDER_POLICY_VERSION,
    }
    identity = _export_config_identity(payload)
    payload["export_config_id"] = "export-config:" + canonical_fingerprint(identity)
    payload["export_config_content_fingerprint"] = canonical_fingerprint(identity)
    validate_export_config(payload)
    return _freeze(payload)


def validate_export_config(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise ContractError("ExportConfig must be an object")
    fields = {
        "schema_version", "source_version", "export_config_id",
        "export_config_content_fingerprint", "formats", "dataset_columns",
        "cell_codec_version", "csv_policy", "xlsx_policy", "partition_policy",
        "sort_policy_version", "artifact_naming_policy_version",
        "text_safety_policy_version", "decimal_render_policy_version",
    }
    _exact_fields(payload, fields, "ExportConfig 1.0.0")
    if payload["schema_version"] != EXPORT_CONFIG_SCHEMA_VERSION:
        raise ContractError("unknown ExportConfig schema version")
    if _plain(payload["source_version"]) != {"evaluation_contracts": M10_D_SOURCE_VERSION}:
        raise ContractError("ExportConfig source version is invalid")
    formats = payload["formats"]
    if not isinstance(formats, (list, tuple)) or list(formats) != sorted(set(formats)):
        raise ContractError("ExportConfig formats are not canonical")
    if not set(formats) <= {"csv", "xlsx"} or "csv" not in formats:
        raise ContractError("ExportConfig formats are invalid")
    expected_columns = {
        name: [{"name": item.name, "kind": item.kind} for item in columns]
        for name, columns in DATASET_COLUMNS.items()
    }
    if _plain(payload["dataset_columns"]) != expected_columns:
        raise ContractError("ExportConfig dataset columns are invalid")
    if payload["cell_codec_version"] != AUDIT_CELL_CODEC_VERSION:
        raise ContractError("ExportConfig cell codec is invalid")
    csv_policy = payload["csv_policy"]
    expected_csv = {
        "policy_version": CSV_POLICY_VERSION, "encoding": "utf-8", "bom": False,
        "dialect": "rfc4180", "delimiter": ",", "line_ending": "crlf",
    }
    if _plain(csv_policy) != expected_csv:
        raise ContractError("ExportConfig CSV policy is invalid")
    xlsx_policy = payload["xlsx_policy"]
    if "xlsx" in formats:
        expected_xlsx = {
            "policy_version": XLSX_POLICY_VERSION, "dependency": "XlsxWriter",
            "dependency_version": "3.2.9", "constant_memory": True,
            "strings_to_formulas": False, "strings_to_urls": False,
            "strings_to_numbers": False, "fixed_created_utc": "2000-01-01T00:00:00Z",
        }
        if _plain(xlsx_policy) != expected_xlsx:
            raise ContractError("ExportConfig XLSX policy is invalid")
    elif xlsx_policy is not None:
        raise ContractError("CSV-only ExportConfig cannot carry XLSX policy")
    partition = payload["partition_policy"]
    if not isinstance(partition, Mapping):
        raise ContractError("ExportConfig partition policy must be an object")
    _exact_fields(partition, {"policy_version", "max_data_rows", "header_rows"}, "partition_policy")
    if partition["policy_version"] != PARTITION_POLICY_VERSION or partition["header_rows"] != 1:
        raise ContractError("ExportConfig partition policy is invalid")
    maximum = partition["max_data_rows"]
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= MAX_DATA_ROWS_PER_PART:
        raise ContractError("max_data_rows must be between 1 and 1,000,000")
    expected_versions = {
        "sort_policy_version": QUERY_SORT_POLICY_VERSION,
        "artifact_naming_policy_version": ARTIFACT_NAMING_POLICY_VERSION,
        "text_safety_policy_version": TEXT_SAFETY_POLICY_VERSION,
        "decimal_render_policy_version": DECIMAL_RENDER_POLICY_VERSION,
    }
    for field, expected in expected_versions.items():
        if payload[field] != expected:
            raise ContractError(f"ExportConfig {field} is invalid")
    expected = canonical_fingerprint(_export_config_identity(payload))
    if payload["export_config_id"] != "export-config:" + expected:
        raise ContractError("ExportConfig ID is invalid")
    if payload["export_config_content_fingerprint"] != expected:
        raise ContractError("ExportConfig content fingerprint is invalid")


def _row_values(dataset: AuditDataset, row: Mapping[str, Any]) -> list[str]:
    return [encode_audit_cell(row[column.name], column.kind) for column in dataset.columns]


def dataset_row_set_fingerprint(dataset: AuditDataset, rows: Sequence[Mapping[str, Any]] | None = None) -> str:
    selected = dataset.rows if rows is None else rows
    return canonical_fingerprint({
        "dataset": dataset.name,
        "columns": [{"name": item.name, "kind": item.kind} for item in dataset.columns],
        "rows": [_row_values(dataset, row) for row in selected],
    })


def partition_dataset(dataset: AuditDataset, max_data_rows: int) -> tuple[tuple[Mapping[str, Any], ...], ...]:
    if not dataset.rows:
        return ()
    return tuple(
        dataset.rows[index:index + max_data_rows]
        for index in range(0, len(dataset.rows), max_data_rows)
    )


def _sort_key(dataset: AuditDataset, row: Mapping[str, Any]) -> str:
    return _canonical_json([row.get(key) for key in dataset.sort_key_columns])


def _dataset_slug(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def _write_csv_part(path: Path, dataset: AuditDataset, rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(
            handle, dialect="excel", delimiter=",", quotechar='"',
            lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL,
        )
        writer.writerow([item.name for item in dataset.columns])
        for row in rows:
            writer.writerow(_row_values(dataset, row))
        handle.flush()
        os.fsync(handle.fileno())


def read_csv_part(path: Path, dataset: AuditDataset) -> tuple[Mapping[str, Any], ...]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ContractError("CSV artifact cannot be read") from exc
    if raw.startswith(b"\xef\xbb\xbf") or b"\n" in raw.replace(b"\r\n", b""):
        raise ContractError("CSV artifact must be UTF-8 without BOM and use CRLF")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("CSV artifact is not UTF-8") from exc
    reader = csv.reader(io.StringIO(text, newline=""))
    rows = list(reader)
    header = [item.name for item in dataset.columns]
    if not rows or rows[0] != header:
        raise ContractError("CSV artifact header does not match its dataset")
    decoded: list[Mapping[str, Any]] = []
    for fields in rows[1:]:
        if len(fields) != len(dataset.columns):
            raise ContractError("CSV artifact row width is invalid")
        decoded.append(_freeze({
            column.name: decode_audit_cell(value, column.kind)
            for column, value in zip(dataset.columns, fields, strict=True)
        }))
    return tuple(decoded)


def _artifact_metadata(
    path: Path,
    *,
    relative_path: str,
    artifact_format: str,
    dataset: AuditDataset,
    rows: Sequence[Mapping[str, Any]],
    part_number: int,
    part_count: int,
    worksheet_row_count: int | None,
    worksheet_name: str | None = None,
    file_evidence: tuple[int, str] | None = None,
) -> dict[str, Any]:
    byte_count, file_sha256 = file_evidence or _file_evidence(path)
    return {
        "relative_path": relative_path,
        "format": artifact_format,
        "dataset": dataset.name,
        "part_number": part_number,
        "part_count": part_count,
        "data_row_count": len(rows),
        "worksheet_row_count": worksheet_row_count,
        "worksheet_name": worksheet_name,
        "first_sort_key": _sort_key(dataset, rows[0]) if rows else None,
        "last_sort_key": _sort_key(dataset, rows[-1]) if rows else None,
        "row_set_fingerprint": dataset_row_set_fingerprint(dataset, rows),
        "byte_count": byte_count,
        "file_sha256": file_sha256,
    }


def _file_evidence(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            byte_count += len(chunk)
            digest.update(chunk)
    return byte_count, "sha256:" + digest.hexdigest()


def _write_csv_artifacts(
    root: Path,
    datasets: Mapping[str, AuditDataset],
    max_data_rows: int,
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for name, dataset in datasets.items():
        parts = partition_dataset(dataset, max_data_rows) or ((),)
        for index, rows in enumerate(parts, 1):
            relative = f"csv/{_dataset_slug(name)}.part-{index:03d}.csv"
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_csv_part(path, dataset, rows)
            decoded = read_csv_part(path, dataset)
            if [
                _row_values(dataset, item) for item in decoded
            ] != [
                _row_values(dataset, item) for item in rows
            ]:
                raise ContractError("CSV artifact failed its typed round-trip")
            artifacts.append(_artifact_metadata(
                path,
                relative_path=relative,
                artifact_format="csv",
                dataset=dataset,
                rows=rows,
                part_number=index,
                part_count=len(parts),
                worksheet_row_count=None,
            ))
    _fsync_directory(root / "csv")
    return artifacts


def _manifest_semantic(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _plain(value) for key, value in payload.items()
        if key != "manifest_content_fingerprint"
    }


def _export_receipt_semantic(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return every materialization fact except the two self-referential hashes."""

    return {
        key: _plain(value) for key, value in payload.items()
        if key not in {"export_receipt_id", "manifest_content_fingerprint"}
    }


def compute_export_receipt_id(payload: Mapping[str, Any]) -> str:
    """Bind a receipt to the complete manifest materialization semantics."""

    return "export-receipt:" + canonical_fingerprint(
        _export_receipt_semantic(payload)
    )


def _safe_relative_path(value: Any) -> str:
    text = _require_text(value, "artifact relative_path")
    if "\\" in text or text.startswith("/"):
        raise ContractError("artifact path must be canonical POSIX relative path")
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts) or PurePosixPath(text).as_posix() != text:
        raise ContractError("artifact path escapes the export package")
    return text


def build_export_manifest(
    execution: EvaluationQueryResult,
    config: Mapping[str, Any],
    *,
    artifacts: Sequence[Mapping[str, Any]],
    generated_at: str,
    code_commit: str,
) -> Mapping[str, Any]:
    validate_query_execution(execution)
    validate_export_config(config)
    try:
        datetime.fromisoformat(generated_at.removesuffix("Z") + "+00:00")
    except (AttributeError, ValueError) as exc:
        raise ContractError("ExportManifest generated_at must be UTC ISO-8601") from exc
    if not generated_at.endswith("Z"):
        raise ContractError("ExportManifest generated_at must end in Z")
    if not re.fullmatch(r"[0-9a-f]{40}", code_commit):
        raise ContractError("ExportManifest code_commit must be full 40-hex")
    ordered_artifacts = sorted(
        (_plain(item) for item in artifacts),
        key=lambda item: (
            item["format"], item["dataset"], item["part_number"],
            item.get("worksheet_name") or "", item["relative_path"],
        ),
    )
    export_identity = {
        "query_result_set_id": execution.result_set["query_result_set_id"],
        "query_result_set_content_fingerprint": execution.result_set["query_result_set_content_fingerprint"],
        "export_config_id": config["export_config_id"],
        "export_config_content_fingerprint": config["export_config_content_fingerprint"],
    }
    export_id = "export:" + canonical_fingerprint(export_identity)
    artifact_set_fingerprint = canonical_fingerprint(ordered_artifacts)
    dataset_counts: dict[str, int] = {name: 0 for name in DATASET_COLUMNS}
    for item in ordered_artifacts:
        if item["format"] == "csv":
            dataset_counts[item["dataset"]] = dataset_counts.get(item["dataset"], 0) + int(item["data_row_count"])
    source_inventory = execution.result_set["source_inventory"]
    source_run_ids = sorted({
        str(item["run_id"]) for item in execution.result_set["result_refs"]
    })
    scope_summary = {
        "result_contracts": sorted({name for name, _ in execution.results}),
        "schema_versions": sorted({str(item["schema_version"]) for _, item in execution.results}),
        "source_versions": sorted({
            str(item["source_version"]["evaluation_contracts"])
            for _, item in execution.results
        }),
        "signal_date_range": _date_range(
            item.get("signal_date") for _, item in execution.results
        ),
        "as_of_range": _date_range(item.get("as_of") for _, item in execution.results),
        "path_statuses": sorted({str(item["path_status"]) for _, item in execution.results}),
        "result_roles": sorted({str(item["result_role"]) for _, item in execution.results}),
        "partition_roles": sorted({str(item["partition_role"]) for _, item in execution.results}),
        "bias_labels": sorted({
            str(label) for _, item in execution.results for label in item.get("bias_labels", ())
        }),
        "status_counts": _status_counts(execution.results),
    }
    payload: dict[str, Any] = {
        "schema_version": EXPORT_MANIFEST_SCHEMA_VERSION,
        "source_version": {"evaluation_contracts": M10_D_SOURCE_VERSION},
        "export_id": export_id,
        "query": _plain(execution.query),
        "query_result_set": _plain(execution.result_set),
        "query_result_set_id": execution.result_set["query_result_set_id"],
        "query_result_set_content_fingerprint": execution.result_set["query_result_set_content_fingerprint"],
        "source_inventory_id": source_inventory["source_inventory_id"],
        "source_inventory_fingerprint": source_inventory["source_inventory_fingerprint"],
        "export_config_id": config["export_config_id"],
        "export_config_content_fingerprint": config["export_config_content_fingerprint"],
        "export_config": _plain(config),
        "source_result_set_fingerprint": execution.result_set["result_set_fingerprint"],
        "source_run_receipt_set_fingerprint": execution.result_set["run_receipt_set_fingerprint"],
        "source_result_refs": _plain(execution.result_set["result_refs"]),
        "source_run_receipt_refs": _plain(execution.result_set["run_receipt_refs"]),
        "source_run_ids": source_run_ids,
        "scope_summary": scope_summary,
        "requested_formats": list(config["formats"]),
        "code_commit": code_commit,
        "generated_at": generated_at,
        "notice": AUDIT_NOTICE,
        "query_row_count": execution.result_set["row_count"],
        "dataset_counts": dict(sorted(dataset_counts.items())),
        "artifacts": ordered_artifacts,
        "artifact_set_fingerprint": artifact_set_fingerprint,
        "status": "completed",
    }
    payload["export_receipt_id"] = compute_export_receipt_id(payload)
    payload["manifest_content_fingerprint"] = canonical_fingerprint(
        _manifest_semantic(payload)
    )
    validate_export_manifest(payload)
    return _freeze(payload)


def validate_export_manifest(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, Mapping):
        raise ContractError("ExportManifest must be an object")
    fields = {
        "schema_version", "source_version", "export_id", "export_receipt_id",
        "manifest_content_fingerprint", "query", "query_result_set_id",
        "query_result_set_content_fingerprint", "query_result_set",
        "source_inventory_id",
        "source_inventory_fingerprint", "export_config_id",
        "export_config_content_fingerprint", "export_config",
        "source_result_set_fingerprint",
        "source_run_receipt_set_fingerprint", "source_result_refs",
        "source_run_receipt_refs", "source_run_ids", "scope_summary",
        "requested_formats", "code_commit", "generated_at",
        "notice", "query_row_count", "dataset_counts", "artifacts",
        "artifact_set_fingerprint", "status",
    }
    _exact_fields(payload, fields, "ExportManifest 2.0.0")
    if payload["schema_version"] != EXPORT_MANIFEST_SCHEMA_VERSION:
        raise ContractError("unknown ExportManifest schema version")
    if _plain(payload["source_version"]) != {"evaluation_contracts": M10_D_SOURCE_VERSION}:
        raise ContractError("ExportManifest source version is invalid")
    validate_evaluation_query(payload["query"])
    validate_query_result_set(payload["query_result_set"])
    validate_export_config(payload["export_config"])
    result_set = payload["query_result_set"]
    if (
        result_set["query_id"] != payload["query"]["query_id"]
        or result_set["query_content_fingerprint"]
        != payload["query"]["query_content_fingerprint"]
        or result_set["query_result_set_id"] != payload["query_result_set_id"]
        or result_set["query_result_set_content_fingerprint"]
        != payload["query_result_set_content_fingerprint"]
    ):
        raise ContractError("ExportManifest query result evidence is inconsistent")
    if (
        payload["export_config"]["export_config_id"] != payload["export_config_id"]
        or payload["export_config"]["export_config_content_fingerprint"]
        != payload["export_config_content_fingerprint"]
    ):
        raise ContractError("ExportManifest export config evidence is inconsistent")
    if not _QUERY_RESULT_SET_ID.fullmatch(str(payload["query_result_set_id"])):
        raise ContractError("ExportManifest query result set ID is invalid")
    if not _EXPORT_CONFIG_ID.fullmatch(str(payload["export_config_id"])):
        raise ContractError("ExportManifest config ID is invalid")
    if not _EXPORT_ID.fullmatch(str(payload["export_id"])):
        raise ContractError("ExportManifest export_id is invalid")
    if not _EXPORT_RECEIPT_ID.fullmatch(str(payload["export_receipt_id"])):
        raise ContractError("ExportManifest export_receipt_id is invalid")
    for field in (
        "manifest_content_fingerprint", "query_result_set_content_fingerprint",
        "source_inventory_fingerprint", "export_config_content_fingerprint",
        "source_result_set_fingerprint", "source_run_receipt_set_fingerprint",
        "artifact_set_fingerprint",
    ):
        _require_sha(payload[field], field)
    if not _SOURCE_INVENTORY_ID.fullmatch(str(payload["source_inventory_id"])):
        raise ContractError("ExportManifest inventory ID is invalid")
    if payload["status"] != "completed" or payload["notice"] != AUDIT_NOTICE:
        raise ContractError("ExportManifest status or audit notice is invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", str(payload["code_commit"])):
        raise ContractError("ExportManifest code_commit is invalid")
    try:
        timestamp = datetime.fromisoformat(str(payload["generated_at"]).removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ContractError("ExportManifest generated_at is invalid") from exc
    if not str(payload["generated_at"]).endswith("Z") or timestamp.utcoffset() != timezone.utc.utcoffset(timestamp):
        raise ContractError("ExportManifest generated_at must be UTC")
    if (
        isinstance(payload["query_row_count"], bool)
        or not isinstance(payload["query_row_count"], int)
        or payload["query_row_count"] < 0
    ):
        raise ContractError("ExportManifest query_row_count is invalid")
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, (list, tuple)):
        raise ContractError("ExportManifest artifacts must be a list")
    artifact_fields = {
        "relative_path", "format", "dataset", "part_number", "part_count",
        "data_row_count", "worksheet_row_count", "worksheet_name",
        "first_sort_key", "last_sort_key",
        "row_set_fingerprint", "byte_count", "file_sha256",
    }
    normalized = []
    paths: dict[str, tuple[str, int, str]] = {}
    worksheet_names: set[str] = set()
    part_groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for item in artifacts:
        if not isinstance(item, Mapping):
            raise ContractError("ExportManifest artifact must be an object")
        _exact_fields(item, artifact_fields, "ExportManifest artifact")
        path = _safe_relative_path(item["relative_path"])
        if path in {"manifest.json", "COMPLETED.json"}:
            raise ContractError("ExportManifest contains a reserved path")
        if item["format"] not in {"csv", "xlsx"} or item["dataset"] not in DATASET_COLUMNS:
            raise ContractError("ExportManifest artifact role is invalid")
        for field in ("part_number", "part_count", "data_row_count", "byte_count"):
            if isinstance(item[field], bool) or not isinstance(item[field], int) or item[field] < (1 if field in {"part_number", "part_count", "byte_count"} else 0):
                raise ContractError("ExportManifest artifact count is invalid")
        if item["worksheet_row_count"] is not None and (
            isinstance(item["worksheet_row_count"], bool)
            or not isinstance(item["worksheet_row_count"], int)
            or item["worksheet_row_count"] < 1
        ):
            raise ContractError("worksheet_row_count is invalid")
        worksheet_name = item["worksheet_name"]
        if item["format"] == "csv":
            if worksheet_name is not None or item["worksheet_row_count"] is not None:
                raise ContractError("CSV artifact cannot carry worksheet metadata")
        elif (
            not isinstance(worksheet_name, str)
            or not worksheet_name
            or len(worksheet_name) > 31
            or item["worksheet_row_count"] != item["data_row_count"] + 1
        ):
            raise ContractError("XLSX worksheet metadata is invalid")
        elif worksheet_name in worksheet_names:
            raise ContractError("ExportManifest contains a duplicate worksheet name")
        else:
            worksheet_names.add(worksheet_name)
        _require_sha(item["row_set_fingerprint"], "row_set_fingerprint")
        _require_sha(item["file_sha256"], "file_sha256")
        physical = (str(item["format"]), int(item["byte_count"]), str(item["file_sha256"]))
        if path in paths:
            if item["format"] != "xlsx" or paths[path] != physical:
                raise ContractError("ExportManifest contains a conflicting duplicate path")
        else:
            paths[path] = physical
        normalized.append(_plain(item))
        part_groups.setdefault((str(item["format"]), str(item["dataset"])), []).append(item)
    ordered = sorted(
        normalized,
        key=lambda item: (
            item["format"], item["dataset"], item["part_number"],
            item.get("worksheet_name") or "", item["relative_path"],
        ),
    )
    if normalized != ordered:
        raise ContractError("ExportManifest artifacts are not canonically sorted")
    for group in part_groups.values():
        count = len(group)
        if [item["part_number"] for item in group] != list(range(1, count + 1)):
            raise ContractError("ExportManifest part numbers are not contiguous")
        if any(item["part_count"] != count for item in group):
            raise ContractError("ExportManifest part_count is inconsistent")
    if payload["artifact_set_fingerprint"] != canonical_fingerprint(ordered):
        raise ContractError("ExportManifest artifact set fingerprint is invalid")
    formats = payload["requested_formats"]
    if (
        not isinstance(formats, (list, tuple))
        or list(formats) != sorted(set(formats))
        or "csv" not in formats
        or not set(formats) <= {"csv", "xlsx"}
        or set(formats) != {item["format"] for item in ordered}
    ):
        raise ContractError("ExportManifest requested formats are inconsistent")
    result_refs = payload["source_result_refs"]
    receipt_refs = payload["source_run_receipt_refs"]
    if not isinstance(result_refs, (list, tuple)) or not isinstance(receipt_refs, (list, tuple)):
        raise ContractError("ExportManifest source references must be lists")
    if payload["source_result_set_fingerprint"] != canonical_fingerprint(_plain(result_refs)):
        raise ContractError("ExportManifest result reference fingerprint is invalid")
    if payload["source_run_receipt_set_fingerprint"] != canonical_fingerprint(_plain(receipt_refs)):
        raise ContractError("ExportManifest receipt reference fingerprint is invalid")
    if (
        _plain(result_refs) != _plain(result_set["result_refs"])
        or _plain(receipt_refs) != _plain(result_set["run_receipt_refs"])
        or payload["source_inventory_id"]
        != result_set["source_inventory"]["source_inventory_id"]
        or payload["source_inventory_fingerprint"]
        != result_set["source_inventory"]["source_inventory_fingerprint"]
    ):
        raise ContractError("ExportManifest source evidence differs from QueryResultSet")
    source_run_ids = payload["source_run_ids"]
    expected_run_ids = sorted({str(item["run_id"]) for item in result_refs})
    if _plain(source_run_ids) != expected_run_ids:
        raise ContractError("ExportManifest source run IDs are inconsistent")
    scope = payload["scope_summary"]
    scope_fields = {
        "result_contracts", "schema_versions", "source_versions",
        "signal_date_range", "as_of_range", "path_statuses", "result_roles",
        "partition_roles", "bias_labels", "status_counts",
    }
    if not isinstance(scope, Mapping):
        raise ContractError("ExportManifest scope_summary must be an object")
    _exact_fields(scope, scope_fields, "ExportManifest scope_summary")
    for field in (
        "result_contracts", "schema_versions", "source_versions", "path_statuses",
        "result_roles", "partition_roles", "bias_labels",
    ):
        value = scope[field]
        if (
            not isinstance(value, (list, tuple))
            or list(value) != sorted(set(value))
            or any(not isinstance(item, str) or not item for item in value)
        ):
            raise ContractError("ExportManifest scope list is not canonical")
    for field in ("signal_date_range", "as_of_range"):
        value = scope[field]
        if not isinstance(value, Mapping):
            raise ContractError("ExportManifest date range must be an object")
        _exact_fields(value, {"from", "to"}, f"scope_summary.{field}")
        if (value["from"] is None) != (value["to"] is None):
            raise ContractError("ExportManifest date range is incomplete")
        if value["from"] is not None and value["from"] > value["to"]:
            raise ContractError("ExportManifest date range is reversed")
    if not isinstance(scope["status_counts"], Mapping) or any(
        not isinstance(key, str)
        or isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        for key, value in scope["status_counts"].items()
    ):
        raise ContractError("ExportManifest status counts are invalid")
    if sum(scope["status_counts"].values()) != payload["query_row_count"]:
        raise ContractError("ExportManifest status counts do not conserve query rows")
    if payload["query_row_count"] != len(result_refs):
        raise ContractError("ExportManifest query row count is inconsistent")
    counts = payload["dataset_counts"]
    if not isinstance(counts, Mapping) or any(
        key not in DATASET_COLUMNS
        or isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        for key, value in counts.items()
    ):
        raise ContractError("ExportManifest dataset counts are invalid")
    csv_counts: dict[str, int] = {}
    for item in ordered:
        if item["format"] == "csv":
            csv_counts[item["dataset"]] = csv_counts.get(item["dataset"], 0) + item["data_row_count"]
    expected_counts = {name: csv_counts.get(name, 0) for name in DATASET_COLUMNS}
    if _plain(counts) != dict(sorted(expected_counts.items())):
        raise ContractError("ExportManifest dataset counts do not match CSV parts")
    main_count = sum(
        csv_counts.get(name, 0)
        for name in ("ForwardOutcomes", "TradeOutcomes", "PortfolioStatus", "ResearchAggregates")
    )
    if main_count != payload["query_row_count"]:
        raise ContractError("ExportManifest result datasets do not conserve query rows")
    if (
        csv_counts.get("ExperimentRuns", 0) != len(receipt_refs)
        or csv_counts.get("BiasMissingData", 0) != len(result_refs)
        or csv_counts.get("HumanReview", 0) != len(result_refs)
        or csv_counts.get("RunSummary", 0) != 1
    ):
        raise ContractError("ExportManifest audit datasets do not conserve their sources")
    max_rows = int(payload["export_config"]["partition_policy"]["max_data_rows"])
    if any(item["data_row_count"] > max_rows for item in ordered):
        raise ContractError("ExportManifest artifact exceeds the approved part limit")
    for (artifact_format, dataset_name), group in part_groups.items():
        if artifact_format != "xlsx":
            continue
        csv_group = part_groups.get(("csv", dataset_name))
        if csv_group is None or [
            (item["part_number"], item["data_row_count"], item["first_sort_key"],
             item["last_sort_key"], item["row_set_fingerprint"])
            for item in group
        ] != [
            (item["part_number"], item["data_row_count"], item["first_sort_key"],
             item["last_sort_key"], item["row_set_fingerprint"])
            for item in csv_group
        ]:
            raise ContractError("CSV and XLSX dataset parts do not conserve the same rows")
    if "xlsx" in formats:
        from .xlsx_export import (
            XLSX_DATASET_ORDER,
            XLSX_WORKBOOK_PATH,
            _expected_worksheet_name,
        )

        actual_xlsx_datasets = {
            dataset_name
            for artifact_format, dataset_name in part_groups
            if artifact_format == "xlsx"
        }
        expected_xlsx_datasets = {
            dataset_name
            for dataset_name in XLSX_DATASET_ORDER
            if csv_counts.get(dataset_name, 0) > 0
        }
        if actual_xlsx_datasets != expected_xlsx_datasets:
            raise ContractError("ExportManifest XLSX datasets do not match source-backed sheets")
        for dataset_name in actual_xlsx_datasets:
            group = part_groups[("xlsx", dataset_name)]
            for item in group:
                if (
                    item["relative_path"] != XLSX_WORKBOOK_PATH
                    or item["worksheet_name"]
                    != _expected_worksheet_name(
                        dataset_name, item["part_number"], item["part_count"]
                    )
                ):
                    raise ContractError("ExportManifest XLSX worksheet identity is invalid")
    export_identity = {
        "query_result_set_id": payload["query_result_set_id"],
        "query_result_set_content_fingerprint": payload["query_result_set_content_fingerprint"],
        "export_config_id": payload["export_config_id"],
        "export_config_content_fingerprint": payload["export_config_content_fingerprint"],
    }
    if payload["export_id"] != "export:" + canonical_fingerprint(export_identity):
        raise ContractError("ExportManifest logical export ID is invalid")
    expected_receipt = compute_export_receipt_id(payload)
    if payload["export_receipt_id"] != expected_receipt:
        raise ContractError("ExportManifest receipt ID is invalid")
    if payload["manifest_content_fingerprint"] != canonical_fingerprint(_manifest_semantic(payload)):
        raise ContractError("ExportManifest content fingerprint is invalid")


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (_canonical_json(payload) + "\n").encode("utf-8")


def _write_fsynced(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _verified_export_root(
    root: str | Path, *, workspace_root: str | Path | None
) -> Path:
    supplied = Path(root)
    if supplied.exists() and supplied.is_symlink():
        raise ContractError("M10-D export root cannot be a symbolic link")
    resolved = require_shadow_root(supplied, workspace_root=workspace_root)
    if resolved.exists() and not resolved.is_dir():
        raise ContractError("M10-D export root must be a directory")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _trees_equal(left: Path, right: Path) -> bool:
    left_files = sorted(path.relative_to(left) for path in left.rglob("*") if path.is_file())
    right_files = sorted(path.relative_to(right) for path in right.rglob("*") if path.is_file())
    if left_files != right_files:
        return False
    for item in left_files:
        left_path = left / item
        right_path = right / item
        if left_path.stat().st_size != right_path.stat().st_size:
            return False
        with left_path.open("rb") as left_handle, right_path.open("rb") as right_handle:
            while True:
                left_chunk = left_handle.read(1024 * 1024)
                right_chunk = right_handle.read(1024 * 1024)
                if left_chunk != right_chunk:
                    return False
                if not left_chunk:
                    break
    return True


def _package_file(package: Path, relative: str) -> Path:
    cursor = package
    for part in PurePosixPath(relative).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ContractError("M10-D package cannot contain symbolic links")
    if not cursor.is_file():
        raise ContractError("M10-D package file is missing")
    return cursor


def _ordered_child_rows(
    rows: Sequence[Mapping[str, Any]], *, label: str
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["parent_id"]), []).append(row)
    for parent_id, items in grouped.items():
        items.sort(key=lambda item: int(item["ordinal"]))
        if [item["ordinal"] for item in items] != list(range(1, len(items) + 1)):
            raise ContractError(f"{label} ordinals are not contiguous for {parent_id}")
    return grouped


def _refs_by_parent(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        parent_id: [
            {
                "id": item["referenced_id"],
                "content_fingerprint": item["content_fingerprint"],
            }
            for item in items
        ]
        for parent_id, items in _ordered_child_rows(
            rows, label="M10-D reference rows"
        ).items()
    }


def _policy_refs_by_parent(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        parent_id: [
            {
                "policy_kind": item["policy_kind"],
                "policy_version": item["policy_version"],
                "policy_fingerprint": item["policy_fingerprint"],
            }
            for item in items
        ]
        for parent_id, items in _ordered_child_rows(
            rows, label="M10-D policy rows"
        ).items()
    }


def verify_export_package(path: Path) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_dir():
        raise ContractError("M10-D export package must be a real directory")
    manifest_path = _package_file(path, "manifest.json")
    completed_path = _package_file(path, "COMPLETED.json")
    try:
        manifest = json.loads(manifest_path.read_bytes())
        completed = json.loads(completed_path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("M10-D export package receipt is unreadable") from exc
    if not isinstance(manifest, Mapping) or not isinstance(completed, Mapping):
        raise ContractError("M10-D export package receipt must be an object")
    validate_export_manifest(manifest)
    expected_completed_fields = {
        "export_receipt_id", "manifest_file_sha256", "artifact_set_fingerprint",
        "status", "notice",
    }
    _exact_fields(completed, expected_completed_fields, "M10-D COMPLETED receipt")
    manifest_sha = "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if completed != {
        "export_receipt_id": manifest["export_receipt_id"],
        "manifest_file_sha256": manifest_sha,
        "artifact_set_fingerprint": manifest["artifact_set_fingerprint"],
        "status": "completed", "notice": AUDIT_NOTICE,
    }:
        raise ContractError("M10-D COMPLETED receipt does not match its manifest")
    declared = {"manifest.json", "COMPLETED.json"}
    checked_physical: set[str] = set()
    csv_rows: dict[str, list[Mapping[str, Any]]] = {}
    csv_parts: dict[tuple[str, int], tuple[Mapping[str, Any], ...]] = {}
    for artifact in manifest["artifacts"]:
        relative = _safe_relative_path(artifact["relative_path"])
        artifact_path = _package_file(path, relative)
        declared.add(relative)
        if relative in checked_physical:
            continue
        checked_physical.add(relative)
        if _file_evidence(artifact_path) != (
            artifact["byte_count"], artifact["file_sha256"]
        ):
            raise ContractError("M10-D artifact bytes do not match the manifest")
        if artifact["format"] == "csv":
            dataset = AuditDataset(
                str(artifact["dataset"]),
                DATASET_COLUMNS[str(artifact["dataset"])],
                (),
                DATASET_SORT_KEYS[str(artifact["dataset"])],
            )
            rows = read_csv_part(artifact_path, dataset)
            matching = [
                item for item in manifest["artifacts"]
                if item["format"] == "csv" and item["relative_path"] == relative
            ]
            if len(matching) != 1:
                raise ContractError("CSV artifact path is not unique")
            if (
                len(rows) != artifact["data_row_count"]
                or dataset_row_set_fingerprint(dataset, rows)
                != artifact["row_set_fingerprint"]
                or (None if not rows else _sort_key(dataset, rows[0]))
                != artifact["first_sort_key"]
                or (None if not rows else _sort_key(dataset, rows[-1]))
                != artifact["last_sort_key"]
            ):
                raise ContractError("CSV artifact rows do not match the manifest")
            csv_rows.setdefault(str(artifact["dataset"]), []).extend(rows)
            csv_parts[(str(artifact["dataset"]), int(artifact["part_number"]))] = rows
    xlsx_artifacts = [
        item for item in manifest["artifacts"] if item["format"] == "xlsx"
    ]
    if xlsx_artifacts:
        from .ooxml import verify_generated_audit_workbook
        from .xlsx_export import _xlsx_artifact_sort_key

        workbook_paths = {str(item["relative_path"]) for item in xlsx_artifacts}
        if len(workbook_paths) != 1:
            raise ContractError("M10-D XLSX export must use one audit workbook")
        workbook_relative = next(iter(workbook_paths))
        verify_generated_audit_workbook(
            _package_file(path, workbook_relative),
            worksheet_artifacts=sorted(xlsx_artifacts, key=_xlsx_artifact_sort_key),
            csv_parts=csv_parts,
        )
    package_items = list(path.rglob("*"))
    if any(item.is_symlink() for item in package_items):
        raise ContractError("M10-D export package cannot contain symbolic links")
    actual = {
        item.relative_to(path).as_posix()
        for item in package_items if item.is_file()
    }
    if actual != declared:
        raise ContractError("M10-D export package contains undeclared files")
    if set(csv_rows) != set(DATASET_COLUMNS):
        raise ContractError("CSV package does not contain the complete dataset set")
    portfolio_refs = _refs_by_parent(csv_rows["PortfolioRunRefs"])
    aggregate_refs = _refs_by_parent(csv_rows["ResearchAggregateRefs"])
    run_policy_refs = _policy_refs_by_parent(csv_rows["RunPolicyRefs"])
    run_input_refs = _refs_by_parent(csv_rows["RunInputRefs"])
    run_result_refs = _refs_by_parent(csv_rows["RunResultRefs"])
    reconstructed_results: list[tuple[str, Mapping[str, Any]]] = []
    for dataset_name in (
        "ForwardOutcomes", "TradeOutcomes", "PortfolioStatus",
        "ResearchAggregates",
    ):
        for row in csv_rows[dataset_name]:
            contract_name = str(row["result_contract"])
            payload = row["payload_json"]
            if not isinstance(payload, Mapping):
                raise ContractError("CSV result payload_json must be an object")
            rebuilt = _plain(payload)
            result_id = str(row["result_id"])
            if contract_name == "PortfolioRun":
                rebuilt["trade_outcome_refs"] = portfolio_refs.get(result_id, [])
            elif contract_name == "ResearchAggregate":
                rebuilt["result_refs"] = aggregate_refs.get(result_id, [])
            reconstructed_results.append((contract_name, _freeze(rebuilt)))
    reconstructed_receipts: list[Mapping[str, Any]] = []
    for row in csv_rows["ExperimentRuns"]:
        payload = row["payload_json"]
        if not isinstance(payload, Mapping):
            raise ContractError("CSV run payload_json must be an object")
        rebuilt = _plain(payload)
        receipt_id = str(row["run_receipt_id"])
        rebuilt["policy_refs"] = run_policy_refs.get(receipt_id, [])
        rebuilt["input_refs"] = run_input_refs.get(receipt_id, [])
        rebuilt["result_refs"] = run_result_refs.get(receipt_id, [])
        reconstructed_receipts.append(_freeze(rebuilt))
    reconstructed = EvaluationQueryResult(
        _freeze(_plain(manifest["query"])),
        _freeze(_plain(manifest["query_result_set"])),
        tuple(reconstructed_results),
        tuple(reconstructed_receipts),
    )
    expected_datasets = build_audit_datasets(reconstructed)
    for dataset_name, expected in expected_datasets.items():
        if list(csv_rows[dataset_name]) != list(expected.rows):
            raise ContractError(
                f"CSV {dataset_name} rows differ from canonical payload projection"
            )
    return _freeze(manifest)


def publish_audit_export(
    execution: EvaluationQueryResult,
    config: Mapping[str, Any],
    *,
    output_root: str | Path,
    generated_at: str,
    code_commit: str,
    workspace_root: str | Path | None = None,
    fault_injector: Callable[[str], None] | None = None,
) -> Path:
    """Build, re-read, fsync, and atomically publish one complete audit package."""

    validate_query_execution(execution)
    validate_export_config(config)
    root = _verified_export_root(output_root, workspace_root=workspace_root)
    datasets = build_audit_datasets(execution)
    staging = Path(tempfile.mkdtemp(prefix=".m10-d-package-", dir=root))
    published = False
    try:
        artifacts = _write_csv_artifacts(
            staging, datasets, int(config["partition_policy"]["max_data_rows"])
        )
        if fault_injector is not None:
            fault_injector("after_csv")
        if "xlsx" in config["formats"]:
            from .xlsx_export import _write_xlsx_artifact

            artifacts.extend(_write_xlsx_artifact(
                staging, datasets,
                max_data_rows=int(config["partition_policy"]["max_data_rows"]),
            ))
        if fault_injector is not None:
            fault_injector("after_artifacts")
        manifest = build_export_manifest(
            execution, config, artifacts=artifacts,
            generated_at=generated_at, code_commit=code_commit,
        )
        manifest_bytes = _canonical_json_bytes(manifest)
        _write_fsynced(staging / "manifest.json", manifest_bytes)
        completed = {
            "export_receipt_id": manifest["export_receipt_id"],
            "manifest_file_sha256": "sha256:" + hashlib.sha256(manifest_bytes).hexdigest(),
            "artifact_set_fingerprint": manifest["artifact_set_fingerprint"],
            "status": "completed", "notice": AUDIT_NOTICE,
        }
        _write_fsynced(staging / "COMPLETED.json", _canonical_json_bytes(completed))
        _fsync_directory(staging)
        verify_export_package(staging)
        if fault_injector is not None:
            fault_injector("before_publish")
        final = root / str(manifest["export_receipt_id"]).rsplit(":", 1)[-1]
        with _chain_lock(root, "M10DExport", str(manifest["export_receipt_id"])):
            if final.exists() or final.is_symlink():
                if final.is_symlink() or not final.is_dir() or not _trees_equal(staging, final):
                    raise ContractError("M10-D export receipt already exists with different bytes")
                verify_export_package(final)
                return final
            os.rename(staging, final)
            published = True
            _fsync_directory(root)
        verify_export_package(final)
        return final
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)


__all__ = [
    "ARTIFACT_NAMING_POLICY_VERSION", "AUDIT_CELL_CODEC_VERSION", "AUDIT_NOTICE",
    "AuditDataset", "CSV_POLICY_VERSION", "ColumnSpec",
    "DECIMAL_RENDER_POLICY_VERSION", "EXPORT_CONFIG_SCHEMA_VERSION",
    "EXPORT_MANIFEST_SCHEMA_VERSION", "MAX_DATA_ROWS_PER_PART",
    "PARTITION_POLICY_VERSION", "TEXT_SAFETY_POLICY_VERSION", "XLSX_POLICY_VERSION",
    "build_audit_datasets", "build_export_config", "build_export_manifest",
    "canonical_decimal", "compute_export_receipt_id",
    "dataset_row_set_fingerprint", "decode_audit_cell",
    "encode_audit_cell", "partition_dataset", "publish_audit_export",
    "read_csv_part", "validate_export_config", "validate_export_manifest",
    "verify_export_package",
]
