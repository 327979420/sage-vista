"""Pure validation rules shared by M01 and later data modules.

The functions in this module perform no file, Git, network, or process I/O.  They
validate injected dictionaries so scanners, research and release preparation do
not grow separate interpretations of the same contract.
"""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import math
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
    "ForwardOutcome": {
        "forward_outcome_id", "logical_result_id", "run_id", "event_id",
        "instrument_id", "signal_date", "window_sessions", "status",
    },
    "TradeOutcome": {
        "trade_outcome_id", "logical_result_id", "run_id", "event_id",
        "instrument_id", "signal_date", "status",
    },
    "PortfolioRun": {
        "portfolio_run_id", "logical_result_id", "run_id", "status",
        "trade_outcome_refs",
    },
    "ResearchAggregate": {
        "research_aggregate_id", "logical_result_id", "run_id", "status",
        "result_refs",
    },
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
    "ForwardOutcome": "forward_outcome_id",
    "TradeOutcome": "trade_outcome_id",
    "PortfolioRun": "portfolio_run_id",
    "ResearchAggregate": "research_aggregate_id",
    "ReleaseManifest": "release_id",
    "SourceInventory": "inventory_id",
    "PublicationAuthorization": "authorization_id",
    "EvaluationSnapshot": "evaluation_snapshot_id",
    "PublicationReceipt": "receipt_id",
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
        else {1, 2} if name == "OpportunityEvent"
        else {2} if name in {
            "ForwardOutcome", "TradeOutcome", "PortfolioRun", "ResearchAggregate",
        }
        else {1, 2} if name == "ExperimentRun"
        else {SUPPORTED_MAJOR}
    )
    for name in CONTRACT_REQUIRED
}


def _stable_id_field(contract_name: str, payload: Mapping[str, Any]) -> str:
    """Return the version-aware stable ID without changing legacy contracts.

    ExperimentRun 1.x identifies a registered experiment.  M10 2.x identifies
    one exact execution with ``run_id``.  Keeping this decision here lets the
    shared collection validator detect duplicate runs without pretending an old
    experiment ID was already a run receipt.
    """

    if contract_name == "ExperimentRun" and str(payload.get("schema_version", "")).startswith("2."):
        return "run_id"
    return ID_FIELDS[contract_name]


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
    source_inventory_evidence: Mapping[str, Any] | None = None,
    publication_authorization_evidence: Mapping[str, Any] | None = None,
    evaluation_snapshot_evidence: Mapping[str, Any] | None = None,
    release_manifest_evidence: Mapping[str, Any] | None = None,
    publication_receipt_evidence: Mapping[str, Any] | None = None,
    current_pointer_evidence: Mapping[str, Any] | None = None,
) -> None:
    """Validate one canonical contract and fail closed on unknown evidence."""

    if contract_name == "CurrentPointer":
        _validate_current_pointer(payload, current_pointer_evidence)
        return
    if contract_name == "PublicationReceipt":
        _validate_publication_receipt(payload, publication_receipt_evidence)
        return
    if contract_name == "ReleaseManifest" and isinstance(payload, Mapping) and payload.get("schema_version") == "2.0.0":
        _validate_release_manifest_v2(payload, release_manifest_evidence)
        return
    if contract_name == "EvaluationSnapshot":
        _validate_evaluation_snapshot(payload, evaluation_snapshot_evidence)
        return
    if contract_name == "PublicationAuthorization":
        _validate_publication_authorization(payload, publication_authorization_evidence)
        return
    if contract_name == "SourceInventory":
        _validate_source_inventory(payload, source_inventory_evidence)
        return
    if contract_name not in CONTRACT_REQUIRED:
        raise ContractError(f"unknown contract: {contract_name}")
    if not isinstance(payload, Mapping):
        raise ContractError(f"{contract_name} payload must be an object")
    missing = sorted((COMMON_REQUIRED | CONTRACT_REQUIRED[contract_name]) - payload.keys())
    if missing:
        raise ContractError(f"{contract_name} missing required fields: {', '.join(missing)}")

    version_match = _require_semver(
        payload["schema_version"],
        "schema_version",
        supported_majors=CONTRACT_SUPPORTED_MAJORS[contract_name],
    )
    schema_major = int(version_match.group(1))
    if contract_name == "ExperimentRun" and schema_major == 2 and "run_id" not in payload:
        raise ContractError("ExperimentRun 2.x missing required field: run_id")

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

    stable_id_field = _stable_id_field(contract_name, payload)
    stable_id = _require_text(payload[stable_id_field], stable_id_field)

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
        "ForwardOutcome": ("forward-outcome:",),
        "TradeOutcome": ("trade-outcome:",),
        "PortfolioRun": ("portfolio-run:",),
        "ResearchAggregate": ("research-aggregate:",),
        "ReleaseManifest": ("sha256:",),
    }.get(contract_name)
    if allowed_prefixes is not None and not stable_id.startswith(allowed_prefixes):
        raise ContractError(f"{stable_id_field} has an invalid contract prefix")
    if contract_name == "ExperimentRun" and schema_major == 2 and not stable_id.startswith(
        "experiment-run:"
    ):
        raise ContractError("run_id has an invalid contract prefix")

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
        major = int(str(payload["schema_version"]).split(".", 1)[0])
        if major == 2:
            required_v2 = {
                "event_content_fingerprint", "instrument_id", "path_status",
                "event_role", "authority_scope", "ranking_snapshot_id",
                "ranking_content_fingerprint", "score_result_id", "rank",
                "selected", "input_identity", "gate_reference",
                "technical_reference", "context_reference", "score_reference",
                "policy_versions", "frozen_ranking",
            }
            missing_v2 = sorted(required_v2 - payload.keys())
            if missing_v2:
                raise ContractError(
                    f"OpportunityEvent 2.x missing required fields: {', '.join(missing_v2)}"
                )
            for field, pattern in (
                ("event_id", r"opportunity:sha256:[0-9a-f]{64}"),
                ("event_content_fingerprint", r"sha256:[0-9a-f]{64}"),
                ("instrument_id", r"instrument:sha256:[0-9a-f]{64}"),
                ("gate_event_id", r"gate:sha256:[0-9a-f]{64}"),
                ("ranking_snapshot_id", r"ranking:sha256:[0-9a-f]{64}"),
                ("ranking_content_fingerprint", r"sha256:[0-9a-f]{64}"),
                ("score_result_id", r"score:sha256:[0-9a-f]{64}"),
            ):
                if not re.fullmatch(pattern, str(payload[field])):
                    raise ContractError(f"OpportunityEvent {field} is invalid")
            if payload["path_status"] != "formal":
                raise ContractError("OpportunityEvent 2.x must use the formal path")
            if payload["event_role"] != "authoritative":
                raise ContractError("OpportunityEvent 2.x requires an authoritative ranking")
            if payload["authority_scope"] != "complex_multifactor_main":
                raise ContractError("OpportunityEvent authority_scope is invalid")
            if isinstance(payload["rank"], bool) or not isinstance(payload["rank"], int) or payload["rank"] < 1:
                raise ContractError("OpportunityEvent rank must be a positive integer")
            _require_bool(payload["selected"], "selected")
            identity = _require_mapping(payload["input_identity"], "input_identity")
            for field, prefix in (
                ("universe_id", "universe:"),
                ("market_snapshot_id", "market:"),
                ("technical_evidence_batch_id", "technical-evidence-batch:"),
                ("model_assessment_batch_id", "model-assessment-batch:"),
                ("context_batch_id", "context-batch:"),
                ("score_batch_id", "score-batch:"),
            ):
                if not _require_text(identity.get(field), f"input_identity.{field}").startswith(prefix):
                    raise ContractError(f"OpportunityEvent input_identity.{field} is invalid")
            if dict(_require_mapping(identity.get("adjustment_policy"), "adjustment_policy")) != ADJUSTMENT_POLICY:
                raise ContractError("OpportunityEvent adjustment_policy must equal the M02 policy")
            for field in (
                "gate_reference", "technical_reference", "model_assessments",
                "context_reference", "score_reference", "policy_versions",
                "frozen_ranking",
            ):
                _require_mapping(payload[field], field)
            root_identity = {
                "schema_major": 2,
                "authority_scope": payload["authority_scope"],
                "instrument_id": payload["instrument_id"],
                "signal_date": payload["signal_date"],
            }
            expected_id = "opportunity:" + "sha256:" + hashlib.sha256(
                _canonical(root_identity)
            ).hexdigest()
            if stable_id != expected_id:
                raise ContractError("OpportunityEvent id does not match its stable root")
            semantic = {
                key: value for key, value in payload.items()
                if key not in {"generated_at", "event_content_fingerprint"}
            }
            expected_content = "sha256:" + hashlib.sha256(_canonical(semantic)).hexdigest()
            if payload["event_content_fingerprint"] != expected_content:
                raise ContractError("OpportunityEvent content fingerprint does not match its facts")
    elif contract_name == "ExperimentRun":
        _require_text(payload["status"], "status")
        _require_mapping(payload["evidence_window"], "evidence_window")
        if not isinstance(payload["input_refs"], (list, tuple, Mapping)):
            raise ContractError("input_refs must be a list or object")
        if not isinstance(payload["result_refs"], (list, tuple, Mapping)):
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


def validate_contracts(
    items: Iterable[tuple[str, Mapping[str, Any]]],
    *,
    source_inventory_evidence: Mapping[str, Any] | None = None,
    publication_authorization_evidence: Mapping[str, Any] | None = None,
    evaluation_snapshot_evidence: Mapping[str, Any] | None = None,
    release_manifest_evidence: Mapping[str, Any] | None = None,
    publication_receipt_evidence: Mapping[str, Any] | None = None,
    current_pointer_evidence: Mapping[str, Any] | None = None,
) -> None:
    """Validate a collection, including stable-ID and event uniqueness rules."""

    seen_ids: set[tuple[str, str]] = set()
    opportunity_keys: set[tuple[str, str, str]] = set()
    for contract_name, payload in items:
        validate_contract(
            contract_name, payload, source_inventory_evidence=source_inventory_evidence,
            publication_authorization_evidence=publication_authorization_evidence,
            evaluation_snapshot_evidence=evaluation_snapshot_evidence,
            release_manifest_evidence=release_manifest_evidence,
            publication_receipt_evidence=publication_receipt_evidence,
            current_pointer_evidence=current_pointer_evidence,
        )
        if contract_name == "CurrentPointer":
            # Mutable singleton, not a content-addressed artifact with a new ID.
            identity = (contract_name, "current")
        else:
            stable_id_field = _stable_id_field(contract_name, payload)
            identity = (contract_name, str(payload[stable_id_field]))
        if identity in seen_ids:
            raise ContractError(f"duplicate stable ID: {identity[1]}")
        seen_ids.add(identity)
        if contract_name == "OpportunityEvent":
            if str(payload["schema_version"]).startswith("2."):
                key = (
                    str(payload["instrument_id"]), str(payload["signal_date"]),
                    str(payload["authority_scope"]),
                )
            else:
                gate_version = str(payload.get("gate_policy_version", "unknown"))
                key = (str(payload["symbol"]), str(payload["signal_date"]), gate_version)
            if key in opportunity_keys:
                raise ContractError("same event root produced two opportunity events")
            opportunity_keys.add(key)


# M12 inventory validation lives at the same public contract boundary as M01–M11.
# Evidence is an injected, lock-frozen trusted index, NEVER the artifact's own
# declaration. The production index adapter and its authentication ship later.
def _m12_exact(value: Any, fields: set[str], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ContractError(f"{label} must contain exactly {sorted(fields)}")


def _m12_ref(value: Any) -> dict[str, str]:
    _m12_exact(value, {"id", "content_fingerprint"}, "M12 Ref")
    stable_id = value["id"]
    fingerprint = value["content_fingerprint"]
    if not isinstance(stable_id, str) or not stable_id.strip() or stable_id != stable_id.strip():
        raise ContractError("M12 Ref id must be canonical nonempty text")
    if not isinstance(fingerprint, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", fingerprint):
        raise ContractError("M12 Ref requires a SHA-256 content fingerprint")
    return {"id": stable_id, "content_fingerprint": fingerprint}


def _m12_refs(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ContractError("M12 references must be an array")
    refs = [_m12_ref(item) for item in value]
    ids = [ref["id"] for ref in refs]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise ContractError("M12 references must be sorted and unique by id")
    return refs


def source_inventory_body(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    """Derive the complete reachable closure from one trusted frozen index.

    Internal adapter input: as_of/config_ref/roots/nodes; each node is an already
    resolved and validated upstream Ref plus its complete direct dependencies.
    The adapter must obtain ALL roots under the inventory lock, and verify source
    types/content before injecting this index. This pure function does not grant
    trust to caller-provided bytes or attest that a remote lock was held.
    """
    _m12_exact(evidence, {"as_of", "config_ref", "roots", "nodes"}, "trusted inventory evidence")
    _require_date(evidence["as_of"], "inventory evidence as_of")
    config = _m12_ref(evidence["config_ref"])
    roots = _m12_refs(evidence["roots"])
    if not roots:
        raise ContractError("inventory requires at least one authoritative root")
    if not isinstance(evidence["nodes"], list):
        raise ContractError("inventory nodes must be an array")
    nodes: dict[str, tuple[dict[str, str], list[dict[str, str]]]] = {}
    for node in evidence["nodes"]:
        _m12_exact(node, {"ref", "dependencies"}, "inventory node")
        ref = _m12_ref(node["ref"])
        if ref["id"] in nodes:
            raise ContractError("duplicate or conflicting inventory node")
        nodes[ref["id"]] = (ref, _m12_refs(node["dependencies"]))

    def resolve(ref: dict[str, str]) -> tuple[dict[str, str], list[dict[str, str]]]:
        node = nodes.get(ref["id"])
        if node is None or node[0] != ref:
            raise ContractError("inventory reference is missing or has conflicting content")
        return node

    resolve(config)
    # Iterative DFS supports long append-only histories without recursion limits.
    seen: set[str] = set()
    active: set[str] = set()
    stack = [(ref, False) for ref in reversed(roots)]
    while stack:
        ref, leaving = stack.pop()
        stable_id = ref["id"]
        node = resolve(ref)
        if leaving:
            active.remove(stable_id)
            seen.add(stable_id)
            continue
        if stable_id in active:
            raise ContractError("inventory reference cycle")
        if stable_id in seen:
            continue
        active.add(stable_id)
        stack.append((ref, True))
        stack.extend((child, False) for child in reversed(node[1]))
    return {
        "schema_version": "1.0.0",
        "as_of": evidence["as_of"],
        "config_ref": config,
        "roots": roots,
        "records": [nodes[key][0] for key in sorted(seen)],
    }


def _validate_source_inventory(payload: Mapping[str, Any], evidence: Mapping[str, Any] | None) -> None:
    _m12_exact(payload, {
        "schema_version", "inventory_id", "content_fingerprint", "generated_at",
        "as_of", "config_ref", "roots", "records",
    }, "SourceInventory")
    if payload["schema_version"] != "1.0.0":
        raise ContractError("unsupported SourceInventory version")
    _m12_time(payload["generated_at"])
    _require_date(payload["as_of"], "SourceInventory.as_of")
    _m12_ref(payload["config_ref"])
    _m12_refs(payload["roots"])
    _m12_refs(payload["records"])
    body = {key: value for key, value in payload.items() if key not in {
        "inventory_id", "content_fingerprint", "generated_at",
    }}
    expected = source_inventory_body(evidence)
    if body != expected:
        raise ContractError("SourceInventory differs from authoritative roots or complete closure")
    fingerprint = "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()
    if payload["content_fingerprint"] != fingerprint or payload["inventory_id"] != "source-inventory:" + fingerprint:
        raise ContractError("SourceInventory identity does not match semantic content")
    if any(ref["id"] == payload["inventory_id"] for ref in [payload["config_ref"], *payload["roots"], *payload["records"]]):
        raise ContractError("SourceInventory cannot reference itself")


M12_AUTHORIZATION_REQUEST_FIELDS = frozenset({
    "action", "prior_authorization_ref", "config_ref", "code_commit",
    "publication_mode", "scope", "effective_from", "valid_until", "permissions", "reason",
})
M12_RESEARCH_PERMISSIONS = ("prepare", "publish", "notify", "rollback")


def _m12_time(value: Any) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value):
        raise ContractError("M12 timestamp must be canonical UTC seconds")
    _require_timestamp(value)


def _m12_text(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ContractError(f"{label} must be canonical nonempty text")


def _m12_commit(value: Any) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ContractError("M12 commit must be a full lowercase Git SHA")


def _m12_job(job: Any) -> None:
    _m12_exact(job, {
        "repository_id", "workflow_ref", "workflow_commit", "run_id", "run_attempt", "environment",
    }, "M12 Job")
    for field in ("repository_id", "workflow_ref", "run_id", "environment"):
        _m12_text(job[field], "Job." + field)
    _m12_commit(job["workflow_commit"])
    if type(job["run_attempt"]) is not int or job["run_attempt"] < 0:
        raise ContractError("Job.run_attempt must be UInt, not bool")


def _m12_authorization_request_fields(payload: Mapping[str, Any]) -> None:
    """One nested request definition for raw sources and authorization records."""
    _m12_exact(payload, set(M12_AUTHORIZATION_REQUEST_FIELDS), "approved request")
    _m12_text(payload["reason"], "reason")
    _m12_ref(payload["config_ref"])
    _m12_commit(payload["code_commit"])
    if payload["prior_authorization_ref"] is not None:
        _m12_ref(payload["prior_authorization_ref"])
    if payload["publication_mode"] != "research_only" or payload["scope"] != "complex_multifactor_main":
        raise ContractError("M12 authorization is limited to the research publication scope")
    _require_date(payload["effective_from"], "effective_from")
    if payload["valid_until"] is not None:
        _require_date(payload["valid_until"], "valid_until")
        if payload["valid_until"] < payload["effective_from"]:
            raise ContractError("authorization expires before its effective date")
    if payload["action"] == "grant":
        if payload["permissions"] != list(M12_RESEARCH_PERMISSIONS):
            raise ContractError("research grant must contain exactly the frozen permissions in order")
    elif payload["action"] == "revoke":
        if payload["permissions"] != [] or payload["prior_authorization_ref"] is None:
            raise ContractError("revocation needs a predecessor and cannot grant permissions")
    else:
        raise ContractError("unknown publication authorization action")


def publication_request_body(source: Mapping[str, Any], *, source_commit: str) -> dict[str, Any]:
    """Parse trusted B2c source bytes; this does not authenticate their provenance.

    The source commit contains the request. Its business code_commit can name a
    different reviewed implementation, including a predecessor being revoked.
    """
    _m12_exact(source, {"source_commit", "path", "blob_sha", "bytes", "sha256", "size_bytes"}, "request source")
    _m12_commit(source_commit)
    _m12_commit(source["source_commit"])
    _m12_commit(source["blob_sha"])
    if source["source_commit"] != source_commit or source["path"] != "config/publication-authorization-request.json":
        raise ContractError("request source differs from the verified execution commit/path")
    raw = source["bytes"]
    if type(raw) is not bytes or not 1 <= len(raw) <= 65_536:
        raise ContractError("request source requires bounded immutable bytes")
    if type(source["size_bytes"]) is not int or source["size_bytes"] != len(raw):
        raise ContractError("request source byte length mismatch")
    if source["sha256"] != "sha256:" + hashlib.sha256(raw).hexdigest():
        raise ContractError("request source byte fingerprint mismatch")
    if source["blob_sha"] != hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest():
        raise ContractError("request source Git blob mismatch")
    request = _m12_json(raw)
    _m12_authorization_request_fields(request)
    return dict(request)


def _m12_authorization_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate intrinsic fields only; not a public approval validator."""
    _m12_exact(payload, set(M12_AUTHORIZATION_REQUEST_FIELDS) | {
        "schema_version", "authorization_id", "content_fingerprint", "generated_at",
        "approver_id", "approval_evidence_ref", "job",
    }, "PublicationAuthorization")
    if payload["schema_version"] != "1.0.0":
        raise ContractError("unsupported PublicationAuthorization version")
    _m12_time(payload["generated_at"])
    _m12_job(payload["job"])
    _m12_text(payload["approver_id"], "approver_id")
    _m12_ref(payload["approval_evidence_ref"])
    _m12_authorization_request_fields({key: payload[key] for key in M12_AUTHORIZATION_REQUEST_FIELDS})
    body = {key: value for key, value in payload.items() if key not in {
        "authorization_id", "content_fingerprint", "generated_at",
    }}
    fingerprint = "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()
    if payload["content_fingerprint"] != fingerprint or payload["authorization_id"] != "publication-authorization:" + fingerprint:
        raise ContractError("PublicationAuthorization identity mismatch")
    for reference in (payload["prior_authorization_ref"], payload["config_ref"], payload["approval_evidence_ref"]):
        if reference is not None and reference["id"] == payload["authorization_id"]:
            raise ContractError("PublicationAuthorization cannot reference itself")
    return body


def _m12_authorization_successor(payload: Mapping[str, Any], previous: Mapping[str, Any] | None) -> None:
    expected_ref = None if previous is None else {
        "id": previous["authorization_id"], "content_fingerprint": previous["content_fingerprint"],
    }
    if payload["prior_authorization_ref"] != expected_ref:
        raise ContractError("authorization must reference the direct trusted predecessor")
    if previous is not None and payload["action"] == "revoke":
        if payload["config_ref"] != previous["config_ref"] or payload["code_commit"] != previous["code_commit"]:
            raise ContractError("revocation cannot change predecessor config or code")


def publication_authorization_body(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    """Bind an approval to a trusted protected-workflow request and chain.

    This is a pure adapter boundary, not GitHub/OIDC authentication. The future
    adapter must verify the protected environment, allowed approver, OIDC claims,
    request/config/code and raw approval receipt, and freeze the complete chain
    under its lock. Caller-submitted JSON must never be injected as evidence.
    """
    fields = {
        "request", "approver_id", "approval_evidence_ref", "job", "history",
    }
    has_source = isinstance(evidence, Mapping) and bool({"request_source", "source_commit"} & set(evidence))
    if has_source:
        fields |= {"request_source", "source_commit"}
    _m12_exact(evidence, fields, "trusted publication approval evidence")
    _m12_authorization_request_fields(evidence["request"])
    if has_source:
        request = publication_request_body(evidence["request_source"], source_commit=evidence["source_commit"])
        if _canonical(request) != _canonical(evidence["request"]):
            raise ContractError("approved request differs from the frozen source bytes")
    if not isinstance(evidence["history"], list):
        raise ContractError("trusted authorization history must be an array")
    previous = None
    seen: set[str] = set()
    for record in evidence["history"]:
        _m12_authorization_fields(record)
        _m12_authorization_successor(record, previous)
        if record["authorization_id"] in seen:
            raise ContractError("duplicate authorization in trusted history")
        seen.add(record["authorization_id"])
        previous = record
    request = evidence["request"]
    _m12_authorization_successor(request, previous)
    return {
        "schema_version": "1.0.0", **request,
        "approver_id": evidence["approver_id"],
        "approval_evidence_ref": evidence["approval_evidence_ref"],
        "job": evidence["job"],
    }


def _validate_publication_authorization(payload: Mapping[str, Any], evidence: Mapping[str, Any] | None) -> None:
    body = _m12_authorization_fields(payload)
    if body != publication_authorization_body(evidence):
        raise ContractError("PublicationAuthorization differs from the trusted approval")
    if any(record["authorization_id"] == payload["authorization_id"] for record in evidence["history"]):
        raise ContractError("new authorization already occurs in predecessor history")


M12_RESULT_METRICS = (
    "gross_return", "net_return", "mfe", "mae", "gross_r_multiple", "mean_gross_return", "win_rate",
)


def _m12_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ContractError("M12 reason codes must be an array")
    for item in value:
        _m12_text(item, "reason code")
    if value != sorted(set(value)):
        raise ContractError("M12 reason codes must be sorted and unique")
    return list(value)


def _m12_result_row(contract: str, result: Mapping[str, Any], as_of: str) -> dict[str, Any]:
    # Deferred import preserves the shared-contract / M10 dependency direction.
    from services.evaluation.contracts import RESULT_TYPES, validate_result

    validate_result(contract, result)
    if result["path_status"] != "formal" or result["result_role"] != "authoritative":
        raise ContractError("M12 research summary cannot promote comparison or legacy results")
    if result["as_of"] > as_of:
        raise ContractError("M12 result cannot exceed the scan cutoff")
    id_field, fingerprint_field, _, _ = RESULT_TYPES[contract]
    allowed = {
        "ForwardOutcome": {"gross_return", "mfe", "mae"},
        "TradeOutcome": {"gross_return", "net_return", "mfe", "mae", "gross_r_multiple"},
        "PortfolioRun": set(),
        "ResearchAggregate": {"mean_gross_return", "win_rate"},
    }[contract]
    return {
        "result_ref": {"id": result[id_field], "content_fingerprint": result[fingerprint_field]},
        "event_id": result.get("event_id"), "result_contract": contract,
        "window_sessions": result.get("window_sessions"), "status": result["status"],
        **{field: result.get(field) if field in allowed else None for field in M12_RESULT_METRICS},
        "unavailable_reason": result.get("status_reason") or result.get("metric_reason") or result.get("net_return_reason"),
    }


def evaluation_snapshot_body(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    """Project validated M10 leaves and counts from a trusted frozen task index.

    The future adapter verifies task scheduling, result-chain heads, persisted
    receipts and index completeness under its lock. This function verifies the
    supplied graph and actual M10 contracts, not the existence of remote state.
    """
    _m12_exact(evidence, {
        "scan_as_of", "inventory", "inventory_evidence", "task_index_ref", "tasks", "results",
    }, "trusted evaluation snapshot evidence")
    cutoff = evidence["scan_as_of"]
    _require_date(cutoff, "scan_as_of")
    inventory = evidence["inventory"]
    validate_contract("SourceInventory", inventory, source_inventory_evidence=evidence["inventory_evidence"])
    index_ref = _m12_ref(evidence["task_index_ref"])
    if inventory["as_of"] != cutoff or inventory["roots"] != [index_ref]:
        raise ContractError("evaluation inventory must freeze the same-day task index root")
    graph = {node["ref"]["id"]: node for node in evidence["inventory_evidence"]["nodes"]}
    inventory_refs = {ref["id"]: ref for ref in inventory["records"]}
    if not isinstance(evidence["tasks"], list) or not isinstance(evidence["results"], list):
        raise ContractError("evaluation tasks and results must be arrays")
    task_refs = _m12_refs([task.get("task_ref") if isinstance(task, Mapping) else None for task in evidence["tasks"]])
    if graph[index_ref["id"]]["dependencies"] != task_refs:
        raise ContractError("evaluation tasks differ from the complete task index")
    rows = {}
    for item in evidence["results"]:
        _m12_exact(item, {"contract_name", "payload"}, "M10 result record")
        if not isinstance(item["contract_name"], str):
            raise ContractError("M10 contract name must be text")
        row = _m12_result_row(item["contract_name"], item["payload"], cutoff)
        reference = row["result_ref"]
        if reference["id"] in rows or inventory_refs.get(reference["id"]) != reference:
            raise ContractError("duplicate result or result outside frozen inventory")
        rows[reference["id"]] = row
    counts = {"due_count": 0, "completed_count": 0, "failed_count": 0, "pending_due_count": 0, "immature_count": 0}
    reasons: set[str] = set()
    referenced: set[str] = set()
    due_days: dict[str, list[bool]] = {}
    for task in evidence["tasks"]:
        _m12_exact(task, {
            "task_ref", "due_on", "state", "result_ref", "result_contract", "event_id", "window_sessions", "reason_codes",
        }, "evaluation task")
        _require_date(task["due_on"], "task.due_on")
        state = task["state"]
        if not isinstance(state, str) or state not in {"queued", "running", "retry_wait", "blocked", "completed"}:
            raise ContractError("unknown evaluation task state")
        if task["result_contract"] not in ("ForwardOutcome", "TradeOutcome", "PortfolioRun", "ResearchAggregate"):
            raise ContractError("unknown evaluation task result contract")
        if task["event_id"] is not None:
            _m12_text(task["event_id"], "task.event_id")
        window = task["window_sessions"]
        if window is not None and (type(window) is not int or window < 0):
            raise ContractError("task.window_sessions must be UInt or null")
        reasons.update(_m12_strings(task["reason_codes"]))
        row = None
        if task["result_ref"] is not None:
            reference = _m12_ref(task["result_ref"])
            row = rows.get(reference["id"])
            if row is None or row["result_ref"] != reference or reference["id"] in referenced:
                raise ContractError("task result is missing, duplicated or has conflicting content")
            if reference not in graph[task["task_ref"]["id"]]["dependencies"]:
                raise ContractError("task result is not bound to its frozen index node")
            if any(row[field] != task[field] for field in ("result_contract", "event_id", "window_sessions")):
                raise ContractError("task result crosses event, window or result family")
            referenced.add(reference["id"])
        due = task["due_on"] <= cutoff
        if state == "completed" and (not due or row is None or row["status"] == "pending"):
            raise ContractError("completed task needs a due, readable terminal M10 result")
        if not due:
            counts["immature_count"] += 1
            continue
        counts["due_count"] += 1
        completed = state == "completed"
        bucket = "completed_count" if completed else "failed_count" if state in {"retry_wait", "blocked"} else "pending_due_count"
        counts[bucket] += 1
        due_days.setdefault(task["due_on"], []).append(completed)
    if referenced != set(rows):
        raise ContractError("evaluation snapshot has extra result objects")
    through = None
    for day in sorted(due_days):
        if not all(due_days[day]):
            break
        through = day
    incomplete = counts["failed_count"] + counts["pending_due_count"]
    state = "current" if not incomplete else "unavailable" if not counts["completed_count"] else "lagging"
    if counts["due_count"] and not incomplete:
        through = cutoff
    result_rows = [rows[key] for key in sorted(rows)]
    return {
        "schema_version": "1.0.0", "scan_as_of": cutoff,
        "inventory_ref": {"id": inventory["inventory_id"], "content_fingerprint": inventory["content_fingerprint"]},
        "state": state, "completed_through": through, **counts,
        "result_refs": [row["result_ref"] for row in result_rows], "result_rows": result_rows,
        "reason_codes": sorted(reasons),
    }


def _validate_evaluation_snapshot(payload: Mapping[str, Any], evidence: Mapping[str, Any] | None) -> None:
    _m12_exact(payload, {
        "schema_version", "evaluation_snapshot_id", "content_fingerprint", "generated_at",
        "scan_as_of", "inventory_ref", "state", "completed_through", "due_count",
        "completed_count", "failed_count", "pending_due_count", "immature_count",
        "result_refs", "result_rows", "reason_codes",
    }, "EvaluationSnapshot")
    if payload["schema_version"] != "1.0.0":
        raise ContractError("unsupported EvaluationSnapshot version")
    _m12_time(payload["generated_at"])
    for field in ("due_count", "completed_count", "failed_count", "pending_due_count", "immature_count"):
        if type(payload[field]) is not int or payload[field] < 0:
            raise ContractError("evaluation counts must be UInt, not bool")
    _m12_refs(payload["result_refs"])
    _m12_strings(payload["reason_codes"])
    if not isinstance(payload["result_rows"], list):
        raise ContractError("result_rows must be an array")
    for row in payload["result_rows"]:
        _m12_exact(row, {
            "result_ref", "event_id", "result_contract", "window_sessions", "status", "unavailable_reason",
            *M12_RESULT_METRICS,
        }, "ResultRow")
        window = row["window_sessions"]
        if window is not None and (type(window) is not int or window < 0):
            raise ContractError("ResultRow.window_sessions must be UInt or null")
        for field in M12_RESULT_METRICS:
            value = row[field]
            if value is not None and (type(value) not in (int, float) or (type(value) is float and not math.isfinite(value))):
                raise ContractError("ResultRow metrics must be finite numbers or null")
    body = {key: value for key, value in payload.items() if key not in {
        "evaluation_snapshot_id", "content_fingerprint", "generated_at",
    }}
    if body != evaluation_snapshot_body(evidence):
        raise ContractError("EvaluationSnapshot differs from frozen tasks or M10 results")
    fingerprint = "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()
    if payload["content_fingerprint"] != fingerprint or payload["evaluation_snapshot_id"] != "evaluation-snapshot:" + fingerprint:
        raise ContractError("EvaluationSnapshot identity mismatch")


# One file/kind registry for M12; independent of the legacy M01 fifteen-file set.
M12_PROJECTION_KINDS = {
    "update-status.json": "status", "overview.json": "overview", "rankings.json": "rankings",
    "technical-evidence.json": "technical_evidence", "favorite-pattern.json": "favorite_pattern",
    "context.json": "context", "events.json": "events", "notification-plan.json": "notification_plan",
}
M12_RELEASE_FILES = frozenset(M12_PROJECTION_KINDS) | {"factor-registry.json", "evaluation.json"}


def _m12_policy_refs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ContractError("M12 policy_refs must be a nonempty array")
    keys = []
    for item in value:
        _m12_exact(item, {
            "module", "name", "version", "content_fingerprint", "definition_commit", "source_path", "source_blob",
        }, "PolicyRef")
        for field in ("module", "name", "version", "source_path"):
            _m12_text(item[field], "PolicyRef." + field)
        if item["module"] not in {f"M{i:02}" for i in range(2, 13)}:
            raise ContractError("PolicyRef module is outside M02–M12")
        _m12_ref({"id": item["name"], "content_fingerprint": item["content_fingerprint"]})
        _m12_commit(item["definition_commit"])
        _m12_commit(item["source_blob"])
        path = PurePosixPath(item["source_path"])
        if path.is_absolute() or ".." in path.parts or path.as_posix() != item["source_path"] or ":" in item["source_path"] or "\\" in item["source_path"] or not path.parts:
            raise ContractError("PolicyRef source_path must be a canonical repository path")
        keys.append((item["module"], item["name"]))
    if keys != sorted(set(keys)):
        raise ContractError("PolicyRefs must be sorted and unique by module/name")
    return [dict(item) for item in value]


def _m12_json(raw: Any, *, allow_release_identity: bool = False) -> Mapping[str, Any]:
    if type(raw) is not bytes:
        raise ContractError("M12 file snapshots must be immutable bytes")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ContractError("duplicate JSON key in release file")
            result[key] = value
        return result

    def constant(value):
        raise ContractError("nonfinite JSON number in release file")

    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("release file must be UTF-8 JSON") from exc
    if not isinstance(payload, Mapping):
        raise ContractError("release file must be a JSON object")
    _canonical(payload)  # Also rejects exponent overflow to Infinity.
    stack = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, Mapping):
            if "release_id" in item and not allow_release_identity:
                raise ContractError("release files cannot contain their release identity")
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return payload


def release_manifest_body(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    """Bind exact bytes to trusted preparation inputs; no filesystem or publish I/O.

    The future adapter authenticates config/policy source blobs, prepared business
    projections, the active approval, previous verified target and inventory dates.
    A matching injected context alone is not proof of those external facts.
    """
    from services.contracts.adapters import adapt_legacy_bytes

    _m12_exact(evidence, {
        "as_of", "code_commit", "config_ref", "policy_refs", "last_verified_release_ref",
        "inventory", "inventory_evidence", "source_dates", "authorization", "authorization_evidence",
        "evaluation", "evaluation_evidence", "registry_ref", "registry_bytes", "projection_expectations", "files",
    }, "trusted release preparation evidence")
    day = evidence["as_of"]
    _require_date(day, "release.as_of")
    _m12_commit(evidence["code_commit"])
    config = _m12_ref(evidence["config_ref"])
    policies = _m12_policy_refs(evidence["policy_refs"])
    previous = evidence["last_verified_release_ref"]
    if previous is not None:
        _m12_ref(previous)
    inventory = evidence["inventory"]
    validate_contract("SourceInventory", inventory, source_inventory_evidence=evidence["inventory_evidence"])
    if inventory["as_of"] != day or inventory["config_ref"] != config:
        raise ContractError("release inventory date/config mismatch")
    references = {item["id"]: item for item in inventory["records"]}
    _m12_exact(evidence["source_dates"], set(references), "inventory source dates")
    for source_date in evidence["source_dates"].values():
        if source_date is not None:
            _require_date(source_date, "source date")
            if source_date > day:
                raise ContractError("release inventory contains future evidence")

    def resolve(reference):
        _m12_ref(reference)
        if references.get(reference["id"]) != reference:
            raise ContractError("release input does not resolve in its frozen inventory")
        return reference

    authorization = evidence["authorization"]
    validate_contract("PublicationAuthorization", authorization, publication_authorization_evidence=evidence["authorization_evidence"])
    if (authorization["action"] != "grant" or authorization["config_ref"] != config
            or authorization["code_commit"] != evidence["code_commit"]
            or authorization["effective_from"] > day
            or (authorization["valid_until"] is not None and authorization["valid_until"] < day)):
        raise ContractError("release needs a matching research grant effective for its date")
    evaluation = evidence["evaluation"]
    validate_contract("EvaluationSnapshot", evaluation, evaluation_snapshot_evidence=evidence["evaluation_evidence"])
    if evaluation["scan_as_of"] != day or evidence["evaluation_evidence"]["inventory"]["config_ref"] != config:
        raise ContractError("evaluation snapshot belongs to another scan date/config")
    evaluation_ref = resolve({"id": evaluation["evaluation_snapshot_id"], "content_fingerprint": evaluation["content_fingerprint"]})
    registry_ref = resolve(evidence["registry_ref"])
    _m12_exact(evidence["projection_expectations"], set(M12_PROJECTION_KINDS), "frozen projection expectations")
    _m12_exact(evidence["files"], set(M12_RELEASE_FILES), "release files")
    entries = []
    for path in sorted(M12_RELEASE_FILES):
        raw = evidence["files"][path]
        content = _m12_json(raw)
        entry = {
            "path": path, "size_bytes": len(raw), "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "required": True, "roles": ["audit", "web"], "as_of": None, "coverage_end": None, "registry_version": None,
        }
        if path == "factor-registry.json":
            if raw != evidence["registry_bytes"]:
                raise ContractError("registry file differs from the pinned registry bytes")
            adapted = adapt_legacy_bytes(path, raw)
            if content["registry_version"] != "0.10.0":
                raise ContractError("first M12 release requires the frozen factor registry 0.10.0")
            entry.update(contract_name="FactorRegistry", schema_version=adapted.schema_version,
                         temporal_class="versioned_config", registry_version=content["registry_version"], source_refs=[registry_ref])
        elif path == "evaluation.json":
            # Reuse the one evaluation contract, then require the exact frozen object.
            validate_contract("EvaluationSnapshot", content, evaluation_snapshot_evidence=evidence["evaluation_evidence"])
            if content != evaluation:
                raise ContractError("evaluation file differs from the frozen snapshot")
            entry.update(contract_name="EvaluationSnapshot", schema_version="1.0.0", temporal_class="research_summary",
                         coverage_end=content["completed_through"], source_refs=[resolve(content["inventory_ref"])])
        else:
            _m12_exact(content, {"schema_version", "kind", "as_of", "source_refs", "data"}, "WebProjection")
            if content["schema_version"] != "1.0.0" or content["kind"] != M12_PROJECTION_KINDS[path] or content["as_of"] != day:
                raise ContractError("projection kind/version/date mismatch")
            refs = _m12_refs(content["source_refs"])
            if not refs:
                raise ContractError("projection requires source evidence even for empty results")
            for reference in refs:
                resolve(reference)
            if _canonical(content) != _canonical(evidence["projection_expectations"][path]):
                raise ContractError("file differs from frozen upstream projection")
            entry.update(contract_name="WebProjection", schema_version="1.0.0", temporal_class="daily_snapshot", as_of=day, source_refs=refs)
            if path == "notification-plan.json":
                entry["roles"] = ["audit", "discord"]
            elif path == "update-status.json":
                entry["roles"] = ["audit", "discord", "web"]
        entries.append(entry)
    return {
        "schema_version": "2.0.0", "as_of": day, "code_commit": evidence["code_commit"], "config_ref": config,
        "authorization_ref": {"id": authorization["authorization_id"], "content_fingerprint": authorization["content_fingerprint"]},
        "publication_mode": "research_only", "future_data_used": False, "previous_release_ref": previous,
        "source_inventory_ref": {"id": inventory["inventory_id"], "content_fingerprint": inventory["content_fingerprint"]},
        "policy_refs": policies, "evaluation_snapshot_ref": evaluation_ref, "files": entries,
    }


def _validate_release_manifest_v2(payload: Mapping[str, Any], evidence: Mapping[str, Any] | None) -> None:
    _m12_exact(payload, {
        "schema_version", "release_id", "content_fingerprint", "generated_at", "as_of", "code_commit", "config_ref",
        "authorization_ref", "publication_mode", "future_data_used", "previous_release_ref", "source_inventory_ref",
        "policy_refs", "evaluation_snapshot_ref", "files",
    }, "ReleaseManifest 2.0.0")
    _m12_time(payload["generated_at"])
    if payload["future_data_used"] is not False:
        raise ContractError("release future_data_used must be boolean false")
    if not isinstance(payload["files"], list):
        raise ContractError("manifest files must be an array")
    for entry in payload["files"]:
        _m12_exact(entry, {
            "path", "contract_name", "schema_version", "size_bytes", "sha256", "roles", "required",
            "temporal_class", "as_of", "coverage_end", "registry_version", "source_refs",
        }, "FileEntry")
        if type(entry["size_bytes"]) is not int or entry["size_bytes"] < 0 or entry["required"] is not True:
            raise ContractError("FileEntry requires a UInt size and required=true")
    body = {key: value for key, value in payload.items() if key not in {"release_id", "content_fingerprint", "generated_at"}}
    if body != release_manifest_body(evidence):
        raise ContractError("manifest differs from exact bytes or trusted release inputs")
    fingerprint = "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()
    if payload["content_fingerprint"] != fingerprint or payload["release_id"] != "release:" + fingerprint:
        raise ContractError("ReleaseManifest identity mismatch")


M12_PAGE_PATHS = ("/", "/zh/watch/industry-radar", "/zh/watch/resonance/favorite-pattern", "/zh/watch/resonance/rare-opportunities")
M12_CHECK_NAMES = frozenset({"contract", "date", "identity", "hash", "coverage", "four_pages", "authorization"})
M12_RECEIPT_DETAILS = {
    "prepare": {"inventory_ref", "checked_files", "checks"},
    "preflight": {"target", "candidate_url", "renderer_version_id", "provider_deployment_id", "manifest_hash", "checked_files", "page_paths", "checks"},
    "promote": {"before", "after", "expected_generation", "resulting_generation", "preflight_ref"},
    "online": {"target", "pointer_generation", "renderer_version_id", "provider_deployment_id", "manifest_hash", "checked_files", "page_paths", "checks"},
    "rollback": {"before", "after", "failed_receipt_ref", "rollback_check_ref", "expected_generation", "resulting_generation"},
    "notify": {"online_receipt_ref", "notification_plan_ref", "items"},
}
M12_RECEIPT_BODY_FIELDS = frozenset({
    "release_ref", "previous_receipt_ref", "job", "fence", "occurred_at", "kind", "outcome", "reason_code", "details",
})


def _m12_uint(value: Any) -> None:
    if type(value) is not int or value < 0:
        raise ContractError("M12 UInt must be a nonnegative integer, not bool")


def _m12_hash(value: Any) -> None:
    _m12_ref({"id": "hash-check", "content_fingerprint": value})


def _m12_pointer_target(value: Any) -> None:
    if not isinstance(value, Mapping) or value.get("kind") not in ("release", "legacy"):
        raise ContractError("unknown PointerTarget kind")
    ref_key = "release_ref" if value["kind"] == "release" else "baseline_ref"
    _m12_exact(value, {"kind", ref_key, "renderer_version_id"}, "PointerTarget")
    _m12_ref(value[ref_key])
    _m12_text(value["renderer_version_id"], "renderer_version_id")


def _m12_checked_files(value: Any) -> None:
    if not isinstance(value, list):
        raise ContractError("checked_files must be an array")
    paths = []
    for item in value:
        _m12_exact(item, {"path", "sha256", "size_bytes"}, "checked file")
        _m12_text(item["path"], "checked path")
        path = PurePosixPath(item["path"])
        if path.is_absolute() or not path.parts or ".." in path.parts or path.as_posix() != item["path"] or ":" in item["path"] or "\\" in item["path"]:
            raise ContractError("checked path must be canonical and relative")
        _m12_hash(item["sha256"])
        _m12_uint(item["size_bytes"])
        paths.append(item["path"])
    if paths != sorted(set(paths)):
        raise ContractError("checked files must be sorted and unique")


def _m12_receipt_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    _m12_exact(payload, set(M12_RECEIPT_BODY_FIELDS) | {
        "schema_version", "receipt_id", "content_fingerprint", "generated_at",
    }, "PublicationReceipt")
    if payload["schema_version"] != "1.0.0":
        raise ContractError("unsupported PublicationReceipt version")
    _m12_time(payload["generated_at"])
    _m12_time(payload["occurred_at"])
    _m12_job(payload["job"])
    _m12_uint(payload["fence"])
    kind, outcome = payload["kind"], payload["outcome"]
    if not isinstance(kind, str) or kind not in M12_RECEIPT_DETAILS or outcome not in ("success", "failed", "uncertain"):
        raise ContractError("unknown receipt kind/outcome")
    if outcome == "success":
        if payload["reason_code"] is not None:
            raise ContractError("successful receipt cannot contain a failure reason")
    elif payload["reason_code"] not in (
        "source_missing", "contract_invalid", "hash_mismatch", "coverage_incomplete", "authority_missing",
        "lease_lost", "switch_conflict", "provider_error", "transport_unknown",
    ):
        raise ContractError("unknown receipt failure reason")
    if outcome == "uncertain" and (kind not in ("notify", "preflight", "online") or payload["reason_code"] != "transport_unknown"):
        raise ContractError("uncertain is reserved for unknown external responses")
    if payload["release_ref"] is None:
        if kind != "prepare" or outcome != "failed":
            raise ContractError("only early prepare failure may lack a release")
    else:
        _m12_ref(payload["release_ref"])
    if payload["previous_receipt_ref"] is not None:
        _m12_ref(payload["previous_receipt_ref"])
    details = payload["details"]
    _m12_exact(details, M12_RECEIPT_DETAILS[kind], "receipt details")
    if kind in ("prepare", "preflight", "online"):
        _m12_checked_files(details["checked_files"])
        if not isinstance(details["checks"], list):
            raise ContractError("checks must be an array")
        names = []
        for check in details["checks"]:
            _m12_exact(check, {"name", "result", "evidence_ref"}, "Check")
            if not isinstance(check["name"], str) or check["name"] not in M12_CHECK_NAMES or check["result"] not in ("pass", "fail"):
                raise ContractError("unknown check name/result")
            _m12_ref(check["evidence_ref"])
            if outcome == "success" and check["result"] != "pass":
                raise ContractError("success cannot contain a failed check")
            names.append(check["name"])
        if names != sorted(set(names)):
            raise ContractError("checks must be sorted and unique")
        required = M12_CHECK_NAMES if kind == "prepare" and outcome == "success" else {"hash", "date", "four_pages", "authorization"} if kind != "prepare" else set()
        if not required <= set(names):
            raise ContractError("receipt lacks required checks")
    if kind == "prepare":
        if details["inventory_ref"] is None:
            if outcome != "failed":
                raise ContractError("successful prepare needs an inventory")
        else:
            _m12_ref(details["inventory_ref"])
    elif kind in ("preflight", "online"):
        _m12_pointer_target(details["target"])
        if details["renderer_version_id"] != details["target"]["renderer_version_id"]:
            raise ContractError("renderer does not match target")
        if details["provider_deployment_id"] is not None:
            _m12_text(details["provider_deployment_id"], "provider_deployment_id")
        _m12_hash(details["manifest_hash"])
        pages = details["page_paths"]
        if not isinstance(pages, list) or any(not isinstance(page, str) or page not in M12_PAGE_PATHS for page in pages) or pages != sorted(set(pages)):
            raise ContractError("receipt page_paths must be a unique sorted subset of the four routes")
        if outcome == "success" and pages != list(M12_PAGE_PATHS):
            raise ContractError("successful verification must cover all four routes")
        if kind == "preflight":
            _m12_text(details["candidate_url"], "candidate_url")
            if not details["candidate_url"].startswith("https://"):
                raise ContractError("candidate URL must use HTTPS")
        else:
            _m12_uint(details["pointer_generation"])
    elif kind in ("promote", "rollback"):
        if details["before"] is not None:
            _m12_pointer_target(details["before"])
        elif kind == "rollback":
            raise ContractError("rollback must identify its failed target")
        _m12_pointer_target(details["after"])
        _m12_uint(details["expected_generation"])
        _m12_uint(details["resulting_generation"])
        if details["resulting_generation"] != details["expected_generation"] + (1 if outcome == "success" else 0):
            raise ContractError("switch generation must advance exactly once on success only")
        if outcome == "success" and details["before"] == details["after"]:
            raise ContractError("successful switch cannot leave the target unchanged")
        for key in (("preflight_ref",) if kind == "promote" else ("failed_receipt_ref", "rollback_check_ref")):
            _m12_ref(details[key])
    else:
        _m12_ref(details["online_receipt_ref"])
        _m12_ref(details["notification_plan_ref"])
        if not isinstance(details["items"], list):
            raise ContractError("notification items must be an array")
        keys = []
        for item in details["items"]:
            _m12_exact(item, {"key", "status", "platform_message_id", "attempt"}, "notification item")
            _m12_hash(item["key"])
            _m12_uint(item["attempt"])
            if item["status"] not in ("sent", "skipped", "failed", "uncertain"):
                raise ContractError("unknown notification item status")
            if item["platform_message_id"] is not None:
                _m12_text(item["platform_message_id"], "platform_message_id")
            if item["status"] == "sent" and item["platform_message_id"] is None:
                raise ContractError("sent requires an actual platform message id")
            if outcome == "success" and item["status"] not in ("sent", "skipped"):
                raise ContractError("notification success contains an incomplete item")
            keys.append(item["key"])
        if keys != sorted(set(keys)):
            raise ContractError("notification keys must be sorted and unique")
    body = {key: value for key, value in payload.items() if key not in {"receipt_id", "content_fingerprint", "generated_at"}}
    fingerprint = "sha256:" + hashlib.sha256(_canonical(body)).hexdigest()
    if payload["content_fingerprint"] != fingerprint or payload["receipt_id"] != "publication-receipt:" + fingerprint:
        raise ContractError("PublicationReceipt identity mismatch")
    return body


def publication_receipt_body(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    """Bind one receipt to a trusted observation, frozen chain and target inventory.

    Platform observations and supporting Ref provenance must be authenticated by
    the future adapter. No claim here means an actual probe, CAS or send occurred.
    """
    _m12_exact(evidence, {"observation", "history", "release", "release_evidence", "release_bytes", "targets", "references", "prepared_files"}, "trusted receipt evidence")
    observation = evidence["observation"]
    _m12_exact(observation, set(M12_RECEIPT_BODY_FIELDS), "receipt observation")
    refs = {ref["id"]: ref for ref in _m12_refs(evidence["references"])}
    if not isinstance(evidence["history"], list) or not isinstance(evidence["targets"], list):
        raise ContractError("receipt history/targets must be arrays")
    history = {}
    previous_ref = None
    for receipt in evidence["history"]:
        _m12_receipt_fields(receipt)
        if receipt["previous_receipt_ref"] != previous_ref or receipt["receipt_id"] in history:
            raise ContractError("receipt history is not a unique direct-predecessor chain")
        if receipt["release_ref"] is None:
            if receipt["job"] != observation["job"] or any(r["release_ref"] is not None for r in history.values()):
                raise ContractError("early prepare history crosses its job root")
        elif receipt["release_ref"] != observation["release_ref"]:
            raise ContractError("receipt history crosses releases")
        previous_ref = {"id": receipt["receipt_id"], "content_fingerprint": receipt["content_fingerprint"]}
        history[receipt["receipt_id"]] = receipt
    if observation["previous_receipt_ref"] != previous_ref:
        raise ContractError("receipt must bind the latest trusted predecessor")
    release = evidence["release"]
    if observation["release_ref"] is None:
        if release is not None or evidence["release_evidence"] is not None or evidence["release_bytes"] is not None:
            raise ContractError("early failure cannot invent a release")
    else:
        validate_contract("ReleaseManifest", release, release_manifest_evidence=evidence["release_evidence"])
        if release["schema_version"] != "2.0.0" or _canonical(_m12_json(evidence["release_bytes"], allow_release_identity=True)) != _canonical(release):
            raise ContractError("receipt must resolve the exact stored M12 manifest bytes")
        expected_ref = {"id": release["release_id"], "content_fingerprint": release["content_fingerprint"]}
        if observation["release_ref"] != expected_ref:
            raise ContractError("receipt release reference mismatch")
    prepared = evidence["prepared_files"]
    if not isinstance(prepared, Mapping) or any(path not in M12_RELEASE_FILES or type(raw) is not bytes for path, raw in prepared.items()):
        raise ContractError("prepared_files must contain partial fixed-file byte snapshots")
    if release is not None and prepared:
        raise ContractError("once a manifest exists its bytes are the sole file authority")
    targets = {}
    for record in evidence["targets"]:
        _m12_exact(record, {"target", "manifest_hash", "files", "public_paths"}, "verified target inventory")
        _m12_pointer_target(record["target"])
        _m12_hash(record["manifest_hash"])
        _m12_checked_files(record["files"])
        paths = [f["path"] for f in record["files"]]
        public = record["public_paths"]
        if not isinstance(public, list) or any(not isinstance(p, str) or p not in paths for p in public) or public != sorted(set(public)):
            raise ContractError("invalid target public file paths")
        key = _canonical(record["target"])
        if key in targets:
            raise ContractError("duplicate target evidence")
        if release is not None and record["target"].get("release_ref") == observation["release_ref"]:
            expected_files = [{k: f[k] for k in ("path", "sha256", "size_bytes")} for f in release["files"]]
            if record["files"] != expected_files or public != [f["path"] for f in release["files"] if "web" in f["roles"]] or record["manifest_hash"] != "sha256:" + hashlib.sha256(evidence["release_bytes"]).hexdigest():
                raise ContractError("current target inventory differs from stored manifest")
        targets[key] = record

    def target_record(target):
        record = targets.get(_canonical(target))
        if record is None:
            raise ContractError("target is not in the trusted verified-target inventory")
        return record

    def resolved(reference):
        _m12_ref(reference)
        if refs.get(reference["id"]) != reference:
            raise ContractError("supporting receipt evidence does not resolve")

    def prior(reference, kind, outcome="success"):
        _m12_ref(reference)
        record = history.get(reference["id"])
        if record is None or reference["content_fingerprint"] != record["content_fingerprint"] or record["kind"] != kind or record["outcome"] != outcome:
            raise ContractError("receipt prerequisite is missing, wrong-kind or unsuccessful")
        return record

    kind, details = observation["kind"], observation["details"]
    if not isinstance(kind, str) or kind not in M12_RECEIPT_DETAILS:
        raise ContractError("unknown observation kind")
    _m12_exact(details, M12_RECEIPT_DETAILS[kind], "observation details")
    success = observation["outcome"] == "success"
    if kind in ("prepare", "preflight", "online"):
        _m12_checked_files(details["checked_files"])
        if not isinstance(details["checks"], list):
            raise ContractError("checks must be an array")
        for check in details["checks"]:
            _m12_exact(check, {"name", "result", "evidence_ref"}, "Check")
            resolved(check["evidence_ref"])
        if kind == "prepare":
            if details["inventory_ref"] is not None:
                resolved(details["inventory_ref"])
                if release is not None and details["inventory_ref"] != release["source_inventory_ref"]:
                    raise ContractError("prepare inventory differs from the release")
            allowed = {path: {"path": path, "size_bytes": len(raw), "sha256": "sha256:" + hashlib.sha256(raw).hexdigest()} for path, raw in prepared.items()} if release is None else {f["path"]: {k: f[k] for k in ("path", "sha256", "size_bytes")} for f in release["files"]}
            required_paths = set(allowed) if success else set()
        else:
            record = target_record(details["target"])
            if kind == "online":
                switches = [r for r in history.values() if r["kind"] in ("promote", "rollback") and r["outcome"] == "success"]
                if not switches or switches[-1]["details"]["after"] != details["target"] or switches[-1]["details"]["resulting_generation"] != details["pointer_generation"]:
                    raise ContractError("online observation is not bound to the latest successful switch")
            if success and details["manifest_hash"] != record["manifest_hash"]:
                raise ContractError("successful verification hash differs from the target manifest")
            allowed = {f["path"]: f for f in record["files"]}
            required_paths = set(record["public_paths"]) if success else set()
        if any(f["path"] not in allowed or (success and allowed[f["path"]] != f) for f in details["checked_files"]) or not required_paths <= {f["path"] for f in details["checked_files"]}:
            raise ContractError("checked files disagree with required target bytes")
    elif kind in ("promote", "rollback"):
        if details["before"] is not None:
            target_record(details["before"])
        target_record(details["after"])
        preflight = prior(details["preflight_ref"] if kind == "promote" else details["rollback_check_ref"], "preflight")
        if preflight["details"]["target"] != details["after"]:
            raise ContractError("switch target differs from its successful preflight")
        if kind == "promote" and details["after"].get("release_ref") != observation["release_ref"]:
            raise ContractError("promote must target the receipt release")
        if kind == "rollback":
            failure = prior(details["failed_receipt_ref"], "online", "failed")
            if failure["details"]["target"] != details["before"]:
                raise ContractError("rollback does not identify the failed online target")
    elif kind == "notify":
        online = prior(details["online_receipt_ref"], "online")
        transitions = [r for r in history.values() if r["kind"] in ("online", "promote", "rollback")]
        if not transitions or transitions[-1] != online or online["details"]["target"].get("release_ref") != observation["release_ref"]:
            raise ContractError("notify needs the latest successful online check of this release")
        expected_plan_ref = release_file_reference(
            release, "notification-plan.json", release_manifest_evidence=evidence["release_evidence"],
        )
        if details["notification_plan_ref"] != expected_plan_ref:
            raise ContractError("notification plan must be the current release's frozen notification-plan.json")
        resolved(details["notification_plan_ref"])
    return {"schema_version": "1.0.0", **observation}


def _validate_publication_receipt(payload: Mapping[str, Any], evidence: Mapping[str, Any] | None) -> None:
    body = _m12_receipt_fields(payload)
    if _canonical(body) != _canonical(publication_receipt_body(evidence)):
        raise ContractError("receipt differs from the trusted operation observation")



def release_file_reference(
    manifest: Mapping[str, Any], path: str, *, release_manifest_evidence: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Derive one file Ref from a fully validated M12 manifest and its bytes.

    File ownership is release + path; content is the exact byte SHA-256 already
    verified at the unique manifest boundary. This is not a notification key.
    """
    validate_contract("ReleaseManifest", manifest, release_manifest_evidence=release_manifest_evidence)
    if manifest["schema_version"] != "2.0.0" or not isinstance(path, str) or path not in M12_RELEASE_FILES:
        raise ContractError("file references require a fixed M12 release file")
    entry = next(item for item in manifest["files"] if item["path"] == path)
    identity = {
        "release_ref": {"id": manifest["release_id"], "content_fingerprint": manifest["content_fingerprint"]},
        "path": path, "sha256": entry["sha256"], "size_bytes": entry["size_bytes"],
    }
    fingerprint = "sha256:" + hashlib.sha256(_canonical(identity)).hexdigest()
    return {"id": "release-file:" + fingerprint, "content_fingerprint": entry["sha256"]}


M12_POINTER_FIELDS = frozenset({
    "schema_version", "generation", "visible", "last_verified", "phase",
    "pending_receipt_ref", "last_receipt_ref", "updated_at",
})


def _m12_pointer_fields(payload: Mapping[str, Any]) -> None:
    _m12_exact(payload, set(M12_POINTER_FIELDS), "CurrentPointer")
    if payload["schema_version"] != "1.0.0":
        raise ContractError("unsupported CurrentPointer version")
    _m12_uint(payload["generation"])
    _m12_time(payload["updated_at"])
    for key in ("visible", "last_verified"):
        if payload[key] is not None:
            _m12_pointer_target(payload[key])
    for key in ("pending_receipt_ref", "last_receipt_ref"):
        if payload[key] is not None:
            _m12_ref(payload[key])
    phase = payload["phase"]
    if phase == "empty":
        if payload["generation"] != 0 or any(payload[k] is not None for k in ("visible", "last_verified", "pending_receipt_ref", "last_receipt_ref")):
            raise ContractError("empty pointer cannot contain a visible target or history")
    elif phase in ("verified", "switching", "rollback_pending"):
        if payload["generation"] == 0 or payload["visible"] is None or payload["last_verified"] is None:
            raise ContractError("nonempty pointer needs visible and verified fallback targets")
        if phase == "verified":
            if payload["visible"] != payload["last_verified"] or payload["pending_receipt_ref"] is not None:
                raise ContractError("verified pointer must equal its verified target with no pending action")
            if payload["visible"]["kind"] == "release" and payload["last_receipt_ref"] is None:
                raise ContractError("verified release requires an online receipt")
        elif payload["pending_receipt_ref"] is None or payload["last_receipt_ref"] is None:
            raise ContractError("incomplete transition requires its durable receipt references")
    else:
        raise ContractError("unknown pointer phase")


def current_pointer_body(evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    """Derive the singleton state from a trusted prior state and validated receipt.

    The future coordinator must load that prior state under its lock and enforce
    the live lease/fence and CAS. This pure transition is not a database write.
    Bootstrap evidence must attest an archived and verified legacy fallback.
    """
    _m12_exact(evidence, {
        "operation", "previous", "expected_generation", "updated_at", "receipt", "receipt_evidence", "bootstrap",
    }, "trusted pointer transition")
    _m12_uint(evidence["expected_generation"])
    _m12_time(evidence["updated_at"])
    previous = evidence["previous"]
    operation = evidence["operation"]
    if operation == "initialize":
        if previous is not None or evidence["expected_generation"] != 0 or any(evidence[k] is not None for k in ("receipt", "receipt_evidence", "bootstrap")):
            raise ContractError("initialize cannot overwrite existing state or imply an action")
        return {"schema_version": "1.0.0", "generation": 0, "visible": None, "last_verified": None,
                "phase": "empty", "pending_receipt_ref": None, "last_receipt_ref": None, "updated_at": evidence["updated_at"]}
    _m12_pointer_fields(previous)
    if evidence["expected_generation"] != previous["generation"]:
        raise ContractError("pointer expected_generation is stale")
    if evidence["updated_at"] < previous["updated_at"]:
        raise ContractError("pointer transition cannot move time backwards")
    result = dict(previous)
    result["updated_at"] = evidence["updated_at"]
    if operation == "bootstrap":
        if previous["phase"] != "empty" or evidence["receipt"] is not None or evidence["receipt_evidence"] is not None:
            raise ContractError("bootstrap only installs the first verified legacy fallback")
        bootstrap = evidence["bootstrap"]
        _m12_exact(bootstrap, {"target", "verification_ref"}, "legacy bootstrap evidence")
        _m12_pointer_target(bootstrap["target"])
        _m12_ref(bootstrap["verification_ref"])
        if bootstrap["target"]["kind"] != "legacy":
            raise ContractError("new releases cannot bypass promotion via bootstrap")
        result.update(generation=1, visible=bootstrap["target"], last_verified=bootstrap["target"], phase="verified")
        return result
    if operation != "apply_receipt" or evidence["bootstrap"] is not None:
        raise ContractError("unknown pointer operation or mixed bootstrap/receipt")
    receipt = evidence["receipt"]
    validate_contract("PublicationReceipt", receipt, publication_receipt_evidence=evidence["receipt_evidence"])
    reference = {"id": receipt["receipt_id"], "content_fingerprint": receipt["content_fingerprint"]}
    if evidence["updated_at"] < receipt["occurred_at"]:
        raise ContractError("pointer update cannot precede its receipt observation")
    if previous["last_receipt_ref"] == reference:
        return dict(previous)  # Lost-response retry: preserve generation and timestamp.
    kind, details, success = receipt["kind"], receipt["details"], receipt["outcome"] == "success"
    if kind not in ("promote", "online", "rollback"):
        raise ContractError("only switch and online receipts update CurrentPointer")
    if previous["phase"] == "empty":
        raise ContractError("a release requires an archived verified fallback first")
    result["last_receipt_ref"] = reference
    if kind in ("promote", "rollback"):
        if details["before"] != previous["visible"] or details["expected_generation"] != previous["generation"]:
            raise ContractError("switch receipt does not match the current target/generation")
        if kind == "promote":
            if previous["phase"] != "verified":
                raise ContractError("cannot publish over an incomplete or failed transition")
            fallback = previous["last_verified"]
            expected_prior_release = fallback["release_ref"] if fallback["kind"] == "release" else None
            if evidence["receipt_evidence"]["release"]["previous_release_ref"] != expected_prior_release:
                raise ContractError("manifest predecessor differs from the pointer's verified fallback")
        else:
            if previous["phase"] not in ("switching", "rollback_pending") or details["after"] != previous["last_verified"]:
                raise ContractError("rollback may only restore the saved verified fallback")
        if success:
            result.update(generation=details["resulting_generation"], visible=details["after"],
                          phase="switching", pending_receipt_ref=reference)
        elif kind == "rollback":
            result.update(phase="rollback_pending", pending_receipt_ref=reference)
        # Failed promote leaves the prior verified target/phase/generation intact.
    else:
        if previous["phase"] not in ("switching", "rollback_pending"):
            raise ContractError("online completion requires an in-progress transition")
        if details["target"] != previous["visible"] or details["pointer_generation"] != previous["generation"]:
            raise ContractError("online receipt checks another target or generation")
        if success:
            if previous["phase"] == "rollback_pending" and previous["visible"] != previous["last_verified"]:
                raise ContractError("failed candidate must roll back before resuming publication")
            result.update(last_verified=previous["visible"], phase="verified", pending_receipt_ref=None)
        else:
            result.update(phase="rollback_pending", pending_receipt_ref=reference)
    return result


def _validate_current_pointer(payload: Mapping[str, Any], evidence: Mapping[str, Any] | None) -> None:
    _m12_pointer_fields(payload)
    if _canonical(payload) != _canonical(current_pointer_body(evidence)):
        raise ContractError("CurrentPointer differs from its trusted transition")
