"""M10-E configuration-driven orchestration over the existing M10 A-D APIs."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
from types import MappingProxyType
from typing import Any, Callable, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError
from services.execution import EXIT_POLICY, current_exit_state
from services.market_data import RepositoryRead

from .aggregate import (
    build_aggregate_scope,
    build_readonly_pending_run,
    evaluate_portfolio_boundary,
    evaluate_research_aggregate,
    store_readonly_evaluation_batch,
)
from .baseline import (
    BASELINE_ADAPTER_VERSION,
    BASELINE_ENGINE_NAME,
    BASELINE_ENGINE_VERSION,
    baseline_run_scope_fingerprint,
    forward_result_scope_keys,
    market_snapshot_evidence_fingerprint,
    trade_result_scope_keys,
)
from .checkpoint import (
    build_research_run_checkpoint,
    current_research_run_checkpoint,
    validate_research_run_checkpoint,
)
from .config import (
    M10_E_ORCHESTRATOR_ENGINE,
    M10_E_SOURCE_VERSION,
    config_resume_scope_fingerprint,
    load_strict_json_object,
    require_strict_integer,
    validate_formal_git_state,
    validate_research_run_config,
)
from .contracts import (
    RESULT_TYPES,
    build_experiment_run_receipt,
    current_experiment_run,
    current_result,
    validate_result,
)
from .export import publish_audit_export
from .policies import (
    AGGREGATION_POLICY,
    EVALUATION_POLICY,
    FORWARD_WINDOW_POLICY,
    PARTITION_POLICY,
)
from .query import execute_evaluation_query
from .runner import (
    evaluate_forward_baseline,
    evaluate_trade_baseline,
    store_baseline_evaluation_batch,
)
from .storage import EvaluationShadowStore


INPUT_BUNDLE_SCHEMA_VERSION = "1.0.0"
ORCHESTRATOR_ENGINE = {
    **M10_E_ORCHESTRATOR_ENGINE,
}

_LOCKS: dict[str, threading.Lock] = {}
_LOCK_GUARD = threading.Lock()


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
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ContractError(f"{label} fields are incomplete or unknown")
    return _plain(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _canonical_ref(stable_id: str, fingerprint: str) -> dict[str, str]:
    return {"id": stable_id, "content_fingerprint": fingerprint}


def _policy_ref(kind: str, policy: Mapping[str, Any]) -> dict[str, str]:
    version = policy.get("policy_version", policy.get("version"))
    fingerprint = policy.get("policy_fingerprint", canonical_fingerprint(_plain(policy)))
    return {
        "policy_kind": kind,
        "policy_version": str(version),
        "policy_fingerprint": str(fingerprint),
    }


def _expected_policies(
    operation: str,
    *,
    source_result_contract: str | None = None,
) -> list[dict[str, str]]:
    policies = [
        _policy_ref("adjustment", ADJUSTMENT_POLICY),
        _policy_ref("evaluation", EVALUATION_POLICY),
        _policy_ref("partition", PARTITION_POLICY),
    ]
    if operation == "forward_evaluation":
        policies.append(_policy_ref("forward_window", FORWARD_WINDOW_POLICY))
    elif operation == "trade_evaluation":
        policies.append(_policy_ref("execution", EXIT_POLICY))
    else:
        policies.append(_policy_ref("aggregation", AGGREGATION_POLICY))
        if source_result_contract == "ForwardOutcome":
            policies.append(_policy_ref("forward_window", FORWARD_WINDOW_POLICY))
        elif operation == "portfolio_boundary" or source_result_contract == "TradeOutcome":
            policies.append(_policy_ref("execution", EXIT_POLICY))
    return sorted(policies, key=lambda item: item["policy_kind"])


@contextmanager
def _config_lock(config_id: str):
    key = config_id
    with _LOCK_GUARD:
        thread_lock = _LOCKS.setdefault(key, threading.Lock())
    lock_root = Path(tempfile.gettempdir()) / "sage-vista-m10e-run-locks"
    lock_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = lock_root / (hashlib.sha256(key.encode()).hexdigest() + ".lock")
    with thread_lock:
        descriptor = os.open(
            lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def _configured_input_refs(config: Mapping[str, Any]) -> list[dict[str, str]]:
    return sorted(
        [
            _plain(ref)
            for unit in config["work_units"]
            for ref in unit["input_refs"]
        ],
        key=lambda item: (item["id"], item["content_fingerprint"]),
    )


def _persisted_current_outcomes(
    store: EvaluationShadowStore,
    contract_name: str,
    expected_refs: list[Mapping[str, Any]],
    claimed_outcomes: list[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Resolve exact M10-C inputs from the configured authoritative store."""

    if contract_name not in {"ForwardOutcome", "TradeOutcome"}:
        raise ContractError("M10-E M10-C source result family is invalid")
    id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
    claims: dict[tuple[str, str], Mapping[str, Any]] = {}
    for claim in claimed_outcomes:
        validate_result(contract_name, claim)
        key = (str(claim[id_field]), str(claim[fingerprint_field]))
        if key in claims:
            raise ContractError("M10-E source bundle contains duplicate outcomes")
        claims[key] = claim
    expected_keys = {
        (str(item["id"]), str(item["content_fingerprint"]))
        for item in expected_refs
    }
    if set(claims) != expected_keys:
        raise ContractError("M10-E source outcomes differ from configured references")

    inventory = store.capture_inventory()
    records = [
        payload for name, payload in inventory.result_records
        if name == contract_name
    ]
    by_key: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    by_logical: dict[str, list[Mapping[str, Any]]] = {}
    for payload in records:
        key = (str(payload[id_field]), str(payload[fingerprint_field]))
        by_key.setdefault(key, []).append(payload)
        by_logical.setdefault(str(payload["logical_result_id"]), []).append(payload)

    resolved: list[Mapping[str, Any]] = []
    for reference in expected_refs:
        key = (str(reference["id"]), str(reference["content_fingerprint"]))
        matches = by_key.get(key, [])
        if len(matches) != 1:
            raise ContractError("M10-E source outcome is not uniquely persisted")
        stored = matches[0]
        producer_receipts = [
            receipt for receipt in inventory.run_receipts
            if receipt["run_id"] == stored["run_id"]
        ]
        if not producer_receipts:
            raise ContractError("M10-E source outcome has no persisted producer run")
        producer_leaf = current_experiment_run(producer_receipts)
        stored_reference = {
            "id": str(stored[id_field]),
            "content_fingerprint": str(stored[fingerprint_field]),
        }
        if (
            producer_leaf["status"] != "completed"
            or stored_reference not in [_plain(item) for item in producer_leaf["result_refs"]]
        ):
            raise ContractError("M10-E source outcome producer run is not complete")
        leaf = current_result(
            contract_name,
            by_logical[str(stored["logical_result_id"])],
        )
        if str(leaf[id_field]) != str(stored[id_field]):
            raise ContractError("M10-E source outcome is not the configured current revision")
        if _plain(claims[key]) != _plain(stored):
            raise ContractError("M10-E source outcome copy differs from persisted evidence")
        resolved.append(stored)
    return resolved


def load_input_bundle(
    config: Mapping[str, Any],
    *,
    store: EvaluationShadowStore | None = None,
) -> Mapping[str, Any]:
    validate_research_run_config(config)
    selector = config["input_selector"]
    if selector["mode"] == "query":
        if store is None:
            raise ContractError("query input_selector requires the configured M10 store")
        execution = execute_evaluation_query(
            store, selector["query"], code_commit=config["code_commit"]
        )
        expected_contract = config["expected_results"]["source_result_contract"]
        actual = {
            (str(payload[RESULT_TYPES[contract][0]]), str(payload[RESULT_TYPES[contract][1]])): (
                contract,
                payload,
            )
            for contract, payload in execution.results
        }
        expected_refs = _configured_input_refs(config)
        if set(actual) != {
            (item["id"], item["content_fingerprint"]) for item in expected_refs
        }:
            raise ContractError("M10-E query results differ from configured work inputs")
        work_items: list[dict[str, Any]] = []
        for unit in config["work_units"]:
            selected = [
                actual[(item["id"], item["content_fingerprint"])]
                for item in unit["input_refs"]
            ]
            if any(contract != expected_contract for contract, _ in selected):
                raise ContractError("M10-E query selected a different result family")
            outcomes = _persisted_current_outcomes(
                store,
                str(expected_contract),
                [_plain(item) for item in unit["input_refs"]],
                [payload for _, payload in selected],
            )
            first = outcomes[0]
            if expected_contract == "ForwardOutcome":
                scope = build_aggregate_scope(
                    source_result_type="forward_outcome",
                    window_sessions=int(first["window_sessions"]),
                    path_status=str(first["path_status"]),
                    result_role=str(first["result_role"]),
                    partition_role=str(first["partition_role"]),
                )
            else:
                scope = build_aggregate_scope(
                    source_result_type="trade_outcome",
                    window_sessions=None,
                    path_status=str(first["path_status"]),
                    result_role=str(first["result_role"]),
                    partition_role=str(first["partition_role"]),
                    execution_policy=first["execution_policy"],
                    cost_policy=first["cost_policy"],
                )
            arguments = (
                {"trade_outcomes": outcomes, "scope": _plain(scope)}
                if config["operation_type"] == "portfolio_boundary"
                else {"outcomes": outcomes, "scope": _plain(scope)}
            )
            work_items.append({
                "work_unit_id": unit["work_unit_id"],
                "arguments": arguments,
            })
        return {
            "schema_version": INPUT_BUNDLE_SCHEMA_VERSION,
            "operation_type": config["operation_type"],
            "input_refs": expected_refs,
            "work_items": work_items,
        }
    if selector["mode"] != "bundle":
        raise ContractError("M10-E input selector mode is unsupported")
    path = Path(selector["bundle_path"])
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ContractError("M10-E input bundle is unavailable") from exc
    if path.is_symlink() or _sha_bytes(raw) != selector["bundle_sha256"]:
        raise ContractError("M10-E input bundle hash does not match the config")
    bundle = load_strict_json_object(path)
    item = _exact(
        bundle,
        {"schema_version", "operation_type", "input_refs", "work_items"},
        "M10-E input bundle",
    )
    if item["schema_version"] != INPUT_BUNDLE_SCHEMA_VERSION or item["operation_type"] != config["operation_type"]:
        raise ContractError("M10-E input bundle version or operation is wrong")
    if _plain(item["input_refs"]) != _plain(config["input_selector"]["refs"]):
        raise ContractError("M10-E input bundle references differ from the config")
    if not isinstance(item["work_items"], list):
        raise ContractError("M10-E input bundle work_items must be a list")
    expected_units = [item["work_unit_id"] for item in config["work_units"]]
    actual_units: list[str] = []
    for work in item["work_items"]:
        work = _exact(work, {"work_unit_id", "arguments"}, "M10-E bundle work item")
        actual_units.append(work["work_unit_id"])
        if not isinstance(work["arguments"], Mapping):
            raise ContractError("M10-E work item arguments must be an object")
    if actual_units != expected_units:
        raise ContractError("M10-E input bundle work units differ from the config")
    if config["operation_type"] in {"portfolio_boundary", "research_aggregate"}:
        if store is None:
            raise ContractError("M10-C input resolution requires the configured M10 store")
        expected_contract = str(config["expected_results"]["source_result_contract"])
        units = {
            str(unit["work_unit_id"]): unit for unit in config["work_units"]
        }
        source_field = (
            "trade_outcomes"
            if config["operation_type"] == "portfolio_boundary"
            else "outcomes"
        )
        resolved_items: list[dict[str, Any]] = []
        for work in item["work_items"]:
            arguments = _plain(work["arguments"])
            if source_field not in arguments or not isinstance(arguments[source_field], list):
                raise ContractError("M10-E M10-C bundle source outcomes are invalid")
            canonical = _persisted_current_outcomes(
                store,
                expected_contract,
                [_plain(ref) for ref in units[str(work["work_unit_id"])]["input_refs"]],
                arguments[source_field],
            )
            arguments[source_field] = [_plain(outcome) for outcome in canonical]
            resolved_items.append({
                "work_unit_id": work["work_unit_id"],
                "arguments": arguments,
            })
        item["work_items"] = resolved_items
    return item


def _repository_read(payload: Mapping[str, Any]) -> RepositoryRead:
    item = _exact(
        payload,
        {"instrument_id", "as_of", "rows", "point_in_time_fingerprint"},
        "RepositoryRead bundle",
    )
    if not isinstance(item["rows"], list):
        raise ContractError("RepositoryRead rows must be a list")
    return RepositoryRead(
        instrument_id=item["instrument_id"], as_of=item["as_of"],
        rows=tuple(item["rows"]),
        point_in_time_fingerprint=item["point_in_time_fingerprint"],
    )


def _market_fingerprint(event: Mapping[str, Any], snapshot: Mapping[str, Any]) -> str:
    matches = [
        item["content_fingerprint"] for item in snapshot["symbols"]
        if item["instrument_id"] == event["instrument_id"]
    ]
    if len(matches) != 1:
        raise ContractError("M10-E market evidence does not uniquely contain the instrument")
    return str(matches[0])


def _actual_forward_refs(arguments: Mapping[str, Any]) -> list[dict[str, str]]:
    event = arguments["event"]
    snapshot = arguments["market_snapshot"]
    calendar = arguments["session_calendar"]
    return sorted([
        _canonical_ref(event["event_id"], event["event_content_fingerprint"]),
        _canonical_ref(snapshot["snapshot_id"], market_snapshot_evidence_fingerprint(snapshot)),
        _canonical_ref(event["input_identity"]["universe_id"], arguments["universe_content_fingerprint"]),
        _canonical_ref(calendar["calendar_id"], calendar["content_fingerprint"]),
    ], key=lambda item: item["id"])


def _actual_trade_refs(arguments: Mapping[str, Any]) -> list[dict[str, str]]:
    event = arguments["event"]
    snapshot = arguments["market_snapshot"]
    link = arguments["trade_plan_link"]
    plan = arguments["trade_plan"]
    states = tuple(arguments["exit_states"])
    state = current_exit_state(states) if states else None
    state_link = arguments["exit_state_link"]
    refs = [
        _canonical_ref(event["event_id"], event["event_content_fingerprint"]),
        _canonical_ref(snapshot["snapshot_id"], market_snapshot_evidence_fingerprint(snapshot)),
        _canonical_ref(event["input_identity"]["universe_id"], arguments["universe_content_fingerprint"]),
        _canonical_ref(link["link_id"], link["link_content_fingerprint"]),
    ]
    if plan is not None:
        refs.append(_canonical_ref(plan["plan_id"], plan["plan_content_fingerprint"]))
    if state is not None:
        refs.append(_canonical_ref(state["exit_state_id"], state["exit_state_content_fingerprint"]))
    if state_link is not None:
        refs.append(_canonical_ref(state_link["link_id"], state_link["link_content_fingerprint"]))
    return sorted(refs, key=lambda item: item["id"])


def _build_baseline_pending(
    config: Mapping[str, Any], work_unit: Mapping[str, Any], arguments: Mapping[str, Any],
    *, generated_at: str,
) -> Mapping[str, Any]:
    operation = config["operation_type"]
    if operation == "forward_evaluation":
        _exact(arguments, {"event", "market_read", "market_snapshot", "session_calendar", "universe_content_fingerprint"}, "forward arguments")
        event = arguments["event"]
        read = _repository_read(arguments["market_read"])
        snapshot = arguments["market_snapshot"]
        calendar = arguments["session_calendar"]
        refs = _actual_forward_refs(arguments)
        contract = "ForwardOutcome"
        as_of = calendar["as_of"]
        expected = forward_result_scope_keys(
            event, snapshot, arguments["universe_content_fingerprint"], calendar, read.rows
        )
        market_fingerprint = _market_fingerprint(event, snapshot)
        signal_date = event["signal_date"]
    else:
        _exact(arguments, {"event", "trade_plan_link", "trade_plan", "exit_states", "exit_state_link", "market_read", "market_snapshot", "universe_content_fingerprint"}, "trade arguments")
        event = arguments["event"]
        read = _repository_read(arguments["market_read"])
        snapshot = arguments["market_snapshot"]
        states = tuple(arguments["exit_states"])
        state = current_exit_state(states) if states else None
        refs = _actual_trade_refs(arguments)
        contract = "TradeOutcome"
        as_of = state["as_of"] if state is not None else config["as_of"]
        expected = trade_result_scope_keys(
            event, arguments["trade_plan_link"], arguments["trade_plan"], state,
            snapshot, arguments["universe_content_fingerprint"],
        )
        market_fingerprint = _market_fingerprint(event, snapshot)
        signal_date = event["signal_date"]
    if refs != _plain(work_unit["input_refs"]):
        raise ContractError("M10-E work unit does not freeze its actual input evidence")
    required_config_refs = [
        _plain(config["universe_ref"]),
        _plain(config["market_snapshot_ref"]),
    ]
    if any(item not in refs for item in required_config_refs):
        raise ContractError("M10-E config data evidence differs from the producer inputs")
    if config["adjustment_policy_ref"]["content_fingerprint"] != canonical_fingerprint(
        ADJUSTMENT_POLICY
    ):
        raise ContractError("M10-E config adjustment evidence is invalid")
    actual_selection = [
        item for item in refs if item["id"].startswith("opportunity:sha256:")
    ]
    if actual_selection != _plain(config["selection_refs"]):
        raise ContractError("M10-E selection evidence differs from the producer inputs")
    actual_execution = [
        item for item in refs
        if item["id"].startswith((
            "plan:sha256:", "exit-state:sha256:", "machine-link:sha256:"
        ))
    ]
    if actual_execution != _plain(config["execution_refs"]):
        raise ContractError("M10-E execution evidence differs from the producer inputs")
    policies = _expected_policies(operation)
    if policies != _plain(config["policy_refs"]):
        raise ContractError("M10-E config policies differ from the producer policies")
    scope = baseline_run_scope_fingerprint(
        contract, input_refs=refs, policy_refs=policies,
        path_status=config["path_status"], result_role=config["result_role"],
        partition_role=config["partition_role"], instrument_id=event["instrument_id"],
        signal_date=signal_date, market_data_fingerprint=market_fingerprint,
        expected_result_keys=expected,
    )
    return build_experiment_run_receipt(
        as_of=as_of, generated_at=generated_at,
        source_version={"evaluation_contracts": config["producer_source_version"]},
        future_data_used=False,
        attempt_id="m10-e-work:" + scope,
        experiment_id=f"M10-E-{operation}", status="pending",
        evidence_window={"start": signal_date, "end": as_of, "evidence_as_of": as_of},
        path_status=config["path_status"], result_role=config["result_role"],
        partition_role=config["partition_role"], bias_labels=list(config["bias_labels"]),
        code_commit=config["code_commit"],
        config_ref={
            "config_id": f"m10-e-{operation}-scope",
            "config_version": config["output_contract"]["schema_version"],
            "content_fingerprint": scope,
        },
        engine={"name": BASELINE_ENGINE_NAME, "version": BASELINE_ENGINE_VERSION, "adapter_version": BASELINE_ADAPTER_VERSION},
        policy_refs=policies, input_refs=refs, result_refs=[], started_at=generated_at,
        finished_at=None, parent_run_id=None, checkpoint_ref=None, error=None,
    )


def _execute_work_unit(
    config: Mapping[str, Any], work_unit: Mapping[str, Any], arguments: Mapping[str, Any],
    store: EvaluationShadowStore, *, generated_at: str,
) -> list[dict[str, str]]:
    operation = config["operation_type"]
    if operation in {"forward_evaluation", "trade_evaluation"}:
        pending = _build_baseline_pending(
            config,
            work_unit,
            arguments,
            generated_at=generated_at,
        )
        read = _repository_read(arguments["market_read"])
        if operation == "forward_evaluation":
            batch = evaluate_forward_baseline(
                arguments["event"], read, arguments["market_snapshot"],
                arguments["session_calendar"],
                universe_content_fingerprint=arguments["universe_content_fingerprint"],
                pending_run_receipt=pending, generated_at=generated_at,
                finished_at=generated_at,
            )
        else:
            batch = evaluate_trade_baseline(
                arguments["event"], arguments["trade_plan_link"], arguments["trade_plan"],
                tuple(arguments["exit_states"]), arguments["exit_state_link"], read,
                arguments["market_snapshot"],
                universe_content_fingerprint=arguments["universe_content_fingerprint"],
                pending_run_receipt=pending, generated_at=generated_at,
                finished_at=generated_at,
            )
        store_baseline_evaluation_batch(store, batch)
        outcomes = batch.outcomes
        contract = batch.result_contract
    else:
        expected_fields = (
            {"trade_outcomes", "scope"}
            if operation == "portfolio_boundary" else {"outcomes", "scope"}
        )
        _exact(arguments, expected_fields, f"{operation} arguments")
        source = tuple(arguments["trade_outcomes"] if operation == "portfolio_boundary" else arguments["outcomes"])
        contract = config["output_contract"]["name"]
        pending = build_readonly_pending_run(
            contract, source, evidence_scope=arguments["scope"], as_of=config["as_of"],
            generated_at=generated_at,
            attempt_id="m10-e-work:" + canonical_fingerprint({
                "operation": operation,
                "input_refs": _plain(work_unit["input_refs"]),
                "evidence_scope": _plain(arguments["scope"]),
            }),
            experiment_id=f"M10-E-{operation}", code_commit=config["code_commit"],
            started_at=generated_at, evidence_start=config["evidence_window"]["start"],
        )
        if _plain(pending["input_refs"]) != _plain(work_unit["input_refs"]):
            raise ContractError("M10-E work unit does not freeze its actual M10-C inputs")
        if _plain(pending["policy_refs"]) != _plain(config["policy_refs"]):
            raise ContractError("M10-E config policies differ from the M10-C producer")
        if operation == "portfolio_boundary":
            batch = evaluate_portfolio_boundary(
                source, portfolio_scope=arguments["scope"], pending_run_receipt=pending,
                generated_at=generated_at, finished_at=generated_at,
            )
        else:
            batch = evaluate_research_aggregate(
                source, aggregate_scope=arguments["scope"], pending_run_receipt=pending,
                generated_at=generated_at, finished_at=generated_at,
            )
        store_readonly_evaluation_batch(store, batch)
        outcomes = (batch.result,)
    id_field, fingerprint_field, _, _ = RESULT_TYPES[contract]
    return sorted([
        {"work_unit_id": work_unit["work_unit_id"], "id": item[id_field], "content_fingerprint": item[fingerprint_field]}
        for item in outcomes
    ], key=lambda item: item["id"])


def _orchestrator_pending(config: Mapping[str, Any], *, generated_at: str) -> Mapping[str, Any]:
    resume = config["resume"]
    checkpoint_ref = None
    if resume["checkpoint_ref"] is not None:
        checkpoint_ref = {
            "checkpoint_id": resume["checkpoint_ref"]["id"],
            "content_fingerprint": resume["checkpoint_ref"]["content_fingerprint"],
        }
    return build_experiment_run_receipt(
        as_of=config["as_of"], generated_at=generated_at,
        source_version={"evaluation_contracts": M10_E_SOURCE_VERSION}, future_data_used=False,
        attempt_id=f"m10-e:{config['config_id']}", experiment_id=f"M10-E-{config['operation_type']}",
        status="pending",
        evidence_window={**_plain(config["evidence_window"]), "evidence_as_of": config["as_of"]},
        path_status=config["path_status"], result_role=config["result_role"],
        partition_role=config["partition_role"], bias_labels=list(config["bias_labels"]),
        code_commit=config["code_commit"],
        config_ref={"config_id": config["config_id"], "config_version": config["schema_version"], "content_fingerprint": config["config_content_fingerprint"]},
        engine=ORCHESTRATOR_ENGINE, policy_refs=list(config["policy_refs"]),
        input_refs=_configured_input_refs(config), result_refs=[],
        started_at=generated_at, finished_at=None,
        parent_run_id=resume["parent_run_id"], checkpoint_ref=checkpoint_ref, error=None,
    )


def _terminal_receipt(
    pending: Mapping[str, Any], *, status: str, result_refs: list[dict[str, str]],
    generated_at: str, error: Mapping[str, str] | None,
) -> Mapping[str, Any]:
    values = _plain(pending)
    for field in (
        "run_id", "run_receipt_id", "run_content_fingerprint",
        "input_set_fingerprint", "result_set_fingerprint",
    ):
        values.pop(field)
    values.update({
        "generated_at": generated_at, "status": status,
        "result_refs": sorted(result_refs, key=lambda item: item["id"]),
        "finished_at": generated_at,
        "supersedes_run_receipt_id": pending["run_receipt_id"], "error": error,
    })
    return build_experiment_run_receipt(**values)


def _checkpoint(
    config: Mapping[str, Any], pending: Mapping[str, Any], completed_units: list[str],
    result_refs: list[dict[str, str]], *, status: str, generated_at: str,
    prior: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    expected = [item["work_unit_id"] for item in config["work_units"]]
    completed_set = set(completed_units)
    return build_research_run_checkpoint(
        run_id=pending["run_id"], config_id=config["config_id"],
        config_content_fingerprint=config["config_content_fingerprint"],
        config_scope_fingerprint=config_resume_scope_fingerprint(config),
        result_family=config["output_contract"]["name"],
        path_status=config["path_status"], result_role=config["result_role"],
        partition_role=config["partition_role"], code_commit=config["code_commit"],
        input_set_fingerprint=pending["input_set_fingerprint"],
        expected_work_units=expected,
        completed_work_units=[unit for unit in expected if unit in completed_set],
        remaining_work_units=[unit for unit in expected if unit not in completed_set],
        result_refs=sorted(result_refs, key=lambda item: (item["work_unit_id"], item["id"])),
        supersedes_checkpoint_id=prior["checkpoint_id"] if prior is not None else None,
        status=status, generated_at=generated_at,
    )


def _summary(
    config: Mapping[str, Any], pending: Mapping[str, Any], *, status: str,
    result_refs: list[dict[str, str]], checkpoint: Mapping[str, Any] | None,
    error: str | None = None, export: Mapping[str, Any] | None = None,
    result_status_counts: Mapping[str, int] | None = None,
    terminal_persisted: bool = True,
) -> Mapping[str, Any]:
    expected = len(config["work_units"]) * int(config["expected_results"]["per_work_unit_count"])
    payload = {
        "run_id": pending["run_id"], "config_id": config["config_id"],
        "config_content_fingerprint": config["config_content_fingerprint"],
        "path_status": config["path_status"], "result_role": config["result_role"],
        "partition_role": config["partition_role"], "status": status,
        "input_count": len(_configured_input_refs(config)),
        "expected_result_count": expected, "completed_result_count": len(result_refs),
        "missing_result_count": expected - len(result_refs),
        "checkpoint_id": checkpoint["checkpoint_id"] if checkpoint is not None else None,
        "error": error, "storage_root": config["storage"]["root_path"],
        "result_status_counts": dict(sorted((result_status_counts or {}).items())),
        "export": _plain(export) if export is not None else None,
        "terminal_persisted": terminal_persisted,
    }
    return _freeze(payload)


def _write_reconciled_checkpoint(
    store: EvaluationShadowStore,
    config: Mapping[str, Any],
    pending: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    generated_at: str,
) -> Mapping[str, Any]:
    status = "ready_to_finalize" if not state["remaining_work_units"] else "in_progress"
    prior = state["checkpoint"]
    if prior is not None and (
        prior["status"] == status
        and list(prior["completed_work_units"]) == list(state["completed_work_units"])
        and _plain(prior["result_refs"]) == _plain(state["result_refs"])
    ):
        return state
    checkpoint = _checkpoint(
        config,
        pending,
        list(state["completed_work_units"]),
        [_plain(item) for item in state["result_refs"]],
        status=status,
        generated_at=generated_at,
        prior=prior,
    )
    store.write_checkpoint(checkpoint)
    return store.reconcile_m10e_run(config, str(pending["run_id"]))


def _terminal_from_reconciliation(
    pending: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    status: str,
    generated_at: str,
    error: Mapping[str, str] | None,
) -> Mapping[str, Any]:
    return _terminal_receipt(
        pending,
        status=status,
        result_refs=[
            {"id": item["id"], "content_fingerprint": item["content_fingerprint"]}
            for item in state["result_refs"]
        ],
        generated_at=generated_at,
        error=error,
    )


def _persist_terminal_failure(
    store: EvaluationShadowStore,
    config: Mapping[str, Any],
    pending: Mapping[str, Any],
    *,
    terminal_status: str,
    category: str,
    message: str,
    clock: Callable[[], str],
) -> ResearchRunExecution:
    state = store.reconcile_m10e_run(config, str(pending["run_id"]))
    try:
        state = _write_reconciled_checkpoint(
            store, config, pending, state, generated_at=clock()
        )
        terminal = _terminal_from_reconciliation(
            pending,
            state,
            status=terminal_status,
            generated_at=clock(),
            error={"category": category, "message": message},
        )
        store.write_run_receipt(terminal)
    except Exception:
        state = store.reconcile_m10e_run(config, str(pending["run_id"]))
        if state["terminal_persisted"]:
            persisted_status = str(state["run_status"])
            return ResearchRunExecution(
                _summary(
                    config, pending, status=persisted_status,
                    result_refs=[_plain(item) for item in state["result_refs"]],
                    checkpoint=state["checkpoint"], error=category,
                    result_status_counts=state["result_status_counts"],
                    terminal_persisted=True,
                ),
                0 if persisted_status == "completed" else 130 if persisted_status == "interrupted" else 2,
            )
        return ResearchRunExecution(
            _summary(
                config, pending, status="pending",
                result_refs=[_plain(item) for item in state["result_refs"]],
                checkpoint=state["checkpoint"], error=category,
                result_status_counts=state["result_status_counts"],
                terminal_persisted=False,
            ),
            130 if terminal_status == "interrupted" else 2,
        )
    state = store.reconcile_m10e_run(config, str(pending["run_id"]))
    return ResearchRunExecution(
        _summary(
            config, pending, status=terminal_status,
            result_refs=[_plain(item) for item in state["result_refs"]],
            checkpoint=state["checkpoint"], error=category,
            result_status_counts=state["result_status_counts"],
            terminal_persisted=True,
        ),
        130 if terminal_status == "interrupted" else 2,
    )


def _resume_evidence(
    config: Mapping[str, Any], inventory: Any,
) -> tuple[list[str], list[dict[str, str]], Mapping[str, Any] | None]:
    if config["resume"]["mode"] == "fresh":
        return [], [], None
    reference = config["resume"]["checkpoint_ref"]
    matches = [item for item in inventory.checkpoints if item["checkpoint_id"] == reference["id"]]
    if len(matches) != 1:
        raise ContractError("M10-E resume checkpoint is not present in storage")
    checkpoint = matches[0]
    validate_research_run_checkpoint(checkpoint)
    parent_chain = [
        item for item in inventory.run_receipts
        if item["run_id"] == config["resume"]["parent_run_id"]
    ]
    if not parent_chain or current_experiment_run(parent_chain)["status"] not in {"interrupted", "failed"}:
        raise ContractError("M10-E resume parent is not an interrupted or failed run")
    if (
        checkpoint["run_id"] != config["resume"]["parent_run_id"]
        or checkpoint["checkpoint_content_fingerprint"] != reference["content_fingerprint"]
        or checkpoint["config_scope_fingerprint"] != config_resume_scope_fingerprint(config)
        or checkpoint["code_commit"] != config["code_commit"]
        or checkpoint["result_family"] != config["output_contract"]["name"]
        or list(checkpoint["expected_work_units"])
        != [item["work_unit_id"] for item in config["work_units"]]
    ):
        raise ContractError("M10-E resume evidence differs from the current config")
    return (
        list(checkpoint["completed_work_units"]),
        [_plain(item) for item in checkpoint["result_refs"]],
        checkpoint,
    )


@dataclass(frozen=True)
class ResearchRunExecution:
    summary: Mapping[str, Any]
    exit_code: int


def execute_research_run(
    config: Mapping[str, Any], *, repo_root: str | Path,
    git_state_provider: Callable[[str | Path], Any],
    clock: Callable[[], str] = _now,
    interrupt_after_work_units: int | None = None,
    export_publisher: Callable[..., Path] = publish_audit_export,
) -> ResearchRunExecution:
    """Run one exact config through one existing M10 result-family producer."""

    validate_research_run_config(config)
    if interrupt_after_work_units is not None:
        require_strict_integer(
            interrupt_after_work_units,
            "interrupt_after_work_units",
            minimum=0,
        )
    validate_formal_git_state(config, repo_root=repo_root, state_provider=git_state_provider)
    if (
        config["operation_type"] in {"forward_evaluation", "trade_evaluation"}
        and _plain(config["policy_refs"]) != _expected_policies(config["operation_type"])
    ):
        raise ContractError("M10-E formal config does not bind the approved policies")
    store = EvaluationShadowStore(config["storage"]["root_path"], workspace_root=repo_root)
    bundle = load_input_bundle(config, store=store)
    generated_at = clock()
    pending = _orchestrator_pending(config, generated_at=generated_at)
    with _config_lock(config["config_id"]):
        store.write_research_config(config)
        inventory = store.capture_inventory()
        existing_chain = [item for item in inventory.run_receipts if item["run_id"] == pending["run_id"]]
        if existing_chain:
            leaf = current_experiment_run(existing_chain)
            if leaf["status"] == "completed":
                state = store.reconcile_m10e_run(config, str(pending["run_id"]))
                return ResearchRunExecution(
                    _summary(
                        config, pending, status="completed",
                        result_refs=[_plain(item) for item in state["result_refs"]],
                        checkpoint=state["checkpoint"],
                        result_status_counts=state["result_status_counts"],
                        terminal_persisted=True,
                    ),
                    0,
                )
            if leaf["status"] != "pending":
                raise ContractError("run_in_progress_or_terminal_conflict")
            state = store.reconcile_m10e_run(config, str(pending["run_id"]))
            if state["remaining_work_units"]:
                raise ContractError("run_in_progress_requires_explicit_resume")
        else:
            _resume_evidence(config, inventory)
            store.write_run_receipt(pending)
            state = store.reconcile_m10e_run(config, str(pending["run_id"]))
        try:
            work_by_id = {item["work_unit_id"]: item for item in bundle["work_items"]}
            for unit in config["work_units"]:
                unit_id = unit["work_unit_id"]
                if unit_id in set(state["completed_work_units"]):
                    continue
                _execute_work_unit(
                    config, unit, work_by_id[unit_id]["arguments"], store,
                    generated_at=clock(),
                )
                state = store.reconcile_m10e_run(config, str(pending["run_id"]))
                state = _write_reconciled_checkpoint(
                    store, config, pending, state, generated_at=clock()
                )
                if (
                    interrupt_after_work_units is not None
                    and len(state["completed_work_units"]) >= interrupt_after_work_units
                    and state["remaining_work_units"]
                ):
                    raise KeyboardInterrupt
            state = store.reconcile_m10e_run(config, str(pending["run_id"]))
            if state["remaining_work_units"] or state["missing_result_count"]:
                raise ContractError("M10-E result set does not conserve the configured expectation")
            state = _write_reconciled_checkpoint(
                store, config, pending, state, generated_at=clock()
            )
            completed = _terminal_from_reconciliation(
                pending, state, status="completed", generated_at=clock(), error=None
            )
            try:
                store.write_run_receipt(completed)
            except Exception as exc:
                return _persist_terminal_failure(
                    store, config, pending,
                    terminal_status="failed",
                    category="terminal_completion_write_failed",
                    message=f"{type(exc).__name__}: {exc}",
                    clock=clock,
                )
            state = store.reconcile_m10e_run(config, str(pending["run_id"]))
            if state["run_status"] != "completed" or not state["terminal_persisted"]:
                raise ContractError("M10-E completed receipt was not persisted")
            result_refs = [_plain(item) for item in state["result_refs"]]
            checkpoint = state["checkpoint"]
            status_counts = state["result_status_counts"]
            export_summary: dict[str, Any] | None = None
            if config["export_plan"]["enabled"]:
                try:
                    execution = execute_evaluation_query(
                        store, config["export_plan"]["query"],
                        code_commit=config["code_commit"],
                    )
                    actual_ids = {item["result_id"] for item in execution.result_set["result_refs"]}
                    if actual_ids != {item["id"] for item in result_refs}:
                        raise ContractError("M10-E export query does not select exactly this run's results")
                    package = export_publisher(
                        execution, config["export_plan"]["config"],
                        output_root=config["export_plan"]["output_root"],
                        generated_at=clock(), code_commit=config["code_commit"],
                        workspace_root=repo_root,
                    )
                    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
                    export_summary = {
                        "status": "completed", "export_id": manifest["export_id"],
                        "export_receipt_id": manifest["export_receipt_id"],
                    }
                except Exception as exc:  # evaluation remains complete by design
                    export_summary = {"status": "failed", "reason": type(exc).__name__}
            return ResearchRunExecution(
                _summary(config, pending, status="completed", result_refs=result_refs,
                         checkpoint=checkpoint, export=export_summary,
                         result_status_counts=status_counts,
                         terminal_persisted=True), 0
            )
        except KeyboardInterrupt:
            return _persist_terminal_failure(
                store, config, pending,
                terminal_status="interrupted",
                category="interrupted",
                message="run interrupted",
                clock=clock,
            )
        except Exception as exc:
            return _persist_terminal_failure(
                store, config, pending,
                terminal_status="failed",
                category=type(exc).__name__,
                message=str(exc),
                clock=clock,
            )


__all__ = [
    "INPUT_BUNDLE_SCHEMA_VERSION", "ORCHESTRATOR_ENGINE", "ResearchRunExecution",
    "execute_research_run", "load_input_bundle",
]
