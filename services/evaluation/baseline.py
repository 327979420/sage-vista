"""Sole internal M10 baseline evaluator for immutable objective outcomes.

This module consumes validated M02, M08, and M09 facts.  It never downloads
data and never recomputes a gate, factor, score, ranking, plan, or exit.  The
first implementation deliberately keeps the calculations small enough to
audit one row at a time.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from services.contracts.market_data import (
    canonical_fingerprint,
    require_date,
    validate_market_data_snapshot,
)
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError, SEMVER
from services.execution import (
    EXIT_POLICY,
    current_exit_state,
    validate_trade_plan,
)
from services.ledger.producer import (
    validate_machine_link,
    validate_opportunity_event,
)
from services.market_data.normalization import validate_adjusted_rows
from services.market_data.repository import RepositoryRead

from .contracts import (
    RESULT_TYPES,
    current_result,
    finalize_result,
    validate_experiment_run,
    validate_result,
)
from .policies import (
    EVALUATION_POLICY,
    FORWARD_WINDOWS,
    FORWARD_WINDOW_POLICY,
    PARTITION_POLICY,
    UNAPPROVED_COST_REFERENCE,
    ZERO_COST_COMPARISON_POLICY,
)


BASELINE_ENGINE_NAME = "sage-vista-internal-baseline"
BASELINE_ENGINE_VERSION = "1.0.0"
BASELINE_ADAPTER_VERSION = "internal-1.0.0"
BASELINE_SOURCE_VERSION = "m10-b-internal-1.0.0"
PRICE_QUANTUM = Decimal("0.00000001")
METRIC_QUANTUM = Decimal("0.0000000001")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
SESSION_CALENDAR_ID = re.compile(r"^session-calendar:sha256:[0-9a-f]{64}$")


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


def _fingerprint(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ContractError(f"{field} must be sha256:<64 lowercase hex>")
    return value


def _decimal(value: Any, field: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ContractError(f"{field} must be a finite number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ContractError(f"{field} must be a finite number") from exc
    if not number.is_finite() or (positive and number <= 0):
        boundary = "positive" if positive else "finite"
        raise ContractError(f"{field} must be {boundary}")
    return number


def _normalized_price(value: Any, field: str) -> float:
    return float(_decimal(value, field, positive=True).quantize(
        PRICE_QUANTUM, rounding=ROUND_HALF_EVEN
    ))


def _normalized_ratio(numerator: Any, denominator: Any, field: str) -> float:
    top = _decimal(numerator, f"{field}.numerator")
    bottom = _decimal(denominator, f"{field}.denominator", positive=True)
    return float(((top / bottom) - Decimal(1)).quantize(
        METRIC_QUANTUM, rounding=ROUND_HALF_EVEN
    ))


def _normalized_quotient(numerator: Any, denominator: Any, field: str) -> float:
    top = _decimal(numerator, f"{field}.numerator")
    bottom = _decimal(denominator, f"{field}.denominator", positive=True)
    return float((top / bottom).quantize(METRIC_QUANTUM, rounding=ROUND_HALF_EVEN))


def build_session_calendar_evidence(
    *,
    calendar_name: str,
    calendar_version: str,
    signal_date: str,
    as_of: str,
    sessions: Sequence[str],
) -> Mapping[str, Any]:
    """Freeze the caller's explicit post-signal trading sessions.

    M10 cannot infer holidays or suspensions from whichever bars happen to be
    present.  The caller therefore supplies the versioned session sequence it
    claims was known at ``as_of``; the evaluator fingerprints and revalidates
    that exact sequence before counting a Forward window.
    """

    if not isinstance(calendar_name, str) or not calendar_name.strip():
        raise ContractError("session calendar name is required")
    if not isinstance(calendar_version, str) or not SEMVER.fullmatch(calendar_version):
        raise ContractError("session calendar version must be SemVer")
    signal_date = require_date(signal_date, "session_calendar.signal_date")
    as_of = require_date(as_of, "session_calendar.as_of")
    if signal_date > as_of:
        raise ContractError("session calendar cannot end before the signal")
    if isinstance(sessions, (str, bytes)):
        raise ContractError("session calendar sessions must be a sequence")
    normalized = [require_date(item, "session_calendar.sessions") for item in sessions]
    if normalized != sorted(set(normalized)):
        raise ContractError("session calendar sessions must be sorted and unique")
    if any(item <= signal_date or item > as_of for item in normalized):
        raise ContractError("session calendar must contain only post-signal sessions through as_of")
    identity = {
        "calendar_name": calendar_name,
        "calendar_version": calendar_version,
    }
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "calendar_id": "session-calendar:" + canonical_fingerprint(identity),
        "calendar_name": calendar_name,
        "calendar_version": calendar_version,
        "signal_date": signal_date,
        "as_of": as_of,
        "sessions": normalized,
    }
    payload["content_fingerprint"] = canonical_fingerprint(payload)
    validate_session_calendar_evidence(payload)
    return _freeze(payload)


def validate_session_calendar_evidence(payload: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "calendar_id", "calendar_name", "calendar_version",
        "signal_date", "as_of", "sessions", "content_fingerprint",
    }
    if not isinstance(payload, Mapping) or set(payload) != required:
        raise ContractError("session calendar evidence fields are incomplete or unknown")
    if payload["schema_version"] != "1.0.0":
        raise ContractError("session calendar evidence schema is unknown")
    if not isinstance(payload["calendar_name"], str) or not payload["calendar_name"].strip():
        raise ContractError("session calendar name is required")
    if not isinstance(payload["calendar_version"], str) or not SEMVER.fullmatch(
        payload["calendar_version"]
    ):
        raise ContractError("session calendar version must be SemVer")
    signal_date = require_date(payload["signal_date"], "session_calendar.signal_date")
    as_of = require_date(payload["as_of"], "session_calendar.as_of")
    sessions = payload["sessions"]
    if not isinstance(sessions, (list, tuple)):
        raise ContractError("session calendar sessions must be a list")
    normalized = [require_date(item, "session_calendar.sessions") for item in sessions]
    if normalized != sorted(set(normalized)):
        raise ContractError("session calendar sessions must be sorted and unique")
    if any(item <= signal_date or item > as_of for item in normalized):
        raise ContractError("session calendar contains an out-of-range session")
    expected_id = "session-calendar:" + canonical_fingerprint({
        "calendar_name": payload["calendar_name"],
        "calendar_version": payload["calendar_version"],
    })
    if payload["calendar_id"] != expected_id or not SESSION_CALENDAR_ID.fullmatch(
        str(payload["calendar_id"])
    ):
        raise ContractError("session calendar ID does not match its versioned source")
    semantic = {
        key: _plain(value) for key, value in payload.items()
        if key != "content_fingerprint"
    }
    if payload["content_fingerprint"] != canonical_fingerprint(semantic):
        raise ContractError("session calendar fingerprint does not match its sessions")


def market_snapshot_evidence_fingerprint(snapshot: Mapping[str, Any]) -> str:
    """Fingerprint one validated M02 snapshot without its generation clock."""

    validate_market_data_snapshot(snapshot)
    return canonical_fingerprint({
        key: _plain(value) for key, value in snapshot.items() if key != "generated_at"
    })


def _validated_market_rows(
    event: Mapping[str, Any],
    read: RepositoryRead,
    market_snapshot: Mapping[str, Any],
    *,
    evaluation_as_of: str,
) -> tuple[dict[str, Any], ...]:
    """Bind delivered rows to their M02 read and market snapshot identities."""

    if not isinstance(read, RepositoryRead):
        raise ContractError("M10 market evidence must be an M02 RepositoryRead")
    if read.instrument_id != event["instrument_id"] or read.as_of != evaluation_as_of:
        raise ContractError("M10 market read crosses its event or evaluation date")
    rows = validate_adjusted_rows(read.rows)
    if any(row["date"] > evaluation_as_of for row in rows):
        raise ContractError("M10 market read contains data after evaluation_as_of")
    actual_fingerprint = canonical_fingerprint(list(rows))
    if read.point_in_time_fingerprint != actual_fingerprint:
        raise ContractError("M10 market read fingerprint does not match delivered rows")

    validate_market_data_snapshot(market_snapshot)
    if (
        market_snapshot["as_of"] != evaluation_as_of
        or market_snapshot["snapshot_id"] is None
        or market_snapshot["universe_id"] != event["input_identity"]["universe_id"]
        or _plain(market_snapshot["adjustment_policy"]) != ADJUSTMENT_POLICY
    ):
        raise ContractError("M10 evaluation snapshot crosses M02 identity or policy")
    matching = [
        item for item in market_snapshot["symbols"]
        if item["instrument_id"] == event["instrument_id"]
    ]
    if len(matching) != 1:
        raise ContractError("M10 evaluation snapshot must contain the event instrument once")
    evidence = matching[0]
    if not rows:
        raise ContractError("M10 evaluation snapshot cannot bind an empty market read")
    if (
        evidence["symbol"] != event["symbol"]
        or evidence["row_count"] != len(rows)
        or evidence["first_date"] != rows[0]["date"]
        or evidence["max_returned_date"] != rows[-1]["date"]
        or evidence["content_fingerprint"] != actual_fingerprint
    ):
        raise ContractError("M10 evaluation snapshot does not match delivered market rows")
    return rows


def _receipt_references(receipt: Mapping[str, Any]) -> dict[str, str]:
    references: dict[str, str] = {}
    for item in receipt["input_refs"]:
        stable_id = str(item["id"])
        if stable_id in references:
            raise ContractError("M10 run receipt contains duplicate input references")
        references[stable_id] = str(item["content_fingerprint"])
    return references


def _require_internal_engine(receipt: Mapping[str, Any]) -> None:
    expected = {
        "name": BASELINE_ENGINE_NAME,
        "version": BASELINE_ENGINE_VERSION,
        "adapter_version": BASELINE_ADAPTER_VERSION,
    }
    if _plain(receipt["engine"]) != expected:
        raise ContractError("M10-B requires the approved internal baseline engine")


def _require_pending_forward_run(
    receipt: Mapping[str, Any],
    *,
    event: Mapping[str, Any],
    market_snapshot: Mapping[str, Any],
    universe_content_fingerprint: str,
    calendar: Mapping[str, Any],
) -> None:
    validate_experiment_run(receipt)
    _require_internal_engine(receipt)
    if receipt["status"] != "pending" or receipt["result_refs"]:
        raise ContractError("Forward evaluation requires its pending root run receipt")
    if receipt["evidence_window"]["evidence_as_of"] != calendar["as_of"]:
        raise ContractError("Forward run receipt and calendar evidence dates differ")
    if receipt["evidence_window"]["start"] > event["signal_date"]:
        raise ContractError("Forward run receipt omits the signal evidence date")
    if (
        receipt["path_status"] != "formal"
        or receipt["path_status"] != event["path_status"]
        or receipt["partition_role"] not in {"development", "validation", "forward"}
    ):
        raise ContractError("Forward run receipt path or partition is invalid")
    refs = _receipt_references(receipt)
    expected = {
        str(event["event_id"]): str(event["event_content_fingerprint"]),
        str(event["input_identity"]["universe_id"]): _fingerprint(
            universe_content_fingerprint, "universe_content_fingerprint"
        ),
        str(market_snapshot["snapshot_id"]): market_snapshot_evidence_fingerprint(
            market_snapshot
        ),
        str(calendar["calendar_id"]): str(calendar["content_fingerprint"]),
    }
    for stable_id, fingerprint in expected.items():
        if refs.get(stable_id) != fingerprint:
            raise ContractError("Forward run receipt omits or changes required input evidence")
    policy_kinds = {str(item["policy_kind"]) for item in receipt["policy_refs"]}
    if not {"adjustment", "evaluation", "forward_window", "partition"}.issubset(
        policy_kinds
    ):
        raise ContractError("Forward run receipt omits an approved policy")


def _finalize_revision(
    contract_name: str,
    values: Mapping[str, Any],
    previous_results: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Append to the one matching chain, while preserving exact replays."""

    for item in previous_results:
        validate_result(contract_name, item)
    initial_values = {**_plain(values), "supersedes_result_id": None}
    initial = finalize_result(contract_name, initial_values)
    matching = [
        item for item in previous_results
        if item["logical_result_id"] == initial["logical_result_id"]
    ]
    if not matching:
        return initial
    leaf = current_result(contract_name, matching)
    if values["as_of"] < leaf["as_of"]:
        raise ContractError("M10 result evaluation cannot move evidence time backwards")

    # Reconstruct the leaf's direct-predecessor binding first.  If all facts
    # are unchanged this yields its exact immutable identity and is idempotent.
    replay = finalize_result(contract_name, {
        **_plain(values),
        "supersedes_result_id": leaf["supersedes_result_id"],
    })
    id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
    if (
        replay[id_field] == leaf[id_field]
        and replay[fingerprint_field] == leaf[fingerprint_field]
    ):
        return leaf
    return finalize_result(contract_name, {
        **_plain(values),
        "supersedes_result_id": leaf[id_field],
    })


def produce_forward_outcomes(
    event: Mapping[str, Any],
    market_read: RepositoryRead,
    market_snapshot: Mapping[str, Any],
    session_calendar: Mapping[str, Any],
    *,
    universe_content_fingerprint: str,
    pending_run_receipt: Mapping[str, Any],
    generated_at: str,
    previous_outcomes: Iterable[Mapping[str, Any]] = (),
) -> tuple[Mapping[str, Any], ...]:
    """Produce all approved Forward windows from one immutable M09 event.

    The first post-signal session's adjusted *open* is the only reference
    price.  The signal close is never read.  Missing calendar sessions remain
    visible as partial/unavailable evidence instead of being replaced by the
    nearest available bar.
    """

    validate_opportunity_event(event)
    if event["path_status"] != "formal" or event["event_role"] != "authoritative":
        raise ContractError("M10 formal ForwardOutcome requires an authoritative event")
    validate_session_calendar_evidence(session_calendar)
    if session_calendar["signal_date"] != event["signal_date"]:
        raise ContractError("Forward calendar belongs to another signal date")
    evaluation_as_of = str(session_calendar["as_of"])
    rows = _validated_market_rows(
        event, market_read, market_snapshot, evaluation_as_of=evaluation_as_of
    )
    _require_pending_forward_run(
        pending_run_receipt,
        event=event,
        market_snapshot=market_snapshot,
        universe_content_fingerprint=universe_content_fingerprint,
        calendar=session_calendar,
    )
    previous = tuple(previous_outcomes)
    row_by_date = {row["date"]: row for row in rows}
    sessions = tuple(session_calendar["sessions"])
    elapsed = len(sessions)
    entry_row = row_by_date.get(sessions[0]) if sessions else None
    entry = (
        {
            "date": sessions[0],
            "price": _normalized_price(entry_row["open"], "ForwardOutcome.entry.open"),
        }
        if entry_row is not None
        else None
    )

    outcomes: list[Mapping[str, Any]] = []
    for window in FORWARD_WINDOWS:
        window_dates = sessions[:window]
        observed_dates = [day for day in window_dates if day in row_by_date]
        observed_through = max(observed_dates) if observed_dates else None
        endpoint = None
        gross_return = None
        mfe = None
        mae = None
        status_reason = None

        if elapsed < window:
            status = "pending"
            status_reason = "window_not_mature"
        else:
            endpoint_row = row_by_date.get(window_dates[-1])
            if endpoint_row is not None:
                endpoint = {
                    "date": window_dates[-1],
                    "price": _normalized_price(
                        endpoint_row["close"], "ForwardOutcome.endpoint.close"
                    ),
                }
            if entry is None:
                status = "unavailable"
                status_reason = "next_session_adjusted_open_unavailable"
            elif endpoint is None:
                status = "unavailable"
                status_reason = "endpoint_adjusted_close_unavailable"
            else:
                gross_return = _normalized_ratio(
                    endpoint["price"], entry["price"], "ForwardOutcome.gross_return"
                )
                if len(observed_dates) != window:
                    status = "partial"
                    status_reason = "window_market_evidence_incomplete"
                else:
                    status = "mature"
                    path = [row_by_date[day] for day in window_dates]
                    mfe = _normalized_ratio(
                        max(row["high"] for row in path),
                        entry["price"],
                        "ForwardOutcome.mfe",
                    )
                    mae = _normalized_ratio(
                        min(row["low"] for row in path),
                        entry["price"],
                        "ForwardOutcome.mae",
                    )

        values = {
            "schema_version": "2.0.0",
            "as_of": evaluation_as_of,
            "generated_at": generated_at,
            "source_version": {"evaluation_contracts": BASELINE_SOURCE_VERSION},
            "future_data_used": False,
            "run_id": pending_run_receipt["run_id"],
            "logical_result_id": "assigned-by-finalizer",
            "supersedes_result_id": None,
            "path_status": pending_run_receipt["path_status"],
            "result_role": pending_run_receipt["result_role"],
            "partition_role": pending_run_receipt["partition_role"],
            "bias_labels": list(pending_run_receipt["bias_labels"]),
            "evaluation_policy": EVALUATION_POLICY,
            "partition_policy": PARTITION_POLICY,
            "event_id": event["event_id"],
            "event_content_fingerprint": event["event_content_fingerprint"],
            "instrument_id": event["instrument_id"],
            "signal_date": event["signal_date"],
            "signal_market_snapshot_id": event["input_identity"]["market_snapshot_id"],
            "window_sessions": window,
            "window_policy": FORWARD_WINDOW_POLICY,
            "session_calendar_id": session_calendar["calendar_id"],
            "session_calendar_fingerprint": session_calendar["content_fingerprint"],
            "status": status,
            "elapsed_session_count": elapsed,
            "observed_session_count": len(observed_dates),
            "observed_through": observed_through,
            "status_reason": status_reason,
            "entry": entry,
            "endpoint": endpoint,
            "gross_return": gross_return,
            "mfe": mfe,
            "mae": mae,
            "price_basis": "provider_adjusted_ohlcv",
            "adjustment_policy": ADJUSTMENT_POLICY,
            "market_data_fingerprint": market_read.point_in_time_fingerprint,
        }
        outcomes.append(_finalize_revision("ForwardOutcome", values, previous))
    return tuple(outcomes)


def _require_pending_trade_run(
    receipt: Mapping[str, Any],
    *,
    event: Mapping[str, Any],
    market_snapshot: Mapping[str, Any],
    universe_content_fingerprint: str,
    trade_plan_link: Mapping[str, Any],
    trade_plan: Mapping[str, Any] | None,
    current_state: Mapping[str, Any] | None,
    exit_state_link: Mapping[str, Any] | None,
) -> None:
    validate_experiment_run(receipt)
    _require_internal_engine(receipt)
    if receipt["status"] != "pending" or receipt["result_refs"]:
        raise ContractError("Trade evaluation requires its pending root run receipt")
    if receipt["path_status"] != "formal" or receipt["path_status"] != event["path_status"]:
        raise ContractError("Trade run receipt path is invalid")
    refs = _receipt_references(receipt)
    expected = {
        str(event["event_id"]): str(event["event_content_fingerprint"]),
        str(event["input_identity"]["universe_id"]): _fingerprint(
            universe_content_fingerprint, "universe_content_fingerprint"
        ),
        str(market_snapshot["snapshot_id"]): market_snapshot_evidence_fingerprint(
            market_snapshot
        ),
        str(trade_plan_link["link_id"]): str(
            trade_plan_link["link_content_fingerprint"]
        ),
    }
    if trade_plan is not None:
        expected[str(trade_plan["plan_id"])] = str(
            trade_plan["plan_content_fingerprint"]
        )
    if current_state is not None:
        expected[str(current_state["exit_state_id"])] = str(
            current_state["exit_state_content_fingerprint"]
        )
    if exit_state_link is not None:
        expected[str(exit_state_link["link_id"])] = str(
            exit_state_link["link_content_fingerprint"]
        )
    for stable_id, fingerprint in expected.items():
        if refs.get(stable_id) != fingerprint:
            raise ContractError("Trade run receipt omits or changes required input evidence")
    policy_kinds = {str(item["policy_kind"]) for item in receipt["policy_refs"]}
    required = {"adjustment", "evaluation", "execution", "partition"}
    if receipt["result_role"] == "comparison":
        required.add("cost_slippage")
    if not required.issubset(policy_kinds):
        raise ContractError("Trade run receipt omits an approved policy")


def _validate_trade_sources(
    event: Mapping[str, Any],
    trade_plan_link: Mapping[str, Any],
    trade_plan: Mapping[str, Any] | None,
    exit_states: Sequence[Mapping[str, Any]],
    exit_state_link: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    """Validate M08/M09 ownership without replaying any execution decision."""

    validate_opportunity_event(event)
    validate_machine_link(trade_plan_link)
    if (
        event["path_status"] != "formal"
        or event["event_role"] != "authoritative"
        or trade_plan_link["event_id"] != event["event_id"]
        or trade_plan_link["instrument_id"] != event["instrument_id"]
        or trade_plan_link["link_type"] != "trade_plan_decision"
    ):
        raise ContractError("Trade evaluation crosses its authoritative M09 event")

    link_status = trade_plan_link["status"]
    if link_status in {"not_created", "unavailable"}:
        if trade_plan is not None or exit_states or exit_state_link is not None:
            raise ContractError("unplanned M09 trade evidence cannot attach M08 execution")
        return None
    if link_status != "created" or trade_plan is None:
        raise ContractError("created trade evidence requires its M08 TradePlan")

    validate_trade_plan(trade_plan)
    if (
        trade_plan["instrument_id"] != event["instrument_id"]
        or trade_plan_link["source_reference"]["plan_id"] != trade_plan["plan_id"]
        or trade_plan_link["source_reference"]["plan_content_fingerprint"]
        != trade_plan["plan_content_fingerprint"]
    ):
        raise ContractError("TradePlan does not match the event's M09 plan link")
    current_state = current_exit_state(exit_states)
    if current_state["plan_id"] != trade_plan["plan_id"] or _plain(
        current_state["plan"]
    ) != _plain(trade_plan):
        raise ContractError("ExitState chain embeds a different TradePlan")
    if exit_state_link is None:
        raise ContractError("Trade evaluation requires the current ExitState M09 link")
    validate_machine_link(exit_state_link)
    if (
        exit_state_link["event_id"] != event["event_id"]
        or exit_state_link["link_type"] != "exit_state"
        or exit_state_link["source_reference"]["exit_state_id"]
        != current_state["exit_state_id"]
        or exit_state_link["source_reference"]["exit_state_content_fingerprint"]
        != current_state["exit_state_content_fingerprint"]
    ):
        raise ContractError("M09 ExitState link does not reference the unique current state")
    return current_state


def produce_trade_outcome(
    event: Mapping[str, Any],
    trade_plan_link: Mapping[str, Any],
    trade_plan: Mapping[str, Any] | None,
    exit_states: Iterable[Mapping[str, Any]],
    exit_state_link: Mapping[str, Any] | None,
    market_read: RepositoryRead,
    market_snapshot: Mapping[str, Any],
    *,
    universe_content_fingerprint: str,
    pending_run_receipt: Mapping[str, Any],
    generated_at: str,
    previous_outcomes: Iterable[Mapping[str, Any]] = (),
) -> Mapping[str, Any]:
    """Calculate one TradeOutcome strictly from frozen M08 execution facts.

    M08 alone decides whether and where the trade entered or exited.  M10
    checks that the delivered price path is the same evidence M08 fingerprinted,
    then calculates only gross return and R.  High/low excursions are not read:
    the unapproved terminal-bar convention remains explicitly unavailable.
    """

    states = tuple(exit_states)
    current_state = _validate_trade_sources(
        event, trade_plan_link, trade_plan, states, exit_state_link
    )
    evaluation_as_of = (
        str(current_state["as_of"]) if current_state is not None
        else str(event["signal_date"])
    )
    rows = _validated_market_rows(
        event, market_read, market_snapshot, evaluation_as_of=evaluation_as_of
    )
    _require_pending_trade_run(
        pending_run_receipt,
        event=event,
        market_snapshot=market_snapshot,
        universe_content_fingerprint=universe_content_fingerprint,
        trade_plan_link=trade_plan_link,
        trade_plan=trade_plan,
        current_state=current_state,
        exit_state_link=exit_state_link,
    )
    if pending_run_receipt["evidence_window"]["evidence_as_of"] != evaluation_as_of:
        raise ContractError("Trade run receipt and ExitState dates differ")

    entry = None
    exit_value = None
    exit_reason = None
    gross_return = None
    gross_r_multiple = None
    holding_sessions = 0
    status_reason = None
    trade_plan_id = None
    trade_plan_fingerprint = None
    exit_state_id = None
    exit_state_fingerprint = None

    if current_state is None:
        status = "no_trade" if trade_plan_link["status"] == "not_created" else "unavailable"
        status_reason = str(trade_plan_link["reason"])
    else:
        assert trade_plan is not None
        trade_plan_id = trade_plan["plan_id"]
        trade_plan_fingerprint = trade_plan["plan_content_fingerprint"]
        exit_state_id = current_state["exit_state_id"]
        exit_state_fingerprint = current_state["exit_state_content_fingerprint"]
        entry = {
            "date": trade_plan["entry"]["date"],
            "price": _normalized_price(
                trade_plan["entry"]["price"], "TradeOutcome.entry.price"
            ),
        }
        holding_sessions = int(current_state["holding_sessions"])
        path = tuple(
            row for row in rows
            if trade_plan["entry_date"] <= row["date"] <= current_state["as_of"]
        )
        if len(path) != holding_sessions or canonical_fingerprint(list(path)) != current_state[
            "market_data_fingerprint"
        ]:
            raise ContractError("Trade market evidence does not match the M08 ExitState path")
        if current_state["state"] == "active":
            status = "pending"
            status_reason = "trade_open"
            if any(
                current_state[field] is not None
                for field in ("exit_reason", "exit_date", "execution_price")
            ):
                raise ContractError("active ExitState cannot contain terminal execution facts")
        else:
            status = "completed"
            exit_reason = current_state["exit_reason"]
            if (
                exit_reason not in {"stop_gap", "stop", "target", "time_40d"}
                or current_state["exit_date"] is None
                or current_state["execution_price"] is None
            ):
                raise ContractError("terminal ExitState lacks its M08 execution facts")
            exit_value = {
                "date": current_state["exit_date"],
                "price": _normalized_price(
                    current_state["execution_price"], "TradeOutcome.exit.price"
                ),
            }
            gross_return = _normalized_ratio(
                exit_value["price"], entry["price"], "TradeOutcome.gross_return"
            )
            initial_risk = _decimal(
                entry["price"], "TradeOutcome.entry.price", positive=True
            ) - _decimal(trade_plan["stop"]["price"], "TradeOutcome.stop.price", positive=True)
            if initial_risk <= 0:
                raise ContractError("TradeOutcome initial risk must be positive")
            gross_r_multiple = _normalized_quotient(
                _decimal(exit_value["price"], "TradeOutcome.exit.price")
                - _decimal(entry["price"], "TradeOutcome.entry.price"),
                initial_risk,
                "TradeOutcome.gross_r_multiple",
            )

    authoritative = pending_run_receipt["result_role"] == "authoritative"
    if authoritative:
        cost_policy = UNAPPROVED_COST_REFERENCE
        net_return = None
        net_status = "unavailable"
        net_reason = "cost_slippage_policy_not_approved"
    else:
        cost_policy = ZERO_COST_COMPARISON_POLICY
        net_return = gross_return if status == "completed" else None
        net_status = "available" if status == "completed" else "unavailable"
        net_reason = None if status == "completed" else "trade_not_completed"

    values = {
        "schema_version": "2.0.0",
        "as_of": evaluation_as_of,
        "generated_at": generated_at,
        "source_version": {"evaluation_contracts": BASELINE_SOURCE_VERSION},
        "future_data_used": False,
        "run_id": pending_run_receipt["run_id"],
        "logical_result_id": "assigned-by-finalizer",
        "supersedes_result_id": None,
        "path_status": pending_run_receipt["path_status"],
        "result_role": pending_run_receipt["result_role"],
        "partition_role": pending_run_receipt["partition_role"],
        "bias_labels": list(pending_run_receipt["bias_labels"]),
        "evaluation_policy": EVALUATION_POLICY,
        "partition_policy": PARTITION_POLICY,
        "event_id": event["event_id"],
        "event_content_fingerprint": event["event_content_fingerprint"],
        "instrument_id": event["instrument_id"],
        "signal_date": event["signal_date"],
        "trade_plan_id": trade_plan_id,
        "trade_plan_content_fingerprint": trade_plan_fingerprint,
        "trade_plan_link_id": trade_plan_link["link_id"],
        "trade_plan_link_content_fingerprint": trade_plan_link[
            "link_content_fingerprint"
        ],
        "exit_state_id": exit_state_id,
        "exit_state_content_fingerprint": exit_state_fingerprint,
        "status": status,
        "status_reason": status_reason,
        "entry": entry,
        "exit": exit_value,
        "exit_reason": exit_reason,
        "holding_sessions": holding_sessions,
        "gross_return": gross_return,
        "gross_r_multiple": gross_r_multiple,
        "net_return": net_return,
        "net_return_status": net_status,
        "net_return_reason": net_reason,
        "mfe": None,
        "mae": None,
        "mfe_status": "unavailable",
        "mae_status": "unavailable",
        "mfe_reason": "exit_day_inclusion_and_intraday_order_not_approved",
        "mae_reason": "exit_day_inclusion_and_intraday_order_not_approved",
        "cost_policy": cost_policy,
        "price_basis": "provider_adjusted_ohlcv",
        "adjustment_policy": ADJUSTMENT_POLICY,
        "market_data_fingerprint": market_read.point_in_time_fingerprint,
        "execution_policy": {
            "policy_version": EXIT_POLICY["policy_version"],
            "policy_fingerprint": EXIT_POLICY["policy_fingerprint"],
        },
    }
    return _finalize_revision(
        "TradeOutcome", values, tuple(previous_outcomes)
    )


__all__ = [
    "BASELINE_ADAPTER_VERSION", "BASELINE_ENGINE_NAME", "BASELINE_ENGINE_VERSION",
    "BASELINE_SOURCE_VERSION", "build_session_calendar_evidence",
    "market_snapshot_evidence_fingerprint", "produce_forward_outcomes",
    "produce_trade_outcome",
    "validate_session_calendar_evidence",
]
