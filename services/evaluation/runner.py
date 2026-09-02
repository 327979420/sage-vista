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
    baseline_run_scope_fingerprint,
    outcome_result_scope_keys,
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
from .policies import FORWARD_WINDOWS


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


def _reference_prefix(stable_id: str) -> str:
    marker = ":sha256:"
    if marker not in stable_id:
        raise ContractError("M10-B run input reference has no stable SHA-256 identity")
    return stable_id.split(marker, 1)[0]


def _validate_input_reference_shape(
    receipt: Mapping[str, Any],
    contract_name: str,
    outcome: Mapping[str, Any],
) -> None:
    ids = [str(item["id"]) for item in receipt["input_refs"]]
    fingerprints = {
        str(item["id"]): str(item["content_fingerprint"])
        for item in receipt["input_refs"]
    }
    prefixes = [_reference_prefix(item) for item in ids]
    if contract_name == "ForwardOutcome":
        if sorted(prefixes) != sorted(
            ["opportunity", "market", "universe", "session-calendar"]
        ):
            raise ContractError("Forward run input evidence is incomplete or contains extras")
        if (
            outcome["event_id"] not in ids
            or outcome["session_calendar_id"] not in ids
            or outcome["evaluation_market_snapshot_id"] not in ids
            or fingerprints.get(str(outcome["session_calendar_id"]))
            != outcome["session_calendar_fingerprint"]
            or fingerprints.get(str(outcome["evaluation_market_snapshot_id"]))
            != outcome["evaluation_market_snapshot_fingerprint"]
            or outcome["universe_id"] not in ids
            or fingerprints.get(str(outcome["universe_id"]))
            != outcome["universe_content_fingerprint"]
        ):
            raise ContractError("Forward outcome does not belong to the frozen event or calendar")
        return

    planned = outcome["trade_plan_id"] is not None
    expected_prefixes = ["opportunity", "market", "universe", "machine-link"]
    if planned:
        expected_prefixes.extend(["plan", "exit-state", "machine-link"])
    if sorted(prefixes) != sorted(expected_prefixes):
        raise ContractError("Trade run input evidence is incomplete or contains extras")
    required = {
        str(outcome["event_id"]), str(outcome["trade_plan_link_id"]),
        str(outcome["evaluation_market_snapshot_id"]),
        str(outcome["universe_id"]),
    }
    if planned:
        required.update({
            str(outcome["trade_plan_id"]), str(outcome["exit_state_id"]),
        })
    if not required.issubset(ids):
        raise ContractError("Trade outcome does not belong to the frozen event or execution")
    if (
        fingerprints.get(str(outcome["evaluation_market_snapshot_id"]))
        != outcome["evaluation_market_snapshot_fingerprint"]
        or fingerprints.get(str(outcome["universe_id"]))
        != outcome["universe_content_fingerprint"]
    ):
        raise ContractError("Trade outcome changes frozen market or universe evidence")


def validate_run_conservation(
    pending_run_receipt: Mapping[str, Any],
    contract_name: str,
    outcomes: Iterable[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Validate one pending run's promised logical set before completion.

    This is the sole M10-B run/result conservation entry.  Both completion and
    batch/storage validation use it, so missing windows or foreign but valid
    outcomes cannot pass through a weaker path.
    """

    _validate_internal_receipt(pending_run_receipt)
    if (
        pending_run_receipt["status"] != "pending"
        or pending_run_receipt["result_refs"]
    ):
        raise ContractError("M10-B conservation requires the pending root receipt")
    frozen = tuple(outcomes)
    references = _result_references(contract_name, frozen)
    if contract_name == "ForwardOutcome":
        if len(frozen) != len(FORWARD_WINDOWS) or {
            item["window_sessions"] for item in frozen
        } != set(FORWARD_WINDOWS):
            raise ContractError("Forward run must conserve all five approved windows")
    elif contract_name == "TradeOutcome":
        if len(frozen) != 1:
            raise ContractError("Trade run must conserve exactly one logical outcome")
    else:
        raise ContractError("M10-B only evaluates ForwardOutcome and TradeOutcome")

    logical_ids = [str(item["logical_result_id"]) for item in frozen]
    if len(logical_ids) != len(set(logical_ids)):
        raise ContractError("M10-B run contains duplicate logical outcomes")
    for outcome in frozen:
        if (
            outcome["run_id"] != pending_run_receipt["run_id"]
            or outcome["path_status"] != pending_run_receipt["path_status"]
            or outcome["result_role"] != pending_run_receipt["result_role"]
            or outcome["partition_role"] != pending_run_receipt["partition_role"]
            or list(outcome["bias_labels"])
            != list(pending_run_receipt["bias_labels"])
            or _plain(outcome["source_version"])
            != {"evaluation_contracts": BASELINE_SOURCE_VERSION}
        ):
            raise ContractError("M10-B outcome does not belong to this run receipt")
        _validate_input_reference_shape(pending_run_receipt, contract_name, outcome)
    market_fingerprints = {str(item["market_data_fingerprint"]) for item in frozen}
    if len(market_fingerprints) != 1:
        raise ContractError("M10-B outcomes cross market evidence fingerprints")
    first = frozen[0]
    actual_scope = baseline_run_scope_fingerprint(
        contract_name,
        input_refs=pending_run_receipt["input_refs"],
        policy_refs=pending_run_receipt["policy_refs"],
        path_status=str(pending_run_receipt["path_status"]),
        result_role=str(pending_run_receipt["result_role"]),
        partition_role=str(pending_run_receipt["partition_role"]),
        instrument_id=str(first["instrument_id"]),
        signal_date=str(first["signal_date"]),
        market_data_fingerprint=next(iter(market_fingerprints)),
        expected_result_keys=outcome_result_scope_keys(contract_name, frozen),
    )
    if pending_run_receipt["config_ref"]["content_fingerprint"] != actual_scope:
        raise ContractError("M10-B outcomes do not match the pending run's frozen scope")
    return references


def complete_baseline_run(
    pending_run_receipt: Mapping[str, Any],
    contract_name: str,
    outcomes: Iterable[Mapping[str, Any]],
    *,
    generated_at: str,
    finished_at: str,
) -> Mapping[str, Any]:
    """Append a completed receipt whose result set exactly matches outcomes."""

    frozen_outcomes = tuple(outcomes)
    references = validate_run_conservation(
        pending_run_receipt, contract_name, frozen_outcomes
    )

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
    expected = validate_run_conservation(
        batch.pending_run_receipt, batch.result_contract, batch.outcomes
    )
    _validate_internal_receipt(batch.completed_run_receipt)
    if current_experiment_run(
        (batch.completed_run_receipt, batch.pending_run_receipt)
    ) != batch.completed_run_receipt:
        raise ContractError("M10-B batch receipt chain is not complete")
    if _plain(batch.completed_run_receipt["result_refs"]) != expected:
        raise ContractError("M10-B completed receipt does not conserve result references")


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
    expected = _plain(batch.completed_run_receipt["result_refs"])
    before = store.result_references_for_run(
        str(batch.pending_run_receipt["run_id"])
    )
    if any(item not in expected for item in before):
        raise ContractError("stored M10-B run contains an unregistered result")
    paths = [store.write_run_receipt(batch.pending_run_receipt)]
    paths.extend(
        store.write_result(batch.result_contract, outcome)
        for outcome in batch.outcomes
    )
    actual = store.result_references_for_run(
        str(batch.pending_run_receipt["run_id"])
    )
    if actual != expected:
        raise ContractError("stored M10-B results do not match the complete receipt")
    paths.append(store.write_run_receipt(batch.completed_run_receipt))
    return tuple(paths)


__all__ = [
    "BaselineEvaluationBatch",
    "complete_baseline_run",
    "evaluate_forward_baseline",
    "evaluate_trade_baseline",
    "store_baseline_evaluation_batch",
    "validate_baseline_evaluation_batch",
    "validate_run_conservation",
]
