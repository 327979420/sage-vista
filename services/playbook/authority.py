"""Trusted authority boundaries for M11 case and lifecycle evidence.

The contracts remain pure data validators.  Formal M11 producers and storage
must additionally resolve sensitive facts through these explicit interfaces.
No default resolver trusts caller-supplied objects.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping, Protocol, Sequence

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError

from .contracts import plain, proposal_preregistration_semantic_fingerprint


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


class PreregistrationAuthorityResolver(Protocol):
    """Resolve an immutable, pre-run registration record for Proposal 2.2."""

    authority_mode: str

    def resolve_preregistration(self, authority_id: str) -> Mapping[str, Any]: ...

    def verify_registration_commit_ancestry(
        self, registration_commit: str, run_code_commit: str
    ) -> bool: ...


_SHA = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def build_preregistration_authority_record(
    *, proposal_semantic_fingerprint: str, registered_at: str,
    registration_commit: str, verified_run_code_commits: Sequence[str],
    authority_mode: str,
) -> Mapping[str, Any]:
    """Build the canonical record returned by a trusted preregistration source."""

    semantic = {
        "proposal_semantic_fingerprint": proposal_semantic_fingerprint,
        "registered_at": registered_at,
        "registration_commit": registration_commit,
        "verified_run_code_commits": sorted(set(verified_run_code_commits)),
        "authority_mode": authority_mode,
    }
    fingerprint = canonical_fingerprint(semantic)
    record = {
        "authority_id": "strategy-preregistration-proof:" + fingerprint,
        "content_fingerprint": fingerprint,
        **semantic,
    }
    validate_preregistration_authority_record(record)
    return record


def validate_preregistration_authority_record(record: Mapping[str, Any]) -> None:
    expected_fields = {
        "authority_id", "content_fingerprint", "proposal_semantic_fingerprint",
        "registered_at", "registration_commit", "verified_run_code_commits",
        "authority_mode",
    }
    if not isinstance(record, Mapping) or set(record) != expected_fields:
        raise ContractError("trusted preregistration record has an invalid shape")
    for field in ("content_fingerprint", "proposal_semantic_fingerprint"):
        if not isinstance(record[field], str) or not _SHA.fullmatch(record[field]):
            raise ContractError(f"trusted preregistration {field} is invalid")
    if record["authority_mode"] not in {"formal", "test"}:
        raise ContractError("trusted preregistration authority mode is invalid")
    if not isinstance(record["registered_at"], str) or not record["registered_at"].endswith("Z"):
        raise ContractError("trusted preregistration time is invalid")
    try:
        datetime.fromisoformat(record["registered_at"][:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError("trusted preregistration time is invalid") from exc
    if not isinstance(record["registration_commit"], str) or not _COMMIT.fullmatch(record["registration_commit"]):
        raise ContractError("trusted preregistration commit is invalid")
    commits = record["verified_run_code_commits"]
    if (
        not isinstance(commits, (list, tuple))
        or not commits
        or list(commits) != sorted(set(commits))
        or any(not isinstance(item, str) or not _COMMIT.fullmatch(item) for item in commits)
    ):
        raise ContractError("trusted preregistration run commits are invalid")
    semantic = {
        key: plain(value)
        for key, value in record.items()
        if key not in {"authority_id", "content_fingerprint"}
    }
    fingerprint = canonical_fingerprint(semantic)
    if record["content_fingerprint"] != fingerprint:
        raise ContractError("trusted preregistration content fingerprint is invalid")
    if record["authority_id"] != "strategy-preregistration-proof:" + fingerprint:
        raise ContractError("trusted preregistration identity is invalid")


def validate_preregistration_authority(
    proposal: Mapping[str, Any],
    resolver: PreregistrationAuthorityResolver | None,
    *,
    pending_run_receipts: Sequence[Mapping[str, Any]] = (),
) -> Mapping[str, Any]:
    """Verify full proposal semantics and, when supplied, pre-run ordering."""

    if resolver is None:
        raise ContractError("formal M11 validation requires a trusted preregistration resolver")
    mode = getattr(resolver, "authority_mode", None)
    if mode not in {"formal", "test"}:
        raise ContractError("formal M11 preregistration resolver is not explicitly trusted")
    authority_ref = proposal.get("preregistration_authority_ref")
    if not isinstance(authority_ref, Mapping):
        raise ContractError("formal M11 proposal lacks preregistration authority")
    callback = getattr(resolver, "resolve_preregistration", None)
    if callback is None or not callable(callback):
        raise ContractError("formal M11 preregistration resolver is unavailable")
    try:
        record = callback(str(authority_ref["id"]))
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError("formal M11 preregistration evidence cannot be resolved") from exc
    if not isinstance(record, Mapping):
        raise ContractError("formal M11 preregistration resolver returned no authority record")
    validate_preregistration_authority_record(record)
    if record["authority_mode"] != mode:
        raise ContractError("preregistration authority mode differs from its resolver")
    if plain(authority_ref) != {
        "id": record["authority_id"],
        "content_fingerprint": record["content_fingerprint"],
    }:
        raise ContractError("proposal preregistration authority reference is invalid")
    expected_semantic = proposal_preregistration_semantic_fingerprint(proposal)
    if record["proposal_semantic_fingerprint"] != expected_semantic:
        raise ContractError("trusted preregistration content differs from the proposal")
    if pending_run_receipts:
        run_commits = sorted({str(item["code_commit"]) for item in pending_run_receipts})
        if list(record["verified_run_code_commits"]) != run_commits:
            raise ContractError("preregistration proof does not cover every M10 run commit")
        ancestry = getattr(resolver, "verify_registration_commit_ancestry", None)
        if ancestry is None or not callable(ancestry):
            raise ContractError("preregistration Git ordering proof is unavailable")
        for run_commit in run_commits:
            try:
                is_ancestor = ancestry(str(record["registration_commit"]), run_commit)
            except ContractError:
                raise
            except Exception as exc:
                raise ContractError("preregistration Git ordering cannot be verified") from exc
            if is_ancestor is not True:
                raise ContractError("preregistration commit does not precede M10 run code")
        registered = datetime.fromisoformat(str(record["registered_at"])[:-1] + "+00:00")
        for receipt in pending_run_receipts:
            started = datetime.fromisoformat(str(receipt["started_at"])[:-1] + "+00:00")
            if registered >= started:
                raise ContractError("preregistration was not frozen before M10 started")
    return record

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
    "PreregistrationAuthorityResolver",
    "build_preregistration_authority_record",
    "resolve_case_authority",
    "validate_case_authority",
    "validate_preregistration_authority",
    "validate_preregistration_authority_record",
    "validate_sensitive_lifecycle_authority",
]
