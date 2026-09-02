"""Pure M10 result contracts, identities, receipts, and revision checks.

This module owns no market, ranking, execution, or research calculation.  It
only validates injected facts, assigns deterministic identities, and rejects
attempts to overwrite an immutable result.  M10-B is the sole place allowed to
calculate the first ForwardOutcome and TradeOutcome values.
"""

from __future__ import annotations

from datetime import datetime
import math
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from services.contracts.market_data import canonical_fingerprint, require_date
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError, SEMVER, validate_contract

from .policies import (
    EVALUATION_POLICY,
    FORWARD_WINDOWS,
    FORWARD_WINDOW_POLICY,
    PARTITION_POLICY,
    UNAPPROVED_COST_REFERENCE,
    ZERO_COST_COMPARISON_POLICY,
    validate_policy,
)


RESULT_SCHEMA_VERSION = "2.0.0"
EXPERIMENT_RUN_SCHEMA_VERSION = "2.0.0"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
INSTRUMENT_ID = re.compile(r"^instrument:sha256:[0-9a-f]{64}$")
EVENT_ID = re.compile(r"^opportunity:sha256:[0-9a-f]{64}$")
RUN_ID = re.compile(r"^experiment-run:sha256:[0-9a-f]{64}$")
RESULT_TYPES = {
    "ForwardOutcome": (
        "forward_outcome_id", "forward_content_fingerprint",
        "forward-outcome", "forward-logical",
    ),
    "TradeOutcome": (
        "trade_outcome_id", "trade_content_fingerprint",
        "trade-outcome", "trade-logical",
    ),
    "PortfolioRun": (
        "portfolio_run_id", "portfolio_content_fingerprint",
        "portfolio-run", "portfolio-logical",
    ),
    "ResearchAggregate": (
        "research_aggregate_id", "aggregate_content_fingerprint",
        "research-aggregate", "aggregate-logical",
    ),
}

COMMON_RESULT_FIELDS = {
    "schema_version", "as_of", "generated_at", "source_version",
    "future_data_used", "run_id", "logical_result_id", "supersedes_result_id",
    "path_status", "result_role", "partition_role", "bias_labels",
    "evaluation_policy", "partition_policy", "input_fingerprint", "status",
}
RESULT_ALLOWED_FIELDS = {
    "ForwardOutcome": COMMON_RESULT_FIELDS | {
        "forward_outcome_id", "forward_content_fingerprint", "event_id",
        "event_content_fingerprint", "instrument_id", "signal_date",
        "signal_market_snapshot_id", "window_sessions", "window_policy",
        "session_calendar_id", "session_calendar_fingerprint",
        "elapsed_session_count", "observed_session_count", "observed_through",
        "status_reason", "entry", "endpoint", "gross_return", "mfe", "mae",
        "price_basis", "adjustment_policy", "market_data_fingerprint",
    },
    "TradeOutcome": COMMON_RESULT_FIELDS | {
        "trade_outcome_id", "trade_content_fingerprint", "event_id",
        "event_content_fingerprint", "instrument_id", "signal_date",
        "trade_plan_id", "trade_plan_content_fingerprint", "trade_plan_link_id",
        "trade_plan_link_content_fingerprint", "exit_state_id",
        "exit_state_content_fingerprint", "status_reason", "entry", "exit",
        "holding_sessions", "gross_return", "gross_r_multiple", "net_return",
        "net_return_status", "net_return_reason", "mfe", "mae", "mfe_status",
        "mae_status", "cost_policy", "price_basis", "adjustment_policy",
        "market_data_fingerprint", "execution_policy",
    },
    "PortfolioRun": COMMON_RESULT_FIELDS | {
        "portfolio_run_id", "portfolio_content_fingerprint", "status_reason",
        "trade_outcome_refs",
    },
    "ResearchAggregate": COMMON_RESULT_FIELDS | {
        "research_aggregate_id", "aggregate_content_fingerprint", "status_reason",
        "result_refs",
    },
}
EXPERIMENT_RUN_ALLOWED_FIELDS = {
    "schema_version", "as_of", "generated_at", "source_version",
    "future_data_used", "run_id", "run_content_fingerprint", "attempt_id",
    "experiment_id", "status", "evidence_window", "path_status", "result_role",
    "partition_role", "bias_labels", "code_commit", "config_ref", "engine",
    "policy_refs", "input_refs", "result_refs", "input_set_fingerprint",
    "result_set_fingerprint", "started_at", "finished_at", "parent_run_id",
    "checkpoint_ref", "error",
}


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


def _timestamp(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ContractError(f"{field} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{field} must be an ISO-8601 UTC timestamp") from exc
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _fingerprint(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ContractError(f"{field} must be sha256:<64 lowercase hex>")
    return value


def _finite(value: Any, field: str, *, allow_none: bool = False) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ContractError(f"{field} must be a finite number")
    return number


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{field} must be a non-negative integer")
    return value


def _semantic(payload: Mapping[str, Any], fingerprint_field: str) -> dict[str, Any]:
    return {
        key: _plain(value)
        for key, value in payload.items()
        if key not in {"generated_at", fingerprint_field}
    }


def _required(payload: Mapping[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(fields - payload.keys())
    if missing:
        raise ContractError(f"{label} missing required fields: {', '.join(missing)}")


def _exact_fields(payload: Mapping[str, Any], fields: set[str], label: str) -> None:
    """Reject both missing and unknown fields for an immutable 2.x contract."""

    _required(payload, fields, label)
    unknown = sorted(payload.keys() - fields)
    if unknown:
        raise ContractError(f"{label} contains unknown fields: {', '.join(unknown)}")


def _exact_mapping(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{label} must be an object")
    _exact_fields(value, fields, label)
    return value


def _validate_roles(payload: Mapping[str, Any]) -> None:
    if payload["path_status"] not in {"formal", "legacy"}:
        raise ContractError("M10 path_status must be formal or legacy")
    if payload["result_role"] not in {"authoritative", "comparison"}:
        raise ContractError("M10 result_role must be authoritative or comparison")
    if payload["partition_role"] not in {"development", "validation", "forward"}:
        raise ContractError("M10 partition_role is invalid")
    biases = payload["bias_labels"]
    if not isinstance(biases, (list, tuple)) or any(
        not isinstance(item, str) or not item for item in biases
    ):
        raise ContractError("bias_labels must be a list of non-empty strings")
    if list(biases) != sorted(set(biases)):
        raise ContractError("bias_labels must be sorted and unique")
    if payload["path_status"] == "formal" and biases:
        raise ContractError("formal M10 results cannot carry legacy bias labels")
    if payload["path_status"] == "legacy" and not biases:
        raise ContractError("legacy M10 results require explicit bias labels")
    if payload["path_status"] == "legacy" and payload["result_role"] == "authoritative":
        raise ContractError("legacy M10 results cannot be authoritative")


def _validate_policy_binding(payload: Mapping[str, Any]) -> None:
    evaluation_policy = payload["evaluation_policy"]
    partition_policy = payload["partition_policy"]
    validate_policy(evaluation_policy, expected_kind="evaluation")
    validate_policy(partition_policy, expected_kind="partition")
    if _plain(evaluation_policy) != _plain(EVALUATION_POLICY):
        raise ContractError("M10-A only knows the approved evaluation policy")
    if _plain(partition_policy) != _plain(PARTITION_POLICY):
        raise ContractError("M10-A only knows the approved partition policy")


def _canonical_input_identity(
    contract_name: str, payload: Mapping[str, Any]
) -> dict[str, Any]:
    """Return the one normalized input identity shared by creation and validation.

    Stable upstream IDs and their content fingerprints are both included.  This
    makes a market, run, event, plan, or policy revision produce a new result
    version without copying or recalculating any M02-M09 fact.
    """

    common = {
        "contract_name": contract_name,
        "schema_major": 2,
        "run_id": payload["run_id"],
        "source_version": _plain(payload["source_version"]),
        "path_status": payload["path_status"],
        "result_role": payload["result_role"],
        "partition_role": payload["partition_role"],
        "bias_labels": _plain(payload["bias_labels"]),
        "evaluation_policy_fingerprint": payload["evaluation_policy"][
            "policy_fingerprint"
        ],
        "partition_policy_fingerprint": payload["partition_policy"][
            "policy_fingerprint"
        ],
    }
    if contract_name == "ForwardOutcome":
        return {
            **common,
            "event_reference": {
                "id": payload["event_id"],
                "content_fingerprint": payload["event_content_fingerprint"],
            },
            "instrument_id": payload["instrument_id"],
            "signal_date": payload["signal_date"],
            "signal_market_snapshot_id": payload["signal_market_snapshot_id"],
            "window_sessions": payload["window_sessions"],
            "window_policy_fingerprint": payload["window_policy"][
                "policy_fingerprint"
            ],
            "session_calendar_id": payload["session_calendar_id"],
            "session_calendar_fingerprint": payload[
                "session_calendar_fingerprint"
            ],
            "price_basis": payload["price_basis"],
            "adjustment_policy": _plain(payload["adjustment_policy"]),
            "market_data_fingerprint": payload["market_data_fingerprint"],
        }
    if contract_name == "TradeOutcome":
        return {
            **common,
            "event_reference": {
                "id": payload["event_id"],
                "content_fingerprint": payload["event_content_fingerprint"],
            },
            "instrument_id": payload["instrument_id"],
            "signal_date": payload["signal_date"],
            "trade_plan_reference": {
                "id": payload["trade_plan_id"],
                "content_fingerprint": payload["trade_plan_content_fingerprint"],
            },
            "trade_plan_link_reference": {
                "id": payload["trade_plan_link_id"],
                "content_fingerprint": payload[
                    "trade_plan_link_content_fingerprint"
                ],
            },
            "exit_state_reference": {
                "id": payload["exit_state_id"],
                "content_fingerprint": payload["exit_state_content_fingerprint"],
            },
            "price_basis": payload["price_basis"],
            "adjustment_policy": _plain(payload["adjustment_policy"]),
            "market_data_fingerprint": payload["market_data_fingerprint"],
            "execution_policy": _plain(payload["execution_policy"]),
            "cost_policy": _plain(payload["cost_policy"]),
        }
    reference_field = (
        "trade_outcome_refs" if contract_name == "PortfolioRun" else "result_refs"
    )
    return {**common, reference_field: _plain(payload[reference_field])}


def result_input_fingerprint(
    contract_name: str, payload: Mapping[str, Any]
) -> str:
    """Fingerprint the normalized input identity without trusting a caller value."""

    if contract_name not in RESULT_TYPES:
        raise ContractError(f"unknown M10 result contract: {contract_name}")
    try:
        return canonical_fingerprint(_canonical_input_identity(contract_name, payload))
    except KeyError as exc:
        raise ContractError(
            f"{contract_name} cannot fingerprint missing input field: {exc.args[0]}"
        ) from exc


def _logical_identity(contract_name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    common = {
        "schema_major": 2,
        "path_status": payload["path_status"],
        "result_role": payload["result_role"],
        "partition_role": payload["partition_role"],
        "evaluation_policy_fingerprint": payload["evaluation_policy"]["policy_fingerprint"],
    }
    if contract_name == "ForwardOutcome":
        return {
            **common,
            "event_id": payload["event_id"],
            "instrument_id": payload["instrument_id"],
            "signal_date": payload["signal_date"],
            "window_sessions": payload["window_sessions"],
            "window_policy_fingerprint": payload["window_policy"]["policy_fingerprint"],
        }
    if contract_name == "TradeOutcome":
        return {
            **common,
            "event_id": payload["event_id"],
            "instrument_id": payload["instrument_id"],
            "signal_date": payload["signal_date"],
            "trade_plan_id": payload["trade_plan_id"],
            "trade_plan_link_id": payload["trade_plan_link_id"],
        }
    reference_field = "trade_outcome_refs" if contract_name == "PortfolioRun" else "result_refs"
    return {
        **common,
        "run_id": payload["run_id"],
        reference_field: _plain(payload[reference_field]),
    }


def _version_identity(contract_name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "logical_result_id": payload["logical_result_id"],
        "as_of": payload["as_of"],
        "status": payload["status"],
        "input_fingerprint": payload["input_fingerprint"],
        "supersedes_result_id": payload["supersedes_result_id"],
    }


def finalize_result(contract_name: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Assign deterministic IDs and a content fingerprint to one result."""

    if contract_name not in RESULT_TYPES:
        raise ContractError(f"unknown M10 result contract: {contract_name}")
    result = _plain(payload)
    expected_input = result_input_fingerprint(contract_name, result)
    provided_input = result.get("input_fingerprint")
    if provided_input is not None and provided_input != expected_input:
        raise ContractError(
            f"{contract_name} input_fingerprint does not match its input facts"
        )
    result["input_fingerprint"] = expected_input
    id_field, fingerprint_field, id_prefix, logical_prefix = RESULT_TYPES[contract_name]
    result["logical_result_id"] = logical_prefix + ":" + canonical_fingerprint(
        _logical_identity(contract_name, result)
    )
    result[id_field] = id_prefix + ":" + canonical_fingerprint(
        _version_identity(contract_name, result)
    )
    result[fingerprint_field] = canonical_fingerprint(_semantic(result, fingerprint_field))
    validate_result(contract_name, result)
    return _freeze(result)


def _validate_common_result(contract_name: str, payload: Mapping[str, Any]) -> None:
    _exact_fields(payload, RESULT_ALLOWED_FIELDS[contract_name], contract_name)
    validate_contract(contract_name, payload)
    if payload["schema_version"] != RESULT_SCHEMA_VERSION:
        raise ContractError(f"formal M10 requires {contract_name} 2.0.0")
    _timestamp(payload["generated_at"], "generated_at")
    if not RUN_ID.fullmatch(str(payload["run_id"])):
        raise ContractError(f"{contract_name} run_id is invalid")
    _validate_roles(payload)
    _validate_policy_binding(payload)
    _fingerprint(payload["input_fingerprint"], "input_fingerprint")
    if payload["input_fingerprint"] != result_input_fingerprint(contract_name, payload):
        raise ContractError(
            f"{contract_name} input_fingerprint does not match its input facts"
        )
    id_field, fingerprint_field, id_prefix, logical_prefix = RESULT_TYPES[contract_name]
    if not re.fullmatch(logical_prefix + r":sha256:[0-9a-f]{64}", str(payload["logical_result_id"])):
        raise ContractError(f"{contract_name} logical_result_id is invalid")
    if not re.fullmatch(id_prefix + r":sha256:[0-9a-f]{64}", str(payload[id_field])):
        raise ContractError(f"{contract_name} stable ID is invalid")
    supersedes = payload["supersedes_result_id"]
    if supersedes is not None and not re.fullmatch(
        id_prefix + r":sha256:[0-9a-f]{64}", str(supersedes)
    ):
        raise ContractError(f"{contract_name} supersedes_result_id is invalid")
    expected_logical = logical_prefix + ":" + canonical_fingerprint(
        _logical_identity(contract_name, payload)
    )
    if payload["logical_result_id"] != expected_logical:
        raise ContractError(f"{contract_name} logical identity does not match its facts")
    expected_id = id_prefix + ":" + canonical_fingerprint(
        _version_identity(contract_name, payload)
    )
    if payload[id_field] != expected_id:
        raise ContractError(f"{contract_name} stable ID does not match its result version")
    if payload[fingerprint_field] != canonical_fingerprint(
        _semantic(payload, fingerprint_field)
    ):
        raise ContractError(f"{contract_name} content fingerprint is invalid")


def _validate_forward(payload: Mapping[str, Any]) -> None:
    _required(
        payload,
        {
            "event_content_fingerprint", "signal_market_snapshot_id",
            "window_policy", "session_calendar_id", "session_calendar_fingerprint",
            "elapsed_session_count", "observed_session_count", "observed_through",
            "status_reason", "entry", "endpoint", "gross_return", "mfe", "mae",
            "price_basis", "adjustment_policy", "market_data_fingerprint",
        },
        "ForwardOutcome",
    )
    if not EVENT_ID.fullmatch(str(payload["event_id"])):
        raise ContractError("ForwardOutcome event_id is invalid")
    if not INSTRUMENT_ID.fullmatch(str(payload["instrument_id"])):
        raise ContractError("ForwardOutcome instrument_id is invalid")
    require_date(payload["signal_date"], "signal_date")
    if payload["signal_date"] > payload["as_of"]:
        raise ContractError("ForwardOutcome signal_date cannot be after as_of")
    _fingerprint(payload["event_content_fingerprint"], "event_content_fingerprint")
    if not str(payload["signal_market_snapshot_id"]).startswith("market:"):
        raise ContractError("ForwardOutcome signal market identity is invalid")
    validate_policy(payload["window_policy"], expected_kind="forward_window")
    if _plain(payload["window_policy"]) != _plain(FORWARD_WINDOW_POLICY):
        raise ContractError("ForwardOutcome uses an unknown window policy")
    if payload["window_sessions"] not in FORWARD_WINDOWS:
        raise ContractError("ForwardOutcome window is not approved")
    if not re.fullmatch(r"session-calendar:sha256:[0-9a-f]{64}", str(payload["session_calendar_id"])):
        raise ContractError("ForwardOutcome session calendar ID is invalid")
    _fingerprint(payload["session_calendar_fingerprint"], "session_calendar_fingerprint")
    elapsed = _non_negative_int(payload["elapsed_session_count"], "elapsed_session_count")
    observed = _non_negative_int(payload["observed_session_count"], "observed_session_count")
    if observed > elapsed:
        raise ContractError("observed sessions cannot exceed elapsed sessions")
    observed_through = payload["observed_through"]
    if observed_through is not None:
        require_date(observed_through, "observed_through")
        if observed_through > payload["as_of"]:
            raise ContractError("ForwardOutcome observes data after as_of")
    if payload["price_basis"] != "provider_adjusted_ohlcv":
        raise ContractError("ForwardOutcome price basis is invalid")
    if _plain(payload["adjustment_policy"]) != ADJUSTMENT_POLICY:
        raise ContractError("ForwardOutcome must bind the M02 adjustment policy")
    _fingerprint(payload["market_data_fingerprint"], "market_data_fingerprint")
    status = payload["status"]
    reason = payload["status_reason"]
    if status not in {"pending", "mature", "partial", "unavailable"}:
        raise ContractError("ForwardOutcome status is invalid")
    if status == "pending":
        if elapsed >= payload["window_sessions"] or reason != "window_not_mature":
            raise ContractError("pending ForwardOutcome must be genuinely immature")
        if any(payload[field] is not None for field in ("endpoint", "gross_return", "mfe", "mae")):
            raise ContractError("pending ForwardOutcome cannot contain mature results")
    elif elapsed < payload["window_sessions"]:
        raise ContractError("an immature ForwardOutcome must remain pending")
    elif status == "mature":
        if reason is not None or observed != payload["window_sessions"]:
            raise ContractError("mature ForwardOutcome requires complete window evidence")
        if payload["entry"] is None or payload["endpoint"] is None:
            raise ContractError("mature ForwardOutcome requires both prices")
        for field in ("gross_return", "mfe", "mae"):
            _finite(payload[field], field)
    elif status == "partial":
        _text(reason, "status_reason")
        if payload["entry"] is None or payload["endpoint"] is None:
            raise ContractError("partial ForwardOutcome requires known endpoints")
        _finite(payload["gross_return"], "gross_return")
        if payload["mfe"] is not None or payload["mae"] is not None:
            raise ContractError("partial ForwardOutcome cannot claim complete excursions")
    else:
        _text(reason, "status_reason")
        if any(payload[field] is not None for field in ("gross_return", "mfe", "mae")):
            raise ContractError("unavailable ForwardOutcome cannot contain guessed results")
    for field in ("entry", "endpoint"):
        value = payload[field]
        if value is not None:
            value = _exact_mapping(
                value, {"date", "price"}, f"ForwardOutcome {field}"
            )
            require_date(value.get("date"), f"{field}.date")
            if value["date"] > payload["as_of"]:
                raise ContractError(f"ForwardOutcome {field} cannot use future data")
            price = _finite(value.get("price"), f"{field}.price")
            if price is None or price <= 0:
                raise ContractError(f"{field}.price must be positive")


def _validate_trade(payload: Mapping[str, Any]) -> None:
    _required(
        payload,
        {
            "event_content_fingerprint", "trade_plan_id", "trade_plan_content_fingerprint",
            "trade_plan_link_id", "trade_plan_link_content_fingerprint", "exit_state_id",
            "exit_state_content_fingerprint", "status_reason", "entry", "exit",
            "holding_sessions", "gross_return", "gross_r_multiple", "net_return",
            "net_return_status", "net_return_reason", "mfe", "mae", "mfe_status",
            "mae_status", "cost_policy", "price_basis", "adjustment_policy",
            "market_data_fingerprint", "execution_policy",
        },
        "TradeOutcome",
    )
    if not EVENT_ID.fullmatch(str(payload["event_id"])):
        raise ContractError("TradeOutcome event_id is invalid")
    if not INSTRUMENT_ID.fullmatch(str(payload["instrument_id"])):
        raise ContractError("TradeOutcome instrument_id is invalid")
    require_date(payload["signal_date"], "signal_date")
    if payload["signal_date"] > payload["as_of"]:
        raise ContractError("TradeOutcome signal_date cannot be after as_of")
    _fingerprint(payload["event_content_fingerprint"], "event_content_fingerprint")
    if payload["price_basis"] != "provider_adjusted_ohlcv":
        raise ContractError("TradeOutcome price basis is invalid")
    if _plain(payload["adjustment_policy"]) != ADJUSTMENT_POLICY:
        raise ContractError("TradeOutcome must bind the M02 adjustment policy")
    _fingerprint(payload["market_data_fingerprint"], "market_data_fingerprint")
    _non_negative_int(payload["holding_sessions"], "holding_sessions")
    status = payload["status"]
    if status not in {"open", "completed", "no_trade", "unavailable"}:
        raise ContractError("TradeOutcome status is invalid")
    if status in {"open", "completed"}:
        if not re.fullmatch(r"plan:sha256:[0-9a-f]{64}", str(payload["trade_plan_id"])):
            raise ContractError("TradeOutcome plan identity is invalid")
        _fingerprint(payload["trade_plan_content_fingerprint"], "trade_plan_content_fingerprint")
        if not re.fullmatch(r"exit-state:sha256:[0-9a-f]{64}", str(payload["exit_state_id"])):
            raise ContractError("TradeOutcome exit state identity is invalid")
        _fingerprint(payload["exit_state_content_fingerprint"], "exit_state_content_fingerprint")
        if payload["entry"] is None:
            raise ContractError("TradeOutcome with a plan requires its entry")
    else:
        _text(payload["status_reason"], "status_reason")
        if any(payload[field] is not None for field in ("trade_plan_id", "exit_state_id", "entry", "exit")):
            raise ContractError("unplanned TradeOutcome cannot fabricate plan or execution facts")
    for field in ("trade_plan_link_id",):
        if not re.fullmatch(r"machine-link:sha256:[0-9a-f]{64}", str(payload[field])):
            raise ContractError("TradeOutcome plan link identity is invalid")
    _fingerprint(payload["trade_plan_link_content_fingerprint"], "trade_plan_link_content_fingerprint")
    if status == "completed":
        if payload["status_reason"] is not None or payload["exit"] is None:
            raise ContractError("completed TradeOutcome requires an exit")
        _finite(payload["gross_return"], "gross_return")
        _finite(payload["gross_r_multiple"], "gross_r_multiple")
    else:
        if payload["gross_return"] is not None or payload["gross_r_multiple"] is not None:
            raise ContractError("non-completed TradeOutcome cannot contain final gross results")
    for field in ("entry", "exit"):
        value = payload[field]
        if value is not None:
            value = _exact_mapping(
                value, {"date", "price"}, f"TradeOutcome {field}"
            )
            require_date(value.get("date"), f"{field}.date")
            if value["date"] > payload["as_of"]:
                raise ContractError(f"TradeOutcome {field} cannot use future data")
            price = _finite(value.get("price"), f"{field}.price")
            if price is None or price <= 0:
                raise ContractError(f"{field}.price must be positive")
    if payload["mfe"] is not None or payload["mae"] is not None:
        raise ContractError("M10-B has no approved terminal-bar excursion policy")
    if payload["mfe_status"] != "unavailable" or payload["mae_status"] != "unavailable":
        raise ContractError("TradeOutcome excursions must remain explicitly unavailable")
    cost_policy = _plain(payload["cost_policy"])
    if payload["result_role"] == "authoritative":
        if cost_policy != _plain(UNAPPROVED_COST_REFERENCE):
            raise ContractError("authoritative TradeOutcome cannot invent a cost policy")
        if (
            payload["net_return"] is not None
            or payload["net_return_status"] != "unavailable"
            or payload["net_return_reason"] != "cost_slippage_policy_not_approved"
        ):
            raise ContractError("authoritative net return must be unavailable without costs")
    else:
        validate_policy(payload["cost_policy"], expected_kind="cost_slippage")
        if _plain(payload["cost_policy"]) != _plain(ZERO_COST_COMPARISON_POLICY):
            raise ContractError("M10-B only knows the zero-cost comparison policy")
        if status == "completed":
            if payload["net_return_status"] != "available":
                raise ContractError("completed zero-cost comparison must label net return available")
            net = _finite(payload["net_return"], "net_return")
            gross = _finite(payload["gross_return"], "gross_return")
            if net != gross:
                raise ContractError("zero-cost comparison net return must equal gross return")
        elif (
            payload["net_return"] is not None
            or payload["net_return_status"] != "unavailable"
            or not isinstance(payload["net_return_reason"], str)
            or not payload["net_return_reason"]
        ):
            raise ContractError("incomplete comparison cannot claim a net return")
    execution_policy = _exact_mapping(
        payload["execution_policy"],
        {"policy_version", "policy_fingerprint"},
        "TradeOutcome execution_policy",
    )
    version = execution_policy["policy_version"]
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise ContractError("TradeOutcome execution policy version is invalid")
    _fingerprint(
        execution_policy["policy_fingerprint"],
        "execution_policy.policy_fingerprint",
    )


def _validate_reference_list(value: Any, field: str, *, required_prefix: str | None = None) -> None:
    if not isinstance(value, (list, tuple)):
        raise ContractError(f"{field} must be a list")
    normalized: list[tuple[str, str]] = []
    for item in value:
        item = _exact_mapping(
            item, {"id", "content_fingerprint"}, f"{field} item"
        )
        stable_id = _text(item.get("id"), f"{field}.id")
        if required_prefix is not None and not stable_id.startswith(required_prefix):
            raise ContractError(f"{field} has an invalid identity")
        fingerprint = _fingerprint(item.get("content_fingerprint"), f"{field}.content_fingerprint")
        normalized.append((stable_id, fingerprint))
    if normalized != sorted(set(normalized)):
        raise ContractError(f"{field} must be sorted and unique")


def _validate_unimplemented_result(contract_name: str, payload: Mapping[str, Any]) -> None:
    field = "trade_outcome_refs" if contract_name == "PortfolioRun" else "result_refs"
    _validate_reference_list(
        payload[field], field,
        required_prefix="trade-outcome:" if contract_name == "PortfolioRun" else None,
    )
    if payload["status"] != "unavailable" or payload.get("status_reason") != (
        "portfolio_policy_not_approved"
        if contract_name == "PortfolioRun"
        else "research_aggregate_not_implemented"
    ):
        raise ContractError(f"{contract_name} calculation is not approved in M10-A")
    forbidden = {
        "equity_curve", "total_return", "annualized_return", "max_drawdown",
        "win_rate", "profit_factor", "expectancy", "statistics",
    }
    if forbidden & payload.keys():
        raise ContractError(f"{contract_name} cannot contain calculated results in M10-A")


def validate_result(contract_name: str, payload: Mapping[str, Any]) -> None:
    """Validate one complete M10 result without performing its calculation."""

    if contract_name not in RESULT_TYPES or not isinstance(payload, Mapping):
        raise ContractError("unknown or invalid M10 result")
    _validate_common_result(contract_name, payload)
    if contract_name == "ForwardOutcome":
        _validate_forward(payload)
    elif contract_name == "TradeOutcome":
        _validate_trade(payload)
    else:
        _validate_unimplemented_result(contract_name, payload)


def current_result(
    contract_name: str, results: Iterable[Mapping[str, Any]]
) -> Mapping[str, Any]:
    """Validate one immutable linear revision chain and return its sole leaf."""

    if contract_name not in RESULT_TYPES:
        raise ContractError("unknown M10 result chain")
    id_field = RESULT_TYPES[contract_name][0]
    items = list(results)
    if not items:
        raise ContractError("M10 result chain is empty")
    by_id: dict[str, Mapping[str, Any]] = {}
    logical_ids: set[str] = set()
    for item in items:
        validate_result(contract_name, item)
        stable_id = str(item[id_field])
        if stable_id in by_id:
            raise ContractError("M10 result chain contains a duplicate identity")
        by_id[stable_id] = item
        logical_ids.add(str(item["logical_result_id"]))
    if len(logical_ids) != 1:
        raise ContractError("M10 result chain crosses logical subjects")
    children: dict[str, str] = {}
    roots: list[str] = []
    for stable_id, item in by_id.items():
        prior = item["supersedes_result_id"]
        if prior is None:
            roots.append(stable_id)
        else:
            if prior not in by_id:
                raise ContractError("M10 result chain has a missing predecessor")
            if prior in children:
                raise ContractError("M10 result chain forks")
            children[str(prior)] = stable_id
            if item["as_of"] < by_id[str(prior)]["as_of"]:
                raise ContractError("M10 result revision moves evidence time backwards")
    if len(roots) != 1:
        raise ContractError("M10 result chain must have one root")
    visited: set[str] = set()
    cursor = roots[0]
    while cursor not in visited:
        visited.add(cursor)
        next_id = children.get(cursor)
        if next_id is None:
            break
        cursor = next_id
    if cursor in children or visited != set(by_id):
        raise ContractError("M10 result chain is cyclic or disconnected")
    return by_id[cursor]


def assert_immutable_compatible(
    contract_name: str,
    existing: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Allow an idempotent replay and reject content under an existing ID."""

    validate_result(contract_name, existing)
    validate_result(contract_name, candidate)
    id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
    if existing[id_field] != candidate[id_field]:
        raise ContractError("immutable compatibility requires the same stable ID")
    if existing[fingerprint_field] != candidate[fingerprint_field]:
        raise ContractError("same M10 result identity has different content")
    return existing


def _run_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_major": 2,
        "attempt_id": payload["attempt_id"],
        "experiment_id": payload["experiment_id"],
        "path_status": payload["path_status"],
        "result_role": payload["result_role"],
        "partition_role": payload["partition_role"],
        "code_commit": payload["code_commit"],
        "config_ref": _plain(payload["config_ref"]),
        "engine": _plain(payload["engine"]),
        "policy_refs": _plain(payload["policy_refs"]),
        "input_set_fingerprint": payload["input_set_fingerprint"],
        "parent_run_id": payload["parent_run_id"],
        "checkpoint_ref": _plain(payload["checkpoint_ref"]),
    }


def _run_semantic(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _plain(value)
        for key, value in payload.items()
        if key not in {"generated_at", "run_content_fingerprint"}
    }


def build_experiment_run_receipt(**values: Any) -> Mapping[str, Any]:
    """Build one terminal ExperimentRun 2.x receipt from injected evidence."""

    payload = _plain(values)
    payload.setdefault("schema_version", EXPERIMENT_RUN_SCHEMA_VERSION)
    payload.setdefault("source_version", {"evaluation_contracts": "m10-a-1.0.0"})
    payload.setdefault("future_data_used", False)
    _required(
        payload,
        {
            "as_of", "generated_at", "attempt_id", "experiment_id", "status",
            "evidence_window", "path_status", "result_role", "partition_role",
            "bias_labels", "code_commit", "config_ref", "engine", "policy_refs",
            "input_refs", "result_refs", "started_at", "finished_at",
            "parent_run_id", "checkpoint_ref", "error",
        },
        "ExperimentRun 2.x builder",
    )
    payload["input_set_fingerprint"] = canonical_fingerprint(payload["input_refs"])
    payload["result_set_fingerprint"] = canonical_fingerprint(payload["result_refs"])
    payload["run_id"] = "experiment-run:" + canonical_fingerprint(_run_identity(payload))
    payload["run_content_fingerprint"] = canonical_fingerprint(_run_semantic(payload))
    validate_experiment_run(payload)
    return _freeze(payload)


def validate_experiment_run(payload: Mapping[str, Any]) -> None:
    """Validate an immutable ExperimentRun 2.x receipt; 1.x stays in M01."""

    _exact_fields(payload, EXPERIMENT_RUN_ALLOWED_FIELDS, "ExperimentRun 2.x")
    validate_contract("ExperimentRun", payload)
    if payload["schema_version"] != EXPERIMENT_RUN_SCHEMA_VERSION:
        raise ContractError("M10 formal receipts require ExperimentRun 2.0.0")
    if not RUN_ID.fullmatch(str(payload["run_id"])):
        raise ContractError("ExperimentRun run_id is invalid")
    _fingerprint(payload["run_content_fingerprint"], "run_content_fingerprint")
    _text(payload["attempt_id"], "attempt_id")
    _text(payload["experiment_id"], "experiment_id")
    _validate_roles(payload)
    if not re.fullmatch(r"[0-9a-f]{40}", str(payload["code_commit"])):
        raise ContractError("ExperimentRun code_commit must be a full 40-hex Git commit")
    config = _exact_mapping(
        payload["config_ref"],
        {"config_id", "config_version", "content_fingerprint"},
        "ExperimentRun config_ref",
    )
    _text(config.get("config_id"), "config_ref.config_id")
    _text(config.get("config_version"), "config_ref.config_version")
    _fingerprint(config.get("content_fingerprint"), "config_ref.content_fingerprint")
    engine = _exact_mapping(
        payload["engine"],
        {"name", "version", "adapter_version"},
        "ExperimentRun engine",
    )
    for field in ("name", "version", "adapter_version"):
        _text(engine.get(field), f"engine.{field}")
    _validate_reference_list(payload["input_refs"], "input_refs")
    _validate_reference_list(payload["result_refs"], "result_refs")
    if payload["input_set_fingerprint"] != canonical_fingerprint(_plain(payload["input_refs"])):
        raise ContractError("ExperimentRun input set fingerprint is invalid")
    if payload["result_set_fingerprint"] != canonical_fingerprint(_plain(payload["result_refs"])):
        raise ContractError("ExperimentRun result set fingerprint is invalid")
    policy_refs = payload["policy_refs"]
    if not isinstance(policy_refs, (list, tuple)) or not policy_refs:
        raise ContractError("ExperimentRun requires policy references")
    policy_pairs: list[tuple[str, str]] = []
    for ref in policy_refs:
        ref = _exact_mapping(
            ref,
            {"policy_kind", "policy_fingerprint"},
            "ExperimentRun policy reference",
        )
        policy_pairs.append((
            _text(ref.get("policy_kind"), "policy_ref.policy_kind"),
            _fingerprint(ref.get("policy_fingerprint"), "policy_ref.policy_fingerprint"),
        ))
    if policy_pairs != sorted(set(policy_pairs)):
        raise ContractError("ExperimentRun policy references must be sorted and unique")
    window = _exact_mapping(
        payload["evidence_window"],
        {"start", "end", "evidence_as_of"},
        "ExperimentRun evidence_window",
    )
    start = require_date(window.get("start"), "evidence_window.start")
    end = require_date(window.get("end"), "evidence_window.end")
    evidence_as_of = require_date(window.get("evidence_as_of"), "evidence_window.evidence_as_of")
    if not start <= end <= evidence_as_of or payload["as_of"] != evidence_as_of:
        raise ContractError("ExperimentRun evidence window is inconsistent")
    started = _timestamp(payload["started_at"], "started_at")
    finished = _timestamp(payload["finished_at"], "finished_at")
    if finished < started:
        raise ContractError("ExperimentRun finished_at predates started_at")
    parent = payload["parent_run_id"]
    if parent is not None and not RUN_ID.fullmatch(str(parent)):
        raise ContractError("ExperimentRun parent_run_id is invalid")
    checkpoint = payload["checkpoint_ref"]
    if checkpoint is not None:
        checkpoint = _exact_mapping(
            checkpoint,
            {"checkpoint_id", "content_fingerprint"},
            "ExperimentRun checkpoint_ref",
        )
        _text(checkpoint["checkpoint_id"], "checkpoint_ref.checkpoint_id")
        _fingerprint(
            checkpoint["content_fingerprint"],
            "checkpoint_ref.content_fingerprint",
        )
    status = payload["status"]
    if status not in {"completed", "failed", "interrupted", "unavailable"}:
        raise ContractError("ExperimentRun terminal status is invalid")
    if status == "completed":
        if not payload["result_refs"] or payload["error"] is not None:
            raise ContractError("completed ExperimentRun requires results and no error")
    else:
        error = _exact_mapping(
            payload["error"], {"category", "message"}, "ExperimentRun error"
        )
        _text(error["category"], "error.category")
        _text(error["message"], "error.message")
    expected_id = "experiment-run:" + canonical_fingerprint(_run_identity(payload))
    if payload["run_id"] != expected_id:
        raise ContractError("ExperimentRun run_id does not match its execution identity")
    if payload["run_content_fingerprint"] != canonical_fingerprint(_run_semantic(payload)):
        raise ContractError("ExperimentRun content fingerprint is invalid")


__all__ = [
    "EXPERIMENT_RUN_SCHEMA_VERSION", "RESULT_SCHEMA_VERSION",
    "assert_immutable_compatible", "build_experiment_run_receipt", "current_result",
    "finalize_result", "result_input_fingerprint", "validate_experiment_run",
    "validate_result",
]
