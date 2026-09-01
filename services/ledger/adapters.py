"""Pure, read-only adapters for the two pre-M09 public ledgers.

The legacy files are audit evidence, not incomplete formal events.  These
functions accept exact source bytes, retain those bytes unchanged, freeze the
decoded records and reconcile only genuinely shared legacy IDs.  Ticker and
date are exposed as audit hints only; they never create a formal identity or
an automatic match.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError


LEGACY_PATH_STATUS = "legacy"
RECONCILIATION_CLASSIFICATIONS = (
    "matched_explicitly",
    "opportunity_only",
    "signal_only",
    "ambiguous",
    "conflict",
)
FORMAL_IDENTITY_FIELDS = (
    "instrument_id",
    "universe_id",
    "market_snapshot_id",
    "gate_event_id",
    "technical_evidence_ids",
    "model_assessment_ids",
    "ranking_snapshot_id",
)


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


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON value is not allowed: {value}")


@dataclass(frozen=True)
class LegacyArchiveRecord:
    """One immutable row from an exact legacy source file."""

    archive_record_id: str
    source_kind: str
    source_index: int
    source_record_id: str | None
    symbol_hint: str | None
    signal_date_hint: str | None
    record_fingerprint: str
    path_status: str
    formal_eligible: bool
    missing_formal_identities: tuple[str, ...]
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class LegacyLedgerArchive:
    """Exact bytes plus immutable structural metadata for one legacy ledger."""

    source_kind: str
    path_status: str
    source_sha256: str
    source_size_bytes: int
    source_schema_version: str
    source_as_of: str | None
    record_count: int
    source_bytes: bytes
    records: tuple[LegacyArchiveRecord, ...]


@dataclass(frozen=True)
class LegacyReconciliationEntry:
    """An audit classification; it never asserts a formal event identity."""

    classification: str
    explicit_legacy_id: str | None
    opportunity_record_ids: tuple[str, ...]
    signal_record_ids: tuple[str, ...]
    symbol_hint: str | None
    signal_date_hint: str | None
    reason: str
    formal_eligible: bool = False


@dataclass(frozen=True)
class LegacyReconciliationReport:
    """Deterministic reconciliation of two exact legacy archive versions."""

    reconciliation_id: str
    path_status: str
    opportunity_source_sha256: str
    signal_source_sha256: str
    opportunity_record_count: int
    signal_record_count: int
    classification_counts: Mapping[str, int]
    formal_records_created: int
    entries: tuple[LegacyReconciliationEntry, ...]


def _adapt_legacy_bytes(
    raw: bytes,
    *,
    source_kind: str,
    schema_field: str,
    records_field: str,
    record_id_field: str,
    date_field: str,
) -> LegacyLedgerArchive:
    if not isinstance(raw, bytes):
        raise ContractError(f"{source_kind} adapter requires exact bytes")
    source_sha256 = "sha256:" + hashlib.sha256(raw).hexdigest()
    try:
        decoded = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise ContractError(f"{source_kind} source is not canonical JSON evidence") from exc
    if not isinstance(decoded, Mapping):
        raise ContractError(f"{source_kind} source root must be an object")
    schema_version = _text(decoded.get(schema_field))
    if schema_version is None:
        raise ContractError(f"{source_kind} source schema is missing")
    rows = decoded.get(records_field)
    if not isinstance(rows, list):
        raise ContractError(f"{source_kind} source records must be a list")

    records: list[LegacyArchiveRecord] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ContractError(f"{source_kind} record {index} must be an object")
        plain = _plain(row)
        source_record_id = _text(plain.get(record_id_field))
        missing = tuple(
            field for field in FORMAL_IDENTITY_FIELDS if not plain.get(field)
        )
        record_fingerprint = canonical_fingerprint(plain)
        archive_record_id = "legacy-record:" + canonical_fingerprint({
            "source_kind": source_kind,
            "source_sha256": source_sha256,
            "source_index": index,
            "record_fingerprint": record_fingerprint,
        })
        records.append(LegacyArchiveRecord(
            archive_record_id=archive_record_id,
            source_kind=source_kind,
            source_index=index,
            source_record_id=source_record_id,
            symbol_hint=_text(plain.get("symbol")),
            signal_date_hint=_text(plain.get(date_field)),
            record_fingerprint=record_fingerprint,
            path_status=LEGACY_PATH_STATUS,
            formal_eligible=False,
            missing_formal_identities=missing,
            payload=_freeze(plain),
        ))

    return LegacyLedgerArchive(
        source_kind=source_kind,
        path_status=LEGACY_PATH_STATUS,
        source_sha256=source_sha256,
        source_size_bytes=len(raw),
        source_schema_version=schema_version,
        source_as_of=_text(decoded.get("as_of")),
        record_count=len(records),
        source_bytes=raw,
        records=tuple(records),
    )


def adapt_legacy_opportunity_ledger(raw: bytes) -> LegacyLedgerArchive:
    """Archive exact ``opportunity-ledger.json`` bytes without upgrading them."""

    return _adapt_legacy_bytes(
        raw,
        source_kind="opportunity_ledger",
        schema_field="schema_version",
        records_field="events",
        record_id_field="event_id",
        date_field="signal_date",
    )


def adapt_legacy_signal_history(raw: bytes) -> LegacyLedgerArchive:
    """Archive exact ``signal-history.json`` bytes without upgrading them."""

    return _adapt_legacy_bytes(
        raw,
        source_kind="signal_history",
        schema_field="signal_schema_version",
        records_field="cases",
        record_id_field="signal_id",
        date_field="first_seen_date",
    )


def _validate_archive(archive: LegacyLedgerArchive, expected_kind: str) -> None:
    if not isinstance(archive, LegacyLedgerArchive):
        raise ContractError("legacy reconciliation requires archive wrappers")
    if archive.source_kind != expected_kind or archive.path_status != LEGACY_PATH_STATUS:
        raise ContractError("legacy reconciliation received the wrong archive kind")
    if archive.record_count != len(archive.records):
        raise ContractError("legacy archive record count does not match its wrapper")
    expected_sha = "sha256:" + hashlib.sha256(archive.source_bytes).hexdigest()
    if archive.source_sha256 != expected_sha or archive.source_size_bytes != len(archive.source_bytes):
        raise ContractError("legacy archive bytes do not match their source receipt")
    for record in archive.records:
        if (
            record.source_kind != expected_kind
            or record.path_status != LEGACY_PATH_STATUS
            or record.formal_eligible is not False
            or record.record_fingerprint != canonical_fingerprint(_plain(record.payload))
        ):
            raise ContractError("legacy archive record changed after adaptation")


def _compatible_hints(
    opportunity: LegacyArchiveRecord,
    signal: LegacyArchiveRecord,
) -> bool:
    symbols_conflict = bool(
        opportunity.symbol_hint
        and signal.symbol_hint
        and opportunity.symbol_hint != signal.symbol_hint
    )
    dates_conflict = bool(
        opportunity.signal_date_hint
        and signal.signal_date_hint
        and opportunity.signal_date_hint != signal.signal_date_hint
    )
    return not symbols_conflict and not dates_conflict


def _common_hint(records: tuple[LegacyArchiveRecord, ...], field: str) -> str | None:
    values = {getattr(record, field) for record in records if getattr(record, field)}
    return next(iter(values)) if len(values) == 1 else None


def _entry(
    classification: str,
    opportunity: tuple[LegacyArchiveRecord, ...] = (),
    signal: tuple[LegacyArchiveRecord, ...] = (),
    *,
    explicit_legacy_id: str | None = None,
    reason: str,
) -> LegacyReconciliationEntry:
    if classification not in RECONCILIATION_CLASSIFICATIONS:
        raise ContractError("unknown legacy reconciliation classification")
    combined = (*opportunity, *signal)
    return LegacyReconciliationEntry(
        classification=classification,
        explicit_legacy_id=explicit_legacy_id,
        opportunity_record_ids=tuple(sorted(x.archive_record_id for x in opportunity)),
        signal_record_ids=tuple(sorted(x.archive_record_id for x in signal)),
        symbol_hint=_common_hint(combined, "symbol_hint"),
        signal_date_hint=_common_hint(combined, "signal_date_hint"),
        reason=reason,
    )


def reconcile_legacy_ledgers(
    opportunity: LegacyLedgerArchive,
    signal: LegacyLedgerArchive,
) -> LegacyReconciliationReport:
    """Reconcile exact legacy sources without inferring a formal relationship.

    Equality of explicit legacy IDs is the sole match rule.  A shared ticker
    and date is recorded as ambiguity only; it is never promoted to a match.
    Every source record appears in exactly one reconciliation entry.
    """

    _validate_archive(opportunity, "opportunity_ledger")
    _validate_archive(signal, "signal_history")
    opportunity_by_id: dict[str, list[LegacyArchiveRecord]] = defaultdict(list)
    signal_by_id: dict[str, list[LegacyArchiveRecord]] = defaultdict(list)
    for record in opportunity.records:
        if record.source_record_id:
            opportunity_by_id[record.source_record_id].append(record)
    for record in signal.records:
        if record.source_record_id:
            signal_by_id[record.source_record_id].append(record)

    used_opportunity: set[str] = set()
    used_signal: set[str] = set()
    entries: list[LegacyReconciliationEntry] = []
    for source_id in sorted(set(opportunity_by_id) | set(signal_by_id)):
        opportunity_rows = tuple(opportunity_by_id.get(source_id, ()))
        signal_rows = tuple(signal_by_id.get(source_id, ()))
        duplicate = len(opportunity_rows) > 1 or len(signal_rows) > 1
        if duplicate:
            entries.append(_entry(
                "conflict",
                opportunity_rows,
                signal_rows,
                explicit_legacy_id=source_id,
                reason="duplicate explicit legacy ID within a source",
            ))
        elif opportunity_rows and signal_rows:
            if _compatible_hints(opportunity_rows[0], signal_rows[0]):
                entries.append(_entry(
                    "matched_explicitly",
                    opportunity_rows,
                    signal_rows,
                    explicit_legacy_id=source_id,
                    reason="exact event_id equals signal_id",
                ))
            else:
                entries.append(_entry(
                    "conflict",
                    opportunity_rows,
                    signal_rows,
                    explicit_legacy_id=source_id,
                    reason="same explicit legacy ID has conflicting symbol or date evidence",
                ))
        else:
            continue
        used_opportunity.update(x.archive_record_id for x in opportunity_rows)
        used_signal.update(x.archive_record_id for x in signal_rows)

    remaining_opportunity = tuple(
        record for record in opportunity.records
        if record.archive_record_id not in used_opportunity
    )
    remaining_signal = tuple(
        record for record in signal.records
        if record.archive_record_id not in used_signal
    )
    opportunity_by_hint: dict[tuple[str, str], list[LegacyArchiveRecord]] = defaultdict(list)
    signal_by_hint: dict[tuple[str, str], list[LegacyArchiveRecord]] = defaultdict(list)
    for record in remaining_opportunity:
        if record.symbol_hint and record.signal_date_hint:
            opportunity_by_hint[(record.symbol_hint, record.signal_date_hint)].append(record)
    for record in remaining_signal:
        if record.symbol_hint and record.signal_date_hint:
            signal_by_hint[(record.symbol_hint, record.signal_date_hint)].append(record)

    for hint in sorted(set(opportunity_by_hint) & set(signal_by_hint)):
        opportunity_rows = tuple(opportunity_by_hint[hint])
        signal_rows = tuple(signal_by_hint[hint])
        entries.append(_entry(
            "ambiguous",
            opportunity_rows,
            signal_rows,
            reason="ticker and date overlap without an equal explicit legacy ID",
        ))
        used_opportunity.update(x.archive_record_id for x in opportunity_rows)
        used_signal.update(x.archive_record_id for x in signal_rows)

    for record in opportunity.records:
        if record.archive_record_id not in used_opportunity:
            entries.append(_entry(
                "opportunity_only",
                (record,),
                reason="no explicit signal-history ID match",
            ))
            used_opportunity.add(record.archive_record_id)
    for record in signal.records:
        if record.archive_record_id not in used_signal:
            entries.append(_entry(
                "signal_only",
                signal=(record,),
                reason="no explicit opportunity-ledger ID match",
            ))
            used_signal.add(record.archive_record_id)

    if len(used_opportunity) != opportunity.record_count or len(used_signal) != signal.record_count:
        raise ContractError("legacy reconciliation did not account for every source record")

    order = {name: index for index, name in enumerate(RECONCILIATION_CLASSIFICATIONS)}
    entries.sort(key=lambda item: (
        order[item.classification],
        item.explicit_legacy_id or "",
        item.symbol_hint or "",
        item.signal_date_hint or "",
        item.opportunity_record_ids,
        item.signal_record_ids,
    ))
    counts = Counter(entry.classification for entry in entries)
    classification_counts = MappingProxyType({
        name: counts.get(name, 0) for name in RECONCILIATION_CLASSIFICATIONS
    })
    identity = {
        "opportunity_source_sha256": opportunity.source_sha256,
        "signal_source_sha256": signal.source_sha256,
        "entries": [
            {
                "classification": entry.classification,
                "explicit_legacy_id": entry.explicit_legacy_id,
                "opportunity_record_ids": list(entry.opportunity_record_ids),
                "signal_record_ids": list(entry.signal_record_ids),
                "reason": entry.reason,
            }
            for entry in entries
        ],
    }
    return LegacyReconciliationReport(
        reconciliation_id="legacy-reconciliation:" + canonical_fingerprint(identity),
        path_status=LEGACY_PATH_STATUS,
        opportunity_source_sha256=opportunity.source_sha256,
        signal_source_sha256=signal.source_sha256,
        opportunity_record_count=opportunity.record_count,
        signal_record_count=signal.record_count,
        classification_counts=classification_counts,
        formal_records_created=0,
        entries=tuple(entries),
    )
