"""M02 field rules for the shared market-data and universe contracts.

This module extends the M01 contract names instead of creating a scanner- or
backtest-specific schema.  Every function is deterministic and performs no
file, network, Git, clock, or process I/O.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from .validation import ContractError, validate_contract


SCHEMA_VERSION = "1.0.0"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
INSTRUMENT_ID = re.compile(r"^instrument:sha256:[0-9a-f]{64}$")
TIERS = {"core", "main", "extended", "small_cap", "delisted"}
PATH_STATUSES = {"formal", "legacy"}
COVERAGE_STATUSES = {"complete", "legacy_observed", "unavailable"}
RECONSTRUCTION_STATUSES = {"reconstructible", "not_reconstructible"}


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as exc:
        raise ContractError("contract evidence must be canonical JSON") from exc


def canonical_fingerprint(value: Any) -> str:
    """Return the repeatable SHA-256 identity of canonical JSON evidence."""

    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def require_date(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{field} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ContractError(f"{field} must be canonical YYYY-MM-DD")
    return value


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value


def _require_fingerprint(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ContractError(f"{field} must be sha256:<64 lowercase hex>")
    return value


def stable_instrument_id(
    *, provider: str, market: str, provider_code: str, listing_lifecycle: str
) -> str:
    """Identify one listing without treating a display ticker as sufficient."""

    lifecycle = _require_text(listing_lifecycle, "listing_lifecycle")
    if lifecycle.lower() in {"unknown", "unavailable"}:
        raise ContractError("listing_lifecycle evidence is required for a stable instrument ID")
    evidence = {
        "provider": _require_text(provider, "provider"),
        "market": _require_text(market, "market"),
        "provider_code": _require_text(provider_code, "provider_code"),
        "listing_lifecycle": lifecycle,
    }
    return "instrument:" + canonical_fingerprint(evidence)


def _normalize_members(members: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    if not isinstance(members, Sequence) or isinstance(members, (str, bytes)) or not members:
        raise ContractError("UniverseSnapshot members must be a non-empty list")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for member in members:
        if not isinstance(member, Mapping):
            raise ContractError("universe member must be an object")
        instrument_id = _require_text(member.get("instrument_id"), "member.instrument_id")
        if not INSTRUMENT_ID.fullmatch(instrument_id):
            raise ContractError("member.instrument_id is not a stable M02 identity")
        if instrument_id in seen:
            raise ContractError("UniverseSnapshot contains a duplicate instrument_id")
        seen.add(instrument_id)
        tier = _require_text(member.get("tier"), "member.tier")
        if tier not in TIERS:
            raise ContractError(f"unknown universe tier: {tier}")
        normalized.append({
            "instrument_id": instrument_id,
            "symbol": _require_text(member.get("symbol"), "member.symbol"),
            "tier": tier,
            "listing_status": _require_text(member.get("listing_status"), "member.listing_status"),
        })
    return sorted(normalized, key=lambda row: row["instrument_id"])


def universe_snapshot_id(
    *,
    as_of: str,
    effective_from: str,
    source_version: Mapping[str, Any],
    eligibility_rule_version: str,
    members: Sequence[Mapping[str, Any]],
) -> str:
    if not isinstance(source_version, Mapping) or not source_version:
        raise ContractError("source_version must contain explicit source evidence")
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "as_of": require_date(as_of, "as_of"),
        "effective_from": require_date(effective_from, "effective_from"),
        "source_version": dict(source_version),
        "eligibility_rule_version": _require_text(
            eligibility_rule_version, "eligibility_rule_version"
        ),
        "members": _normalize_members(members),
    }
    if evidence["effective_from"] > evidence["as_of"]:
        raise ContractError("universe effective_from cannot be after as_of")
    return "universe:" + canonical_fingerprint(evidence)


def validate_universe_snapshot(payload: Mapping[str, Any]) -> None:
    """Validate point-in-time membership and recompute its stable identity."""

    validate_contract("UniverseSnapshot", payload)
    effective_from = require_date(payload["effective_from"], "effective_from")
    if effective_from > payload["as_of"]:
        raise ContractError("universe effective_from cannot be after as_of")
    if payload["path_status"] not in PATH_STATUSES:
        raise ContractError("UniverseSnapshot path_status must be formal or legacy")
    if payload["coverage_status"] not in COVERAGE_STATUSES:
        raise ContractError("UniverseSnapshot coverage_status is unknown")
    if payload["path_status"] == "formal" and payload["coverage_status"] != "complete":
        raise ContractError("formal historical universe requires complete point-in-time evidence")
    members = _normalize_members(payload["members"])
    expected = universe_snapshot_id(
        as_of=payload["as_of"],
        effective_from=effective_from,
        source_version=payload["source_version"],
        eligibility_rule_version=payload["eligibility_rule_version"],
        members=members,
    )
    if payload["universe_id"] != expected:
        raise ContractError("universe_id does not match canonical membership evidence")


def select_universe_snapshot(
    snapshots: Iterable[Mapping[str, Any]], *, as_of: str, path_status: str = "formal"
) -> Mapping[str, Any] | None:
    """Select the newest known snapshot without filling history from the future."""

    as_of = require_date(as_of, "as_of")
    if path_status not in PATH_STATUSES:
        raise ContractError("path_status must be formal or legacy")
    eligible: list[Mapping[str, Any]] = []
    for snapshot in snapshots:
        validate_universe_snapshot(snapshot)
        # A formal replay may never silently consume a legacy-observed list,
        # and a legacy replay should stay reproducible on its own evidence.
        if (
            snapshot["path_status"] == path_status
            and snapshot["effective_from"] <= as_of
            and snapshot["as_of"] <= as_of
        ):
            eligible.append(snapshot)
    if not eligible:
        if path_status == "legacy":
            return None
        raise ContractError("universe_unavailable")
    selected = max(eligible, key=lambda item: (item["effective_from"], item["as_of"]))
    if path_status == "formal" and (
        selected["path_status"] != "formal" or selected["coverage_status"] != "complete"
    ):
        raise ContractError("universe_unavailable")
    return selected


def market_data_snapshot_id(payload: Mapping[str, Any]) -> str:
    """Compute a snapshot ID without generated_at or display ordering."""

    symbols = payload.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        raise ContractError("MarketDataSnapshot symbols must be a non-empty list")
    identity_rows = []
    for row in symbols:
        if not isinstance(row, Mapping):
            raise ContractError("market snapshot symbol entry must be an object")
        identity_rows.append({
            "instrument_id": _require_text(row.get("instrument_id"), "symbol.instrument_id"),
            "symbol": _require_text(row.get("symbol"), "symbol.symbol"),
            "row_count": row.get("row_count"),
            "first_date": row.get("first_date"),
            "max_returned_date": row.get("max_returned_date"),
            "content_fingerprint": row.get("content_fingerprint"),
        })
    evidence = {
        "schema_version": payload.get("schema_version"),
        "as_of": payload.get("as_of"),
        "market": payload.get("market"),
        "data_source": payload.get("data_source"),
        "adjustment_policy": payload.get("adjustment_policy"),
        "universe_id": payload.get("universe_id"),
        "raw_revision": payload.get("raw_revision"),
        "symbols": sorted(identity_rows, key=lambda row: row["instrument_id"]),
    }
    return "market:" + canonical_fingerprint(evidence)


def validate_market_data_snapshot(payload: Mapping[str, Any]) -> None:
    """Validate that a shared market snapshot cannot contain future evidence."""

    validate_contract("MarketDataSnapshot", payload)
    if not isinstance(payload["data_source"], Mapping):
        raise ContractError("data_source must be an object")
    _require_text(payload["data_source"].get("provider"), "data_source.provider")
    _require_text(payload["data_source"].get("dataset"), "data_source.dataset")
    if not isinstance(payload["adjustment_policy"], Mapping):
        raise ContractError("adjustment_policy must be an object")
    _require_text(payload["adjustment_policy"].get("version"), "adjustment_policy.version")
    _require_text(payload["adjustment_policy"].get("formula"), "adjustment_policy.formula")
    _require_text(payload["universe_id"], "universe_id")
    _require_fingerprint(payload["raw_revision"], "raw_revision")
    max_returned = require_date(payload["max_returned_date"], "max_returned_date")
    if max_returned > payload["as_of"]:
        raise ContractError("MarketDataSnapshot contains data after as_of")
    if not isinstance(payload["symbols"], list) or not payload["symbols"]:
        raise ContractError("MarketDataSnapshot symbols must be a non-empty list")

    seen: set[str] = set()
    symbol_maxima: list[str] = []
    for row in payload["symbols"]:
        instrument_id = _require_text(row.get("instrument_id"), "symbol.instrument_id")
        if instrument_id in seen:
            raise ContractError("MarketDataSnapshot contains duplicate instrument_id")
        seen.add(instrument_id)
        if not INSTRUMENT_ID.fullmatch(instrument_id):
            raise ContractError("symbol.instrument_id is not a stable M02 identity")
        _require_text(row.get("symbol"), "symbol.symbol")
        if not isinstance(row.get("row_count"), int) or row["row_count"] <= 0:
            raise ContractError("symbol.row_count must be positive")
        first = require_date(row.get("first_date"), "symbol.first_date")
        maximum = require_date(row.get("max_returned_date"), "symbol.max_returned_date")
        if first > maximum or maximum > payload["as_of"]:
            raise ContractError("symbol date coverage is invalid or contains future rows")
        _require_fingerprint(row.get("content_fingerprint"), "symbol.content_fingerprint")
        symbol_maxima.append(maximum)
    if max(symbol_maxima) != max_returned:
        raise ContractError("snapshot max_returned_date does not match symbol evidence")
    if payload["snapshot_id"] != market_data_snapshot_id(payload):
        raise ContractError("snapshot_id does not match canonical market evidence")


def revision_record(
    *,
    changed_date: str,
    old_row: Mapping[str, Any],
    new_row: Mapping[str, Any],
    before_fingerprint: str,
    after_fingerprint: str,
    previous_revision_id: str | None,
    reconstruction_status: str = "reconstructible",
    reconstruction_reason: str | None = None,
) -> dict[str, Any]:
    """Build one append-only, row-level supplier revision record."""

    require_date(changed_date, "changed_date")
    _require_fingerprint(before_fingerprint, "before_fingerprint")
    _require_fingerprint(after_fingerprint, "after_fingerprint")
    if before_fingerprint == after_fingerprint:
        raise ContractError("a revision must change the full-history fingerprint")
    if dict(old_row) == dict(new_row):
        raise ContractError("a revision must preserve distinct old and new values")
    if old_row.get("date") != changed_date or new_row.get("date") != changed_date:
        raise ContractError("revision rows must identify changed_date")
    if reconstruction_status not in RECONSTRUCTION_STATUSES:
        raise ContractError("unknown reconstruction_status")
    if reconstruction_status == "not_reconstructible" and not reconstruction_reason:
        raise ContractError("not_reconstructible revisions require an explicit reason")
    evidence = {
        "changed_date": changed_date,
        "old_row": dict(old_row),
        "new_row": dict(new_row),
        "before_fingerprint": before_fingerprint,
        "after_fingerprint": after_fingerprint,
        "previous_revision_id": previous_revision_id,
        "reconstruction_status": reconstruction_status,
        "reconstruction_reason": reconstruction_reason,
    }
    return {"revision_id": "revision:" + canonical_fingerprint(evidence), **evidence}


def validate_revision_chain(records: Sequence[Mapping[str, Any]]) -> None:
    """Check append order, row evidence and full-history fingerprint continuity."""

    previous_id: str | None = None
    previous_after: str | None = None
    seen: set[str] = set()
    for record in records:
        rebuilt = revision_record(
            changed_date=record.get("changed_date"),
            old_row=record.get("old_row", {}),
            new_row=record.get("new_row", {}),
            before_fingerprint=record.get("before_fingerprint"),
            after_fingerprint=record.get("after_fingerprint"),
            previous_revision_id=record.get("previous_revision_id"),
            reconstruction_status=record.get("reconstruction_status"),
            reconstruction_reason=record.get("reconstruction_reason"),
        )
        revision_id = record.get("revision_id")
        if revision_id != rebuilt["revision_id"]:
            raise ContractError("revision_id does not match revision evidence")
        if revision_id in seen:
            raise ContractError("revision log contains a duplicate revision_id")
        seen.add(revision_id)
        if record.get("previous_revision_id") != previous_id:
            raise ContractError("revision chain previous_revision_id is broken")
        if previous_after is not None and record.get("before_fingerprint") != previous_after:
            raise ContractError("revision fingerprint chain is broken")
        previous_id = revision_id
        previous_after = record.get("after_fingerprint")
