"""The one read-only adapter registry for current legacy JSON artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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


def _utc(value: Any) -> str:
    if not isinstance(value, str):
        raise ContractError("legacy artifact lacks generated_at evidence")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ContractError("legacy generated_at lacks timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _date(payload: Mapping[str, Any], key: str = "as_of") -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ContractError(f"legacy artifact lacks {key} evidence")
    return value


def _false(payload: Mapping[str, Any], key: str = "future_data_used") -> bool:
    value = payload.get(key)
    if value is not False:
        raise ContractError(f"legacy {key} is missing or not explicitly false")
    return False


def _favorite_future(payload: Mapping[str, Any]) -> bool:
    records = list(payload.get("entry_ready_candidates", [])) + list(payload.get("near_matches", []))
    if not records:
        raise ContractError("favorite-pattern has no records carrying future-data audits")
    if any(item.get("audit", {}).get("future_data_used") is not False for item in records):
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
    "production-state.json": (("ReleaseManifest",), _date, _generated_from_update, lambda p: False if p.get("live_verified") is True else (_ for _ in ()).throw(ContractError("production receipt is not verified")), _source(website="website_version", commit="deployment_commit")),
    "backtest-state.json": (("ExperimentRun",), lambda p: _date(p.get("coverage", {}), "end"), _generated_from_state, lambda p: False, _source(schema="schema_version", mode="mode")),
    "experiment-catalog.json": (("ExperimentRun",), lambda p: _date_from_timestamp(p.get("generated_at")), lambda p: _utc(p.get("generated_at")), lambda p: False, _source(schema="schema_version")),
}


def _date_from_timestamp(value: Any) -> str:
    if not isinstance(value, str):
        raise ContractError("legacy artifact lacks timestamp evidence")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()


def adapt_legacy_file(path: Path) -> AdaptedArtifact:
    """Read one registered legacy file without modifying it and expose evidence."""

    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, Mapping):
        raise ContractError("legacy artifact root must be an object")
    if path.name == "factor-registry.json":
        version = payload.get("registry_version")
        if not isinstance(version, str) or not version:
            raise ContractError("factor registry lacks registry_version")
        return AdaptedArtifact(
            path=path.name,
            contract_types=("TechnicalEvidence",),
            schema_version="1.0.0",
            adapter_version=ADAPTER_VERSION,
            source_version={"registry": version},
            temporal_class="versioned_config",
            as_of=None,
            generated_at="unknown",
            future_data_used=None,
        )
    if path.name == "decision-summary.json":
        coverage = payload.get("coverage")
        source_experiment = payload.get("source_experiment")
        if not isinstance(coverage, Mapping) or not isinstance(coverage.get("end"), str):
            raise ContractError("decision summary lacks coverage.end")
        if not isinstance(source_experiment, str) or not source_experiment:
            raise ContractError("decision summary lacks source_experiment")
        return AdaptedArtifact(
            path=path.name,
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
    spec = SPECS.get(path.name)
    if spec is None:
        raise ContractError(f"no registered adapter for {path.name}")
    contract_types, as_of, generated_at, future, source = spec
    source_version = source(payload)
    if not source_version:
        raise ContractError("legacy artifact lacks source_version evidence")
    return AdaptedArtifact(
        path=path.name,
        contract_types=contract_types,
        schema_version="1.0.0",
        adapter_version=ADAPTER_VERSION,
        source_version=source_version,
        temporal_class="daily_snapshot",
        as_of=as_of(payload),
        generated_at=generated_at(payload),
        future_data_used=future(payload),
    )
