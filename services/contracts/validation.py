"""Pure validation rules shared by M01 and later data modules.

The functions in this module perform no file, Git, network, or process I/O.  They
validate injected dictionaries so scanners, research and release preparation do
not grow separate interpretations of the same contract.
"""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import AbstractSet, Any, Iterable, Mapping


class ContractError(ValueError):
    """Raised when evidence cannot satisfy a known contract."""


SUPPORTED_MAJOR = 1
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
FROZEN_RELEASE_NAMES = frozenset({
    "update-status.json",
    "factor-registry.json",
    "daily-factor-snapshot.json",
    "unified-v2-latest.json",
    "favorite-pattern.json",
    "market-etf-watch.json",
    "industry-radar.json",
    "opportunity-ledger-latest.json",
    "signal-history-summary.json",
    "rare-opportunity-radar.json",
    "decision-summary.json",
    "resonance-tracker.json",
    "unified-v2-rankings.json",
    "opportunity-ledger.json",
    "signal-history.json",
})

COMMON_REQUIRED = {
    "schema_version",
    "as_of",
    "generated_at",
    "source_version",
    "future_data_used",
}

CONTRACT_REQUIRED = {
    "MarketDataSnapshot": {
        "snapshot_id", "market", "symbols", "adjustment_policy", "data_source",
        "universe_id", "raw_revision", "max_returned_date",
    },
    "UniverseSnapshot": {
        "universe_id", "members", "qualifications", "eligibility_rule_version", "effective_from",
        "path_status", "coverage_status",
    },
    "GateEvent": {"gate_event_id", "symbol", "signal_date", "gate_policy_version", "passed"},
    "TechnicalEvidence": {"evidence_id", "factor_id", "factor_version", "timeframe", "evidence_date", "available"},
    "ModelAssessment": {"assessment_id", "gate_event_id", "model_id", "model_version", "eligible"},
    "ContextSnapshot": {"context_id", "context_type", "status", "evidence"},
    "TradePlan": {"plan_id", "event_id", "entry", "stop", "execution_policy_version", "status"},
    "OpportunityEvent": {"event_id", "symbol", "signal_date", "gate_event_id", "model_assessments"},
    "ReleaseManifest": {"release_id", "files"},
    "ExperimentRun": {"experiment_id", "status", "evidence_window", "input_refs", "result_refs"},
}

ID_FIELDS = {
    "MarketDataSnapshot": "snapshot_id",
    "UniverseSnapshot": "universe_id",
    "GateEvent": "gate_event_id",
    "TechnicalEvidence": "evidence_id",
    "ModelAssessment": "assessment_id",
    "ContextSnapshot": "context_id",
    "TradePlan": "plan_id",
    "OpportunityEvent": "event_id",
    "ReleaseManifest": "release_id",
    "ExperimentRun": "experiment_id",
}

CONTRACT_SUPPORTED_MAJORS = {
    name: ({2} if name == "UniverseSnapshot" else {SUPPORTED_MAJOR})
    for name in CONTRACT_REQUIRED
}


def _require_date(value: Any, field: str) -> None:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{field} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ContractError(f"{field} must be canonical YYYY-MM-DD")


def _require_timestamp(value: Any) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError("generated_at must be an ISO-8601 UTC timestamp ending in Z")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError("generated_at must be a valid ISO-8601 timestamp") from exc


def _canonical(value: Mapping[str, object]) -> bytes:
    """Encode contract evidence deterministically and reject JSON non-values."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as exc:
        raise ContractError("contract evidence must be canonical JSON") from exc


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{field} must be a boolean")
    return value


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{field} must be an object")
    return value


def _require_semver(
    value: Any, field: str, *, supported_majors: set[int] | None = None
) -> re.Match[str]:
    match = SEMVER.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ContractError(f"{field} must be MAJOR.MINOR.PATCH")
    allowed = supported_majors or {SUPPORTED_MAJOR}
    if int(match.group(1)) not in allowed:
        raise ContractError(f"unknown {field} major version: {match.group(1)}")
    return match


def _require_safe_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError("manifest file path must be a non-empty relative path")
    if "\\" in value or re.match(r"^[A-Za-z]:", value):
        raise ContractError("manifest file path must use canonical POSIX relative syntax")
    parts = value.split("/")
    if value.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise ContractError("manifest file path escapes or is not canonical")
    if str(PurePosixPath(value)) != value:
        raise ContractError("manifest file path is not canonical")
    return value


def validate_contract(
    contract_name: str,
    payload: Mapping[str, Any],
    *,
    known_experiment_ids: AbstractSet[str] | None = None,
    allow_partial_manifest: bool = False,
) -> None:
    """Validate one canonical contract and fail closed on unknown evidence."""

    if contract_name not in CONTRACT_REQUIRED:
        raise ContractError(f"unknown contract: {contract_name}")
    if not isinstance(payload, Mapping):
        raise ContractError(f"{contract_name} payload must be an object")
    missing = sorted((COMMON_REQUIRED | CONTRACT_REQUIRED[contract_name]) - payload.keys())
    if missing:
        raise ContractError(f"{contract_name} missing required fields: {', '.join(missing)}")

    _require_semver(
        payload["schema_version"],
        "schema_version",
        supported_majors=CONTRACT_SUPPORTED_MAJORS[contract_name],
    )

    _require_date(payload["as_of"], "as_of")
    _require_timestamp(payload["generated_at"])
    if not isinstance(payload["source_version"], Mapping) or not payload["source_version"]:
        raise ContractError("source_version must contain explicit source evidence")
    _canonical({"source_version": dict(payload["source_version"])})
    if payload["future_data_used"] is not False:
        raise ContractError("future_data_used must be the boolean false")

    adapter_version = payload.get("adapter_version")
    if adapter_version is not None and (
        not isinstance(adapter_version, str) or not adapter_version.startswith("legacy-adapter-")
    ):
        raise ContractError("adapter_version must identify a legacy adapter")

    stable_id = _require_text(payload[ID_FIELDS[contract_name]], ID_FIELDS[contract_name])

    allowed_prefixes = {
        "MarketDataSnapshot": ("market:",),
        "UniverseSnapshot": ("universe:",),
        "GateEvent": ("gate:",),
        "TechnicalEvidence": ("evidence:",),
        "ModelAssessment": ("assessment:",),
        "ContextSnapshot": ("context:",),
        "TradePlan": ("plan:",),
        # Older examples used event:, while the target design uses opportunity:.
        "OpportunityEvent": ("event:", "opportunity:"),
        "ReleaseManifest": ("sha256:",),
    }.get(contract_name)
    if allowed_prefixes is not None and not stable_id.startswith(allowed_prefixes):
        raise ContractError(f"{ID_FIELDS[contract_name]} has an invalid contract prefix")

    if contract_name in {"GateEvent", "OpportunityEvent"}:
        _require_date(payload["signal_date"], "signal_date")
        if payload["signal_date"] != payload["as_of"]:
            raise ContractError("event signal_date must equal as_of")

    if contract_name == "GateEvent":
        symbol = _require_text(payload["symbol"], "symbol")
        gate_policy = _require_text(payload["gate_policy_version"], "gate_policy_version")
        _require_bool(payload["passed"], "passed")
        expected = f"gate:{symbol}:{payload['signal_date']}:{gate_policy}"
        if stable_id != expected:
            raise ContractError("gate_event_id does not match symbol/date/gate policy")
    elif contract_name == "TechnicalEvidence":
        _require_text(payload["factor_id"], "factor_id")
        _require_text(payload["factor_version"], "factor_version")
        _require_text(payload["timeframe"], "timeframe")
        _require_date(payload["evidence_date"], "evidence_date")
        if payload["evidence_date"] > payload["as_of"]:
            raise ContractError("TechnicalEvidence evidence_date cannot be after as_of")
        _require_bool(payload["available"], "available")
    elif contract_name == "ModelAssessment":
        _require_text(payload["gate_event_id"], "gate_event_id")
        _require_text(payload["model_id"], "model_id")
        _require_text(payload["model_version"], "model_version")
        _require_bool(payload["eligible"], "eligible")
    elif contract_name == "ContextSnapshot":
        _require_text(payload["context_type"], "context_type")
        _require_text(payload["status"], "status")
        _require_mapping(payload["evidence"], "evidence")
    elif contract_name == "TradePlan":
        _require_text(payload["event_id"], "event_id")
        _require_mapping(payload["entry"], "entry")
        _require_mapping(payload["stop"], "stop")
        _require_text(payload["execution_policy_version"], "execution_policy_version")
        _require_text(payload["status"], "status")
    elif contract_name == "OpportunityEvent":
        _require_text(payload["symbol"], "symbol")
        _require_text(payload["gate_event_id"], "gate_event_id")
        _require_mapping(payload["model_assessments"], "model_assessments")
    elif contract_name == "ExperimentRun":
        _require_text(payload["status"], "status")
        _require_mapping(payload["evidence_window"], "evidence_window")
        if not isinstance(payload["input_refs"], (list, Mapping)):
            raise ContractError("input_refs must be a list or object")
        if not isinstance(payload["result_refs"], (list, Mapping)):
            raise ContractError("result_refs must be a list or object")

    if contract_name == "ReleaseManifest":
        files = payload["files"]
        if not isinstance(files, list) or not files:
            raise ContractError("ReleaseManifest files must be a non-empty list")
        seen_paths: set[str] = set()
        required = {
            "path", "contract_types", "schema_version",
            "source_version", "temporal_class", "size_bytes", "sha256", "required", "roles",
        }
        for entry in files:
            if not isinstance(entry, Mapping):
                raise ContractError("ReleaseManifest file entry must be an object")
            missing_entry = sorted(required - entry.keys())
            if missing_entry:
                raise ContractError(f"manifest file entry missing: {', '.join(missing_entry)}")
            path = _require_safe_relative_path(entry["path"])
            if path in seen_paths:
                raise ContractError("manifest file paths must be unique")
            seen_paths.add(path)
            contract_types = entry["contract_types"]
            if (
                not isinstance(contract_types, list)
                or not contract_types
                or any(name not in CONTRACT_REQUIRED for name in contract_types)
                or len(set(contract_types)) != len(contract_types)
            ):
                raise ContractError("manifest entry contract_types are invalid")
            _require_semver(entry["schema_version"], "manifest entry schema_version")
            entry_adapter = entry.get("adapter_version")
            if entry_adapter is not None and (
                not isinstance(entry_adapter, str)
                or not entry_adapter.startswith("legacy-adapter-")
            ):
                raise ContractError("manifest entry adapter_version is invalid")
            if not isinstance(entry["source_version"], Mapping) or not entry["source_version"]:
                raise ContractError("manifest entry source_version is missing")
            _canonical({"source_version": dict(entry["source_version"])})
            _require_bool(entry["required"], "manifest entry required")
            temporal_class = entry["temporal_class"]
            if temporal_class == "daily_snapshot":
                if "as_of" not in entry or "future_data_used" not in entry:
                    raise ContractError("daily snapshot lacks date or future-data evidence")
                _require_date(entry["as_of"], "manifest file as_of")
                if entry["as_of"] != payload["as_of"]:
                    raise ContractError("manifest file date does not match release date")
                if entry["future_data_used"] is not False:
                    raise ContractError("daily snapshot future_data_used must be false")
            elif temporal_class == "versioned_config":
                if not isinstance(entry.get("registry_version"), str) or not entry["registry_version"].strip():
                    raise ContractError("versioned config lacks registry_version")
                if "as_of" in entry or "future_data_used" in entry:
                    raise ContractError("versioned config must not fabricate daily fields")
            elif temporal_class == "research_summary":
                if (
                    not isinstance(entry.get("coverage_end"), str)
                    or not isinstance(entry.get("source_experiment"), str)
                    or not entry["source_experiment"].strip()
                ):
                    raise ContractError("research summary lacks coverage or source experiment")
                if known_experiment_ids is None:
                    raise ContractError("research summary requires injected authoritative experiment IDs")
                if entry["source_experiment"] not in known_experiment_ids:
                    raise ContractError("research summary source experiment does not exist")
                _require_date(entry["coverage_end"], "research coverage_end")
                if entry["coverage_end"] > payload["as_of"]:
                    raise ContractError("research summary coverage ends after release")
                if entry.get("prohibited_uses") != ["scan", "score", "rank"]:
                    raise ContractError("research summary prohibited uses are not frozen")
                if "as_of" in entry or "future_data_used" in entry:
                    raise ContractError("research summary must not fabricate daily fields")
            else:
                raise ContractError(f"unknown temporal_class: {temporal_class}")
            if (
                isinstance(entry["size_bytes"], bool)
                or not isinstance(entry["size_bytes"], int)
                or entry["size_bytes"] < 0
            ):
                raise ContractError("manifest file size is invalid")
            if not re.fullmatch(r"[0-9a-f]{64}", str(entry["sha256"])):
                raise ContractError("manifest file sha256 is invalid")
            roles = entry["roles"]
            if (
                not isinstance(roles, list)
                or not roles
                or len(set(roles)) != len(roles)
                or not set(roles) <= {"web", "discord", "audit"}
            ):
                raise ContractError("manifest file roles are invalid")
        if not allow_partial_manifest and seen_paths != FROZEN_RELEASE_NAMES:
            missing = sorted(FROZEN_RELEASE_NAMES - seen_paths)
            extra = sorted(seen_paths - FROZEN_RELEASE_NAMES)
            raise ContractError(f"manifest membership mismatch; missing={missing}, extra={extra}")
        canonical_files = sorted(files, key=lambda item: str(item["path"]))
        expected_release_id = "sha256:" + hashlib.sha256(
            _canonical({"as_of": payload["as_of"], "files": canonical_files})
        ).hexdigest()
        if payload["release_id"] != expected_release_id:
            raise ContractError("release_id does not match canonical manifest entries")


def validate_contracts(items: Iterable[tuple[str, Mapping[str, Any]]]) -> None:
    """Validate a collection, including stable-ID and event uniqueness rules."""

    seen_ids: set[tuple[str, str]] = set()
    opportunity_keys: set[tuple[str, str, str]] = set()
    for contract_name, payload in items:
        validate_contract(contract_name, payload)
        identity = (contract_name, str(payload[ID_FIELDS[contract_name]]))
        if identity in seen_ids:
            raise ContractError(f"duplicate stable ID: {identity[1]}")
        seen_ids.add(identity)
        if contract_name == "OpportunityEvent":
            gate_version = str(payload.get("gate_policy_version", "unknown"))
            key = (str(payload["symbol"]), str(payload["signal_date"]), gate_version)
            if key in opportunity_keys:
                raise ContractError("same symbol/day/gate policy produced two opportunity events")
            opportunity_keys.add(key)
