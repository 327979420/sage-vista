"""Versioned M10 policies for objective shadow evaluation.

The policies are immutable data.  They describe the approved first contract
surface only; no function here reads prices, calculates a return, or chooses a
strategy.  A later M10-B producer must consume these identities instead of
copying windows or missing-value behavior into callers.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError, SEMVER


FORWARD_WINDOWS = (1, 5, 20, 60, 100)


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


def build_policy(
    *, kind: str, version: str, name: str, rules: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Build one content-addressed policy without consulting mutable state."""

    payload = {
        "schema_version": "1.0.0",
        "policy_kind": kind,
        "policy_version": version,
        "policy_name": name,
        "rules": _plain(rules),
    }
    payload["policy_fingerprint"] = canonical_fingerprint(payload)
    validate_policy(payload, expected_kind=kind)
    return _freeze(payload)


def validate_policy(policy: Mapping[str, Any], *, expected_kind: str) -> None:
    if not isinstance(policy, Mapping) or policy.get("schema_version") != "1.0.0":
        raise ContractError("M10 policy schema must be 1.0.0")
    if policy.get("policy_kind") != expected_kind:
        raise ContractError("M10 policy kind is invalid")
    version = policy.get("policy_version")
    if (
        not isinstance(version, str)
        or not SEMVER.fullmatch(version)
        or not version.startswith("1.")
    ):
        raise ContractError("M10 policy requires a known 1.x SemVer")
    if not isinstance(policy.get("policy_name"), str) or not policy["policy_name"]:
        raise ContractError("M10 policy name is required")
    if not isinstance(policy.get("rules"), Mapping):
        raise ContractError("M10 policy rules must be an object")
    evidence = {
        key: _plain(value) for key, value in policy.items() if key != "policy_fingerprint"
    }
    if policy.get("policy_fingerprint") != canonical_fingerprint(evidence):
        raise ContractError("M10 policy fingerprint does not match its content")


EVALUATION_POLICY = build_policy(
    kind="evaluation",
    version="1.0.0",
    name="m10_objective_outcome_baseline",
    rules={
        "upstream_facts": ["M02", "M07", "M08", "M09"],
        "future_data_cutoff": "as_of_inclusive",
        "price_basis": "provider_adjusted_ohlcv",
        "formal_missing_cost_net_return": "unavailable",
        "zero_cost_net_return_role": "comparison_only",
        "non_finite_numbers": "reject",
    },
)


FORWARD_WINDOW_POLICY = build_policy(
    kind="forward_window",
    version="1.1.0",
    name="fixed_trading_session_windows",
    rules={
        "window_sessions": list(FORWARD_WINDOWS),
        "unit": "completed_trading_sessions",
        "reference_price": "first_post_signal_session_adjusted_open",
        "endpoint_price": "nth_post_signal_session_adjusted_close",
        "excursion_range": "first_post_signal_session_through_endpoint_inclusive",
        "not_yet_mature": "pending",
        "due_but_incomplete": ["partial", "unavailable"],
        "calendar_days_are_not_sessions": True,
    },
)


PARTITION_POLICY = build_policy(
    kind="partition",
    version="1.0.0",
    name="explicit_research_partition",
    rules={
        "roles": ["development", "validation", "forward"],
        "date_boundaries_must_be_explicit": True,
        "one_result_one_partition": True,
    },
)


AGGREGATION_POLICY = build_policy(
    kind="aggregation",
    version="1.0.0",
    name="m10_readonly_gross_outcome_summary",
    rules={
        "accepted_result_types": ["forward_outcome", "trade_outcome"],
        "one_result_type_per_aggregate": True,
        "one_forward_window_per_aggregate": True,
        "value_source": "frozen_gross_return_only",
        "missing_values_are_zero": False,
        "win_definition": "gross_return_gt_zero",
        "loss_definition": "gross_return_lt_zero",
        "flat_definition": "gross_return_eq_zero",
        "win_rate_denominator": "evaluated_count_including_flat",
        "gross_loss_storage": "absolute_value",
        "gross_expectancy": "mean_gross_return",
        "decimal_quantum": "0.0000000001",
        "rounding": "ROUND_HALF_EVEN",
        "non_finite_numbers": "reject",
    },
)


ZERO_COST_COMPARISON_POLICY = build_policy(
    kind="cost_slippage",
    version="1.0.0",
    name="zero_cost_comparison_only",
    rules={
        "commission": 0.0,
        "slippage": 0.0,
        "allowed_result_role": "comparison",
        "formal_authoritative": False,
    },
)


UNAPPROVED_COST_REFERENCE = _freeze({
    "status": "unapproved",
    "policy_version": None,
    "policy_fingerprint": None,
})


def policy_reference(policy: Mapping[str, Any], *, status: str = "approved") -> Mapping[str, Any]:
    """Return the minimal immutable reference stored by result contracts."""

    validate_policy(policy, expected_kind=str(policy.get("policy_kind", "")))
    if status not in {"approved", "comparison_only"}:
        raise ContractError("M10 policy reference status is invalid")
    return _freeze({
        "status": status,
        "policy_version": policy["policy_version"],
        "policy_fingerprint": policy["policy_fingerprint"],
    })


__all__ = [
    "AGGREGATION_POLICY",
    "EVALUATION_POLICY",
    "FORWARD_WINDOWS",
    "FORWARD_WINDOW_POLICY",
    "PARTITION_POLICY",
    "UNAPPROVED_COST_REFERENCE",
    "ZERO_COST_COMPARISON_POLICY",
    "build_policy",
    "policy_reference",
    "validate_policy",
]
