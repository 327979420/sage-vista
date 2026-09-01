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

from .policies import ADJUSTMENT_POLICY


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
    "GateScanAudit": {
        "scan_audit_id", "scan_batch_id", "gate_policy_version", "path_status",
        "input_identity", "input_count", "gate_event_created_count",
        "baseline_passed_count", "baseline_failed_count", "non_event_reason_counts",
        "audit_status", "reason_codes",
    },
    "TechnicalEvidence": {"evidence_id", "factor_id", "factor_version", "timeframe", "evidence_date", "available"},
    "ModelAssessment": {"assessment_id", "gate_event_id", "model_id", "model_version", "eligible"},
    "ContextSnapshot": {"context_id", "context_type", "status", "evidence"},
    "ScoreResult": {
        "score_result_id", "instrument_id", "gate_event_id", "model_assessment_id",
        "context_snapshot_id", "score_policy_version", "total_score", "status",
    },
    "RankingSnapshot": {
        "ranking_snapshot_id", "ranking_role", "score_policy_version",
        "ranking_policy_version", "authority_policy_version", "ranked_entries",
        "excluded_entries", "selected_entries",
    },
    "TradePlan": {"plan_id", "event_id", "entry", "stop", "execution_policy_version", "status"},
    "ExitState": {
        "exit_state_id", "plan_id", "plan", "previous_exit_state_id",
        "market_data_fingerprint", "holding_sessions", "state",
        "exit_policy_version", "exit_policy_fingerprint",
    },
    "OpportunityEvent": {"event_id", "symbol", "signal_date", "gate_event_id", "model_assessments"},
    "ReleaseManifest": {"release_id", "files"},
    "ExperimentRun": {"experiment_id", "status", "evidence_window", "input_refs", "result_refs"},
}

ID_FIELDS = {
    "MarketDataSnapshot": "snapshot_id",
    "UniverseSnapshot": "universe_id",
    "GateEvent": "gate_event_id",
    "GateScanAudit": "scan_audit_id",
    "TechnicalEvidence": "evidence_id",
    "ModelAssessment": "assessment_id",
    "ContextSnapshot": "context_id",
    "ScoreResult": "score_result_id",
    "RankingSnapshot": "ranking_snapshot_id",
    "TradePlan": "plan_id",
    "ExitState": "exit_state_id",
    "OpportunityEvent": "event_id",
    "ReleaseManifest": "release_id",
    "ExperimentRun": "experiment_id",
}

CONTRACT_SUPPORTED_MAJORS = {
    name: (
        {2, 3} if name == "UniverseSnapshot"
        else {1, 2} if name == "GateEvent"
        else {1, 2} if name in {
            "TechnicalEvidence", "ModelAssessment", "ContextSnapshot",
            "ScoreResult", "RankingSnapshot", "TradePlan",
        }
        else {2} if name == "ExitState"
        else {SUPPORTED_MAJOR}
    )
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

    def plain(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {key: plain(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [plain(child) for child in item]
        return item

    try:
        return json.dumps(
            plain(value),
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
    allowed = {SUPPORTED_MAJOR} if supported_majors is None else supported_majors
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
        "GateScanAudit": ("gate-audit:",),
        "TechnicalEvidence": ("evidence:",),
        "ModelAssessment": ("assessment:",),
        "ContextSnapshot": ("context:",),
        "ScoreResult": ("score:",),
        "RankingSnapshot": ("ranking:",),
        "TradePlan": ("plan:",),
        "ExitState": ("exit-state:",),
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
        major = int(str(payload["schema_version"]).split(".", 1)[0])
        symbol = _require_text(payload["symbol"], "symbol")
        gate_policy = _require_text(payload["gate_policy_version"], "gate_policy_version")
        _require_bool(payload["passed"], "passed")
        if major == 1:
            expected = f"gate:{symbol}:{payload['signal_date']}:{gate_policy}"
            if stable_id != expected:
                raise ContractError("gate_event_id does not match symbol/date/gate policy")
        else:
            required_v2 = {
                "event_content_fingerprint", "logical_signal_id", "supersedes_event_id",
                "instrument_id", "path_status", "input_identity", "baseline_checks",
                "baseline_passed", "baseline_reason_codes", "shadow_assessment", "bias_labels",
            }
            missing_v2 = sorted(required_v2 - payload.keys())
            if missing_v2:
                raise ContractError(f"GateEvent 2.x missing required fields: {', '.join(missing_v2)}")
            if not re.fullmatch(r"gate:sha256:[0-9a-f]{64}", stable_id):
                raise ContractError("GateEvent 2.x gate_event_id is invalid")
            if not re.fullmatch(r"gate-signal:sha256:[0-9a-f]{64}", str(payload["logical_signal_id"])):
                raise ContractError("logical_signal_id is invalid")
            if not re.fullmatch(r"instrument:sha256:[0-9a-f]{64}", str(payload["instrument_id"])):
                raise ContractError("instrument_id is invalid")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(payload["event_content_fingerprint"])):
                raise ContractError("event_content_fingerprint is invalid")
            supersedes = payload["supersedes_event_id"]
            if supersedes is not None and not re.fullmatch(r"gate:sha256:[0-9a-f]{64}", str(supersedes)):
                raise ContractError("supersedes_event_id is invalid")
            path_status = payload["path_status"]
            if path_status not in {"formal", "legacy"}:
                raise ContractError("GateEvent path_status must be formal or legacy")
            identity = _require_mapping(payload["input_identity"], "input_identity")
            for field, prefix in (("universe_id", "universe:"), ("market_snapshot_id", "market:")):
                if not _require_text(identity.get(field), f"input_identity.{field}").startswith(prefix):
                    raise ContractError(f"input_identity.{field} has an invalid prefix")
            if dict(_require_mapping(identity.get("adjustment_policy"), "adjustment_policy")) != ADJUSTMENT_POLICY:
                raise ContractError("GateEvent adjustment_policy must equal the M02 policy")
            baseline_passed = _require_bool(payload["baseline_passed"], "baseline_passed")
            if payload["passed"] != baseline_passed:
                raise ContractError("passed must equal baseline_passed")
            checks = _require_mapping(payload["baseline_checks"], "baseline_checks")
            required_checks = {
                "data_integrity", "tradability_liquidity", "exact_daily_macd_cross",
                "legacy_long_trend_equivalence",
            }
            if set(checks) != required_checks or any(
                not isinstance(checks[name], Mapping)
                or checks[name].get("status") not in {"passed", "failed"}
                for name in required_checks
            ):
                raise ContractError("GateEvent baseline_checks are incomplete or invalid")
            if not isinstance(payload["baseline_reason_codes"], (list, tuple)):
                raise ContractError("baseline_reason_codes must be a list")
            shadow = _require_mapping(payload["shadow_assessment"], "shadow_assessment")
            if shadow.get("production_effect") is not False:
                raise ContractError("shadow_assessment.production_effect must be false")
            for field in (
                "shadow_fact_schema_version", "local_structure", "multi_year_drawdown",
                "monthly_state", "weekly_state", "supply_risk",
            ):
                if field not in shadow:
                    raise ContractError(f"shadow_assessment missing {field}")
            if shadow.get("long_term_state") not in {
                "uptrend_pullback", "long_base_reversal", "broad_range",
                "structural_damage", "unavailable",
            }:
                raise ContractError("shadow_assessment.long_term_state is invalid")
            biases = payload["bias_labels"]
            if (
                not isinstance(biases, (list, tuple))
                or (path_status == "formal" and biases)
                or (path_status == "legacy" and not biases)
            ):
                raise ContractError("GateEvent bias_labels do not match path_status")
            identity_evidence = {
                "schema_major": 2,
                "instrument_id": payload["instrument_id"],
                "signal_date": payload["signal_date"],
                "gate_policy_version": gate_policy,
                "path_status": path_status,
                "universe_id": identity["universe_id"],
                "market_snapshot_id": identity["market_snapshot_id"],
                "adjustment_policy": dict(identity["adjustment_policy"]),
            }
            expected = "gate:sha256:" + hashlib.sha256(_canonical(identity_evidence)).hexdigest()
            if stable_id != expected:
                raise ContractError("gate_event_id does not match canonical M03 identity")
            logical_evidence = dict(identity_evidence)
            del logical_evidence["market_snapshot_id"]
            expected_logical = "gate-signal:sha256:" + hashlib.sha256(
                _canonical(logical_evidence)
            ).hexdigest()
            if payload["logical_signal_id"] != expected_logical:
                raise ContractError("logical_signal_id does not match canonical M03 identity")
            semantic = {
                key: value for key, value in payload.items()
                if key not in {"generated_at", "event_content_fingerprint"}
            }
            expected_content = "sha256:" + hashlib.sha256(_canonical(semantic)).hexdigest()
            if payload["event_content_fingerprint"] != expected_content:
                raise ContractError("event_content_fingerprint does not match GateEvent facts")
            revision = payload.get("market_revision_evidence")
            if supersedes is not None:
                revision = _require_mapping(revision, "market_revision_evidence")
                if revision.get("to_market_snapshot_id") != identity["market_snapshot_id"]:
                    raise ContractError("market revision evidence does not bind replacement snapshot")
                if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(revision.get("revision_id"))):
                    raise ContractError("market revision evidence has an invalid revision_id")
    elif contract_name == "GateScanAudit":
        if not re.fullmatch(r"gate-audit:sha256:[0-9a-f]{64}", stable_id):
            raise ContractError("scan_audit_id is invalid")
        _require_text(payload["scan_batch_id"], "scan_batch_id")
        _require_text(payload["gate_policy_version"], "gate_policy_version")
        if payload["path_status"] not in {"formal", "legacy"}:
            raise ContractError("GateScanAudit path_status must be formal or legacy")
        identity = _require_mapping(payload["input_identity"], "input_identity")
        for field in (
            "input_count", "gate_event_created_count", "baseline_passed_count",
            "baseline_failed_count",
        ):
            value = payload[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ContractError(f"{field} must be a non-negative integer")
        counts = _require_mapping(payload["non_event_reason_counts"], "non_event_reason_counts")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts.values()):
            raise ContractError("non_event_reason_counts must contain non-negative integers")
        _require_text(payload["audit_status"], "audit_status")
        if not isinstance(payload["reason_codes"], (list, tuple)):
            raise ContractError("reason_codes must be a list")
        if payload["baseline_passed_count"] + payload["baseline_failed_count"] != payload["gate_event_created_count"]:
            raise ContractError("GateScanAudit baseline counts do not match created events")
        if sum(counts.values()) + payload["gate_event_created_count"] != payload["input_count"]:
            raise ContractError("GateScanAudit event and non-event counts do not match input_count")
        audit_identity = {
            "as_of": payload["as_of"],
            "scan_batch_id": payload["scan_batch_id"],
            "gate_policy_version": payload["gate_policy_version"],
            "path_status": payload["path_status"],
            "universe_id": identity.get("universe_id"),
            "market_snapshot_id": identity.get("market_snapshot_id"),
            "adjustment_policy": identity.get("adjustment_policy"),
        }
        expected_audit = "gate-audit:sha256:" + hashlib.sha256(
            _canonical(audit_identity)
        ).hexdigest()
        if stable_id != expected_audit:
            raise ContractError("scan_audit_id does not match canonical M03 identity")
    elif contract_name == "TechnicalEvidence":
        major = int(str(payload["schema_version"]).split(".", 1)[0])
        _require_text(payload["factor_id"], "factor_id")
        if not isinstance(payload["factor_version"], str) or not SEMVER.fullmatch(payload["factor_version"]):
            raise ContractError("factor_version must be MAJOR.MINOR.PATCH")
        _require_text(payload["timeframe"], "timeframe")
        _require_date(payload["evidence_date"], "evidence_date")
        if payload["evidence_date"] > payload["as_of"]:
            raise ContractError("TechnicalEvidence evidence_date cannot be after as_of")
        _require_bool(payload["available"], "available")
        if major == 2:
            required_v2 = {
                "evidence_content_fingerprint", "gate_event_id", "instrument_id",
                "path_status", "universe_id", "market_snapshot_id",
                "adjustment_policy", "registry_version", "detector_policy_version",
                "family", "source_kind", "raw_hit", "qualified_hit", "blocked_by",
                "recent_hit", "latest_hit_date", "bars_since_hit", "value",
                "evidence", "lookahead_audit", "bias_labels",
            }
            missing_v2 = sorted(required_v2 - payload.keys())
            if missing_v2:
                raise ContractError(
                    f"TechnicalEvidence 2.x missing required fields: {', '.join(missing_v2)}"
                )
            if not re.fullmatch(r"evidence:sha256:[0-9a-f]{64}", stable_id):
                raise ContractError("TechnicalEvidence 2.x evidence_id is invalid")
            for field, pattern in (
                ("gate_event_id", r"gate:sha256:[0-9a-f]{64}"),
                ("instrument_id", r"instrument:sha256:[0-9a-f]{64}"),
                ("universe_id", r"universe:sha256:[0-9a-f]{64}"),
                ("market_snapshot_id", r"market:sha256:[0-9a-f]{64}"),
            ):
                if not re.fullmatch(pattern, str(payload[field])):
                    raise ContractError(f"TechnicalEvidence {field} is invalid")
            if dict(_require_mapping(payload["adjustment_policy"], "adjustment_policy")) != ADJUSTMENT_POLICY:
                raise ContractError("TechnicalEvidence adjustment_policy must equal the M02 policy")
            if not isinstance(payload["registry_version"], str) or not SEMVER.fullmatch(payload["registry_version"]):
                raise ContractError("registry_version must be MAJOR.MINOR.PATCH")
            _require_text(payload["detector_policy_version"], "detector_policy_version")
            _require_text(payload["family"], "family")
            if payload["path_status"] not in {"formal", "legacy"}:
                raise ContractError("TechnicalEvidence path_status must be formal or legacy")
            if payload["source_kind"] not in {"gate_reference", "factor_detector"}:
                raise ContractError("TechnicalEvidence source_kind is invalid")
            raw_hit = _require_bool(payload["raw_hit"], "raw_hit")
            qualified_hit = _require_bool(payload["qualified_hit"], "qualified_hit")
            _require_bool(payload["recent_hit"], "recent_hit")
            if qualified_hit and not raw_hit:
                raise ContractError("qualified_hit cannot be true when raw_hit is false")
            blocked_by = payload["blocked_by"]
            if (
                not isinstance(blocked_by, (list, tuple))
                or any(not isinstance(item, str) or not item for item in blocked_by)
                or len(blocked_by) != len(set(blocked_by))
            ):
                raise ContractError("blocked_by must contain unique factor IDs")
            if blocked_by and qualified_hit:
                raise ContractError("blocked evidence cannot be a qualified hit")
            latest_hit = payload["latest_hit_date"]
            if latest_hit is not None:
                _require_date(latest_hit, "latest_hit_date")
                if latest_hit > payload["as_of"]:
                    raise ContractError("latest_hit_date cannot be after as_of")
            bars_since = payload["bars_since_hit"]
            if bars_since is not None and (
                isinstance(bars_since, bool) or not isinstance(bars_since, int) or bars_since < 0
            ):
                raise ContractError("bars_since_hit must be a non-negative integer or null")
            _require_mapping(payload["evidence"], "evidence")
            audit = _require_mapping(payload["lookahead_audit"], "lookahead_audit")
            if audit.get("future_data_used") is not False:
                raise ContractError("TechnicalEvidence lookahead audit must fail closed")
            biases = payload["bias_labels"]
            if (
                not isinstance(biases, (list, tuple))
                or (payload["path_status"] == "formal" and biases)
                or (payload["path_status"] == "legacy" and not biases)
            ):
                raise ContractError("TechnicalEvidence bias_labels do not match path_status")
            identity = {
                "gate_event_id": payload["gate_event_id"],
                "instrument_id": payload["instrument_id"],
                "as_of": payload["as_of"],
                "path_status": payload["path_status"],
                "universe_id": payload["universe_id"],
                "market_snapshot_id": payload["market_snapshot_id"],
                "adjustment_policy": dict(payload["adjustment_policy"]),
                "registry_version": payload["registry_version"],
                "detector_policy_version": payload["detector_policy_version"],
                "factor_id": payload["factor_id"],
                "factor_version": payload["factor_version"],
            }
            expected_id = "evidence:sha256:" + hashlib.sha256(_canonical(identity)).hexdigest()
            if stable_id != expected_id:
                raise ContractError("evidence_id does not match canonical M04 identity")
            semantic = {
                key: value for key, value in payload.items()
                if key not in {"generated_at", "evidence_content_fingerprint"}
            }
            expected_content = "sha256:" + hashlib.sha256(_canonical(semantic)).hexdigest()
            if payload["evidence_content_fingerprint"] != expected_content:
                raise ContractError("TechnicalEvidence content fingerprint does not match facts")
    elif contract_name == "ModelAssessment":
        _require_text(payload["gate_event_id"], "gate_event_id")
        _require_text(payload["model_id"], "model_id")
        _require_text(payload["model_version"], "model_version")
        _require_bool(payload["eligible"], "eligible")
        major = int(str(payload["schema_version"]).split(".", 1)[0])
        if major == 2:
            required_v2 = {
                "assessment_content_fingerprint", "instrument_id", "path_status",
                "input_identity", "evidence_batch_id", "technical_evidence_ids",
                "status", "matched_facts", "missing_facts", "risk_facts",
                "warnings", "model_specific_facts",
                "model_specific_facts_fingerprint", "production_effect", "bias_labels",
            }
            missing_v2 = sorted(required_v2 - payload.keys())
            if missing_v2:
                raise ContractError(
                    f"ModelAssessment 2.x missing required fields: {', '.join(missing_v2)}"
                )
            if not re.fullmatch(r"assessment:sha256:[0-9a-f]{64}", stable_id):
                raise ContractError("ModelAssessment 2.x assessment_id is invalid")
            if not re.fullmatch(r"gate:sha256:[0-9a-f]{64}", str(payload["gate_event_id"])):
                raise ContractError("ModelAssessment gate_event_id is invalid")
            if not re.fullmatch(r"instrument:sha256:[0-9a-f]{64}", str(payload["instrument_id"])):
                raise ContractError("ModelAssessment instrument_id is invalid")
            if not SEMVER.fullmatch(str(payload["model_version"])):
                raise ContractError("ModelAssessment model_version must be MAJOR.MINOR.PATCH")
            if payload["path_status"] != "formal":
                raise ContractError("ModelAssessment 2.x must use the formal path")
            identity = _require_mapping(payload["input_identity"], "input_identity")
            for field, pattern in (
                ("universe_id", r"universe:sha256:[0-9a-f]{64}"),
                ("market_snapshot_id", r"market:sha256:[0-9a-f]{64}"),
            ):
                if not re.fullmatch(pattern, str(identity.get(field))):
                    raise ContractError(f"ModelAssessment {field} is invalid")
            if dict(_require_mapping(identity.get("adjustment_policy"), "adjustment_policy")) != ADJUSTMENT_POLICY:
                raise ContractError("ModelAssessment adjustment_policy must equal the M02 policy")
            _require_text(payload["evidence_batch_id"], "evidence_batch_id")
            evidence_ids = payload["technical_evidence_ids"]
            if (
                not isinstance(evidence_ids, (list, tuple))
                or not evidence_ids
                or any(
                    not re.fullmatch(r"evidence:sha256:[0-9a-f]{64}", str(item))
                    for item in evidence_ids
                )
                or list(evidence_ids) != sorted(set(evidence_ids))
            ):
                raise ContractError("technical_evidence_ids must be sorted unique formal evidence IDs")
            _require_text(payload["status"], "status")
            for field in ("matched_facts", "missing_facts", "risk_facts"):
                values = payload[field]
                if not isinstance(values, (list, tuple)) or any(
                    not isinstance(item, Mapping) for item in values
                ):
                    raise ContractError(f"ModelAssessment {field} must be a list of evidence references")
            warnings = payload["warnings"]
            if not isinstance(warnings, (list, tuple)) or any(
                not isinstance(item, str) or not item for item in warnings
            ):
                raise ContractError("ModelAssessment warnings must be text")
            model_facts = _require_mapping(payload["model_specific_facts"], "model_specific_facts")
            expected_model_facts = "sha256:" + hashlib.sha256(_canonical(model_facts)).hexdigest()
            if payload["model_specific_facts_fingerprint"] != expected_model_facts:
                raise ContractError("model-specific fact fingerprint does not match facts")
            if _require_bool(payload["production_effect"], "production_effect") is not False:
                raise ContractError("ModelAssessment 2.x must remain shadow-only")
            biases = payload["bias_labels"]
            if (
                not isinstance(biases, (list, tuple))
                or biases
            ):
                raise ContractError("formal ModelAssessment cannot carry legacy bias labels")
            assessment_identity = {
                "gate_event_id": payload["gate_event_id"],
                "instrument_id": payload["instrument_id"],
                "as_of": payload["as_of"],
                "path_status": payload["path_status"],
                "input_identity": dict(identity),
                "model_id": payload["model_id"],
                "model_version": payload["model_version"],
                "evidence_batch_id": payload["evidence_batch_id"],
                "technical_evidence_ids": list(evidence_ids),
                "model_specific_facts_fingerprint": payload["model_specific_facts_fingerprint"],
            }
            expected_id = "assessment:sha256:" + hashlib.sha256(
                _canonical(assessment_identity)
            ).hexdigest()
            if stable_id != expected_id:
                raise ContractError("assessment_id does not match canonical M05 identity")
            semantic = {
                key: value for key, value in payload.items()
                if key not in {"generated_at", "assessment_content_fingerprint"}
            }
            expected_content = "sha256:" + hashlib.sha256(_canonical(semantic)).hexdigest()
            if payload["assessment_content_fingerprint"] != expected_content:
                raise ContractError("ModelAssessment content fingerprint does not match facts")
    elif contract_name == "ContextSnapshot":
        _require_text(payload["context_type"], "context_type")
        _require_text(payload["status"], "status")
        _require_mapping(payload["evidence"], "evidence")
        major = int(str(payload["schema_version"]).split(".", 1)[0])
        if major == 2:
            required_v2 = {
                "context_content_fingerprint", "instrument_id", "path_status",
                "input_identity", "gate_event_id", "technical_evidence_batch_id",
                "model_assessment_batch_id", "technical_evidence_ids",
                "model_assessment_ids", "registry_version", "membership_links",
                "production_effect", "bias_labels",
            }
            missing_v2 = sorted(required_v2 - payload.keys())
            if missing_v2:
                raise ContractError(
                    f"ContextSnapshot 2.x missing required fields: {', '.join(missing_v2)}"
                )
            if payload["context_type"] != "market_industry":
                raise ContractError("ContextSnapshot 2.x context_type must be market_industry")
            if payload["path_status"] != "formal":
                raise ContractError("ContextSnapshot 2.x must use the formal path")
            if _require_bool(payload["production_effect"], "production_effect") is not False:
                raise ContractError("ContextSnapshot 2.x must remain shadow-only")
            if not re.fullmatch(r"context:sha256:[0-9a-f]{64}", stable_id):
                raise ContractError("ContextSnapshot 2.x context_id is invalid")
            if not re.fullmatch(
                r"sha256:[0-9a-f]{64}", str(payload["context_content_fingerprint"])
            ):
                raise ContractError("ContextSnapshot content fingerprint is invalid")
            if not re.fullmatch(
                r"instrument:sha256:[0-9a-f]{64}", str(payload["instrument_id"])
            ):
                raise ContractError("ContextSnapshot instrument_id is invalid")
            identity = _require_mapping(payload["input_identity"], "input_identity")
            for field, prefix in (
                ("stock_universe_id", "universe:"),
                ("stock_market_snapshot_id", "market:"),
                ("etf_universe_id", "universe:"),
                ("etf_market_snapshot_id", "market:"),
            ):
                if not _require_text(identity.get(field), f"input_identity.{field}").startswith(prefix):
                    raise ContractError(f"input_identity.{field} has an invalid prefix")
            if dict(_require_mapping(identity.get("adjustment_policy"), "adjustment_policy")) != ADJUSTMENT_POLICY:
                raise ContractError("ContextSnapshot adjustment_policy must equal the M02 policy")
            if not _require_text(payload["gate_event_id"], "gate_event_id").startswith("gate:"):
                raise ContractError("ContextSnapshot gate_event_id is invalid")
            for field in ("technical_evidence_ids", "model_assessment_ids", "membership_links"):
                value = payload[field]
                if not isinstance(value, (list, tuple)):
                    raise ContractError(f"ContextSnapshot {field} must be a list")
            if len(payload["membership_links"]) != len({
                item.get("etf_id") for item in payload["membership_links"]
                if isinstance(item, Mapping)
            }):
                raise ContractError("ContextSnapshot membership links contain duplicate ETFs")
            biases = payload["bias_labels"]
            if not isinstance(biases, (list, tuple)) or biases:
                raise ContractError("formal ContextSnapshot cannot carry legacy bias labels")
    elif contract_name == "ScoreResult":
        _require_text(payload["instrument_id"], "instrument_id")
        _require_text(payload["gate_event_id"], "gate_event_id")
        _require_text(payload["model_assessment_id"], "model_assessment_id")
        _require_text(payload["context_snapshot_id"], "context_snapshot_id")
        _require_text(payload["score_policy_version"], "score_policy_version")
        _require_text(payload["status"], "status")
        major = int(str(payload["schema_version"]).split(".", 1)[0])
        if major == 2:
            required_v2 = {
                "score_content_fingerprint", "path_status", "input_identity",
                "technical_evidence_batch_id", "technical_evidence_ids",
                "score_policy_fingerprint", "score_input_fingerprint", "components",
                "metrics", "warnings", "missing_facts", "exclusion_reason",
                "context_reference",
            }
            missing_v2 = sorted(required_v2 - payload.keys())
            if missing_v2:
                raise ContractError(
                    f"ScoreResult 2.x missing required fields: {', '.join(missing_v2)}"
                )
            if payload["path_status"] != "formal":
                raise ContractError("ScoreResult 2.x must use the formal path")
            for field, pattern in (
                ("score_result_id", r"score:sha256:[0-9a-f]{64}"),
                ("score_content_fingerprint", r"sha256:[0-9a-f]{64}"),
                ("score_input_fingerprint", r"sha256:[0-9a-f]{64}"),
                ("score_policy_fingerprint", r"sha256:[0-9a-f]{64}"),
                ("instrument_id", r"instrument:sha256:[0-9a-f]{64}"),
                ("gate_event_id", r"gate:sha256:[0-9a-f]{64}"),
                ("model_assessment_id", r"assessment:sha256:[0-9a-f]{64}"),
                ("context_snapshot_id", r"context:sha256:[0-9a-f]{64}"),
            ):
                if not re.fullmatch(pattern, str(payload[field])):
                    raise ContractError(f"ScoreResult {field} is invalid")
            _require_semver(payload["score_policy_version"], "score_policy_version", supported_majors={1})
            identity = _require_mapping(payload["input_identity"], "input_identity")
            for field, prefix in (
                ("universe_id", "universe:"),
                ("market_snapshot_id", "market:"),
            ):
                if not _require_text(identity.get(field), f"input_identity.{field}").startswith(prefix):
                    raise ContractError(f"ScoreResult input_identity.{field} is invalid")
            if dict(_require_mapping(identity.get("adjustment_policy"), "adjustment_policy")) != ADJUSTMENT_POLICY:
                raise ContractError("ScoreResult adjustment_policy must equal the M02 policy")
            evidence_ids = payload["technical_evidence_ids"]
            if (
                not isinstance(evidence_ids, (list, tuple))
                or not evidence_ids
                or list(evidence_ids) != sorted(set(evidence_ids))
                or any(not re.fullmatch(r"evidence:sha256:[0-9a-f]{64}", str(item)) for item in evidence_ids)
            ):
                raise ContractError("ScoreResult technical_evidence_ids must be sorted unique formal IDs")
            for field in ("components", "warnings", "missing_facts"):
                if not isinstance(payload[field], (list, tuple)):
                    raise ContractError(f"ScoreResult {field} must be a list")
            if any(not isinstance(item, Mapping) for item in payload["components"]):
                raise ContractError("ScoreResult components must be objects")
            if any(not isinstance(item, str) or not item for item in (*payload["warnings"], *payload["missing_facts"])):
                raise ContractError("ScoreResult warnings and missing_facts must be text")
            _require_mapping(payload["metrics"], "metrics")
            _require_mapping(payload["context_reference"], "context_reference")
            status = payload["status"]
            if status not in {"scored", "excluded", "unavailable"}:
                raise ContractError("ScoreResult status is invalid")
            total = payload["total_score"]
            if status == "scored":
                if isinstance(total, bool) or not isinstance(total, (int, float)):
                    raise ContractError("scored ScoreResult requires a numeric total_score")
            elif total is not None:
                raise ContractError("unscored ScoreResult total_score must be null")
            reason = payload["exclusion_reason"]
            if status == "scored" and reason is not None:
                raise ContractError("scored ScoreResult cannot have an exclusion reason")
            if status != "scored" and (not isinstance(reason, str) or not reason):
                raise ContractError("unscored ScoreResult requires an exclusion reason")
    elif contract_name == "RankingSnapshot":
        _require_text(payload["ranking_role"], "ranking_role")
        _require_text(payload["score_policy_version"], "score_policy_version")
        _require_text(payload["ranking_policy_version"], "ranking_policy_version")
        _require_text(payload["authority_policy_version"], "authority_policy_version")
        major = int(str(payload["schema_version"]).split(".", 1)[0])
        if major == 2:
            required_v2 = {
                "ranking_content_fingerprint", "path_status", "authority_scope",
                "input_identity", "score_policy_fingerprint", "ranking_policy_fingerprint",
                "authority_policy_fingerprint", "score_result_ids", "input_count",
                "score_results", "activation", "comparison_to_snapshot_id", "future_data_used",
            }
            missing_v2 = sorted(required_v2 - payload.keys())
            if missing_v2:
                raise ContractError(
                    f"RankingSnapshot 2.x missing required fields: {', '.join(missing_v2)}"
                )
            if payload["path_status"] != "formal":
                raise ContractError("RankingSnapshot 2.x must use the formal path")
            if payload["authority_scope"] != "complex_multifactor_main":
                raise ContractError("RankingSnapshot has an unknown authority scope")
            for field, pattern in (
                ("ranking_snapshot_id", r"ranking:sha256:[0-9a-f]{64}"),
                ("ranking_content_fingerprint", r"sha256:[0-9a-f]{64}"),
                ("score_policy_fingerprint", r"sha256:[0-9a-f]{64}"),
                ("ranking_policy_fingerprint", r"sha256:[0-9a-f]{64}"),
                ("authority_policy_fingerprint", r"sha256:[0-9a-f]{64}"),
            ):
                if not re.fullmatch(pattern, str(payload[field])):
                    raise ContractError(f"RankingSnapshot {field} is invalid")
            for field in ("score_policy_version", "ranking_policy_version", "authority_policy_version"):
                _require_semver(payload[field], field, supported_majors={1})
            role = payload["ranking_role"]
            if role not in {"shadow", "comparison", "authoritative"}:
                raise ContractError("RankingSnapshot ranking_role is invalid")
            activation = payload["activation"]
            comparison = payload["comparison_to_snapshot_id"]
            if role == "authoritative":
                activation = _require_mapping(activation, "activation")
                _require_date(activation.get("effective_from"), "activation.effective_from")
                _require_text(activation.get("activation_id"), "activation.activation_id")
                _require_text(activation.get("approval_ref"), "activation.approval_ref")
                if payload["as_of"] < activation["effective_from"]:
                    raise ContractError("authority policy is not effective for this date")
                if comparison is not None:
                    raise ContractError("authoritative ranking cannot be a comparison")
            elif activation is not None:
                raise ContractError("non-authoritative ranking cannot carry activation")
            if role == "comparison":
                if not isinstance(comparison, str) or not re.fullmatch(r"ranking:sha256:[0-9a-f]{64}", comparison):
                    raise ContractError("comparison ranking requires the original snapshot ID")
            elif comparison is not None:
                raise ContractError("only comparison rankings may reference an original snapshot")
            result_ids = payload["score_result_ids"]
            if (
                not isinstance(result_ids, (list, tuple))
                or list(result_ids) != sorted(set(result_ids))
                or any(not re.fullmatch(r"score:sha256:[0-9a-f]{64}", str(item)) for item in result_ids)
            ):
                raise ContractError("RankingSnapshot score_result_ids must be sorted unique IDs")
            if isinstance(payload["input_count"], bool) or not isinstance(payload["input_count"], int) or payload["input_count"] < 0:
                raise ContractError("RankingSnapshot input_count must be a non-negative integer")
            for field in ("ranked_entries", "excluded_entries", "selected_entries"):
                if not isinstance(payload[field], (list, tuple)) or any(not isinstance(item, Mapping) for item in payload[field]):
                    raise ContractError(f"RankingSnapshot {field} must contain objects")
            score_results = payload["score_results"]
            if not isinstance(score_results, (list, tuple)) or any(not isinstance(item, Mapping) for item in score_results):
                raise ContractError("RankingSnapshot score_results must contain objects")
            embedded_ids = [str(item.get("score_result_id")) for item in score_results]
            if sorted(embedded_ids) != list(result_ids) or len(embedded_ids) != len(set(embedded_ids)):
                raise ContractError("RankingSnapshot embedded score results do not match identities")
            for result in score_results:
                validate_contract("ScoreResult", result)
            ranked_ids = [str(item.get("score_result_id")) for item in payload["ranked_entries"]]
            excluded_ids = [str(item.get("score_result_id")) for item in payload["excluded_entries"]]
            selected_ids = [str(item.get("score_result_id")) for item in payload["selected_entries"]]
            if len(ranked_ids) != len(set(ranked_ids)) or len(excluded_ids) != len(set(excluded_ids)):
                raise ContractError("RankingSnapshot contains duplicate entries")
            if set(ranked_ids) & set(excluded_ids) or set(ranked_ids) | set(excluded_ids) != set(result_ids):
                raise ContractError("RankingSnapshot entries do not conserve score results")
            if len(ranked_ids) + len(excluded_ids) != payload["input_count"]:
                raise ContractError("RankingSnapshot input_count does not conserve entries")
            if selected_ids != ranked_ids[:len(selected_ids)]:
                raise ContractError("selected entries must be a strict ordered ranking prefix")
            if [item.get("rank") for item in payload["ranked_entries"]] != list(range(1, len(ranked_ids) + 1)):
                raise ContractError("RankingSnapshot ranks must be contiguous")
    elif contract_name == "TradePlan":
        _require_text(payload["event_id"], "event_id")
        _require_mapping(payload["entry"], "entry")
        _require_mapping(payload["stop"], "stop")
        _require_text(payload["execution_policy_version"], "execution_policy_version")
        _require_text(payload["status"], "status")
        if str(payload["schema_version"]).startswith("2."):
            required_v2 = {
                "plan_content_fingerprint", "signal_date", "entry_date", "path_status",
                "plan_role", "instrument_id", "ranking_snapshot_id", "score_result_id",
                "gate_event_id", "input_identity", "support_evidence_id",
                "technical_evidence_ids", "price_basis", "support", "target",
                "max_hold_sessions", "invalidation_conditions", "plan_policy_version",
                "plan_policy_fingerprint", "exit_policy_version",
                "exit_policy_fingerprint", "disabled_experiments",
            }
            missing_v2 = sorted(required_v2 - payload.keys())
            if missing_v2:
                raise ContractError(f"TradePlan 2.x missing required fields: {', '.join(missing_v2)}")
            _require_date(payload["signal_date"], "signal_date")
            _require_date(payload["entry_date"], "entry_date")
            if payload["entry_date"] <= payload["signal_date"]:
                raise ContractError("TradePlan entry must follow its signal date")
            for field in ("input_identity", "support", "target"):
                _require_mapping(payload[field], field)
            for field in ("plan_policy_version", "exit_policy_version"):
                _require_semver(payload[field], field, supported_majors={1})
            if not isinstance(payload["technical_evidence_ids"], (list, tuple)):
                raise ContractError("TradePlan technical evidence IDs must be a list")
    elif contract_name == "ExitState":
        _require_text(payload["plan_id"], "plan_id")
        _require_mapping(payload["plan"], "plan")
        _require_text(payload["market_data_fingerprint"], "market_data_fingerprint")
        _require_text(payload["state"], "state")
        _require_text(payload["exit_policy_version"], "exit_policy_version")
        _require_text(payload["exit_policy_fingerprint"], "exit_policy_fingerprint")
        if isinstance(payload["holding_sessions"], bool) or not isinstance(payload["holding_sessions"], int) or payload["holding_sessions"] < 0:
            raise ContractError("ExitState holding_sessions must be a non-negative integer")
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
            supported_majors = set.intersection(
                *(set(CONTRACT_SUPPORTED_MAJORS[name]) for name in contract_types)
            )
            if not supported_majors:
                raise ContractError(
                    "manifest entry contract_types have incompatible schema major versions"
                )
            _require_semver(
                entry["schema_version"],
                "manifest entry schema_version",
                supported_majors=supported_majors,
            )
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
