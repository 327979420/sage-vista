"""Strict versioned configuration for the M10-E research orchestrator.

The configuration contains orchestration facts only.  It selects exactly one
existing M10 result family and never implements an evaluation algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from services.contracts.market_data import canonical_fingerprint, require_date
from services.contracts.validation import ContractError


RESEARCH_RUN_CONFIG_SCHEMA_VERSION = "2.0.0"
M10_E_SOURCE_VERSION = "m10-e-cli-1.0.0"
M10_E_ORCHESTRATOR_ENGINE = {
    "name": "sage-vista-m10e-orchestrator",
    "version": "1.0.0",
    "adapter_version": "cli-1.0.0",
}
CONFIG_ID = re.compile(r"^research-run-config:sha256:[0-9a-f]{64}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
STABLE_ID = re.compile(r"^[a-z][a-z0-9-]*:sha256:[0-9a-f]{64}$")
GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")

OPERATIONS = {
    "forward_evaluation": {
        "contract": "ForwardOutcome",
        "schema": "2.1.0",
        "producer": "m10-b-internal-1.1.0",
        "engine": ("sage-vista-internal-baseline", "1.0.0", "internal-1.0.0"),
        "policies": {"adjustment", "evaluation", "forward_window", "partition"},
        "count": 5,
        "windows": [1, 5, 20, 60, 100],
    },
    "trade_evaluation": {
        "contract": "TradeOutcome",
        "schema": "2.0.0",
        "producer": "m10-b-internal-1.1.0",
        "engine": ("sage-vista-internal-baseline", "1.0.0", "internal-1.0.0"),
        "policies": {"adjustment", "evaluation", "execution", "partition"},
        "count": 1,
        "windows": [],
    },
    "portfolio_boundary": {
        "contract": "PortfolioRun",
        "schema": "2.1.0",
        "producer": "m10-c-readonly-1.0.0",
        "engine": ("sage-vista-readonly-aggregate", "1.0.0", "shadow-1.0.0"),
        "policies": {"adjustment", "aggregation", "evaluation", "execution", "partition"},
        "count": 1,
        "windows": [],
    },
    "research_aggregate": {
        "contract": "ResearchAggregate",
        "schema": "2.1.0",
        "producer": "m10-c-readonly-1.0.0",
        "engine": ("sage-vista-readonly-aggregate", "1.0.0", "shadow-1.0.0"),
        "policies": {"adjustment", "aggregation", "evaluation", "partition"},
        "count": 1,
        "windows": [],
    },
}

_FIELDS = {
    "schema_version", "source_version", "config_id",
    "config_content_fingerprint", "operation_type", "as_of",
    "evidence_window", "path_status", "result_role", "partition_role",
    "bias_labels", "universe_ref", "market_snapshot_ref",
    "adjustment_policy_ref", "selection_refs", "execution_refs",
    "input_selector", "policy_refs", "engine", "producer_source_version",
    "output_contract", "storage", "export_plan", "resume", "work_units",
    "expected_results", "code_commit",
}
_DYNAMIC_ALIASES = {"latest", "today", "current_branch", "latest_manifest"}


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


def _exact(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object")
    missing = sorted(fields - set(value))
    unknown = sorted(set(value) - fields)
    if missing:
        raise ContractError(f"{label} missing fields: {', '.join(missing)}")
    if unknown:
        raise ContractError(f"{label} unknown fields: {', '.join(unknown)}")
    return _plain(value)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    if value.strip().lower() in _DYNAMIC_ALIASES:
        raise ContractError(f"{field} cannot use a dynamic alias")
    return value


def _sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ContractError(f"{field} must be sha256:<64 lowercase hex>")
    return value


def _stable_ref(value: Any, label: str) -> dict[str, str]:
    item = _exact(value, {"id", "content_fingerprint"}, label)
    if not isinstance(item["id"], str) or not STABLE_ID.fullmatch(item["id"]):
        raise ContractError(f"{label}.id must be a stable content-addressed ID")
    _sha(item["content_fingerprint"], f"{label}.content_fingerprint")
    return item


def _refs(value: Any, label: str, *, allow_empty: bool = True) -> list[dict[str, str]]:
    if not isinstance(value, (list, tuple)) or (not allow_empty and not value):
        raise ContractError(f"{label} must be a list")
    normalized = [_stable_ref(item, label) for item in value]
    keys = [(item["id"], item["content_fingerprint"]) for item in normalized]
    if len(keys) != len(set(keys)) or len({item[0] for item in keys}) != len(keys):
        raise ContractError(f"{label} contains duplicate or conflicting references")
    return sorted(normalized, key=lambda item: (item["id"], item["content_fingerprint"]))


def _policy_refs(value: Any, expected: set[str]) -> list[dict[str, str]]:
    if not isinstance(value, (list, tuple)):
        raise ContractError("policy_refs must be a list")
    normalized: list[dict[str, str]] = []
    for raw in value:
        item = _exact(
            raw,
            {"policy_kind", "policy_version", "policy_fingerprint"},
            "policy_ref",
        )
        kind = _text(item["policy_kind"], "policy_kind")
        version = _text(item["policy_version"], "policy_version")
        if version.strip().lower() in _DYNAMIC_ALIASES:
            raise ContractError("policy_version cannot be dynamic")
        _sha(item["policy_fingerprint"], "policy_fingerprint")
        normalized.append(item)
    kinds = [item["policy_kind"] for item in normalized]
    if len(kinds) != len(set(kinds)) or set(kinds) != expected:
        raise ContractError("policy_refs do not exactly match the selected operation")
    return sorted(normalized, key=lambda item: item["policy_kind"])


def _source_version(value: Any) -> dict[str, str]:
    item = _exact(value, {"evaluation_contracts"}, "source_version")
    if item["evaluation_contracts"] != M10_E_SOURCE_VERSION:
        raise ContractError("ResearchRunConfig source_version is not approved")
    return item


def _normalize(values: Mapping[str, Any], *, derived: bool) -> dict[str, Any]:
    payload = _plain(values)
    if not derived:
        payload.pop("config_id", None)
        payload.pop("config_content_fingerprint", None)
    required = _FIELDS if derived else _FIELDS - {"config_id", "config_content_fingerprint"}
    _exact(payload, required, "ResearchRunConfig 2.0.0")
    if payload["schema_version"] != RESEARCH_RUN_CONFIG_SCHEMA_VERSION:
        raise ContractError("ResearchRunConfig schema version is unknown")
    payload["source_version"] = _source_version(payload["source_version"])
    operation = _text(payload["operation_type"], "operation_type")
    if operation not in OPERATIONS:
        raise ContractError("ResearchRunConfig operation_type is unknown")
    spec = OPERATIONS[operation]
    payload["as_of"] = require_date(payload["as_of"], "ResearchRunConfig.as_of")
    window = _exact(payload["evidence_window"], {"start", "end"}, "evidence_window")
    window["start"] = require_date(window["start"], "evidence_window.start")
    window["end"] = require_date(window["end"], "evidence_window.end")
    if window["start"] > window["end"] or window["end"] > payload["as_of"]:
        raise ContractError("ResearchRunConfig evidence_window is invalid")
    payload["evidence_window"] = window
    if payload["path_status"] != "formal" or payload["result_role"] != "authoritative":
        raise ContractError("M10-E first version accepts only formal authoritative runs")
    if payload["partition_role"] not in {"development", "validation", "forward"}:
        raise ContractError("ResearchRunConfig partition_role is invalid")
    if not isinstance(payload["bias_labels"], (list, tuple)) or not all(
        isinstance(item, str) and item for item in payload["bias_labels"]
    ):
        raise ContractError("bias_labels must be a string list")
    payload["bias_labels"] = sorted(set(payload["bias_labels"]))
    if payload["bias_labels"]:
        raise ContractError("formal M10-E config cannot contain bias labels")
    for field in ("universe_ref", "market_snapshot_ref", "adjustment_policy_ref"):
        if payload[field] is not None:
            payload[field] = _stable_ref(payload[field], field)
    baseline_operation = operation in {"forward_evaluation", "trade_evaluation"}
    evidence_refs = (
        payload["universe_ref"], payload["market_snapshot_ref"],
        payload["adjustment_policy_ref"],
    )
    if baseline_operation and any(item is None for item in evidence_refs):
        raise ContractError("M10-B config requires universe, market, and adjustment evidence")
    if not baseline_operation and any(item is not None for item in evidence_refs):
        raise ContractError("M10-C config must not fabricate M02 evidence references")
    payload["selection_refs"] = _refs(payload["selection_refs"], "selection_refs")
    payload["execution_refs"] = _refs(payload["execution_refs"], "execution_refs")
    if operation == "forward_evaluation" and not payload["selection_refs"]:
        raise ContractError("Forward config requires selection evidence")
    if operation == "trade_evaluation" and (
        not payload["selection_refs"] or not payload["execution_refs"]
    ):
        raise ContractError("Trade config requires selection and execution evidence")
    if operation in {"portfolio_boundary", "research_aggregate"} and (
        payload["selection_refs"] or payload["execution_refs"]
    ):
        raise ContractError("M10-C config accepts only persisted Outcome input refs")
    selector = _exact(
        payload["input_selector"],
        {"mode", "refs", "bundle_path", "bundle_sha256", "query"},
        "input_selector",
    )
    selector["mode"] = _text(selector["mode"], "input_selector.mode")
    selector["refs"] = _refs(selector["refs"], "input_selector.refs")
    if selector["mode"] == "bundle":
        if not selector["refs"]:
            raise ContractError("bundle input_selector requires explicit references")
        _text(selector["bundle_path"], "input_selector.bundle_path")
        _sha(selector["bundle_sha256"], "input_selector.bundle_sha256")
        if selector["query"] is not None:
            raise ContractError("bundle input_selector cannot contain a query")
    elif selector["mode"] == "query":
        if operation not in {"portfolio_boundary", "research_aggregate"}:
            raise ContractError("query input_selector is only valid for persisted M10 Outcomes")
        if selector["refs"]:
            raise ContractError("query input_selector cannot also contain explicit refs")
        if selector["bundle_path"] is not None or selector["bundle_sha256"] is not None:
            raise ContractError("query input_selector cannot contain a bundle")
        if not isinstance(selector["query"], Mapping):
            raise ContractError("query input_selector requires a complete query")
        from .query import validate_evaluation_query

        validate_evaluation_query(selector["query"])
    else:
        raise ContractError("input_selector.mode is unknown")
    payload["input_selector"] = selector
    expected_policy_kinds = set(spec["policies"])
    expected_result_input = payload["expected_results"]
    if (
        operation == "research_aggregate"
        and isinstance(expected_result_input, Mapping)
        and expected_result_input.get("source_result_contract") == "ForwardOutcome"
    ):
        expected_policy_kinds.add("forward_window")
    elif (
        operation == "research_aggregate"
        and isinstance(expected_result_input, Mapping)
        and expected_result_input.get("source_result_contract") == "TradeOutcome"
    ):
        expected_policy_kinds.add("execution")
    payload["policy_refs"] = _policy_refs(payload["policy_refs"], expected_policy_kinds)
    engine = _exact(payload["engine"], {"name", "version", "adapter_version"}, "engine")
    if (engine["name"], engine["version"], engine["adapter_version"]) != spec["engine"]:
        raise ContractError("ResearchRunConfig engine does not match its operation")
    payload["engine"] = engine
    if payload["producer_source_version"] != spec["producer"]:
        raise ContractError("producer_source_version does not match its operation")
    output = _exact(payload["output_contract"], {"name", "schema_version", "source_version"}, "output_contract")
    if (output["name"], output["schema_version"], output["source_version"]) != (
        spec["contract"], spec["schema"], spec["producer"]
    ):
        raise ContractError("output_contract does not match its operation")
    payload["output_contract"] = output
    storage = _exact(payload["storage"], {"root_kind", "root_path"}, "storage")
    if storage["root_kind"] not in {"temporary", "workspace_work"}:
        raise ContractError("storage.root_kind is not an approved shadow root")
    _text(storage["root_path"], "storage.root_path")
    payload["storage"] = storage
    export_plan = _exact(payload["export_plan"], {"enabled", "query", "config", "formats", "output_root"}, "export_plan")
    if not isinstance(export_plan["enabled"], bool):
        raise ContractError("export_plan.enabled must be boolean")
    if export_plan["enabled"]:
        if not isinstance(export_plan["query"], Mapping) or not isinstance(export_plan["config"], Mapping):
            raise ContractError("enabled export_plan requires full query and export config")
        if not isinstance(export_plan["formats"], (list, tuple)) or not export_plan["formats"]:
            raise ContractError("enabled export_plan requires formats")
        export_plan["formats"] = sorted(set(export_plan["formats"]))
        if any(item not in {"csv", "xlsx"} for item in export_plan["formats"]):
            raise ContractError("export_plan format is unknown")
        _text(export_plan["output_root"], "export_plan.output_root")
        from .export import validate_export_config
        from .query import validate_evaluation_query

        validate_evaluation_query(export_plan["query"])
        validate_export_config(export_plan["config"])
        if export_plan["formats"] != list(export_plan["config"]["formats"]):
            raise ContractError("export_plan formats differ from ExportConfig")
    elif any(export_plan[field] is not None for field in ("query", "config", "output_root")) or export_plan["formats"] != []:
        raise ContractError("disabled export_plan must not contain export inputs")
    payload["export_plan"] = export_plan
    resume = _exact(payload["resume"], {"mode", "parent_run_id", "checkpoint_ref"}, "resume")
    if resume["mode"] == "fresh":
        if resume["parent_run_id"] is not None or resume["checkpoint_ref"] is not None:
            raise ContractError("fresh config cannot contain resume evidence")
    elif resume["mode"] == "checkpoint":
        if not isinstance(resume["parent_run_id"], str) or not STABLE_ID.fullmatch(resume["parent_run_id"]):
            raise ContractError("checkpoint resume requires parent_run_id")
        resume["checkpoint_ref"] = _stable_ref(resume["checkpoint_ref"], "resume.checkpoint_ref")
    else:
        raise ContractError("resume.mode is unknown")
    payload["resume"] = resume
    if not isinstance(payload["work_units"], (list, tuple)) or not payload["work_units"]:
        raise ContractError("work_units must be a non-empty ordered list")
    units: list[dict[str, Any]] = []
    seen_units: set[str] = set()
    for raw in payload["work_units"]:
        item = _exact(raw, {"work_unit_id", "start", "end", "input_refs"}, "work_unit")
        unit_id = _text(item["work_unit_id"], "work_unit_id")
        if unit_id in seen_units:
            raise ContractError("work_units contain duplicate IDs")
        seen_units.add(unit_id)
        item["start"] = require_date(item["start"], "work_unit.start")
        item["end"] = require_date(item["end"], "work_unit.end")
        if item["start"] > item["end"]:
            raise ContractError("work_unit range is invalid")
        item["input_refs"] = _refs(item["input_refs"], "work_unit.input_refs", allow_empty=False)
        units.append(item)
    payload["work_units"] = units
    unit_refs = sorted(
        [item for unit in units for item in unit["input_refs"]],
        key=lambda item: (item["id"], item["content_fingerprint"]),
    )
    if len({item["id"] for item in unit_refs}) != len(unit_refs):
        raise ContractError("work units cannot claim the same input reference twice")
    if selector["mode"] == "bundle" and unit_refs != selector["refs"]:
        raise ContractError("bundle input refs must equal the complete work-unit inputs")
    expected = _exact(
        payload["expected_results"],
        {
            "contract", "schema_version", "source_version", "per_work_unit_count",
            "forward_windows", "source_result_contract",
        },
        "expected_results",
    )
    if (
        expected["contract"] != spec["contract"]
        or expected["schema_version"] != spec["schema"]
        or expected["source_version"] != spec["producer"]
        or expected["per_work_unit_count"] != spec["count"]
        or expected["forward_windows"] != spec["windows"]
    ):
        raise ContractError("expected_results does not match the selected operation")
    source_result_contract = expected["source_result_contract"]
    if operation in {"forward_evaluation", "trade_evaluation"}:
        if source_result_contract is not None:
            raise ContractError("baseline expected_results cannot name a source result contract")
    elif operation == "portfolio_boundary":
        if source_result_contract != "TradeOutcome":
            raise ContractError("PortfolioRun requires TradeOutcome source results")
    elif source_result_contract not in {"ForwardOutcome", "TradeOutcome"}:
        raise ContractError("ResearchAggregate source result contract is invalid")
    payload["expected_results"] = expected
    if not isinstance(payload["code_commit"], str) or not GIT_COMMIT.fullmatch(payload["code_commit"]):
        raise ContractError("code_commit must be a full Git commit")
    return payload


def _semantic(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _plain(value)
        for key, value in payload.items()
        if key not in {"config_id", "config_content_fingerprint"}
    }


def build_research_run_config(**values: Any) -> Mapping[str, Any]:
    payload = _normalize(values, derived=False)
    fingerprint = canonical_fingerprint(_semantic(payload))
    payload["config_id"] = "research-run-config:" + fingerprint
    payload["config_content_fingerprint"] = fingerprint
    validate_research_run_config(payload)
    return _freeze(payload)


def validate_research_run_config(payload: Mapping[str, Any]) -> None:
    normalized = _normalize(payload, derived=True)
    semantic = _semantic(normalized)
    fingerprint = canonical_fingerprint(semantic)
    if normalized["config_content_fingerprint"] != fingerprint:
        raise ContractError("ResearchRunConfig content fingerprint is invalid")
    if normalized["config_id"] != "research-run-config:" + fingerprint or not CONFIG_ID.fullmatch(normalized["config_id"]):
        raise ContractError("ResearchRunConfig ID does not match its content")
    if normalized != _plain(payload):
        raise ContractError("ResearchRunConfig is not canonically normalized")


def is_m10e_receipt_candidate(payload: Mapping[str, Any]) -> bool:
    source = payload.get("source_version")
    engine = payload.get("engine")
    source_value = source.get("evaluation_contracts") if isinstance(source, Mapping) else None
    engine_name = engine.get("name") if isinstance(engine, Mapping) else None
    return (
        isinstance(source_value, str) and source_value.startswith("m10-e-cli-")
    ) or engine_name == M10_E_ORCHESTRATOR_ENGINE["name"]


def validate_m10e_receipt_identity(payload: Mapping[str, Any]) -> None:
    """Validate the one approved M10-E ExperimentRun receipt identity."""

    from .contracts import validate_experiment_run

    validate_experiment_run(payload)
    if payload["source_version"] != {"evaluation_contracts": M10_E_SOURCE_VERSION}:
        raise ContractError("M10-E ExperimentRun source version is invalid")
    if _plain(payload["engine"]) != M10_E_ORCHESTRATOR_ENGINE:
        raise ContractError("M10-E ExperimentRun engine identity is invalid")
    config = payload["config_ref"]
    if (
        config["config_version"] != RESEARCH_RUN_CONFIG_SCHEMA_VERSION
        or not CONFIG_ID.fullmatch(config["config_id"])
    ):
        raise ContractError("M10-E ExperimentRun config reference is invalid")


def _pairs_no_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"strict JSON contains duplicate key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ContractError(f"strict JSON rejects non-finite value: {value}")


def load_strict_json_object(path: str | Path) -> Mapping[str, Any]:
    source = Path(path)
    try:
        raw = source.read_text(encoding="utf-8")
        payload = json.loads(
            raw,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=_reject_constant,
        )
    except ContractError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("ResearchRunConfig is not strict UTF-8 JSON") from exc
    if not isinstance(payload, Mapping):
        raise ContractError("strict JSON root must be an object")
    return _freeze(payload)


def load_research_run_config(path: str | Path) -> Mapping[str, Any]:
    payload = load_strict_json_object(path)
    validate_research_run_config(payload)
    return payload


def config_resume_scope_fingerprint(config: Mapping[str, Any]) -> str:
    """Bind all resumable facts while excluding the explicit resume pointer."""

    validate_research_run_config(config)
    return canonical_fingerprint({
        key: _plain(value) for key, value in config.items()
        if key not in {"config_id", "config_content_fingerprint", "resume"}
    })


@dataclass(frozen=True)
class GitState:
    head: str
    worktree_clean: bool
    index_clean: bool


def current_git_state(repo_root: str | Path) -> GitState:
    root = Path(repo_root)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        text=True, capture_output=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain=v1"], cwd=root, check=True,
        text=True, capture_output=True,
    ).stdout.splitlines()
    index_clean = not any(line and line[0] not in {" ", "?"} for line in status)
    worktree_clean = not any(line and (line[1] != " " or line.startswith("??")) for line in status)
    return GitState(head=head, worktree_clean=worktree_clean, index_clean=index_clean)


def validate_formal_git_state(
    config: Mapping[str, Any],
    *,
    repo_root: str | Path,
    state_provider: Callable[[str | Path], GitState] = current_git_state,
) -> None:
    validate_research_run_config(config)
    state = state_provider(repo_root)
    if state.head != config["code_commit"]:
        raise ContractError("formal run code_commit does not match HEAD")
    if not state.worktree_clean or not state.index_clean:
        raise ContractError("formal run requires a clean worktree and index")


__all__ = [
    "GitState", "M10_E_ORCHESTRATOR_ENGINE", "M10_E_SOURCE_VERSION", "OPERATIONS",
    "RESEARCH_RUN_CONFIG_SCHEMA_VERSION", "build_research_run_config",
    "config_resume_scope_fingerprint", "current_git_state",
    "is_m10e_receipt_candidate", "load_research_run_config",
    "load_strict_json_object", "validate_formal_git_state",
    "validate_m10e_receipt_identity", "validate_research_run_config",
]
