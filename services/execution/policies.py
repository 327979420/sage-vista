"""Immutable M08 plan and exit policies; consumers cannot inject magic numbers."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError, SEMVER
from services.scanner.support_risk import EXECUTION_POLICY_VERSION


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


def build_policy(*, kind: str, version: str, rules: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = {
        "schema_version": "1.0.0",
        "policy_kind": kind,
        "policy_version": version,
        "rules": _plain(rules),
    }
    payload["policy_fingerprint"] = canonical_fingerprint(payload)
    validate_policy(payload, expected_kind=kind)
    return _freeze(payload)


def validate_policy(policy: Mapping[str, Any], *, expected_kind: str) -> None:
    if not isinstance(policy, Mapping) or policy.get("schema_version") != "1.0.0":
        raise ContractError("M08 policy schema must be 1.0.0")
    if policy.get("policy_kind") != expected_kind:
        raise ContractError("M08 policy kind is invalid")
    version = policy.get("policy_version")
    if not isinstance(version, str) or not SEMVER.fullmatch(version) or not version.startswith("1."):
        raise ContractError("M08 policy requires a known 1.x SemVer")
    if not isinstance(policy.get("rules"), Mapping):
        raise ContractError("M08 policy rules must be an object")
    evidence = {key: _plain(value) for key, value in policy.items() if key != "policy_fingerprint"}
    if policy.get("policy_fingerprint") != canonical_fingerprint(evidence):
        raise ContractError("M08 policy fingerprint does not match its content")


PLAN_POLICY = build_policy(
    kind="plan",
    version="1.0.0",
    rules={
        "legacy_execution_policy_version": EXECUTION_POLICY_VERSION,
        "ranking_entry_scope": "selected_entries",
        "entry_rule": "next_adjusted_open",
        "support_buffer_fraction": 0.05,
        "maximum_loss_fraction": 0.10,
        "target_r_multiple": 2.0,
        "max_hold_sessions": 40,
        "price_basis": "provider_adjusted_ohlcv",
        "missing_evidence_behavior": "unavailable_no_plan",
        "disabled_experiments": [
            "holding_30_60_126",
            "sell_90pct_at_2r_keep_10pct",
            "close_trailing_8pct",
            "daily_dual_exit_families",
            "higher_timeframe_dual_bearish_exit",
        ],
    },
)

EXIT_POLICY = build_policy(
    kind="exit",
    version="1.0.0",
    rules={
        "gap_stop_fill": "completed_bar_open",
        "ordinary_stop_test": "completed_bar_low_lte_stop",
        "target_test": "completed_bar_open_or_high_gte_target",
        "same_bar_priority": ["stop_gap", "stop", "target"],
        "time_exit": "session_40_completed_close",
        "performance_metrics": "none",
        "deferred_experiments_effect": False,
    },
)


__all__ = ["EXIT_POLICY", "PLAN_POLICY", "build_policy", "validate_policy"]
