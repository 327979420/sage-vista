"""Trusted authority boundaries for M11 case and lifecycle evidence.

The contracts remain pure data validators.  Formal M11 producers and storage
must additionally resolve sensitive facts through these explicit interfaces.
No default resolver trusts caller-supplied objects.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from services.contracts.validation import ContractError

from .contracts import plain


class CaseAuthorityResolver(Protocol):
    """Resolve a persisted M09 event to its frozen case-registration fact."""

    authority_mode: str

    def resolve_case(self, event_id: str) -> Mapping[str, Any]: ...


class LifecycleAuthorityResolver(Protocol):
    """Resolve approval, main implementation, and M12 activation evidence."""

    authority_mode: str

    def resolve_user_approval(
        self, proposal: Mapping[str, Any], event: Mapping[str, Any]
    ) -> bool: ...

    def resolve_main_implementation(
        self, proposal: Mapping[str, Any], event: Mapping[str, Any]
    ) -> bool: ...

    def resolve_m12_activation(
        self, proposal: Mapping[str, Any], event: Mapping[str, Any]
    ) -> bool: ...


def _resolved(resolver: Any, method: str, key: str, label: str) -> Mapping[str, Any]:
    if resolver is None:
        raise ContractError(f"formal M11 {label} requires a trusted evidence resolver")
    if getattr(resolver, "authority_mode", None) not in {"formal", "test"}:
        raise ContractError(f"formal M11 {label} resolver is not explicitly trusted")
    callback = getattr(resolver, method, None)
    if callback is None or not callable(callback):
        raise ContractError(f"formal M11 {label} resolver is unavailable")
    try:
        value = callback(key)
    except ContractError:
        raise
    except Exception as exc:  # a resolver failure is an authority failure
        raise ContractError(f"formal M11 {label} evidence cannot be resolved") from exc
    if not isinstance(value, Mapping):
        raise ContractError(f"formal M11 {label} resolver returned no authority record")
    return value


def resolve_case_authority(
    event: Mapping[str, Any],
    resolver: CaseAuthorityResolver | None,
) -> Mapping[str, Any]:
    """Resolve and verify the complete stable case identity for one M09 event."""

    resolved = _resolved(resolver, "resolve_case", str(event["event_id"]), "case")
    fields = {
        "event_id": event["event_id"],
        "instrument_id": event["instrument_id"],
        "signal_date": event["signal_date"],
        "event_content_fingerprint": event["event_content_fingerprint"],
    }
    if set(resolved) != {*fields, "seen_before"}:
        raise ContractError("trusted M09 case registration has an invalid shape")
    if not isinstance(resolved["seen_before"], bool):
        raise ContractError("trusted M09 case registration lacks seen_before evidence")
    expected = {**fields, "seen_before": resolved["seen_before"]}
    if plain(resolved) != plain(expected):
        raise ContractError("proposal case differs from trusted M09 case registration")
    return expected


def validate_case_authority(
    case: Mapping[str, Any],
    event: Mapping[str, Any],
    resolver: CaseAuthorityResolver | None,
) -> None:
    """Bind one proposal case to the stable persisted M09 event identity."""

    resolved = resolve_case_authority(event, resolver)
    for field in (
        "event_id", "instrument_id", "signal_date", "event_content_fingerprint",
    ):
        if case[field] != event[field]:
            raise ContractError("proposal case crosses its persisted M09 event identity")
    if case["seen_before"] is not resolved["seen_before"]:
        raise ContractError("proposal case seen_before is not authority-derived")
    if case["seen_before"] and case["role"] in {"validation", "forward"}:
        raise ContractError("a previously seen case cannot be independent evidence")


def validate_sensitive_lifecycle_authority(
    proposal: Mapping[str, Any],
    event: Mapping[str, Any],
    resolver: LifecycleAuthorityResolver | None,
) -> None:
    """Resolve every sensitive lifecycle transition from its authority source."""

    event_type = event["event_type"]
    labels = {
        "user_decision_recorded": ("resolve_user_approval", "user approval"),
        "implementation_recorded": ("resolve_main_implementation", "main implementation"),
        "production_activation_recorded": ("resolve_m12_activation", "M12 activation"),
    }
    if event_type not in labels:
        return
    method, label = labels[event_type]
    if resolver is None:
        raise ContractError(f"formal M11 {label} requires a trusted evidence resolver")
    if getattr(resolver, "authority_mode", None) not in {"formal", "test"}:
        raise ContractError(f"formal M11 {label} resolver is not explicitly trusted")
    callback = getattr(resolver, method, None)
    if callback is None or not callable(callback):
        raise ContractError(f"formal M11 {label} resolver is unavailable")
    try:
        accepted = callback(proposal, event)
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(f"formal M11 {label} evidence cannot be resolved") from exc
    if accepted is not True:
        raise ContractError(f"{event_type} differs from trusted authority evidence")


__all__ = [
    "CaseAuthorityResolver",
    "LifecycleAuthorityResolver",
    "resolve_case_authority",
    "validate_case_authority",
    "validate_sensitive_lifecycle_authority",
]
