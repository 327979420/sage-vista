"""Versioned M07 scoring, ordering and authority policies.

Policies are immutable data.  Consumers may select an approved policy, but may
not copy its weights, missing-data behavior or sort keys into their own code.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError, SEMVER
from services.scanner.factor_registry import REGISTRY_VERSION


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def build_policy(*, kind: str, version: str, name: str, rules: Mapping[str, Any]) -> Mapping[str, Any]:
    """Create one content-addressed policy without consulting clocks or files."""

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
    if not isinstance(policy, Mapping):
        raise ContractError("M07 policy must be an object")
    if policy.get("schema_version") != "1.0.0":
        raise ContractError("M07 policy schema_version must be 1.0.0")
    if policy.get("policy_kind") != expected_kind:
        raise ContractError("M07 policy kind is incorrect")
    version = policy.get("policy_version")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise ContractError("M07 policy_version must be MAJOR.MINOR.PATCH")
    if int(version.split(".", 1)[0]) != 1:
        raise ContractError("unknown M07 policy major version")
    if not isinstance(policy.get("policy_name"), str) or not policy["policy_name"]:
        raise ContractError("M07 policy_name is required")
    if not isinstance(policy.get("rules"), Mapping):
        raise ContractError("M07 policy rules must be an object")
    evidence = {key: _plain(value) for key, value in policy.items() if key != "policy_fingerprint"}
    if policy.get("policy_fingerprint") != canonical_fingerprint(evidence):
        raise ContractError("M07 policy fingerprint does not match its contents")


SCORE_POLICY = build_policy(
    kind="score",
    version="1.0.0",
    name="technical_resonance_count",
    rules={
        "model_id": "complex_multifactor",
        "factor_registry_version": REGISTRY_VERSION,
        "gate_factor_ids": ["macd.daily_bull_cross", "qualification.long_trend"],
        "risk_family": "risk",
        "components": [
            "positive_hit_count",
            "family_count",
            "parent_child_confirmation_bonus",
            "timeframe_resonance_bonus",
        ],
        "missing_fact_behavior": "exclude",
        "context_effect": "reference_only_zero",
        "total_formula": "positive_hit_count + family_count + parent_child_confirmation_bonus + timeframe_resonance_bonus",
    },
)

RANKING_POLICY = build_policy(
    kind="ranking",
    version="1.0.0",
    name="technical_resonance_deterministic_order",
    rules={
        "authority_scope": "complex_multifactor_main",
        "accepted_score_policy_version": "1.0.0",
        "sort_keys": [
            {"field": "total_score", "direction": "desc"},
            {"field": "timeframe_resonance_bonus", "direction": "desc"},
            {"field": "family_count", "direction": "desc"},
            {"field": "positive_hit_count", "direction": "desc"},
            {"field": "instrument_id", "direction": "asc"},
        ],
        "selected_limit": 5,
        "favorite_pattern_effect": "none",
        "context_effect": "none",
    },
)

AUTHORITY_POLICY = build_policy(
    kind="authority",
    version="1.0.0",
    name="future_effective_append_only_authority",
    rules={
        "authority_scope": "complex_multifactor_main",
        "one_authoritative_snapshot_per_identity": True,
        "future_effective_only": True,
        "historical_recalculation_role": "comparison",
        "latest_version_is_not_automatic_authority": True,
    },
)


__all__ = [
    "AUTHORITY_POLICY",
    "RANKING_POLICY",
    "SCORE_POLICY",
    "build_policy",
    "validate_policy",
]
