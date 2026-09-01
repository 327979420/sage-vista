"""Sole M08 formal producer for immutable plans and simulated exit states."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from services.contracts.market_data import canonical_fingerprint, require_date
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError, validate_contract
from services.factors.support import SupportEvidenceBatch, validate_support_evidence_batch
from services.market_data.normalization import validate_adjusted_rows
from services.market_data.repository import RepositoryRead
from services.ranking.producer import validate_ranking_snapshot

from .policies import EXIT_POLICY, PLAN_POLICY, validate_policy


TRADE_PLAN_SCHEMA_VERSION = "2.0.0"
EXIT_STATE_SCHEMA_VERSION = "2.0.0"
EXECUTION_PRODUCER_VERSION = "m08-shadow-1.0.0"


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


def _semantic(payload: Mapping[str, Any], fingerprint_field: str) -> dict[str, Any]:
    return {
        key: _plain(value)
        for key, value in payload.items()
        if key not in {"generated_at", fingerprint_field}
    }


def _plan_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_major": 2,
        "as_of": payload["as_of"],
        "signal_date": payload["signal_date"],
        "entry_date": payload["entry_date"],
        "path_status": payload["path_status"],
        "plan_role": payload["plan_role"],
        "instrument_id": payload["instrument_id"],
        "ranking_snapshot_id": payload["ranking_snapshot_id"],
        "score_result_id": payload["score_result_id"],
        "gate_event_id": payload["gate_event_id"],
        "input_identity": _plain(payload["input_identity"]),
        "support_evidence_id": payload["support_evidence_id"],
        "entry": _plain(payload["entry"]),
        "plan_policy_version": payload["plan_policy_version"],
        "plan_policy_fingerprint": payload["plan_policy_fingerprint"],
        "exit_policy_version": payload["exit_policy_version"],
        "exit_policy_fingerprint": payload["exit_policy_fingerprint"],
    }


def validate_trade_plan(payload: Mapping[str, Any]) -> None:
    validate_contract("TradePlan", payload)
    if payload["schema_version"] != TRADE_PLAN_SCHEMA_VERSION:
        raise ContractError("formal M08 consumers require TradePlan 2.0.0")
    if payload["path_status"] != "formal" or payload["plan_role"] not in {"shadow", "comparison", "authoritative"}:
        raise ContractError("TradePlan path or role is invalid")
    if _plain(payload["input_identity"]["adjustment_policy"]) != ADJUSTMENT_POLICY:
        raise ContractError("TradePlan must bind the M02 adjustment policy")
    if payload["price_basis"] != "provider_adjusted_ohlcv":
        raise ContractError("TradePlan price_basis must describe adjusted data, not broker fills")
    expected = "plan:" + canonical_fingerprint(_plan_identity(payload))
    if payload["plan_id"] != expected:
        raise ContractError("TradePlan id does not match its complete identity")
    if payload["plan_content_fingerprint"] != canonical_fingerprint(
        _semantic(payload, "plan_content_fingerprint")
    ):
        raise ContractError("TradePlan content fingerprint is invalid")
    if payload["status"] != "active":
        raise ContractError("a complete TradePlan must be active")
    entry = float(payload["entry"]["price"])
    stop = float(payload["stop"]["price"])
    target = float(payload["target"]["price"])
    if not 0 < stop < entry < target:
        raise ContractError("TradePlan prices are not executable")
    if payload["max_hold_sessions"] != 40 or payload["target"]["r_multiple"] != 2.0:
        raise ContractError("M08 v1 plan must preserve the approved legacy behavior")
    if list(payload["disabled_experiments"]) != list(PLAN_POLICY["rules"]["disabled_experiments"]):
        raise ContractError("deferred experiments must remain disabled")


@dataclass(frozen=True)
class TradePlanBatch:
    batch_id: str
    as_of: str
    ranking_snapshot_id: str
    plans: tuple[Mapping[str, Any], ...]
    decisions: tuple[Mapping[str, Any], ...]


def validate_trade_plan_batch(batch: TradePlanBatch) -> None:
    """Validate one complete M08 decision batch before M09 links to it."""

    if not isinstance(batch, TradePlanBatch):
        raise ContractError("expected an M08 TradePlanBatch")
    plans = list(batch.plans)
    decisions = list(batch.decisions)
    plan_by_id: dict[str, Mapping[str, Any]] = {}
    for plan in plans:
        validate_trade_plan(plan)
        plan_id = str(plan["plan_id"])
        if plan_id in plan_by_id:
            raise ContractError("TradePlanBatch contains duplicate plans")
        if plan["signal_date"] != batch.as_of or plan["ranking_snapshot_id"] != batch.ranking_snapshot_id:
            raise ContractError("TradePlanBatch plan does not match its batch identity")
        plan_by_id[plan_id] = plan
    if plans != sorted(plans, key=lambda item: str(item["instrument_id"])):
        raise ContractError("TradePlanBatch plans must use canonical order")
    decision_ids: set[str] = set()
    referenced_plans: set[str] = set()
    for decision in decisions:
        required = {
            "instrument_id", "ranking_snapshot_id", "score_result_id",
            "gate_event_id", "status", "reason", "plan_id",
        }
        if not isinstance(decision, Mapping) or required - decision.keys():
            raise ContractError("TradePlanBatch decision is incomplete")
        score_result_id = str(decision["score_result_id"])
        if score_result_id in decision_ids:
            raise ContractError("TradePlanBatch contains duplicate decisions")
        decision_ids.add(score_result_id)
        if decision["ranking_snapshot_id"] != batch.ranking_snapshot_id:
            raise ContractError("TradePlanBatch decision references another ranking")
        status = decision["status"]
        if status not in {"created", "not_created", "unavailable"}:
            raise ContractError("TradePlanBatch decision status is invalid")
        plan_id = decision["plan_id"]
        if status == "created":
            if plan_id not in plan_by_id:
                raise ContractError("created TradePlanBatch decision has no plan")
            plan = plan_by_id[str(plan_id)]
            if any(
                decision[field] != plan[field]
                for field in ("instrument_id", "score_result_id", "gate_event_id")
            ):
                raise ContractError("TradePlanBatch decision does not match its plan")
            if decision["reason"] is not None:
                raise ContractError("created TradePlanBatch decision cannot have a reason")
            referenced_plans.add(str(plan_id))
        elif plan_id is not None or not isinstance(decision["reason"], str) or not decision["reason"]:
            raise ContractError("uncreated TradePlanBatch decision requires one explicit reason")
    if decisions != sorted(decisions, key=lambda item: str(item["instrument_id"])):
        raise ContractError("TradePlanBatch decisions must use canonical order")
    if referenced_plans != set(plan_by_id):
        raise ContractError("TradePlanBatch contains a plan without one created decision")
    identity = {
        "as_of": batch.as_of,
        "ranking_snapshot_id": batch.ranking_snapshot_id,
        "plans": [
            {"id": item["plan_id"], "content": item["plan_content_fingerprint"]}
            for item in plans
        ],
        "decisions": [_plain(item) for item in decisions],
    }
    if batch.batch_id != "trade-plan-batch:" + canonical_fingerprint(identity):
        raise ContractError("TradePlanBatch identity does not match its contents")


def _validated_entry_read(read: RepositoryRead, *, instrument_id: str, signal_date: str) -> tuple[dict[str, Any], ...]:
    if not isinstance(read, RepositoryRead) or read.instrument_id != instrument_id:
        raise ContractError("entry evidence is not the requested M02 repository read")
    rows = validate_adjusted_rows(read.rows)
    if read.point_in_time_fingerprint != canonical_fingerprint(list(rows)):
        raise ContractError("entry repository fingerprint does not match adjusted rows")
    if not rows or rows[-1]["date"] != read.as_of:
        raise ContractError("entry repository read is not complete through its as_of")
    after = tuple(row for row in rows if row["date"] > signal_date)
    if not after or after[0]["date"] != read.as_of:
        raise ContractError("entry read must end at the first available session after the signal")
    return rows


def produce_trade_plans(
    ranking_snapshot: Mapping[str, Any],
    support_evidence: SupportEvidenceBatch,
    *,
    entry_reads: Mapping[str, RepositoryRead],
    generated_at: str,
    plan_policy: Mapping[str, Any] = PLAN_POLICY,
    exit_policy: Mapping[str, Any] = EXIT_POLICY,
) -> TradePlanBatch:
    """Create plans only for selected entries after their real next open exists."""

    validate_ranking_snapshot(ranking_snapshot)
    validate_support_evidence_batch(support_evidence)
    validate_policy(plan_policy, expected_kind="plan")
    validate_policy(exit_policy, expected_kind="exit")
    if ranking_snapshot["path_status"] != "formal" or support_evidence.path_status != "formal":
        raise ContractError("formal M08 cannot accept legacy evidence")
    if support_evidence.as_of != ranking_snapshot["as_of"]:
        raise ContractError("support and ranking dates differ")
    support_by_event = {str(item["gate_event_id"]): item for item in support_evidence.evidence}
    selected_ids = {str(item["score_result_id"]) for item in ranking_snapshot["selected_entries"]}
    plans: list[Mapping[str, Any]] = []
    decisions: list[Mapping[str, Any]] = []
    for entry in ranking_snapshot["ranked_entries"]:
        decision = {
            "instrument_id": entry["instrument_id"],
            "ranking_snapshot_id": ranking_snapshot["ranking_snapshot_id"],
            "score_result_id": entry["score_result_id"],
            "gate_event_id": entry["gate_event_id"],
        }
        if entry["score_result_id"] not in selected_ids:
            decisions.append(_freeze({**decision, "status": "not_created", "reason": "not_selected_for_plan", "plan_id": None}))
            continue
        support = support_by_event.get(str(entry["gate_event_id"]))
        if support is None or support["instrument_id"] != entry["instrument_id"]:
            decisions.append(_freeze({**decision, "status": "unavailable", "reason": "support_evidence_missing", "plan_id": None}))
            continue
        support_plan = support["support_plan"]
        if not support_plan["available"]:
            decisions.append(_freeze({**decision, "status": "unavailable", "reason": "support_unavailable", "plan_id": None}))
            continue
        read = entry_reads.get(str(entry["instrument_id"]))
        if read is None:
            decisions.append(_freeze({**decision, "status": "unavailable", "reason": "next_adjusted_open_unavailable", "plan_id": None}))
            continue
        rows = _validated_entry_read(read, instrument_id=str(entry["instrument_id"]), signal_date=str(ranking_snapshot["as_of"]))
        entry_row = rows[-1]
        entry_price = float(entry_row["open"])
        support_level = float(support_plan["level"])
        structural_stop = support_level * (1 - float(plan_policy["rules"]["support_buffer_fraction"]))
        maximum_loss_stop = entry_price * (1 - float(plan_policy["rules"]["maximum_loss_fraction"]))
        stop = max(structural_stop, maximum_loss_stop)
        if stop <= 0 or stop >= entry_price:
            decisions.append(_freeze({**decision, "status": "unavailable", "reason": "entry_at_or_below_planned_stop", "plan_id": None}))
            continue
        risk = entry_price - stop
        target = entry_price + float(plan_policy["rules"]["target_r_multiple"]) * risk
        payload: dict[str, Any] = {
            "schema_version": TRADE_PLAN_SCHEMA_VERSION,
            "as_of": entry_row["date"],
            "generated_at": generated_at,
            "source_version": {"execution_producer": EXECUTION_PRODUCER_VERSION},
            "future_data_used": False,
            "event_id": entry["gate_event_id"],
            "signal_date": ranking_snapshot["as_of"],
            "entry_date": entry_row["date"],
            "path_status": "formal",
            "plan_role": ranking_snapshot["ranking_role"],
            "instrument_id": entry["instrument_id"],
            "ranking_snapshot_id": ranking_snapshot["ranking_snapshot_id"],
            "score_result_id": entry["score_result_id"],
            "gate_event_id": entry["gate_event_id"],
            "input_identity": {
                "universe_id": ranking_snapshot["input_identity"]["universe_id"],
                "signal_market_snapshot_id": ranking_snapshot["input_identity"]["market_snapshot_id"],
                "entry_market_data_fingerprint": read.point_in_time_fingerprint,
                "adjustment_policy": dict(ADJUSTMENT_POLICY),
            },
            "support_evidence_id": support["support_evidence_id"],
            "technical_evidence_ids": list(support["technical_evidence_ids"]),
            "price_basis": "provider_adjusted_ohlcv",
            "entry": {"rule": "next_adjusted_open", "date": entry_row["date"], "price": round(entry_price, 6)},
            "support": {"frozen_as_of": support["as_of"], "level": round(support_level, 6), "source": support_plan["source"]},
            "stop": {
                "price": round(stop, 6),
                "structural_stop": round(structural_stop, 6),
                "maximum_loss_stop": round(maximum_loss_stop, 6),
                "source": support_plan["source"] if structural_stop >= maximum_loss_stop else "max-loss-10pct-cap",
            },
            "target": {"price": round(target, 6), "r_multiple": 2.0},
            "max_hold_sessions": 40,
            "invalidation_conditions": ["missing_entry_price", "missing_support_evidence", "entry_at_or_below_planned_stop"],
            "plan_policy_version": plan_policy["policy_version"],
            "plan_policy_fingerprint": plan_policy["policy_fingerprint"],
            "exit_policy_version": exit_policy["policy_version"],
            "exit_policy_fingerprint": exit_policy["policy_fingerprint"],
            "execution_policy_version": plan_policy["rules"]["legacy_execution_policy_version"],
            "disabled_experiments": list(plan_policy["rules"]["disabled_experiments"]),
            "status": "active",
        }
        payload["plan_id"] = "plan:" + canonical_fingerprint(_plan_identity(payload))
        payload["plan_content_fingerprint"] = canonical_fingerprint(_semantic(payload, "plan_content_fingerprint"))
        validate_trade_plan(payload)
        frozen = _freeze(payload)
        plans.append(frozen)
        decisions.append(_freeze({**decision, "status": "created", "reason": None, "plan_id": payload["plan_id"]}))
    plans.sort(key=lambda item: str(item["instrument_id"]))
    decisions.sort(key=lambda item: str(item["instrument_id"]))
    identity = {
        "as_of": ranking_snapshot["as_of"],
        "ranking_snapshot_id": ranking_snapshot["ranking_snapshot_id"],
        "plans": [{"id": item["plan_id"], "content": item["plan_content_fingerprint"]} for item in plans],
        "decisions": [_plain(item) for item in decisions],
    }
    batch = TradePlanBatch(
        batch_id="trade-plan-batch:" + canonical_fingerprint(identity),
        as_of=str(ranking_snapshot["as_of"]),
        ranking_snapshot_id=str(ranking_snapshot["ranking_snapshot_id"]),
        plans=tuple(plans),
        decisions=tuple(decisions),
    )
    validate_trade_plan_batch(batch)
    return batch


def _exit_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_major": 2,
        "plan_id": payload["plan_id"],
        "as_of": payload["as_of"],
        "previous_exit_state_id": payload["previous_exit_state_id"],
        "holding_sessions": payload["holding_sessions"],
        "state": payload["state"],
        "market_data_fingerprint": payload["market_data_fingerprint"],
        "exit_policy_version": payload["exit_policy_version"],
        "exit_policy_fingerprint": payload["exit_policy_fingerprint"],
    }


def validate_exit_state(payload: Mapping[str, Any]) -> None:
    validate_contract("ExitState", payload)
    validate_trade_plan(payload["plan"])
    if payload["schema_version"] != EXIT_STATE_SCHEMA_VERSION or payload["path_status"] != "formal":
        raise ContractError("formal M08 consumers require ExitState 2.0.0")
    if payload["exit_state_id"] != "exit-state:" + canonical_fingerprint(_exit_identity(payload)):
        raise ContractError("ExitState id does not match its transition identity")
    if payload["exit_state_content_fingerprint"] != canonical_fingerprint(
        _semantic(payload, "exit_state_content_fingerprint")
    ):
        raise ContractError("ExitState content fingerprint is invalid")
    if payload["state"] not in {"active", "closed_stop_gap", "closed_stop", "closed_target", "closed_time_40d"}:
        raise ContractError("ExitState state is invalid")
    if any(key in payload for key in ("return", "r_multiple", "mfe", "mae")):
        raise ContractError("M08 ExitState cannot contain performance metrics")


def advance_exit_state(
    plan: Mapping[str, Any],
    *,
    completed_bars: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    generated_at: str,
    previous_state: Mapping[str, Any] | None = None,
    exit_policy: Mapping[str, Any] = EXIT_POLICY,
) -> Mapping[str, Any]:
    """Rebuild one immutable current state from completed bars only."""

    validate_trade_plan(plan)
    validate_policy(exit_policy, expected_kind="exit")
    rows = validate_adjusted_rows(completed_bars)
    path = tuple(row for row in rows if row["date"] >= plan["entry_date"])
    if path and path[0]["date"] != plan["entry_date"]:
        raise ContractError("exit path must begin on the plan entry date")
    if previous_state is not None:
        validate_exit_state(previous_state)
        if previous_state["plan_id"] != plan["plan_id"]:
            raise ContractError("ExitState revision crosses TradePlan identities")
        prior_held = int(previous_state["holding_sessions"])
        if prior_held > len(path):
            raise ContractError("ExitState revision is missing previously observed bars")
        if canonical_fingerprint(list(path[:prior_held])) != previous_state["market_data_fingerprint"]:
            raise ContractError("ExitState revision rewrites previously observed market evidence")
        if previous_state["state"] != "active":
            if prior_held == len(path):
                return previous_state
            raise ContractError("a terminal ExitState cannot be advanced")
    stop = float(plan["stop"]["price"])
    target = float(plan["target"]["price"])
    state = "active"
    exit_reason = None
    execution_price = None
    exit_date = None
    held = min(len(path), int(plan["max_hold_sessions"]))
    for index, bar in enumerate(path[: int(plan["max_hold_sessions"])], 1):
        if float(bar["open"]) <= stop:
            state, exit_reason, execution_price = "closed_stop_gap", "stop_gap", float(bar["open"])
        elif float(bar["low"]) <= stop:
            state, exit_reason, execution_price = "closed_stop", "stop", stop
        elif float(bar["open"]) >= target or float(bar["high"]) >= target:
            state, exit_reason, execution_price = "closed_target", "target", target
        elif index == int(plan["max_hold_sessions"]):
            state, exit_reason, execution_price = "closed_time_40d", "time_40d", float(bar["close"])
        if state != "active":
            held, exit_date = index, bar["date"]
            break
    as_of = path[min(held, len(path)) - 1]["date"] if path and held else plan["entry_date"]
    market_fingerprint = canonical_fingerprint(list(path[:held]))
    payload: dict[str, Any] = {
        "schema_version": EXIT_STATE_SCHEMA_VERSION,
        "as_of": as_of,
        "generated_at": generated_at,
        "source_version": {"execution_producer": EXECUTION_PRODUCER_VERSION},
        "future_data_used": False,
        "exit_state_id": "pending",
        "plan_id": plan["plan_id"],
        "plan": _plain(plan),
        "path_status": "formal",
        "previous_exit_state_id": previous_state["exit_state_id"] if previous_state else None,
        "market_data_fingerprint": market_fingerprint,
        "price_basis": "provider_adjusted_ohlcv",
        "holding_sessions": held,
        "state": state,
        "exit_reason": exit_reason,
        "exit_date": exit_date,
        "execution_price": round(execution_price, 6) if execution_price is not None else None,
        "exit_policy_version": exit_policy["policy_version"],
        "exit_policy_fingerprint": exit_policy["policy_fingerprint"],
    }
    payload["exit_state_id"] = "exit-state:" + canonical_fingerprint(_exit_identity(payload))
    payload["exit_state_content_fingerprint"] = canonical_fingerprint(_semantic(payload, "exit_state_content_fingerprint"))
    validate_exit_state(payload)
    if previous_state is not None and held == int(previous_state["holding_sessions"]):
        if (
            payload["market_data_fingerprint"] == previous_state["market_data_fingerprint"]
            and payload["state"] == previous_state["state"]
            and payload["execution_price"] == previous_state["execution_price"]
        ):
            return previous_state
    return _freeze(payload)


__all__ = [
    "EXIT_STATE_SCHEMA_VERSION", "TRADE_PLAN_SCHEMA_VERSION", "TradePlanBatch",
    "advance_exit_state", "produce_trade_plans", "validate_exit_state", "validate_trade_plan",
]
