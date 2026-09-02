"""Run M10-B outcomes through one receipt-bound internal baseline path.

The low-level producers require a pending ExperimentRun receipt before they
calculate anything.  This module closes that receipt only after every outcome
has validated, so a completed run can never claim missing or foreign results.
Daily and replay shadows call these same two entry points.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from services.contracts.validation import ContractError

from .baseline import (
    BASELINE_ADAPTER_VERSION,
    BASELINE_ENGINE_NAME,
    BASELINE_ENGINE_VERSION,
    BASELINE_SOURCE_VERSION,
    produce_forward_outcomes,
    produce_trade_outcome,
)
from .contracts import (
    RESULT_TYPES,
    build_experiment_run_receipt,
    current_experiment_run,
    validate_experiment_run,
    validate_result,
)
from .storage import EvaluationShadowStore


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


@dataclass(frozen=True)
class BaselineEvaluationBatch:
    """One pending receipt, its immutable results, and the closing receipt."""

    result_contract: str
    pending_run_receipt: Mapping[str, Any]
    outcomes: tuple[Mapping[str, Any], ...]
    completed_run_receipt: Mapping[str, Any]


def _validate_internal_receipt(receipt: Mapping[str, Any]) -> None:
    validate_experiment_run(receipt)
    if _plain(receipt["engine"]) != {
        "name": BASELINE_ENGINE_NAME,
        "version": BASELINE_ENGINE_VERSION,
        "adapter_version": BASELINE_ADAPTER_VERSION,
    }:
        raise ContractError("M10-B run receipt does not use the internal baseline engine")


def _validate_outcome_ownership(
    receipt: Mapping[str, Any], outcomes: Iterable[Mapping[str, Any]]
) -> None:
    for outcome in outcomes:
        if (
            outcome["run_id"] != receipt["run_id"]
            or outcome["path_status"] != receipt["path_status"]
            or outcome["result_role"] != receipt["result_role"]
            or outcome["partition_role"] != receipt["partition_role"]
            or list(outcome["bias_labels"]) != list(receipt["bias_labels"])
            or _plain(outcome["source_version"])
            != {"evaluation_contracts": BASELINE_SOURCE_VERSION}
        ):
            raise ContractError("M10-B outcome does not belong to this run receipt")


def _result_references(
    contract_name: str, outcomes: Iterable[Mapping[str, Any]]
) -> list[dict[str, str]]:
    if contract_name not in {"ForwardOutcome", "TradeOutcome"}:
        raise ContractError("M10-B only evaluates ForwardOutcome and TradeOutcome")
    id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
    references: list[dict[str, str]] = []
    for outcome in outcomes:
        validate_result(contract_name, outcome)
        references.append({
            "id": str(outcome[id_field]),
            "content_fingerprint": str(outcome[fingerprint_field]),
        })
    if not references:
        raise ContractError("a completed M10-B run must contain at least one outcome")
    return sorted(
        references,
        key=lambda item: (item["id"], item["content_fingerprint"]),
    )


def complete_baseline_run(
    pending_run_receipt: Mapping[str, Any],
    contract_name: str,
    outcomes: Iterable[Mapping[str, Any]],
    *,
    generated_at: str,
    finished_at: str,
) -> Mapping[str, Any]:
    """Append a completed receipt whose result set exactly matches outcomes."""

    _validate_internal_receipt(pending_run_receipt)
    if (
        pending_run_receipt["status"] != "pending"
        or pending_run_receipt["result_refs"]
    ):
        raise ContractError("M10-B completion requires its pending root receipt")
    frozen_outcomes = tuple(outcomes)
    references = _result_references(contract_name, frozen_outcomes)
    _validate_outcome_ownership(pending_run_receipt, frozen_outcomes)

    values = _plain(pending_run_receipt)
    for derived in (
        "run_id",
        "run_receipt_id",
        "run_content_fingerprint",
        "input_set_fingerprint",
        "result_set_fingerprint",
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
    if completed["run_id"] != pending_run_receipt["run_id"]:
        raise ContractError("completed receipt changed the M10-B run root")
    if current_experiment_run((completed, pending_run_receipt)) != completed:
        raise ContractError("completed receipt is not the unique run-chain leaf")
    return completed


def validate_baseline_evaluation_batch(batch: BaselineEvaluationBatch) -> None:
    """Validate receipt/result conservation for one complete shadow run."""

    if not isinstance(batch, BaselineEvaluationBatch):
        raise ContractError("expected an M10-B BaselineEvaluationBatch")
    expected = _result_references(batch.result_contract, batch.outcomes)
    _validate_internal_receipt(batch.pending_run_receipt)
    _validate_internal_receipt(batch.completed_run_receipt)
    if current_experiment_run(
        (batch.completed_run_receipt, batch.pending_run_receipt)
    ) != batch.completed_run_receipt:
        raise ContractError("M10-B batch receipt chain is not complete")
    if _plain(batch.completed_run_receipt["result_refs"]) != expected:
        raise ContractError("M10-B completed receipt does not conserve result references")
    _validate_outcome_ownership(batch.pending_run_receipt, batch.outcomes)


def evaluate_forward_baseline(
    event: Mapping[str, Any],
    market_read: Any,
    market_snapshot: Mapping[str, Any],
    session_calendar: Mapping[str, Any],
    *,
    universe_content_fingerprint: str,
    pending_run_receipt: Mapping[str, Any],
    generated_at: str,
    finished_at: str,
    previous_outcomes: Iterable[Mapping[str, Any]] = (),
) -> BaselineEvaluationBatch:
    """Evaluate all approved Forward windows and close their one run receipt."""

    outcomes = produce_forward_outcomes(
        event,
        market_read,
        market_snapshot,
        session_calendar,
        universe_content_fingerprint=universe_content_fingerprint,
        pending_run_receipt=pending_run_receipt,
        generated_at=generated_at,
        previous_outcomes=previous_outcomes,
    )
    completed = complete_baseline_run(
        pending_run_receipt,
        "ForwardOutcome",
        outcomes,
        generated_at=finished_at,
        finished_at=finished_at,
    )
    batch = BaselineEvaluationBatch(
        result_contract="ForwardOutcome",
        pending_run_receipt=pending_run_receipt,
        outcomes=outcomes,
        completed_run_receipt=completed,
    )
    validate_baseline_evaluation_batch(batch)
    return batch


def evaluate_trade_baseline(
    event: Mapping[str, Any],
    trade_plan_link: Mapping[str, Any],
    trade_plan: Mapping[str, Any] | None,
    exit_states: Iterable[Mapping[str, Any]],
    exit_state_link: Mapping[str, Any] | None,
    market_read: Any,
    market_snapshot: Mapping[str, Any],
    *,
    universe_content_fingerprint: str,
    pending_run_receipt: Mapping[str, Any],
    generated_at: str,
    finished_at: str,
    previous_outcomes: Iterable[Mapping[str, Any]] = (),
) -> BaselineEvaluationBatch:
    """Evaluate one M08 trade without re-running its execution state machine."""

    outcome = produce_trade_outcome(
        event,
        trade_plan_link,
        trade_plan,
        exit_states,
        exit_state_link,
        market_read,
        market_snapshot,
        universe_content_fingerprint=universe_content_fingerprint,
        pending_run_receipt=pending_run_receipt,
        generated_at=generated_at,
        previous_outcomes=previous_outcomes,
    )
    outcomes = (outcome,)
    completed = complete_baseline_run(
        pending_run_receipt,
        "TradeOutcome",
        outcomes,
        generated_at=finished_at,
        finished_at=finished_at,
    )
    batch = BaselineEvaluationBatch(
        result_contract="TradeOutcome",
        pending_run_receipt=pending_run_receipt,
        outcomes=outcomes,
        completed_run_receipt=completed,
    )
    validate_baseline_evaluation_batch(batch)
    return batch


def store_baseline_evaluation_batch(
    store: EvaluationShadowStore, batch: BaselineEvaluationBatch
) -> tuple[Any, ...]:
    """Persist pending first, results second, and the truthful completion last."""

    if not isinstance(store, EvaluationShadowStore):
        raise ContractError("M10-B storage requires EvaluationShadowStore")
    validate_baseline_evaluation_batch(batch)
    paths = [store.write_run_receipt(batch.pending_run_receipt)]
    paths.extend(
        store.write_result(batch.result_contract, outcome)
        for outcome in batch.outcomes
    )
    paths.append(store.write_run_receipt(batch.completed_run_receipt))
    return tuple(paths)


__all__ = [
    "BaselineEvaluationBatch",
    "complete_baseline_run",
    "evaluate_forward_baseline",
    "evaluate_trade_baseline",
    "store_baseline_evaluation_batch",
    "validate_baseline_evaluation_batch",
]
