"""Pure validation and point-in-time selection for M06 ETF evidence."""

from __future__ import annotations

from datetime import date
import re
from typing import Any, Mapping, Sequence

from services.contracts.market_data import canonical_fingerprint, require_date
from services.contracts.validation import ContractError


ETF_ID = re.compile(r"^etf:sha256:[0-9a-f]{64}$")
INSTRUMENT_ID = re.compile(r"^instrument:sha256:[0-9a-f]{64}$")
CATEGORIES = {"broad_market", "sector", "industry", "theme"}


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value


def validate_etf_registry(registry: Mapping[str, Any]) -> None:
    """Require a small, explicit registry instead of claiming every ETF."""

    if registry.get("schema_version") != "1.0.0":
        raise ContractError("M06 ETF registry schema version is unknown")
    _text(registry.get("registry_version"), "registry_version")
    require_date(registry.get("as_of_date"), "registry.as_of_date")
    items = registry.get("etfs")
    if not isinstance(items, list) or not items:
        raise ContractError("M06 ETF registry must contain a selected ETF list")
    symbols: set[str] = set()
    ids: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise ContractError("ETF registry entry must be an object")
        symbol = _text(item.get("symbol"), "ETF symbol")
        etf_id = _text(item.get("etf_id"), "ETF id")
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol):
            raise ContractError("ETF symbol is not canonical")
        if not ETF_ID.fullmatch(etf_id):
            raise ContractError("ETF id is not a stable M06 identity")
        if symbol in symbols or etf_id in ids:
            raise ContractError("ETF registry contains a duplicate identity")
        symbols.add(symbol)
        ids.add(etf_id)
        if item.get("category") not in CATEGORIES:
            raise ContractError("ETF category is unknown")
        for field in ("label", "issuer", "membership_source_url", "historical_membership_evidence"):
            _text(item.get(field), f"ETF {field}")
        require_date(item.get("membership_as_of_date"), "ETF membership_as_of_date")
        if not isinstance(item.get("formal_current_forward_eligible"), bool):
            raise ContractError("ETF formal eligibility must be explicit")


def validate_membership_registry(registry: Mapping[str, Any]) -> None:
    """Validate append-only membership evidence without inventing identities."""

    if registry.get("schema_version") != "1.0.0":
        raise ContractError("M06 membership registry schema version is unknown")
    _text(registry.get("mapping_registry_version"), "mapping_registry_version")
    snapshots = registry.get("snapshots")
    if not isinstance(snapshots, list):
        raise ContractError("membership snapshots must be a list")
    ids: set[str] = set()
    content_by_key: dict[tuple[str, str, str], str] = {}
    for snapshot in snapshots:
        if not isinstance(snapshot, Mapping):
            raise ContractError("membership snapshot must be an object")
        mapping_id = _text(snapshot.get("mapping_id"), "mapping_id")
        if mapping_id in ids:
            raise ContractError("membership registry contains a duplicate mapping_id")
        ids.add(mapping_id)
        symbol = _text(snapshot.get("etf_symbol"), "membership ETF symbol")
        effective = require_date(snapshot.get("effective_from"), "membership effective_from")
        require_date(snapshot.get("membership_as_of_date"), "membership_as_of_date")
        path_status = snapshot.get("path_status")
        if path_status not in {"formal", "legacy"}:
            raise ContractError("membership path_status must be formal or legacy")
        if not isinstance(snapshot.get("formal_eligible"), bool):
            raise ContractError("membership formal_eligible must be explicit")
        members = snapshot.get("members")
        if not isinstance(members, list):
            raise ContractError("membership members must be a list")
        members_source_count = snapshot.get("members_source_count")
        unresolved_member_count = snapshot.get("unresolved_member_count")
        if (
            isinstance(members_source_count, bool)
            or not isinstance(members_source_count, int)
            or members_source_count < 0
        ):
            raise ContractError("members_source_count must be a non-negative integer")
        if (
            isinstance(unresolved_member_count, bool)
            or not isinstance(unresolved_member_count, int)
            or unresolved_member_count < 0
        ):
            raise ContractError("unresolved_member_count must be a non-negative integer")
        if members_source_count < len(members):
            raise ContractError("members_source_count cannot be smaller than parsed members")
        if members_source_count != len(members) + unresolved_member_count:
            raise ContractError("membership counts do not conserve source members")
        member_ids: set[str] = set()
        for member in members:
            if not isinstance(member, Mapping):
                raise ContractError("membership member must be an object")
            instrument_id = _text(member.get("instrument_id"), "member instrument_id")
            if not INSTRUMENT_ID.fullmatch(instrument_id):
                raise ContractError("membership member lacks stable instrument identity")
            if instrument_id in member_ids:
                raise ContractError("membership snapshot contains a duplicate member")
            member_ids.add(instrument_id)
            _text(member.get("symbol"), "member symbol")
            weight = member.get("weight")
            if weight is not None and (not isinstance(weight, (int, float)) or weight < 0):
                raise ContractError("membership weight must be a non-negative number")
        if path_status == "formal":
            if unresolved_member_count != 0:
                raise ContractError("formal membership cannot contain unresolved members")
            if members_source_count != len(members):
                raise ContractError("formal membership source coverage must be complete")
            if (
                snapshot.get("formal_eligible") is not True
                or snapshot.get("identity_status") != "stable_instrument_id"
                or not members
                or snapshot.get("bias_labels") not in ([], ())
            ):
                raise ContractError("formal membership lacks complete stable identity evidence")
        if path_status == "legacy" and not snapshot.get("bias_labels"):
            raise ContractError("legacy membership must explain its bias")
        key = (symbol, effective, path_status)
        content = canonical_fingerprint(snapshot)
        previous = content_by_key.get(key)
        if previous is not None and previous != content:
            raise ContractError("membership registry has conflicting same-date snapshots")
        content_by_key[key] = content


def select_membership_snapshot(
    snapshots: Sequence[Mapping[str, Any]],
    *,
    etf_symbol: str,
    as_of: str,
    path_status: str,
) -> Mapping[str, Any]:
    """Select only evidence effective on the requested date; never backfill."""

    require_date(as_of, "as_of")
    if path_status not in {"formal", "legacy"}:
        raise ContractError("membership path must be formal or legacy")
    wrapper = {
        "schema_version": "1.0.0",
        "mapping_registry_version": "selection-validation",
        "snapshots": list(snapshots),
    }
    validate_membership_registry(wrapper)
    candidates = [
        item for item in snapshots
        if item["etf_symbol"] == etf_symbol
        and item["path_status"] == path_status
        and item["effective_from"] <= as_of
    ]
    if path_status == "formal":
        candidates = [item for item in candidates if item["formal_eligible"] is True]
    if not candidates:
        raise ContractError("membership_unavailable for requested ETF/date/path")
    latest_date = max(item["effective_from"] for item in candidates)
    latest = [item for item in candidates if item["effective_from"] == latest_date]
    unique = {canonical_fingerprint(item): item for item in latest}
    if len(unique) != 1:
        raise ContractError("membership snapshot conflict")
    return next(iter(unique.values()))
