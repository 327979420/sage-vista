"""The sole M02 shadow repository for cached daily market bars.

The repository has no provider implementation of its own.  Tests or a future
approved integration must inject an object with ``fetch(instrument_id, dates)``.
Only the repository writes its private cache format; callers receive immutable
point-in-time results and never a writable cache path.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
from pathlib import Path
import re
import threading
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence

from services.contracts.market_data import (
    canonical_fingerprint,
    require_date,
    revision_record,
    validate_revision_chain,
)
from services.contracts.validation import ContractError

from .normalization import adjusted_point_in_time_rows, validate_raw_rows
from .storage import atomic_write_validated_json, require_shadow_root


REPOSITORY_SCHEMA_VERSION = "1.0.0"
INSTRUMENT_ID = re.compile(r"^instrument:sha256:([0-9a-f]{64})$")


class MarketDataSource(Protocol):
    """Injected source boundary; production networking is outside package D."""

    def fetch(self, instrument_id: str, dates: tuple[str, ...]) -> Iterable[Mapping[str, Any]]:
        """Return exactly the requested canonical daily rows in date order."""


@dataclass(frozen=True)
class RepositoryRead:
    instrument_id: str
    as_of: str
    rows: tuple[Mapping[str, Any], ...]
    point_in_time_fingerprint: str


class MarketDataRepository:
    """Validate, fill and atomically persist one non-truncating history per listing."""

    _thread_locks: dict[str, threading.Lock] = {}
    _thread_locks_guard = threading.Lock()

    def __init__(
        self,
        root: str | Path,
        source: MarketDataSource,
        *,
        workspace_root: str | Path | None = None,
        before_replace: Callable[[Path, Path], None] | None = None,
    ) -> None:
        # Fail before retaining the provider or deriving any writable child.
        self._root = require_shadow_root(root, workspace_root=workspace_root)
        self._source = source
        self._before_replace = before_replace
        self._instrument_dir = self._root / "instruments"
        self._lock_dir = self._root / ".locks"

    @staticmethod
    def _digest(instrument_id: str) -> str:
        if not isinstance(instrument_id, str):
            raise ContractError("instrument_id must be a stable M02 identity")
        match = INSTRUMENT_ID.fullmatch(instrument_id)
        if not match:
            raise ContractError("instrument_id is unsafe or non-canonical")
        return match.group(1)

    def _safe_child(self, directory: Path, name: str) -> Path:
        """Derive paths internally and prove they stay under the configured root."""

        path = (directory / name).resolve()
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise ContractError("repository path escapes its configured root") from exc
        return path

    def _instrument_path(self, instrument_id: str) -> Path:
        return self._safe_child(self._instrument_dir, self._digest(instrument_id) + ".json")

    @contextmanager
    def _instrument_lock(self, instrument_id: str):
        """Serialize threads and processes so one missing range is fetched once."""

        digest = self._digest(instrument_id)
        lock_key = str(self._safe_child(self._lock_dir, digest + ".lock"))
        with self._thread_locks_guard:
            thread_lock = self._thread_locks.setdefault(lock_key, threading.Lock())
        with thread_lock:
            self._lock_dir.mkdir(parents=True, exist_ok=True)
            lock_path = self._safe_child(self._lock_dir, digest + ".lock")
            with lock_path.open("a+b") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _empty_state(instrument_id: str) -> dict[str, Any]:
        bars: list[dict[str, Any]] = []
        return {
            "schema_version": REPOSITORY_SCHEMA_VERSION,
            "instrument_id": instrument_id,
            "bars": bars,
            "current_fingerprint": canonical_fingerprint(bars),
            "revision_log": [],
        }

    def _load_state(self, path: Path, instrument_id: str) -> dict[str, Any]:
        if not path.exists():
            return self._empty_state(instrument_id)
        try:
            payload = json.loads(path.read_bytes())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError("repository cache is not valid JSON") from exc
        if not isinstance(payload, Mapping):
            raise ContractError("repository cache root must be an object")
        if payload.get("schema_version") != REPOSITORY_SCHEMA_VERSION:
            raise ContractError("unknown repository cache schema version")
        if payload.get("instrument_id") != instrument_id:
            raise ContractError("repository cache instrument identity mismatch")
        bars = list(validate_raw_rows(payload.get("bars", [])))
        if payload.get("current_fingerprint") != canonical_fingerprint(bars):
            raise ContractError("repository cache fingerprint mismatch")
        revisions = payload.get("revision_log")
        if not isinstance(revisions, list):
            raise ContractError("repository revision_log must be a list")
        validate_revision_chain(revisions)
        return {
            "schema_version": REPOSITORY_SCHEMA_VERSION,
            "instrument_id": instrument_id,
            "bars": bars,
            "current_fingerprint": payload["current_fingerprint"],
            "revision_log": [dict(record) for record in revisions],
        }

    @staticmethod
    def _requested_dates(values: Sequence[str], *, as_of: str, field: str) -> tuple[str, ...]:
        if isinstance(values, (str, bytes)):
            raise ContractError(f"{field} must be a sequence of dates")
        dates = [require_date(value, field) for value in values]
        if len(dates) != len(set(dates)):
            raise ContractError(f"{field} contains duplicate dates")
        if any(value > as_of for value in dates):
            raise ContractError(f"{field} cannot contain dates after as_of")
        return tuple(sorted(dates))

    def _atomic_write(self, path: Path, payload: Mapping[str, Any]) -> None:
        atomic_write_validated_json(
            path,
            payload,
            validator=lambda staged: self._load_staged_state(
                staged, str(payload["instrument_id"])
            ),
            before_replace=self._before_replace,
        )

    @staticmethod
    def _load_staged_state(payload: Any, instrument_id: str) -> None:
        if not isinstance(payload, Mapping) or payload.get("instrument_id") != instrument_id:
            raise ContractError("staged repository state identity mismatch")
        if payload.get("schema_version") != REPOSITORY_SCHEMA_VERSION:
            raise ContractError("staged repository schema version mismatch")
        bars = list(validate_raw_rows(payload.get("bars", [])))
        if payload.get("current_fingerprint") != canonical_fingerprint(bars):
            raise ContractError("staged repository fingerprint mismatch")
        revisions = payload.get("revision_log")
        if not isinstance(revisions, list):
            raise ContractError("staged revision_log must be a list")
        validate_revision_chain(revisions)

    def read(
        self,
        instrument_id: str,
        *,
        as_of: str,
        required_dates: Sequence[str] = (),
        refresh_dates: Sequence[str] = (),
        revision_reconstructible: bool = True,
        reconstruction_reason: str | None = None,
    ) -> RepositoryRead:
        """Fill only explicit gaps/refreshes, then return an adjusted point-in-time view."""

        as_of = require_date(as_of, "as_of")
        required = self._requested_dates(required_dates, as_of=as_of, field="required_dates")
        refresh = self._requested_dates(refresh_dates, as_of=as_of, field="refresh_dates")
        if not revision_reconstructible and not reconstruction_reason:
            raise ContractError("not_reconstructible refreshes require an explicit reason")
        path = self._instrument_path(instrument_id)

        with self._instrument_lock(instrument_id):
            state = self._load_state(path, instrument_id)
            original = {row["date"]: dict(row) for row in state["bars"]}
            missing = set(required) - original.keys()
            requested = tuple(sorted(missing | set(refresh)))

            fetched_rows: tuple[dict[str, Any], ...] = ()
            if requested:
                fetched_rows = validate_raw_rows(self._source.fetch(instrument_id, requested))
                fetched_dates = tuple(row["date"] for row in fetched_rows)
                if fetched_dates != requested:
                    raise ContractError("data source must return exactly the requested missing/refresh dates")

            working = {day: dict(row) for day, row in original.items()}
            revisions = [dict(record) for record in state["revision_log"]]
            changed = False

            # Confirmed refreshes may revise existing rows.  Every other old row
            # is immutable in this operation and is checked again before write.
            for row in fetched_rows:
                day = row["date"]
                if day not in original:
                    continue
                if day not in refresh:
                    raise ContractError("data source attempted an unconfirmed overwrite")
                if original[day] == row:
                    continue
                before = canonical_fingerprint([working[key] for key in sorted(working)])
                old_row = dict(working[day])
                working[day] = dict(row)
                after = canonical_fingerprint([working[key] for key in sorted(working)])
                previous = revisions[-1] if revisions else None
                revisions.append(revision_record(
                    instrument_id=instrument_id,
                    changed_date=day,
                    old_row=old_row,
                    new_row=row,
                    before_fingerprint=before,
                    after_fingerprint=after,
                    previous_revision_id=previous["revision_id"] if previous else None,
                    previous_revision_fingerprint=previous["revision_fingerprint"] if previous else None,
                    reconstruction_status=(
                        "reconstructible" if revision_reconstructible else "not_reconstructible"
                    ),
                    reconstruction_reason=reconstruction_reason,
                ))
                changed = True

            for row in fetched_rows:
                if row["date"] in original:
                    continue
                working[row["date"]] = dict(row)
                changed = True

            if not original.keys() <= working.keys():
                raise ContractError("repository update attempted to truncate existing history")
            for day, old_row in original.items():
                if day not in refresh and working[day] != old_row:
                    raise ContractError("repository update attempted an unconfirmed overwrite")

            bars = list(validate_raw_rows(working[key] for key in sorted(working)))
            validate_revision_chain(revisions)
            current_fingerprint = canonical_fingerprint(bars)
            if changed:
                self._atomic_write(path, {
                    "schema_version": REPOSITORY_SCHEMA_VERSION,
                    "instrument_id": instrument_id,
                    "bars": bars,
                    "current_fingerprint": current_fingerprint,
                    "revision_log": revisions,
                })

            point_in_time = adjusted_point_in_time_rows(bars, as_of=as_of)
            return RepositoryRead(
                instrument_id=instrument_id,
                as_of=as_of,
                rows=point_in_time,
                # Never expose the full-cache fingerprint here: it could depend
                # on bars after as_of and make a historical read future-sensitive.
                point_in_time_fingerprint=canonical_fingerprint(point_in_time),
            )
