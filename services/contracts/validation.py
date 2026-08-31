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
        "universe_id", "members", "eligibility_rule_version", "effective_from",
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
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


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
    missing = sorted((COMMON_REQUIRED | CONTRACT_REQUIRED[contract_name]) - payload.keys())
    if missing:
        raise ContractError(f"{contract_name} missing required fields: {', '.join(missing)}")

    version = payload["schema_version"]
    match = SEMVER.fullmatch(version) if isinstance(version, str) else None
    if not match:
        raise ContractError("schema_version must be MAJOR.MINOR.PATCH")
    if int(match.group(1)) != SUPPORTED_MAJOR:
        raise ContractError(f"unknown schema major version: {match.group(1)}")

    _require_date(payload["as_of"], "as_of")
    _require_timestamp(payload["generated_at"])
    if not isinstance(payload["source_version"], Mapping) or not payload["source_version"]:
        raise ContractError("source_version must contain explicit source evidence")
    if payload["future_data_used"] is not False:
        raise ContractError("future_data_used must be the boolean false")

    adapter_version = payload.get("adapter_version")
    if adapter_version is not None and (
        not isinstance(adapter_version, str) or not adapter_version.startswith("legacy-adapter-")
    ):
        raise ContractError("adapter_version must identify a legacy adapter")

    stable_id = payload[ID_FIELDS[contract_name]]
    if not isinstance(stable_id, str) or not stable_id.strip():
        raise ContractError(f"{ID_FIELDS[contract_name]} must be a non-empty stable ID")

    if contract_name in {"GateEvent", "OpportunityEvent"}:
        _require_date(payload["signal_date"], "signal_date")
        if payload["signal_date"] != payload["as_of"]:
            raise ContractError("event signal_date must equal as_of")

    if contract_name == "ReleaseManifest":
        files = payload["files"]
        if not isinstance(files, list) or not files:
            raise ContractError("ReleaseManifest files must be a non-empty list")
        seen_paths: set[str] = set()
        required = {
            "path", "contract_types", "schema_version", "adapter_version",
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
            if not SEMVER.fullmatch(str(entry["schema_version"])):
                raise ContractError("manifest entry schema_version must be SemVer")
            if not str(entry["adapter_version"]).startswith("legacy-adapter-"):
                raise ContractError("manifest entry adapter_version is invalid")
            if not isinstance(entry["source_version"], Mapping) or not entry["source_version"]:
                raise ContractError("manifest entry source_version is missing")
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
            if not isinstance(entry["size_bytes"], int) or entry["size_bytes"] < 0:
                raise ContractError("manifest file size is invalid")
            if not re.fullmatch(r"[0-9a-f]{64}", str(entry["sha256"])):
                raise ContractError("manifest file sha256 is invalid")
            roles = entry["roles"]
            if not isinstance(roles, list) or not roles or not set(roles) <= {"web", "discord", "audit"}:
                raise ContractError("manifest file roles are invalid")
        if not allow_partial_manifest and seen_paths != FROZEN_RELEASE_NAMES:
            missing = sorted(FROZEN_RELEASE_NAMES - seen_paths)
            extra = sorted(seen_paths - FROZEN_RELEASE_NAMES)
            raise ContractError(f"manifest membership mismatch; missing={missing}, extra={extra}")
        expected_release_id = "sha256:" + hashlib.sha256(
            _canonical({"as_of": payload["as_of"], "files": files})
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
