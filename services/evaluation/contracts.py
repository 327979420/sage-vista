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
    AGGREGATION_POLICY,
    EVALUATION_POLICY,
    FORWARD_WINDOWS,
    FORWARD_WINDOW_POLICY,
    PARTITION_POLICY,
    UNAPPROVED_COST_REFERENCE,
    ZERO_COST_COMPARISON_POLICY,
    validate_policy,
)
from .metrics import decimal_metric, profit_factor_semantics, quantized_ratio


RESULT_SCHEMA_VERSION = "2.0.0"
FORWARD_OUTCOME_SCHEMA_VERSION = "2.1.0"
PORTFOLIO_RUN_SCHEMA_VERSION = "2.1.0"
RESEARCH_AGGREGATE_SCHEMA_VERSION = "2.1.0"
EXPERIMENT_RUN_SCHEMA_VERSION = "2.0.0"
M10_C_SOURCE_VERSION = "m10-c-readonly-1.0.0"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
STABLE_REFERENCE_PREFIXES = {
    "instrument": "instrument",
    "universe": "universe",
    "market_snapshot": "market",
    "gate_event": "gate",
    "technical_evidence": "evidence",
    "model_assessment": "assessment",
    "context_snapshot": "context",
    "score_result": "score",
    "ranking_snapshot": "ranking",
    "trade_plan": "plan",
    "exit_state": "exit-state",
    "opportunity_event": "opportunity",
    "machine_link": "machine-link",
    "session_calendar": "session-calendar",
    "forward_outcome": "forward-outcome",
    "trade_outcome": "trade-outcome",
    "portfolio_run": "portfolio-run",
    "research_aggregate": "research-aggregate",
    "experiment_run": "experiment-run",
    "experiment_run_receipt": "experiment-run-receipt",
}
EXPERIMENT_INPUT_REFERENCE_ROLES = {
    "instrument", "universe", "market_snapshot", "gate_event",
    "technical_evidence", "model_assessment", "context_snapshot",
    "score_result", "ranking_snapshot", "trade_plan", "exit_state",
    "opportunity_event", "machine_link", "session_calendar",
    "forward_outcome", "trade_outcome", "portfolio_run",
    "research_aggregate",
}
EXPERIMENT_RESULT_REFERENCE_ROLES = {
    "forward_outcome", "trade_outcome", "portfolio_run",
    "research_aggregate",
}
ALLOWED_RUN_POLICY_KINDS = {
    "adjustment", "aggregation", "cost_slippage", "evaluation", "execution",
    "forward_window", "partition",
}
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
FORWARD_OUTCOME_2_0_FIELDS = COMMON_RESULT_FIELDS | {
    "forward_outcome_id", "forward_content_fingerprint", "event_id",
    "event_content_fingerprint", "instrument_id", "signal_date",
    "signal_market_snapshot_id", "evaluation_market_snapshot_id",
    "evaluation_market_snapshot_fingerprint", "universe_id",
    "universe_content_fingerprint", "window_sessions", "window_policy",
    "session_calendar_id", "session_calendar_fingerprint",
    "elapsed_session_count", "observed_session_count", "observed_through",
    "status_reason", "entry", "endpoint", "gross_return", "mfe", "mae",
    "price_basis", "adjustment_policy", "market_data_fingerprint",
}
FORWARD_OUTCOME_FIELDS_BY_VERSION = {
    RESULT_SCHEMA_VERSION: FORWARD_OUTCOME_2_0_FIELDS,
    FORWARD_OUTCOME_SCHEMA_VERSION: (
        FORWARD_OUTCOME_2_0_FIELDS | {"target_session_date"}
    ),
}
RESULT_ALLOWED_FIELDS = {
    "ForwardOutcome": FORWARD_OUTCOME_2_0_FIELDS,
    "TradeOutcome": COMMON_RESULT_FIELDS | {
        "trade_outcome_id", "trade_content_fingerprint", "event_id",
        "event_content_fingerprint", "instrument_id", "signal_date",
        "trade_plan_id", "trade_plan_content_fingerprint", "trade_plan_link_id",
        "trade_plan_link_content_fingerprint", "exit_state_id",
        "exit_state_content_fingerprint", "status_reason", "entry", "exit",
        "evaluation_market_snapshot_id", "evaluation_market_snapshot_fingerprint",
        "universe_id", "universe_content_fingerprint",
        "exit_reason", "holding_sessions", "gross_return", "gross_r_multiple", "net_return",
        "net_return_status", "net_return_reason", "mfe", "mae", "mfe_status",
        "mae_status", "mfe_reason", "mae_reason", "cost_policy",
        "price_basis", "adjustment_policy",
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
PORTFOLIO_RUN_2_1_FIELDS = COMMON_RESULT_FIELDS | {
    "portfolio_run_id", "portfolio_content_fingerprint", "status_reason",
    "trade_outcome_refs", "result_set_fingerprint", "aggregation_policy",
    "portfolio_scope",
}
RESEARCH_AGGREGATE_2_1_FIELDS = COMMON_RESULT_FIELDS | {
    "research_aggregate_id", "aggregate_content_fingerprint",
    "source_result_type", "window_sessions", "aggregate_scope",
    "aggregation_policy", "result_refs", "result_set_fingerprint",
    "total_count", "status_counts", "evaluated_count", "missing_count",
    "missing_rate", "win_count", "loss_count", "flat_count", "win_rate",
    "mean_gross_return", "median_gross_return", "gross_profit",
    "gross_loss_abs", "profit_factor", "gross_expectancy", "metric_status",
    "metric_reason",
}
RESULT_FIELDS_BY_VERSION = {
    "PortfolioRun": {
        RESULT_SCHEMA_VERSION: RESULT_ALLOWED_FIELDS["PortfolioRun"],
        PORTFOLIO_RUN_SCHEMA_VERSION: PORTFOLIO_RUN_2_1_FIELDS,
    },
    "ResearchAggregate": {
        RESULT_SCHEMA_VERSION: RESULT_ALLOWED_FIELDS["ResearchAggregate"],
        RESEARCH_AGGREGATE_SCHEMA_VERSION: RESEARCH_AGGREGATE_2_1_FIELDS,
    },
}
EXPERIMENT_RUN_ALLOWED_FIELDS = {
    "schema_version", "as_of", "generated_at", "source_version",
    "future_data_used", "run_id", "run_receipt_id",
    "supersedes_run_receipt_id", "run_content_fingerprint", "attempt_id",
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


def _validate_source_version(value: Any) -> Mapping[str, Any]:
    source = _exact_mapping(
        value, {"evaluation_contracts"}, "ExperimentRun source_version"
    )
    _text(source["evaluation_contracts"], "source_version.evaluation_contracts")
    return source


def validate_m10c_source_version(payload: Mapping[str, Any]) -> None:
    """Require the sole source identity approved for new formal M10-C records."""

    if not isinstance(payload, Mapping) or _plain(payload.get("source_version")) != {
        "evaluation_contracts": M10_C_SOURCE_VERSION,
    }:
        raise ContractError("M10-C requires its approved readonly source version")


def _stable_reference_role(
    value: Any, *, field: str, allowed_roles: set[str]
) -> str:
    """Validate one typed, content-addressed ID without prefix guessing."""

    if not isinstance(value, str):
        raise ContractError(f"{field} must be a stable reference ID")
    unknown_roles = allowed_roles - STABLE_REFERENCE_PREFIXES.keys()
    if unknown_roles:
        raise ContractError(f"{field} uses unknown reference roles")
    for role in sorted(allowed_roles):
        prefix = STABLE_REFERENCE_PREFIXES[role]
        if re.fullmatch(re.escape(prefix) + r":sha256:[0-9a-f]{64}", value):
            return role
    raise ContractError(f"{field} has an invalid or disallowed stable ID")


def _normalize_reference_list(value: Any) -> Any:
    if not isinstance(value, (list, tuple)):
        return value
    items = [_plain(item) for item in value]
    return sorted(
        items,
        key=lambda item: (
            str(item.get("id", "")) if isinstance(item, Mapping) else str(item),
            str(item.get("content_fingerprint", ""))
            if isinstance(item, Mapping)
            else "",
        ),
    )


def _normalize_policy_references(value: Any) -> Any:
    if not isinstance(value, (list, tuple)):
        return value
    items = [_plain(item) for item in value]
    return sorted(
        items,
        key=lambda item: (
            str(item.get("policy_kind", ""))
            if isinstance(item, Mapping)
            else str(item),
            str(item.get("policy_version", ""))
            if isinstance(item, Mapping)
            else "",
            str(item.get("policy_fingerprint", ""))
            if isinstance(item, Mapping)
            else "",
        ),
    )


def _validate_run_policy_references(value: Any) -> set[str]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ContractError("ExperimentRun requires policy references")
    known_policies = {
        "aggregation": AGGREGATION_POLICY,
        "evaluation": EVALUATION_POLICY,
        "partition": PARTITION_POLICY,
        "forward_window": FORWARD_WINDOW_POLICY,
        "cost_slippage": ZERO_COST_COMPARISON_POLICY,
    }
    seen: set[str] = set()
    normalized: list[tuple[str, str, str]] = []
    for raw in value:
        ref = _exact_mapping(
            raw,
            {"policy_kind", "policy_version", "policy_fingerprint"},
            "ExperimentRun policy reference",
        )
        kind = _text(ref["policy_kind"], "policy_ref.policy_kind")
        if kind not in ALLOWED_RUN_POLICY_KINDS:
            raise ContractError("ExperimentRun policy kind is not approved")
        if kind in seen:
            raise ContractError("ExperimentRun policy kind is duplicated")
        seen.add(kind)
        version = _text(ref["policy_version"], "policy_ref.policy_version")
        fingerprint = _fingerprint(
            ref["policy_fingerprint"], "policy_ref.policy_fingerprint"
        )
        if kind in known_policies:
            expected = known_policies[kind]
            if (
                version != expected["policy_version"]
                or fingerprint != expected["policy_fingerprint"]
            ):
                raise ContractError(
                    f"ExperimentRun {kind} policy does not match the approved policy"
                )
        elif kind == "adjustment":
            if (
                version != ADJUSTMENT_POLICY["version"]
                or fingerprint != canonical_fingerprint(ADJUSTMENT_POLICY)
            ):
                raise ContractError(
                    "ExperimentRun adjustment policy does not match M02"
                )
        elif not SEMVER.fullmatch(version):
            raise ContractError(
                f"ExperimentRun {kind} policy version must be SemVer"
            )
        normalized.append((kind, version, fingerprint))
    if [item[0] for item in normalized] != sorted(seen):
        raise ContractError("ExperimentRun policy references must be canonical")
    if not {"evaluation", "partition"}.issubset(seen):
        raise ContractError(
            "ExperimentRun requires evaluation and partition policies"
        )
    return seen


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
        identity = {
            **common,
            "event_reference": {
                "id": payload["event_id"],
                "content_fingerprint": payload["event_content_fingerprint"],
            },
            "instrument_id": payload["instrument_id"],
            "signal_date": payload["signal_date"],
            "signal_market_snapshot_id": payload["signal_market_snapshot_id"],
            "evaluation_market_snapshot_reference": {
                "id": payload["evaluation_market_snapshot_id"],
                "content_fingerprint": payload[
                    "evaluation_market_snapshot_fingerprint"
                ],
            },
            "universe_reference": {
                "id": payload["universe_id"],
                "content_fingerprint": payload["universe_content_fingerprint"],
            },
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
        if "target_session_date" in payload:
            identity["target_session_date"] = payload["target_session_date"]
        return identity
    if contract_name == "TradeOutcome":
        return {
            **common,
            "event_reference": {
                "id": payload["event_id"],
                "content_fingerprint": payload["event_content_fingerprint"],
            },
            "instrument_id": payload["instrument_id"],
            "signal_date": payload["signal_date"],
            "evaluation_market_snapshot_reference": {
                "id": payload["evaluation_market_snapshot_id"],
                "content_fingerprint": payload[
                    "evaluation_market_snapshot_fingerprint"
                ],
            },
            "universe_reference": {
                "id": payload["universe_id"],
                "content_fingerprint": payload["universe_content_fingerprint"],
            },
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
    identity = {**common, reference_field: _plain(payload[reference_field])}
    if payload.get("schema_version") != RESULT_SCHEMA_VERSION:
        identity.update({
            "schema_version": payload["schema_version"],
            "result_set_fingerprint": payload["result_set_fingerprint"],
            "aggregation_policy_fingerprint": payload["aggregation_policy"][
                "policy_fingerprint"
            ],
            "evidence_scope": _plain(
                payload[
                    "portfolio_scope"
                    if contract_name == "PortfolioRun"
                    else "aggregate_scope"
                ]
            ),
        })
    return identity


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
        }
    reference_field = "trade_outcome_refs" if contract_name == "PortfolioRun" else "result_refs"
    identity = {
        **common,
        "run_id": payload["run_id"],
        reference_field: _plain(payload[reference_field]),
    }
    if payload.get("schema_version") != RESULT_SCHEMA_VERSION:
        identity["schema_version"] = payload["schema_version"]
        if contract_name == "ResearchAggregate":
            identity.update({
                "source_result_type": payload["source_result_type"],
                "window_sessions": payload["window_sessions"],
            })
    return identity


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
    if contract_name == "PortfolioRun" and "trade_outcome_refs" in result:
        result["trade_outcome_refs"] = _normalize_reference_list(
            result["trade_outcome_refs"]
        )
    elif contract_name == "ResearchAggregate" and "result_refs" in result:
        result["result_refs"] = _normalize_reference_list(result["result_refs"])
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
    schema_version = payload.get("schema_version")
    if contract_name == "ForwardOutcome":
        allowed = FORWARD_OUTCOME_FIELDS_BY_VERSION.get(schema_version)
        if allowed is None:
            raise ContractError("ForwardOutcome schema version is unknown")
    elif contract_name in RESULT_FIELDS_BY_VERSION:
        allowed = RESULT_FIELDS_BY_VERSION[contract_name].get(schema_version)
        if allowed is None:
            raise ContractError(f"{contract_name} schema version is unknown")
    else:
        allowed = RESULT_ALLOWED_FIELDS[contract_name]
        if schema_version != RESULT_SCHEMA_VERSION:
            raise ContractError(f"formal M10 requires {contract_name} 2.0.0")
    _exact_fields(payload, allowed, f"{contract_name} {schema_version}")
    validate_contract(contract_name, payload)
    _timestamp(payload["generated_at"], "generated_at")
    _stable_reference_role(
        payload["run_id"], field=f"{contract_name}.run_id",
        allowed_roles={"experiment_run"},
    )
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
            "evaluation_market_snapshot_id", "evaluation_market_snapshot_fingerprint",
            "universe_id", "universe_content_fingerprint",
            "window_policy", "session_calendar_id", "session_calendar_fingerprint",
            "elapsed_session_count", "observed_session_count", "observed_through",
            "status_reason", "entry", "endpoint", "gross_return", "mfe", "mae",
            "price_basis", "adjustment_policy", "market_data_fingerprint",
        },
        "ForwardOutcome",
    )
    _stable_reference_role(
        payload["event_id"], field="ForwardOutcome.event_id",
        allowed_roles={"opportunity_event"},
    )
    _stable_reference_role(
        payload["instrument_id"], field="ForwardOutcome.instrument_id",
        allowed_roles={"instrument"},
    )
    require_date(payload["signal_date"], "signal_date")
    if payload["signal_date"] > payload["as_of"]:
        raise ContractError("ForwardOutcome signal_date cannot be after as_of")
    _fingerprint(payload["event_content_fingerprint"], "event_content_fingerprint")
    _stable_reference_role(
        payload["signal_market_snapshot_id"],
        field="ForwardOutcome.signal_market_snapshot_id",
        allowed_roles={"market_snapshot"},
    )
    _stable_reference_role(
        payload["evaluation_market_snapshot_id"],
        field="ForwardOutcome.evaluation_market_snapshot_id",
        allowed_roles={"market_snapshot"},
    )
    _fingerprint(
        payload["evaluation_market_snapshot_fingerprint"],
        "evaluation_market_snapshot_fingerprint",
    )
    _stable_reference_role(
        payload["universe_id"], field="ForwardOutcome.universe_id",
        allowed_roles={"universe"},
    )
    _fingerprint(payload["universe_content_fingerprint"], "universe_content_fingerprint")
    validate_policy(payload["window_policy"], expected_kind="forward_window")
    if _plain(payload["window_policy"]) != _plain(FORWARD_WINDOW_POLICY):
        raise ContractError("ForwardOutcome uses an unknown window policy")
    if payload["window_sessions"] not in FORWARD_WINDOWS:
        raise ContractError("ForwardOutcome window is not approved")
    _stable_reference_role(
        payload["session_calendar_id"],
        field="ForwardOutcome.session_calendar_id",
        allowed_roles={"session_calendar"},
    )
    _fingerprint(payload["session_calendar_fingerprint"], "session_calendar_fingerprint")
    modern_forward = payload["schema_version"] == FORWARD_OUTCOME_SCHEMA_VERSION
    target_session_date = payload.get("target_session_date")
    if target_session_date is not None:
        target_session_date = require_date(
            target_session_date, "ForwardOutcome.target_session_date"
        )
        if target_session_date <= payload["signal_date"]:
            raise ContractError("ForwardOutcome target session must follow the signal")
    elapsed = _non_negative_int(payload["elapsed_session_count"], "elapsed_session_count")
    observed = _non_negative_int(payload["observed_session_count"], "observed_session_count")
    if observed > elapsed:
        raise ContractError("observed sessions cannot exceed elapsed sessions")
    observed_through = payload["observed_through"]
    if observed_through is not None:
        require_date(observed_through, "observed_through")
        if observed_through > payload["as_of"]:
            raise ContractError("ForwardOutcome observes data after as_of")
        if target_session_date is not None and observed_through > target_session_date:
            raise ContractError(
                "ForwardOutcome cannot observe beyond its target session"
            )
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
        if modern_forward and target_session_date is not None:
            raise ContractError("pending ForwardOutcome 2.1 target must be null")
        if any(payload[field] is not None for field in ("endpoint", "gross_return", "mfe", "mae")):
            raise ContractError("pending ForwardOutcome cannot contain mature results")
    else:
        if elapsed < payload["window_sessions"]:
            raise ContractError("an immature ForwardOutcome must remain pending")
        if modern_forward and target_session_date is None:
            raise ContractError("matured ForwardOutcome 2.1 requires its target session")
        if target_session_date is not None and target_session_date > payload["as_of"]:
            raise ContractError("matured ForwardOutcome target cannot be after as_of")
        if status == "mature":
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
            if (
                field == "endpoint"
                and target_session_date is not None
                and value["date"] != target_session_date
            ):
                raise ContractError(
                    "ForwardOutcome endpoint date must match its target session"
                )
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
            "exit_reason",
            "holding_sessions", "gross_return", "gross_r_multiple", "net_return",
            "net_return_status", "net_return_reason", "mfe", "mae", "mfe_status",
            "mae_status", "mfe_reason", "mae_reason", "cost_policy",
            "price_basis", "adjustment_policy",
            "evaluation_market_snapshot_id", "evaluation_market_snapshot_fingerprint",
            "universe_id", "universe_content_fingerprint",
            "market_data_fingerprint", "execution_policy",
        },
        "TradeOutcome",
    )
    _stable_reference_role(
        payload["event_id"], field="TradeOutcome.event_id",
        allowed_roles={"opportunity_event"},
    )
    _stable_reference_role(
        payload["instrument_id"], field="TradeOutcome.instrument_id",
        allowed_roles={"instrument"},
    )
    require_date(payload["signal_date"], "signal_date")
    if payload["signal_date"] > payload["as_of"]:
        raise ContractError("TradeOutcome signal_date cannot be after as_of")
    _fingerprint(payload["event_content_fingerprint"], "event_content_fingerprint")
    _stable_reference_role(
        payload["evaluation_market_snapshot_id"],
        field="TradeOutcome.evaluation_market_snapshot_id",
        allowed_roles={"market_snapshot"},
    )
    _fingerprint(
        payload["evaluation_market_snapshot_fingerprint"],
        "evaluation_market_snapshot_fingerprint",
    )
    _stable_reference_role(
        payload["universe_id"], field="TradeOutcome.universe_id",
        allowed_roles={"universe"},
    )
    _fingerprint(payload["universe_content_fingerprint"], "universe_content_fingerprint")
    if payload["price_basis"] != "provider_adjusted_ohlcv":
        raise ContractError("TradeOutcome price basis is invalid")
    if _plain(payload["adjustment_policy"]) != ADJUSTMENT_POLICY:
        raise ContractError("TradeOutcome must bind the M02 adjustment policy")
    _fingerprint(payload["market_data_fingerprint"], "market_data_fingerprint")
    _non_negative_int(payload["holding_sessions"], "holding_sessions")
    status = payload["status"]
    if status not in {"pending", "completed", "no_trade", "unavailable"}:
        raise ContractError("TradeOutcome status is invalid")
    if status in {"pending", "completed"}:
        _stable_reference_role(
            payload["trade_plan_id"], field="TradeOutcome.trade_plan_id",
            allowed_roles={"trade_plan"},
        )
        _fingerprint(payload["trade_plan_content_fingerprint"], "trade_plan_content_fingerprint")
        _stable_reference_role(
            payload["exit_state_id"], field="TradeOutcome.exit_state_id",
            allowed_roles={"exit_state"},
        )
        _fingerprint(payload["exit_state_content_fingerprint"], "exit_state_content_fingerprint")
        if payload["entry"] is None:
            raise ContractError("TradeOutcome with a plan requires its entry")
    else:
        _text(payload["status_reason"], "status_reason")
        if any(payload[field] is not None for field in ("trade_plan_id", "exit_state_id", "entry", "exit")):
            raise ContractError("unplanned TradeOutcome cannot fabricate plan or execution facts")
    _stable_reference_role(
        payload["trade_plan_link_id"], field="TradeOutcome.trade_plan_link_id",
        allowed_roles={"machine_link"},
    )
    _fingerprint(payload["trade_plan_link_content_fingerprint"], "trade_plan_link_content_fingerprint")
    if status == "completed":
        if payload["status_reason"] is not None or payload["exit"] is None:
            raise ContractError("completed TradeOutcome requires an exit")
        if "exit_reason" in payload and payload["exit_reason"] not in {
            "stop_gap", "stop", "target", "time_40d",
        }:
            raise ContractError("completed TradeOutcome exit reason is invalid")
        _finite(payload["gross_return"], "gross_return")
        _finite(payload["gross_r_multiple"], "gross_r_multiple")
    else:
        if "exit_reason" in payload and payload["exit_reason"] is not None:
            raise ContractError("non-completed TradeOutcome cannot claim an exit reason")
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
    excursion_reason = "exit_day_inclusion_and_intraday_order_not_approved"
    for field in ("mfe_reason", "mae_reason"):
        if field in payload and payload[field] != excursion_reason:
            raise ContractError("TradeOutcome excursion reason is invalid")
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


def _validate_reference_list(
    value: Any,
    field: str,
    *,
    allowed_roles: set[str],
    allow_empty: bool = True,
) -> set[str]:
    if not isinstance(value, (list, tuple)):
        raise ContractError(f"{field} must be a list")
    if not allow_empty and not value:
        raise ContractError(f"{field} cannot be empty")
    normalized: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    roles: set[str] = set()
    for item in value:
        item = _exact_mapping(
            item, {"id", "content_fingerprint"}, f"{field} item"
        )
        stable_id = _text(item.get("id"), f"{field}.id")
        roles.add(_stable_reference_role(
            stable_id, field=f"{field}.id", allowed_roles=allowed_roles
        ))
        if stable_id in seen_ids:
            raise ContractError(f"{field} contains a duplicate stable ID")
        seen_ids.add(stable_id)
        fingerprint = _fingerprint(item.get("content_fingerprint"), f"{field}.content_fingerprint")
        normalized.append((stable_id, fingerprint))
    if normalized != sorted(normalized):
        raise ContractError(f"{field} must be sorted and unique")
    return roles


_M10_C_SCOPE_FIELDS = {
    "source_result_type", "window_sessions", "path_status", "result_role",
    "partition_role", "evaluation_policy_fingerprint",
    "partition_policy_fingerprint", "adjustment_policy_fingerprint",
    "window_policy_fingerprint", "execution_policy_version",
    "execution_policy_fingerprint", "cost_policy_status",
    "cost_policy_version", "cost_policy_fingerprint",
}
def _quantized_ratio(numerator: int, denominator: int) -> float:
    return quantized_ratio(numerator, denominator)


def _validate_m10c_scope(value: Any, *, expected_type: str) -> Mapping[str, Any]:
    scope = _exact_mapping(value, _M10_C_SCOPE_FIELDS, "M10-C evidence scope")
    if scope["source_result_type"] != expected_type:
        raise ContractError("M10-C evidence scope has the wrong result type")
    if scope["path_status"] != "formal":
        raise ContractError("M10-C 2.1 only accepts formal evidence")
    if scope["result_role"] not in {"authoritative", "comparison"}:
        raise ContractError("M10-C evidence role is invalid")
    if scope["partition_role"] not in {"development", "validation", "forward"}:
        raise ContractError("M10-C evidence partition is invalid")
    expected_fingerprints = {
        "evaluation_policy_fingerprint": EVALUATION_POLICY["policy_fingerprint"],
        "partition_policy_fingerprint": PARTITION_POLICY["policy_fingerprint"],
        "adjustment_policy_fingerprint": canonical_fingerprint(ADJUSTMENT_POLICY),
    }
    for field, expected in expected_fingerprints.items():
        _fingerprint(scope[field], f"M10-C scope.{field}")
        if scope[field] != expected:
            raise ContractError(f"M10-C scope {field} is not approved")
    if expected_type == "forward_outcome":
        if scope["window_sessions"] not in FORWARD_WINDOWS:
            raise ContractError("M10-C Forward scope requires one approved window")
        if scope["window_policy_fingerprint"] != FORWARD_WINDOW_POLICY[
            "policy_fingerprint"
        ]:
            raise ContractError("M10-C Forward scope window policy is invalid")
        if any(
            scope[field] is not None
            for field in (
                "execution_policy_version", "execution_policy_fingerprint",
                "cost_policy_status", "cost_policy_version", "cost_policy_fingerprint",
            )
        ):
            raise ContractError("M10-C Forward scope cannot carry trade policies")
    else:
        if scope["window_sessions"] is not None or scope["window_policy_fingerprint"] is not None:
            raise ContractError("M10-C Trade scope cannot carry a Forward window")
        version = scope["execution_policy_version"]
        if not isinstance(version, str) or not SEMVER.fullmatch(version):
            raise ContractError("M10-C Trade scope execution policy is invalid")
        _fingerprint(
            scope["execution_policy_fingerprint"],
            "M10-C scope.execution_policy_fingerprint",
        )
        if scope["result_role"] == "authoritative":
            if (
                scope["cost_policy_status"] != "unapproved"
                or scope["cost_policy_version"] is not None
                or scope["cost_policy_fingerprint"] is not None
            ):
                raise ContractError("authoritative M10-C scope cannot invent costs")
        elif (
            scope["cost_policy_status"] != "comparison_only"
            or scope["cost_policy_version"]
            != ZERO_COST_COMPARISON_POLICY["policy_version"]
            or scope["cost_policy_fingerprint"]
            != ZERO_COST_COMPARISON_POLICY["policy_fingerprint"]
        ):
            raise ContractError("comparison M10-C scope cost policy is invalid")
    return scope


def validate_m10c_scope(value: Any, *, expected_type: str) -> None:
    """Validate the one strict evidence-scope shape used by M10-C."""

    if expected_type not in {"forward_outcome", "trade_outcome"}:
        raise ContractError("M10-C scope result type is invalid")
    _validate_m10c_scope(value, expected_type=expected_type)


def _validate_m10c_common(
    payload: Mapping[str, Any], *, scope_field: str, expected_type: str
) -> Mapping[str, Any]:
    validate_m10c_source_version(payload)
    if payload["path_status"] != "formal":
        raise ContractError("M10-C 2.1 results must be formal")
    validate_policy(payload["aggregation_policy"], expected_kind="aggregation")
    if _plain(payload["aggregation_policy"]) != _plain(AGGREGATION_POLICY):
        raise ContractError("M10-C result uses an unknown aggregation policy")
    scope = _validate_m10c_scope(payload[scope_field], expected_type=expected_type)
    if any(
        payload[field] != scope[field]
        for field in ("path_status", "result_role", "partition_role")
    ):
        raise ContractError("M10-C result role does not match its evidence scope")
    return scope


def _validate_portfolio_2_1(payload: Mapping[str, Any]) -> None:
    _validate_m10c_common(
        payload, scope_field="portfolio_scope", expected_type="trade_outcome"
    )
    _validate_reference_list(
        payload["trade_outcome_refs"],
        "trade_outcome_refs",
        allowed_roles={"trade_outcome"},
    )
    _fingerprint(payload["result_set_fingerprint"], "result_set_fingerprint")
    if payload["result_set_fingerprint"] != canonical_fingerprint(
        _plain(payload["trade_outcome_refs"])
    ):
        raise ContractError("PortfolioRun result set fingerprint is invalid")
    if (
        payload["status"] != "unavailable"
        or payload["status_reason"]
        != "capital_allocation_policy_not_approved"
    ):
        raise ContractError("M10-C PortfolioRun must remain unavailable")


def _validate_optional_metric(value: Any, field: str) -> float | None:
    return _finite(value, field, allow_none=True)


def _validate_research_2_1(payload: Mapping[str, Any]) -> None:
    source_type = payload["source_result_type"]
    if source_type not in {"forward_outcome", "trade_outcome"}:
        raise ContractError("ResearchAggregate source result type is invalid")
    scope = _validate_m10c_common(
        payload, scope_field="aggregate_scope", expected_type=source_type
    )
    if payload["window_sessions"] != scope["window_sessions"]:
        raise ContractError("ResearchAggregate window does not match its scope")
    roles = _validate_reference_list(
        payload["result_refs"],
        "result_refs",
        allowed_roles={
            "forward_outcome" if source_type == "forward_outcome" else "trade_outcome"
        },
    )
    if roles and roles != {
        "forward_outcome" if source_type == "forward_outcome" else "trade_outcome"
    }:
        raise ContractError("ResearchAggregate references mixed result types")
    _fingerprint(payload["result_set_fingerprint"], "result_set_fingerprint")
    if payload["result_set_fingerprint"] != canonical_fingerprint(
        _plain(payload["result_refs"])
    ):
        raise ContractError("ResearchAggregate result set fingerprint is invalid")
    if payload["status"] != "completed":
        raise ContractError("M10-C ResearchAggregate calculation must complete")

    total = _non_negative_int(payload["total_count"], "total_count")
    evaluated = _non_negative_int(payload["evaluated_count"], "evaluated_count")
    missing = _non_negative_int(payload["missing_count"], "missing_count")
    expected_statuses = (
        {"pending", "mature", "partial", "unavailable"}
        if source_type == "forward_outcome"
        else {"completed", "open", "no_trade", "unavailable"}
    )
    counts = _exact_mapping(
        payload["status_counts"], expected_statuses, "ResearchAggregate status_counts"
    )
    for name in expected_statuses:
        _non_negative_int(counts[name], f"status_counts.{name}")
    if total != sum(counts.values()) or total != evaluated + missing:
        raise ContractError("ResearchAggregate counts do not conserve inputs")
    if source_type == "forward_outcome":
        if not counts["mature"] <= evaluated <= counts["mature"] + counts["partial"]:
            raise ContractError(
                "Forward ResearchAggregate evaluated count contradicts status buckets"
            )
    elif evaluated != counts["completed"]:
        raise ContractError(
            "Trade ResearchAggregate can evaluate completed outcomes only"
        )
    win = _non_negative_int(payload["win_count"], "win_count")
    loss = _non_negative_int(payload["loss_count"], "loss_count")
    flat = _non_negative_int(payload["flat_count"], "flat_count")
    if win + loss + flat != evaluated:
        raise ContractError("ResearchAggregate outcome classes do not conserve samples")
    expected_missing_rate = None if total == 0 else _quantized_ratio(missing, total)
    if payload["missing_rate"] != expected_missing_rate:
        raise ContractError("ResearchAggregate missing_rate is inconsistent")

    metric_fields = (
        "win_rate", "mean_gross_return", "median_gross_return", "gross_profit",
        "gross_loss_abs", "profit_factor", "gross_expectancy",
    )
    metrics = {
        field: _validate_optional_metric(payload[field], field)
        for field in metric_fields
    }
    if evaluated == 0:
        if any(value is not None for value in metrics.values()):
            raise ContractError("empty ResearchAggregate cannot contain return metrics")
        if (
            payload["metric_status"] != "unavailable"
            or payload["metric_reason"] != "empty_sample"
        ):
            raise ContractError("empty ResearchAggregate requires explicit status")
        return
    if payload["metric_status"] != "available":
        raise ContractError("evaluated ResearchAggregate metrics must be available")
    if any(
        metrics[field] is None
        for field in (
            "win_rate", "mean_gross_return", "median_gross_return",
            "gross_profit", "gross_loss_abs", "gross_expectancy",
        )
    ):
        raise ContractError("evaluated ResearchAggregate is missing metrics")
    if payload["win_rate"] != _quantized_ratio(win, evaluated):
        raise ContractError("ResearchAggregate win_rate is inconsistent")
    if payload["gross_expectancy"] != payload["mean_gross_return"]:
        raise ContractError("gross_expectancy must equal mean_gross_return")
    gross_profit = decimal_metric(payload["gross_profit"], "gross_profit")
    gross_loss = decimal_metric(payload["gross_loss_abs"], "gross_loss_abs")
    expected_pf, expected_reason = profit_factor_semantics(gross_profit, gross_loss)
    if (
        payload["profit_factor"] != expected_pf
        or payload["metric_reason"] != expected_reason
    ):
        raise ContractError("ResearchAggregate profit factor semantics are inconsistent")
    if expected_reason == "undefined_zero_profit_and_loss" and (win != 0 or loss != 0):
        raise ContractError("all-flat ResearchAggregate counts are inconsistent")


def _validate_unimplemented_result(contract_name: str, payload: Mapping[str, Any]) -> None:
    field = "trade_outcome_refs" if contract_name == "PortfolioRun" else "result_refs"
    _validate_reference_list(
        payload[field], field,
        allowed_roles={"trade_outcome"}
        if contract_name == "PortfolioRun"
        else {"forward_outcome", "trade_outcome", "portfolio_run"},
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
    elif (
        contract_name == "PortfolioRun"
        and payload["schema_version"] == PORTFOLIO_RUN_SCHEMA_VERSION
    ):
        _validate_portfolio_2_1(payload)
    elif (
        contract_name == "ResearchAggregate"
        and payload["schema_version"] == RESEARCH_AGGREGATE_SCHEMA_VERSION
    ):
        _validate_research_2_1(payload)
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
        "source_version": _plain(payload["source_version"]),
        "evidence_window": _plain(payload["evidence_window"]),
        "path_status": payload["path_status"],
        "result_role": payload["result_role"],
        "partition_role": payload["partition_role"],
        "bias_labels": _plain(payload["bias_labels"]),
        "code_commit": payload["code_commit"],
        "config_ref": _plain(payload["config_ref"]),
        "engine": _plain(payload["engine"]),
        "policy_refs": _plain(payload["policy_refs"]),
        "input_set_fingerprint": payload["input_set_fingerprint"],
        "parent_run_id": payload["parent_run_id"],
        "checkpoint_ref": _plain(payload["checkpoint_ref"]),
    }


def _run_receipt_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": payload["run_id"],
        "status": payload["status"],
        "result_set_fingerprint": payload["result_set_fingerprint"],
        "supersedes_run_receipt_id": payload["supersedes_run_receipt_id"],
    }


def _run_semantic(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _plain(value)
        for key, value in payload.items()
        if key not in {"generated_at", "run_content_fingerprint"}
    }


def build_experiment_run_receipt(**values: Any) -> Mapping[str, Any]:
    """Build one immutable ExperimentRun 2.x receipt revision."""

    payload = _plain(values)
    payload.setdefault("schema_version", EXPERIMENT_RUN_SCHEMA_VERSION)
    payload.setdefault("source_version", {"evaluation_contracts": "m10-a-1.0.0"})
    payload.setdefault("future_data_used", False)
    payload.setdefault("supersedes_run_receipt_id", None)
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
    if (
        isinstance(payload.get("bias_labels"), (list, tuple))
        and all(isinstance(item, str) for item in payload["bias_labels"])
    ):
        payload["bias_labels"] = sorted(payload["bias_labels"])
    payload["policy_refs"] = _normalize_policy_references(payload["policy_refs"])
    payload["input_refs"] = _normalize_reference_list(payload["input_refs"])
    payload["result_refs"] = _normalize_reference_list(payload["result_refs"])
    payload["input_set_fingerprint"] = canonical_fingerprint(payload["input_refs"])
    payload["result_set_fingerprint"] = canonical_fingerprint(payload["result_refs"])
    payload["run_id"] = "experiment-run:" + canonical_fingerprint(_run_identity(payload))
    payload["run_receipt_id"] = (
        "experiment-run-receipt:"
        + canonical_fingerprint(_run_receipt_identity(payload))
    )
    payload["run_content_fingerprint"] = canonical_fingerprint(_run_semantic(payload))
    validate_experiment_run(payload)
    return _freeze(payload)


def validate_experiment_run(payload: Mapping[str, Any]) -> None:
    """Validate an immutable ExperimentRun 2.x receipt; 1.x stays in M01."""

    _exact_fields(payload, EXPERIMENT_RUN_ALLOWED_FIELDS, "ExperimentRun 2.x")
    validate_contract("ExperimentRun", payload)
    if payload["schema_version"] != EXPERIMENT_RUN_SCHEMA_VERSION:
        raise ContractError("M10 formal receipts require ExperimentRun 2.0.0")
    source = _validate_source_version(payload["source_version"])
    m10c_run = source["evaluation_contracts"] == M10_C_SOURCE_VERSION
    _stable_reference_role(
        payload["run_id"], field="ExperimentRun.run_id",
        allowed_roles={"experiment_run"},
    )
    _stable_reference_role(
        payload["run_receipt_id"], field="ExperimentRun.run_receipt_id",
        allowed_roles={"experiment_run_receipt"},
    )
    supersedes_receipt = payload["supersedes_run_receipt_id"]
    if supersedes_receipt is not None:
        _stable_reference_role(
            supersedes_receipt,
            field="ExperimentRun.supersedes_run_receipt_id",
            allowed_roles={"experiment_run_receipt"},
        )
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
    input_roles = _validate_reference_list(
        payload["input_refs"], "input_refs",
        allowed_roles=EXPERIMENT_INPUT_REFERENCE_ROLES,
        allow_empty=m10c_run,
    )
    result_roles = _validate_reference_list(
        payload["result_refs"], "result_refs",
        allowed_roles=EXPERIMENT_RESULT_REFERENCE_ROLES,
    )
    if payload["input_set_fingerprint"] != canonical_fingerprint(_plain(payload["input_refs"])):
        raise ContractError("ExperimentRun input set fingerprint is invalid")
    if payload["result_set_fingerprint"] != canonical_fingerprint(_plain(payload["result_refs"])):
        raise ContractError("ExperimentRun result set fingerprint is invalid")
    policy_kinds = _validate_run_policy_references(payload["policy_refs"])
    if m10c_run:
        if "aggregation" not in policy_kinds:
            raise ContractError("M10-C runs require the aggregation policy")
        if result_roles - {"portfolio_run", "research_aggregate"}:
            raise ContractError("M10-C runs cannot emit other M10 result types")
    if result_roles & {"forward_outcome", "trade_outcome"}:
        if not {"market_snapshot", "universe"}.issubset(input_roles):
            raise ContractError(
                "price outcomes require market and universe input references"
            )
        if "adjustment" not in policy_kinds:
            raise ContractError(
                "price outcomes require the M02 adjustment policy"
            )
    if "forward_outcome" in result_roles and "forward_window" not in policy_kinds:
        raise ContractError("ForwardOutcome runs require the window policy")
    if "trade_outcome" in result_roles:
        if "execution" not in policy_kinds:
            raise ContractError("TradeOutcome runs require execution policy evidence")
        if payload["result_role"] == "comparison" and "cost_slippage" not in policy_kinds:
            raise ContractError(
                "comparison TradeOutcome runs require cost/slippage policy evidence"
            )
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
    finished = payload["finished_at"]
    if finished is not None:
        finished = _timestamp(finished, "finished_at")
        if finished < started:
            raise ContractError("ExperimentRun finished_at predates started_at")
    parent = payload["parent_run_id"]
    if parent is not None:
        _stable_reference_role(
            parent, field="ExperimentRun.parent_run_id",
            allowed_roles={"experiment_run"},
        )
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
    if status not in {"pending", "completed", "failed", "interrupted", "unavailable"}:
        raise ContractError("ExperimentRun status is invalid")
    if status == "pending":
        if (
            payload["result_refs"]
            or payload["error"] is not None
            or payload["finished_at"] is not None
            or supersedes_receipt is not None
        ):
            raise ContractError(
                "pending ExperimentRun must be an unfinished root receipt"
            )
    elif status == "completed":
        if (
            not payload["result_refs"]
            or payload["error"] is not None
            or payload["finished_at"] is None
        ):
            raise ContractError("completed ExperimentRun requires results and no error")
    else:
        if payload["finished_at"] is None:
            raise ContractError("terminal ExperimentRun requires finished_at")
        error = _exact_mapping(
            payload["error"], {"category", "message"}, "ExperimentRun error"
        )
        _text(error["category"], "error.category")
        _text(error["message"], "error.message")
    expected_id = "experiment-run:" + canonical_fingerprint(_run_identity(payload))
    if payload["run_id"] != expected_id:
        raise ContractError("ExperimentRun run_id does not match its execution identity")
    expected_receipt_id = (
        "experiment-run-receipt:"
        + canonical_fingerprint(_run_receipt_identity(payload))
    )
    if payload["run_receipt_id"] != expected_receipt_id:
        raise ContractError(
            "ExperimentRun receipt identity does not match its revision"
        )
    if payload["run_content_fingerprint"] != canonical_fingerprint(_run_semantic(payload)):
        raise ContractError("ExperimentRun content fingerprint is invalid")


def current_experiment_run(
    receipts: Iterable[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Validate one linear receipt chain and return its sole current revision."""

    items = list(receipts)
    if not items:
        raise ContractError("ExperimentRun receipt chain is empty")
    by_id: dict[str, Mapping[str, Any]] = {}
    run_ids: set[str] = set()
    for item in items:
        validate_experiment_run(item)
        receipt_id = str(item["run_receipt_id"])
        if receipt_id in by_id:
            raise ContractError("ExperimentRun receipt chain has a duplicate identity")
        by_id[receipt_id] = item
        run_ids.add(str(item["run_id"]))
    if len(run_ids) != 1:
        raise ContractError("ExperimentRun receipt chain crosses run roots")

    roots: list[str] = []
    children: dict[str, str] = {}
    for receipt_id, item in by_id.items():
        prior = item["supersedes_run_receipt_id"]
        if prior is None:
            roots.append(receipt_id)
            continue
        if prior not in by_id:
            raise ContractError("ExperimentRun receipt chain has a missing predecessor")
        if prior in children:
            raise ContractError("ExperimentRun receipt chain forks")
        if by_id[prior]["status"] != "pending" or item["status"] == "pending":
            raise ContractError("ExperimentRun receipt transition is invalid")
        children[str(prior)] = receipt_id
    if len(roots) != 1:
        raise ContractError("ExperimentRun receipt chain must have one root")

    visited: set[str] = set()
    cursor = roots[0]
    while cursor not in visited:
        visited.add(cursor)
        next_id = children.get(cursor)
        if next_id is None:
            break
        cursor = next_id
    if cursor in children or visited != set(by_id):
        raise ContractError("ExperimentRun receipt chain is cyclic or disconnected")
    return by_id[cursor]


__all__ = [
    "EXPERIMENT_RUN_SCHEMA_VERSION", "FORWARD_OUTCOME_SCHEMA_VERSION",
    "M10_C_SOURCE_VERSION", "PORTFOLIO_RUN_SCHEMA_VERSION",
    "RESEARCH_AGGREGATE_SCHEMA_VERSION", "RESULT_SCHEMA_VERSION",
    "assert_immutable_compatible", "build_experiment_run_receipt",
    "current_experiment_run", "current_result",
    "finalize_result", "result_input_fingerprint", "validate_experiment_run",
    "validate_m10c_scope", "validate_m10c_source_version", "validate_result",
]
