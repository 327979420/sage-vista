"""M10-C portfolio boundary and deterministic read-only gross summaries.

This module accepts complete immutable M10 outcomes, never market rows.  It is
the sole M10-C producer for PortfolioRun 2.1 and ResearchAggregate 2.1.  Both
daily and replay shadows must call these same pure entry points.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError

from .contracts import (
    M10_C_SOURCE_VERSION,
    PORTFOLIO_RUN_SCHEMA_VERSION,
    RESEARCH_AGGREGATE_SCHEMA_VERSION,
    RESULT_TYPES,
    build_experiment_run_receipt,
    current_experiment_run,
    current_result,
    finalize_result,
    validate_experiment_run,
    validate_m10c_scope,
    validate_m10c_source_version,
    validate_result,
)
from .policies import (
    AGGREGATION_POLICY,
    EVALUATION_POLICY,
    FORWARD_WINDOWS,
    FORWARD_WINDOW_POLICY,
    PARTITION_POLICY,
    ZERO_COST_COMPARISON_POLICY,
)
from .metrics import (
    decimal_metric,
    profit_factor_semantics,
    quantized_metric,
    quantized_ratio,
)


READONLY_ENGINE_NAME = "sage-vista-readonly-aggregate"
READONLY_ENGINE_VERSION = "1.0.0"
READONLY_ADAPTER_VERSION = "shadow-1.0.0"


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


def build_aggregate_scope(
    *,
    source_result_type: str,
    window_sessions: int | None,
    path_status: str,
    result_role: str,
    partition_role: str,
    execution_policy: Mapping[str, Any] | None = None,
    cost_policy: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Build the strict, non-query scope used by empty and non-empty batches."""

    if source_result_type == "forward_outcome":
        scope = {
            "source_result_type": source_result_type,
            "window_sessions": window_sessions,
            "path_status": path_status,
            "result_role": result_role,
            "partition_role": partition_role,
            "evaluation_policy_fingerprint": EVALUATION_POLICY["policy_fingerprint"],
            "partition_policy_fingerprint": PARTITION_POLICY["policy_fingerprint"],
            "adjustment_policy_fingerprint": canonical_fingerprint(ADJUSTMENT_POLICY),
            "window_policy_fingerprint": FORWARD_WINDOW_POLICY["policy_fingerprint"],
            "execution_policy_version": None,
            "execution_policy_fingerprint": None,
            "cost_policy_status": None,
            "cost_policy_version": None,
            "cost_policy_fingerprint": None,
        }
    elif source_result_type == "trade_outcome":
        if not isinstance(execution_policy, Mapping) or not isinstance(cost_policy, Mapping):
            raise ContractError("M10-C Trade scope requires execution and cost evidence")
        if "status" in cost_policy:
            cost_status = cost_policy.get("status")
            cost_version = cost_policy.get("policy_version")
            cost_fingerprint = cost_policy.get("policy_fingerprint")
        else:
            cost_status = "comparison_only"
            cost_version = cost_policy.get("policy_version")
            cost_fingerprint = cost_policy.get("policy_fingerprint")
        scope = {
            "source_result_type": source_result_type,
            "window_sessions": None,
            "path_status": path_status,
            "result_role": result_role,
            "partition_role": partition_role,
            "evaluation_policy_fingerprint": EVALUATION_POLICY["policy_fingerprint"],
            "partition_policy_fingerprint": PARTITION_POLICY["policy_fingerprint"],
            "adjustment_policy_fingerprint": canonical_fingerprint(ADJUSTMENT_POLICY),
            "window_policy_fingerprint": None,
            "execution_policy_version": execution_policy.get("policy_version"),
            "execution_policy_fingerprint": execution_policy.get("policy_fingerprint"),
            "cost_policy_status": cost_status,
            "cost_policy_version": cost_version,
            "cost_policy_fingerprint": cost_fingerprint,
        }
    else:
        raise ContractError("M10-C scope accepts only ForwardOutcome or TradeOutcome")
    validate_m10c_scope(scope, expected_type=source_result_type)
    return _freeze(scope)


def _scope_from_outcome(
    contract_name: str, outcome: Mapping[str, Any]
) -> Mapping[str, Any]:
    if contract_name == "ForwardOutcome":
        return build_aggregate_scope(
            source_result_type="forward_outcome",
            window_sessions=int(outcome["window_sessions"]),
            path_status=str(outcome["path_status"]),
            result_role=str(outcome["result_role"]),
            partition_role=str(outcome["partition_role"]),
        )
    return build_aggregate_scope(
        source_result_type="trade_outcome",
        window_sessions=None,
        path_status=str(outcome["path_status"]),
        result_role=str(outcome["result_role"]),
        partition_role=str(outcome["partition_role"]),
        execution_policy=outcome["execution_policy"],
        cost_policy=outcome["cost_policy"],
    )


def _validated_inputs(
    contract_name: str,
    outcomes: Iterable[Mapping[str, Any]],
    scope: Mapping[str, Any],
) -> tuple[tuple[Mapping[str, Any], ...], list[dict[str, str]]]:
    if contract_name not in {"ForwardOutcome", "TradeOutcome"}:
        raise ContractError("M10-C accepts only ForwardOutcome or TradeOutcome inputs")
    expected_type = (
        "forward_outcome" if contract_name == "ForwardOutcome" else "trade_outcome"
    )
    validate_m10c_scope(scope, expected_type=expected_type)
    id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
    normalized: list[tuple[str, Mapping[str, Any]]] = []
    seen_ids: set[str] = set()
    seen_logical: set[str] = set()
    for outcome in outcomes:
        validate_result(contract_name, outcome)
        stable_id = str(outcome[id_field])
        logical_id = str(outcome["logical_result_id"])
        if stable_id in seen_ids:
            raise ContractError("M10-C input contains a duplicate result ID")
        if logical_id in seen_logical:
            raise ContractError("M10-C input contains multiple revisions of one result")
        if _plain(_scope_from_outcome(contract_name, outcome)) != _plain(scope):
            raise ContractError("M10-C input outcomes do not share one evidence scope")
        seen_ids.add(stable_id)
        seen_logical.add(logical_id)
        normalized.append((stable_id, outcome))
    normalized.sort(key=lambda item: item[0])
    frozen = tuple(item[1] for item in normalized)
    references = [
        {
            "id": str(item[id_field]),
            "content_fingerprint": str(item[fingerprint_field]),
        }
        for item in frozen
    ]
    return frozen, references


def _policy_refs(scope: Mapping[str, Any]) -> list[dict[str, str]]:
    refs = [
        {
            "policy_kind": "adjustment",
            "policy_version": ADJUSTMENT_POLICY["version"],
            "policy_fingerprint": canonical_fingerprint(ADJUSTMENT_POLICY),
        },
        {
            "policy_kind": "aggregation",
            "policy_version": AGGREGATION_POLICY["policy_version"],
            "policy_fingerprint": AGGREGATION_POLICY["policy_fingerprint"],
        },
        {
            "policy_kind": "evaluation",
            "policy_version": EVALUATION_POLICY["policy_version"],
            "policy_fingerprint": EVALUATION_POLICY["policy_fingerprint"],
        },
        {
            "policy_kind": "partition",
            "policy_version": PARTITION_POLICY["policy_version"],
            "policy_fingerprint": PARTITION_POLICY["policy_fingerprint"],
        },
    ]
    if scope["source_result_type"] == "forward_outcome":
        refs.append({
            "policy_kind": "forward_window",
            "policy_version": FORWARD_WINDOW_POLICY["policy_version"],
            "policy_fingerprint": FORWARD_WINDOW_POLICY["policy_fingerprint"],
        })
    else:
        refs.append({
            "policy_kind": "execution",
            "policy_version": str(scope["execution_policy_version"]),
            "policy_fingerprint": str(scope["execution_policy_fingerprint"]),
        })
        if scope["result_role"] == "comparison":
            refs.append({
                "policy_kind": "cost_slippage",
                "policy_version": ZERO_COST_COMPARISON_POLICY["policy_version"],
                "policy_fingerprint": ZERO_COST_COMPARISON_POLICY[
                    "policy_fingerprint"
                ],
            })
    return sorted(refs, key=lambda item: item["policy_kind"])


def readonly_run_scope_fingerprint(
    result_contract: str,
    *,
    input_refs: Iterable[Mapping[str, Any]],
    policy_refs: Iterable[Mapping[str, Any]],
    evidence_scope: Mapping[str, Any],
) -> str:
    """Bind a pending M10-C receipt to its exact immutable input set and scope."""

    if result_contract not in {"PortfolioRun", "ResearchAggregate"}:
        raise ContractError("M10-C run result contract is invalid")
    return canonical_fingerprint({
        "result_contract": result_contract,
        "input_refs": sorted(
            [_plain(item) for item in input_refs],
            key=lambda item: (item["id"], item["content_fingerprint"]),
        ),
        "policy_refs": sorted(
            [_plain(item) for item in policy_refs],
            key=lambda item: (
                item["policy_kind"], item["policy_version"],
                item["policy_fingerprint"],
            ),
        ),
        "evidence_scope": _plain(evidence_scope),
    })


def build_readonly_pending_run(
    result_contract: str,
    outcomes: Iterable[Mapping[str, Any]],
    *,
    evidence_scope: Mapping[str, Any],
    as_of: str,
    generated_at: str,
    attempt_id: str,
    experiment_id: str,
    code_commit: str,
    started_at: str,
    evidence_start: str | None = None,
) -> Mapping[str, Any]:
    """Create the pending receipt that freezes one M10-C expected result."""

    source_contract = (
        "TradeOutcome"
        if result_contract == "PortfolioRun"
        else (
            "ForwardOutcome"
            if evidence_scope.get("source_result_type") == "forward_outcome"
            else "TradeOutcome"
        )
    )
    frozen, references = _validated_inputs(source_contract, outcomes, evidence_scope)
    if any(str(item["as_of"]) > as_of for item in frozen):
        raise ContractError("M10-C run cannot aggregate results after its as_of")
    policies = _policy_refs(evidence_scope)
    scope_fingerprint = readonly_run_scope_fingerprint(
        result_contract,
        input_refs=references,
        policy_refs=policies,
        evidence_scope=evidence_scope,
    )
    start = evidence_start or min(
        (str(item["signal_date"]) for item in frozen), default=as_of
    )
    receipt = build_experiment_run_receipt(
        as_of=as_of,
        generated_at=generated_at,
        source_version={"evaluation_contracts": M10_C_SOURCE_VERSION},
        future_data_used=False,
        attempt_id=attempt_id,
        experiment_id=experiment_id,
        status="pending",
        evidence_window={"start": start, "end": as_of, "evidence_as_of": as_of},
        path_status=evidence_scope["path_status"],
        result_role=evidence_scope["result_role"],
        partition_role=evidence_scope["partition_role"],
        bias_labels=[],
        code_commit=code_commit,
        config_ref={
            "config_id": "m10-c-readonly-scope",
            "config_version": "1.0.0",
            "content_fingerprint": scope_fingerprint,
        },
        engine={
            "name": READONLY_ENGINE_NAME,
            "version": READONLY_ENGINE_VERSION,
            "adapter_version": READONLY_ADAPTER_VERSION,
        },
        policy_refs=policies,
        input_refs=references,
        result_refs=[],
        started_at=started_at,
        finished_at=None,
        parent_run_id=None,
        checkpoint_ref=None,
        error=None,
    )
    _validate_pending_run(
        receipt,
        result_contract=result_contract,
        input_refs=references,
        evidence_scope=evidence_scope,
    )
    return receipt


def _validate_pending_run(
    receipt: Mapping[str, Any],
    *,
    result_contract: str,
    input_refs: Iterable[Mapping[str, Any]],
    evidence_scope: Mapping[str, Any],
) -> None:
    validate_readonly_receipt_identity(receipt)
    if (
        receipt["status"] != "pending"
        or receipt["result_refs"]
        or receipt["future_data_used"] is not False
    ):
        raise ContractError("M10-C production requires an unfinished pending receipt")
    if _plain(receipt["engine"]) != {
        "name": READONLY_ENGINE_NAME,
        "version": READONLY_ENGINE_VERSION,
        "adapter_version": READONLY_ADAPTER_VERSION,
    }:
        raise ContractError("M10-C receipt uses the wrong engine")
    expected_refs = sorted(
        [_plain(item) for item in input_refs],
        key=lambda item: (item["id"], item["content_fingerprint"]),
    )
    if _plain(receipt["input_refs"]) != expected_refs:
        raise ContractError("M10-C pending receipt does not freeze the input set")
    expected_policies = _policy_refs(evidence_scope)
    if _plain(receipt["policy_refs"]) != expected_policies:
        raise ContractError("M10-C pending receipt does not freeze the policies")
    expected_scope = readonly_run_scope_fingerprint(
        result_contract,
        input_refs=expected_refs,
        policy_refs=expected_policies,
        evidence_scope=evidence_scope,
    )
    if receipt["config_ref"]["content_fingerprint"] != expected_scope:
        raise ContractError("M10-C pending receipt does not freeze its evidence scope")
    if any(
        receipt[field] != evidence_scope[field]
        for field in ("path_status", "result_role", "partition_role")
    ):
        raise ContractError("M10-C pending receipt role differs from its scope")


def validate_readonly_receipt_identity(receipt: Mapping[str, Any]) -> None:
    """Validate the exact source and engine identity of an M10-C receipt."""

    validate_experiment_run(receipt)
    validate_m10c_source_version(receipt)
    if _plain(receipt["engine"]) != {
        "name": READONLY_ENGINE_NAME,
        "version": READONLY_ENGINE_VERSION,
        "adapter_version": READONLY_ADAPTER_VERSION,
    }:
        raise ContractError("M10-C receipt uses the wrong engine")


def _result_base(
    pending: Mapping[str, Any], *, generated_at: str, status: str
) -> dict[str, Any]:
    return {
        "as_of": pending["as_of"],
        "generated_at": generated_at,
        "source_version": {"evaluation_contracts": M10_C_SOURCE_VERSION},
        "future_data_used": False,
        "run_id": pending["run_id"],
        "logical_result_id": "assigned-by-finalizer",
        "supersedes_result_id": None,
        "path_status": pending["path_status"],
        "result_role": pending["result_role"],
        "partition_role": pending["partition_role"],
        "bias_labels": list(pending["bias_labels"]),
        "evaluation_policy": EVALUATION_POLICY,
        "partition_policy": PARTITION_POLICY,
        "status": status,
    }


def _finalize_revision(
    contract_name: str,
    values: Mapping[str, Any],
    previous_results: Iterable[Mapping[str, Any]],
) -> Mapping[str, Any]:
    previous = tuple(previous_results)
    candidate = finalize_result(contract_name, values)
    if not previous:
        return candidate
    leaf = current_result(contract_name, previous)
    if leaf["logical_result_id"] != candidate["logical_result_id"]:
        raise ContractError("M10-C revision crosses logical result identities")
    id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
    if candidate[id_field] == leaf[id_field]:
        if candidate[fingerprint_field] != leaf[fingerprint_field]:
            raise ContractError("same M10-C identity has different content")
        return leaf
    revised = _plain(values)
    revised["supersedes_result_id"] = leaf[id_field]
    return finalize_result(contract_name, revised)


def produce_portfolio_boundary(
    trade_outcomes: Iterable[Mapping[str, Any]],
    *,
    portfolio_scope: Mapping[str, Any],
    pending_run_receipt: Mapping[str, Any],
    generated_at: str,
    previous_results: Iterable[Mapping[str, Any]] = (),
) -> Mapping[str, Any]:
    """Produce the unavailable PortfolioRun boundary without portfolio math."""

    frozen, references = _validated_inputs(
        "TradeOutcome", trade_outcomes, portfolio_scope
    )
    del frozen
    _validate_pending_run(
        pending_run_receipt,
        result_contract="PortfolioRun",
        input_refs=references,
        evidence_scope=portfolio_scope,
    )
    values = {
        **_result_base(
            pending_run_receipt, generated_at=generated_at, status="unavailable"
        ),
        "schema_version": PORTFOLIO_RUN_SCHEMA_VERSION,
        "status_reason": "capital_allocation_policy_not_approved",
        "aggregation_policy": AGGREGATION_POLICY,
        "portfolio_scope": _plain(portfolio_scope),
        "trade_outcome_refs": references,
        "result_set_fingerprint": canonical_fingerprint(references),
    }
    return _finalize_revision(
        "PortfolioRun", values, previous_results
    )


def _trade_status(outcome: Mapping[str, Any]) -> str:
    status = outcome["status"]
    if status == "pending":
        if outcome["status_reason"] != "trade_open":
            raise ContractError("M10-C cannot map an unknown pending TradeOutcome")
        return "open"
    if status not in {"completed", "no_trade", "unavailable"}:
        raise ContractError("M10-C TradeOutcome status is not aggregatable")
    return str(status)


def _statistics(
    source_result_type: str, outcomes: tuple[Mapping[str, Any], ...]
) -> dict[str, Any]:
    status_names = (
        ("pending", "mature", "partial", "unavailable")
        if source_result_type == "forward_outcome"
        else ("completed", "open", "no_trade", "unavailable")
    )
    status_counts = {name: 0 for name in status_names}
    evaluated: list[Decimal] = []
    for outcome in outcomes:
        bucket = (
            str(outcome["status"])
            if source_result_type == "forward_outcome"
            else _trade_status(outcome)
        )
        status_counts[bucket] += 1
        eligible = (
            bucket == "mature"
            or (bucket == "partial" and outcome["gross_return"] is not None)
            if source_result_type == "forward_outcome"
            else bucket == "completed"
        )
        if eligible:
            evaluated.append(decimal_metric(outcome["gross_return"], "gross_return"))

    total = len(outcomes)
    evaluated_count = len(evaluated)
    missing_count = total - evaluated_count
    missing_rate = None if total == 0 else quantized_ratio(missing_count, total)
    wins = [value for value in evaluated if value > 0]
    losses = [value for value in evaluated if value < 0]
    flats = [value for value in evaluated if value == 0]
    base = {
        "total_count": total,
        "status_counts": status_counts,
        "evaluated_count": evaluated_count,
        "missing_count": missing_count,
        "missing_rate": missing_rate,
        "win_count": len(wins),
        "loss_count": len(losses),
        "flat_count": len(flats),
    }
    if not evaluated:
        return {
            **base,
            "win_rate": None,
            "mean_gross_return": None,
            "median_gross_return": None,
            "gross_profit": None,
            "gross_loss_abs": None,
            "profit_factor": None,
            "gross_expectancy": None,
            "metric_status": "unavailable",
            "metric_reason": "empty_sample",
        }

    ordered = sorted(evaluated)
    midpoint = len(ordered) // 2
    median = (
        ordered[midpoint]
        if len(ordered) % 2
        else (ordered[midpoint - 1] + ordered[midpoint]) / Decimal(2)
    )
    mean = sum(evaluated, Decimal(0)) / Decimal(evaluated_count)
    gross_profit = sum(wins, Decimal(0))
    gross_loss = abs(sum(losses, Decimal(0)))
    gross_profit_value = quantized_metric(gross_profit)
    gross_loss_value = quantized_metric(gross_loss)
    profit_factor, metric_reason = profit_factor_semantics(
        gross_profit_value, gross_loss_value
    )
    mean_value = quantized_metric(mean)
    return {
        **base,
        "win_rate": quantized_ratio(len(wins), evaluated_count),
        "mean_gross_return": mean_value,
        "median_gross_return": quantized_metric(median),
        "gross_profit": gross_profit_value,
        "gross_loss_abs": gross_loss_value,
        "profit_factor": profit_factor,
        "gross_expectancy": mean_value,
        "metric_status": "available",
        "metric_reason": metric_reason,
    }


def produce_research_aggregate(
    outcomes: Iterable[Mapping[str, Any]],
    *,
    aggregate_scope: Mapping[str, Any],
    pending_run_receipt: Mapping[str, Any],
    generated_at: str,
    previous_results: Iterable[Mapping[str, Any]] = (),
) -> Mapping[str, Any]:
    """Summarize frozen gross returns without reading prices or recomputing facts."""

    source_type = str(aggregate_scope.get("source_result_type"))
    contract_name = (
        "ForwardOutcome" if source_type == "forward_outcome" else "TradeOutcome"
    )
    frozen, references = _validated_inputs(
        contract_name, outcomes, aggregate_scope
    )
    _validate_pending_run(
        pending_run_receipt,
        result_contract="ResearchAggregate",
        input_refs=references,
        evidence_scope=aggregate_scope,
    )
    values = {
        **_result_base(
            pending_run_receipt, generated_at=generated_at, status="completed"
        ),
        "schema_version": RESEARCH_AGGREGATE_SCHEMA_VERSION,
        "source_result_type": source_type,
        "window_sessions": aggregate_scope["window_sessions"],
        "aggregate_scope": _plain(aggregate_scope),
        "aggregation_policy": AGGREGATION_POLICY,
        "result_refs": references,
        "result_set_fingerprint": canonical_fingerprint(references),
        **_statistics(source_type, frozen),
    }
    return _finalize_revision(
        "ResearchAggregate", values, previous_results
    )


def validate_readonly_run_conservation(
    pending_run_receipt: Mapping[str, Any],
    result_contract: str,
    result: Mapping[str, Any],
    source_outcomes: Iterable[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Recompute one M10-C result from complete inputs before completion."""

    if result_contract not in {"PortfolioRun", "ResearchAggregate"}:
        raise ContractError("M10-C result contract is invalid")
    validate_result(result_contract, result)
    validate_m10c_source_version(result)
    if result_contract == "PortfolioRun":
        scope = result["portfolio_scope"]
        source_contract = "TradeOutcome"
        reference_field = "trade_outcome_refs"
    else:
        scope = result["aggregate_scope"]
        source_contract = (
            "ForwardOutcome"
            if result["source_result_type"] == "forward_outcome"
            else "TradeOutcome"
        )
        reference_field = "result_refs"
    frozen, input_refs = _validated_inputs(
        source_contract, source_outcomes, scope
    )
    if any(str(item["as_of"]) > pending_run_receipt["as_of"] for item in frozen):
        raise ContractError("M10-C source outcome is later than the run evidence cutoff")
    if _plain(result[reference_field]) != input_refs:
        raise ContractError("M10-C result references do not match complete inputs")
    _validate_pending_run(
        pending_run_receipt,
        result_contract=result_contract,
        input_refs=input_refs,
        evidence_scope=scope,
    )
    if (
        result["run_id"] != pending_run_receipt["run_id"]
        or result["as_of"] != pending_run_receipt["as_of"]
    ):
        raise ContractError("M10-C result does not belong to the pending run")
    if result_contract == "ResearchAggregate":
        expected_statistics = _statistics(result["source_result_type"], frozen)
        for field, expected in expected_statistics.items():
            if _plain(result[field]) != expected:
                raise ContractError(
                    f"M10-C aggregate {field} does not match complete inputs"
                )
    id_field, fingerprint_field, _, _ = RESULT_TYPES[result_contract]
    return [{
        "id": str(result[id_field]),
        "content_fingerprint": str(result[fingerprint_field]),
    }]


def complete_readonly_run(
    pending_run_receipt: Mapping[str, Any],
    result_contract: str,
    result: Mapping[str, Any],
    source_outcomes: Iterable[Mapping[str, Any]],
    *,
    generated_at: str,
    finished_at: str,
) -> Mapping[str, Any]:
    references = validate_readonly_run_conservation(
        pending_run_receipt, result_contract, result, source_outcomes
    )
    values = _plain(pending_run_receipt)
    for derived in (
        "run_id", "run_receipt_id", "run_content_fingerprint",
        "input_set_fingerprint", "result_set_fingerprint",
    ):
        values.pop(derived)
    values.update({
        "generated_at": generated_at,
        "status": "completed",
        "result_refs": references,
        "finished_at": finished_at,
        "supersedes_run_receipt_id": pending_run_receipt["run_receipt_id"],
        "error": None,
    })
    completed = build_experiment_run_receipt(**values)
    validate_m10c_source_version(completed)
    if (
        completed["run_id"] != pending_run_receipt["run_id"]
        or current_experiment_run((pending_run_receipt, completed)) != completed
    ):
        raise ContractError("M10-C completed receipt changed its run root")
    return completed


@dataclass(frozen=True)
class ReadonlyEvaluationBatch:
    result_contract: str
    source_contract: str
    source_outcomes: tuple[Mapping[str, Any], ...]
    pending_run_receipt: Mapping[str, Any]
    result: Mapping[str, Any]
    completed_run_receipt: Mapping[str, Any]


def validate_readonly_evaluation_batch(batch: ReadonlyEvaluationBatch) -> None:
    if not isinstance(batch, ReadonlyEvaluationBatch):
        raise ContractError("expected an M10-C ReadonlyEvaluationBatch")
    expected = validate_readonly_run_conservation(
        batch.pending_run_receipt,
        batch.result_contract,
        batch.result,
        batch.source_outcomes,
    )
    validate_experiment_run(batch.completed_run_receipt)
    validate_m10c_source_version(batch.completed_run_receipt)
    if (
        batch.completed_run_receipt["status"] != "completed"
        or batch.completed_run_receipt["error"] is not None
        or
        current_experiment_run(
            (batch.pending_run_receipt, batch.completed_run_receipt)
        )
        != batch.completed_run_receipt
        or _plain(batch.completed_run_receipt["result_refs"]) != expected
    ):
        raise ContractError("M10-C batch does not conserve its result")


def evaluate_portfolio_boundary(
    trade_outcomes: Iterable[Mapping[str, Any]],
    *,
    portfolio_scope: Mapping[str, Any],
    pending_run_receipt: Mapping[str, Any],
    generated_at: str,
    finished_at: str,
    previous_results: Iterable[Mapping[str, Any]] = (),
) -> ReadonlyEvaluationBatch:
    frozen_outcomes = tuple(trade_outcomes)
    result = produce_portfolio_boundary(
        frozen_outcomes,
        portfolio_scope=portfolio_scope,
        pending_run_receipt=pending_run_receipt,
        generated_at=generated_at,
        previous_results=previous_results,
    )
    completed = complete_readonly_run(
        pending_run_receipt,
        "PortfolioRun",
        result,
        frozen_outcomes,
        generated_at=finished_at,
        finished_at=finished_at,
    )
    batch = ReadonlyEvaluationBatch(
        "PortfolioRun", "TradeOutcome", frozen_outcomes,
        pending_run_receipt, result, completed
    )
    validate_readonly_evaluation_batch(batch)
    return batch


def evaluate_research_aggregate(
    outcomes: Iterable[Mapping[str, Any]],
    *,
    aggregate_scope: Mapping[str, Any],
    pending_run_receipt: Mapping[str, Any],
    generated_at: str,
    finished_at: str,
    previous_results: Iterable[Mapping[str, Any]] = (),
) -> ReadonlyEvaluationBatch:
    frozen_outcomes = tuple(outcomes)
    result = produce_research_aggregate(
        frozen_outcomes,
        aggregate_scope=aggregate_scope,
        pending_run_receipt=pending_run_receipt,
        generated_at=generated_at,
        previous_results=previous_results,
    )
    completed = complete_readonly_run(
        pending_run_receipt,
        "ResearchAggregate",
        result,
        frozen_outcomes,
        generated_at=finished_at,
        finished_at=finished_at,
    )
    batch = ReadonlyEvaluationBatch(
        "ResearchAggregate",
        (
            "ForwardOutcome"
            if aggregate_scope["source_result_type"] == "forward_outcome"
            else "TradeOutcome"
        ),
        frozen_outcomes,
        pending_run_receipt,
        result,
        completed,
    )
    validate_readonly_evaluation_batch(batch)
    return batch


def store_readonly_evaluation_batch(
    store: Any, batch: ReadonlyEvaluationBatch
) -> tuple[Any, ...]:
    """Persist pending, one M10-C result, then its completed receipt."""

    from .storage import EvaluationShadowStore

    if not isinstance(store, EvaluationShadowStore):
        raise ContractError("M10-C storage requires EvaluationShadowStore")
    validate_readonly_evaluation_batch(batch)
    paths = [store.write_run_receipt(batch.pending_run_receipt)]
    paths.append(store.write_result(
        batch.result_contract,
        batch.result,
        source_records=batch.source_outcomes,
    ))
    paths.append(store.write_run_receipt(batch.completed_run_receipt))
    return tuple(paths)


__all__ = [
    "M10_C_SOURCE_VERSION", "READONLY_ADAPTER_VERSION", "READONLY_ENGINE_NAME",
    "READONLY_ENGINE_VERSION", "ReadonlyEvaluationBatch", "build_aggregate_scope",
    "build_readonly_pending_run", "complete_readonly_run",
    "evaluate_portfolio_boundary", "evaluate_research_aggregate",
    "produce_portfolio_boundary", "produce_research_aggregate",
    "readonly_run_scope_fingerprint", "store_readonly_evaluation_batch",
    "validate_readonly_evaluation_batch", "validate_readonly_run_conservation",
    "validate_readonly_receipt_identity",
]
