"""The one read-only adapter registry for current legacy JSON artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from .validation import ContractError


ADAPTER_VERSION = "legacy-adapter-1.0.0"


@dataclass(frozen=True)
class AdaptedArtifact:
    path: str
    contract_types: tuple[str, ...]
    schema_version: str
    adapter_version: str
    source_version: Mapping[str, Any]
    temporal_class: str
    as_of: str | None
    generated_at: str
    future_data_used: bool | None
    coverage_end: str | None = None
    source_experiment: str | None = None
    validation_scope: str = "registered_legacy_shape"
    warnings: tuple[str, ...] = ()


def _utc(value: Any) -> str:
    if not isinstance(value, str):
        raise ContractError("legacy artifact lacks generated_at evidence")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("legacy generated_at is not a valid timestamp") from exc
    if parsed.tzinfo is None:
        raise ContractError("legacy generated_at lacks timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _date(payload: Mapping[str, Any], key: str = "as_of") -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ContractError(f"legacy artifact lacks {key} evidence")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"legacy artifact has invalid {key} evidence") from exc
    if parsed.isoformat() != value:
        raise ContractError(f"legacy artifact has non-canonical {key} evidence")
    return value


def _false(payload: Mapping[str, Any], key: str = "future_data_used") -> bool:
    value = payload.get(key)
    if value is not False:
        raise ContractError(f"legacy {key} is missing or not explicitly false")
    return False


def _favorite_future(payload: Mapping[str, Any]) -> bool:
    ready = payload.get("entry_ready_candidates", [])
    near = payload.get("near_matches", [])
    if not isinstance(ready, list) or not isinstance(near, list):
        raise ContractError("favorite-pattern candidate collections must be lists")
    records = ready + near
    if not records:
        raise ContractError("favorite-pattern has no records carrying future-data audits")
    if any(
        not isinstance(item, Mapping)
        or not isinstance(item.get("audit"), Mapping)
        or item["audit"].get("future_data_used") is not False
        for item in records
    ):
        raise ContractError("favorite-pattern record lacks explicit future-data evidence")
    return False


def _nested_future_false(payload: Mapping[str, Any]) -> bool:
    values: list[Any] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key in {"future_data_used", "future_rows_used"}:
                    values.append(child)
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    if not values or any(value is not False for value in values):
        raise ContractError("legacy artifact lacks consistent nested future-data evidence")
    return False


def _verified_future_false(payload: Mapping[str, Any]) -> bool:
    """Require both a verified receipt and its explicit look-ahead evidence."""

    if payload.get("live_verified") is not True:
        raise ContractError("production receipt is not verified")
    return _false(payload)


def _coverage_end(payload: Mapping[str, Any]) -> str:
    coverage = payload.get("coverage")
    if not isinstance(coverage, Mapping):
        raise ContractError("legacy artifact lacks coverage")
    return _date(coverage, "end")


def _generated_from_update(payload: Mapping[str, Any]) -> str:
    value = payload.get("last_successful_update_at")
    return _utc(value) if value is not None else "unknown"


def _generated_from_state(payload: Mapping[str, Any]) -> str:
    return _utc(payload.get("updated_at"))


Spec = tuple[tuple[str, ...], Callable[[Mapping[str, Any]], str], Callable[[Mapping[str, Any]], str], Callable[[Mapping[str, Any]], bool], Callable[[Mapping[str, Any]], Mapping[str, Any]]]


def _source(**values: str) -> Callable[[Mapping[str, Any]], Mapping[str, Any]]:
    return lambda payload: {name: payload.get(field) for name, field in values.items() if payload.get(field) is not None}


SPECS: dict[str, Spec] = {
    "update-status.json": (("ReleaseManifest",), lambda p: _date(p, "source_latest_complete_date"), _generated_from_update, _false, _source(provider="provider")),
    "unified-v2-latest.json": (("ModelAssessment", "TradePlan"), _coverage_end, lambda p: _utc(p.get("generated_at")), _false, _source(model="version")),
    "daily-factor-snapshot.json": (("UniverseSnapshot", "GateEvent", "TechnicalEvidence"), _date, _generated_from_update, _false, _source(registry="registry_version", snapshot="snapshot_mode_version")),
    "favorite-pattern.json": (("ModelAssessment", "TradePlan"), _date, _generated_from_update, _favorite_future, _source(model="pattern_version", generalization="generalization_version")),
    "market-etf-watch.json": (("ContextSnapshot",), _date, lambda p: _utc(p.get("generated_at")), _false, _source(mode="mode")),
    "industry-radar.json": (("ContextSnapshot",), _date, lambda p: _utc(p.get("generated_at")), _false, _source(membership="membership_version", mode="mode")),
    "opportunity-ledger.json": (("OpportunityEvent",), _date, lambda p: _utc(p.get("generated_at")), lambda p: _false(p, "selection_future_data_used"), _source(schema="schema_version")),
    "opportunity-ledger-latest.json": (("OpportunityEvent",), _date, lambda p: _utc(p.get("generated_at")), lambda p: _false(p, "selection_future_data_used"), _source(schema="schema_version")),
    "signal-history.json": (("OpportunityEvent",), _date, lambda p: _utc(p.get("generated_at")), _false, _source(schema="signal_schema_version", mode="observation_mode")),
    "signal-history-summary.json": (("OpportunityEvent",), _date, _generated_from_update, _false, lambda p: {"legacy_source_version": "unknown"}),
    "rare-opportunity-radar.json": (("ModelAssessment",), _date, lambda p: _utc(p.get("generated_at")), lambda p: _false(p.get("scan", {})), _source(registry="registry_version", source="factor_source")),
    "resonance-tracker.json": (("ModelAssessment",), _date, lambda p: _utc(p.get("generated_at")), _nested_future_false, lambda p: {"ruleset": p.get("consistency_audit", {}).get("ruleset_version", "unknown")}),
    "unified-v2-rankings.json": (("ModelAssessment", "TradePlan"), _coverage_end, lambda p: _utc(p.get("generated_at")), _false, _source(model="version")),
    "production-state.json": (("ReleaseManifest",), _date, _generated_from_update, _verified_future_false, _source(website="website_version", commit="deployment_commit")),
    # Operational/research state may only claim no look-ahead when the source
    # artifact itself carries that evidence.  Absence is not equivalent to false.
    "backtest-state.json": (("ExperimentRun",), lambda p: _date(p.get("coverage", {}), "end"), _generated_from_state, _false, _source(schema="schema_version", mode="mode")),
    "experiment-catalog.json": (("ExperimentRun",), lambda p: _date_from_timestamp(p.get("generated_at")), lambda p: _utc(p.get("generated_at")), _false, _source(schema="schema_version")),
}


LEGACY_LIST_FIELDS: dict[str, tuple[str, ...]] = {
    "factor-registry.json": ("factors",),
    "daily-factor-snapshot.json": ("symbols",),
    "unified-v2-latest.json": ("days", "factor_registry_versions", "model_versions"),
    "unified-v2-rankings.json": ("days", "factor_registry_versions", "model_versions"),
    "favorite-pattern.json": ("entry_ready_candidates", "near_matches"),
    "market-etf-watch.json": ("funds",),
    "industry-radar.json": ("themes",),
    "opportunity-ledger.json": ("events",),
    "opportunity-ledger-latest.json": ("events",),
    "signal-history.json": ("cases",),
    "signal-history-summary.json": ("cases",),
    "rare-opportunity-radar.json": ("signals",),
    "resonance-tracker.json": ("combined_top10",),
}

LEGACY_MAPPING_FIELDS: dict[str, tuple[str, ...]] = {
    "unified-v2-latest.json": ("coverage",),
    "unified-v2-rankings.json": ("coverage",),
    "market-etf-watch.json": ("layers", "ratios"),
    "industry-radar.json": ("ticker_context",),
    "opportunity-ledger.json": ("coverage",),
    "opportunity-ledger-latest.json": ("coverage",),
    "rare-opportunity-radar.json": ("scan",),
    "resonance-tracker.json": ("details",),
    "decision-summary.json": ("coverage",),
}


def _validate_legacy_shape(name: str, payload: Mapping[str, Any]) -> None:
    """Reject obvious internal corruption before attaching contract labels."""

    for field in LEGACY_LIST_FIELDS.get(name, ()):
        value = payload.get(field)
        if not isinstance(value, list):
            raise ContractError(f"legacy {name} field {field} must be a list")
    for field in LEGACY_MAPPING_FIELDS.get(name, ()):
        value = payload.get(field)
        if not isinstance(value, Mapping):
            raise ContractError(f"legacy {name} field {field} must be an object")
    if name in {"unified-v2-latest.json", "unified-v2-rankings.json"}:
        for field in ("factor_registry_versions", "model_versions"):
            values = payload[field]
            if not values or any(not isinstance(value, str) or not value for value in values):
                raise ContractError(f"legacy {name} field {field} must contain version strings")


def _reject_json_constant(value: str) -> None:
    raise ContractError(f"legacy artifact contains non-JSON numeric value: {value}")


def _date_from_timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise ContractError("legacy artifact lacks timestamp evidence")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError as exc:
        raise ContractError("legacy artifact has invalid timestamp evidence") from exc


def adapt_legacy_bytes(name: str, raw: bytes) -> AdaptedArtifact:
    """Adapt one immutable byte snapshot; callers decide where bytes came from."""

    try:
        payload = json.loads(raw, parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("legacy artifact is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise ContractError("legacy artifact root must be an object")
    _validate_legacy_shape(name, payload)
    if name == "factor-registry.json":
        version = payload.get("registry_version")
        if not isinstance(version, str) or not version:
            raise ContractError("factor registry lacks registry_version")
        return AdaptedArtifact(
            path=name,
            contract_types=("TechnicalEvidence",),
            schema_version="1.0.0",
            adapter_version=ADAPTER_VERSION,
            source_version={"registry": version},
            temporal_class="versioned_config",
            as_of=None,
            generated_at="unknown",
            future_data_used=None,
        )
    if name == "decision-summary.json":
        coverage = payload.get("coverage")
        source_experiment = payload.get("source_experiment")
        if not isinstance(coverage, Mapping) or not isinstance(coverage.get("end"), str):
            raise ContractError("decision summary lacks coverage.end")
        if not isinstance(source_experiment, str) or not source_experiment:
            raise ContractError("decision summary lacks source_experiment")
        return AdaptedArtifact(
            path=name,
            contract_types=("ExperimentRun",),
            schema_version="1.0.0",
            adapter_version=ADAPTER_VERSION,
            source_version={"report": payload.get("version", "unknown")},
            temporal_class="research_summary",
            as_of=None,
            generated_at=_utc(payload.get("generated_at")),
            future_data_used=None,
            coverage_end=coverage["end"],
            source_experiment=source_experiment,
        )
    spec = SPECS.get(name)
    if spec is None:
        raise ContractError(f"no registered adapter for {name}")
    contract_types, as_of, generated_at, future, source = spec
    source_version = source(payload)
    if not source_version:
        raise ContractError("legacy artifact lacks source_version evidence")
    return AdaptedArtifact(
        path=name,
        contract_types=contract_types,
        schema_version="1.0.0",
        adapter_version=ADAPTER_VERSION,
        source_version=source_version,
        temporal_class="daily_snapshot",
        as_of=as_of(payload),
        generated_at=generated_at(payload),
        future_data_used=future(payload),
    )


def adapt_legacy_file(path: Path) -> AdaptedArtifact:
    """Read one registered legacy file once without modifying it."""

    return adapt_legacy_bytes(path.name, path.read_bytes())
