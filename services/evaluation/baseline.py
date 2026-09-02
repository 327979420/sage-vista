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
from services.ledger.producer import validate_opportunity_event
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


def _require_pending_forward_run(
    receipt: Mapping[str, Any],
    *,
    event: Mapping[str, Any],
    market_snapshot: Mapping[str, Any],
    universe_content_fingerprint: str,
    calendar: Mapping[str, Any],
) -> None:
    validate_experiment_run(receipt)
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


__all__ = [
    "BASELINE_ADAPTER_VERSION", "BASELINE_ENGINE_NAME", "BASELINE_ENGINE_VERSION",
    "BASELINE_SOURCE_VERSION", "build_session_calendar_evidence",
    "market_snapshot_evidence_fingerprint", "produce_forward_outcomes",
    "validate_session_calendar_evidence",
]
