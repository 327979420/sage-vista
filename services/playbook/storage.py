"""Append-only, atomic, shadow-only M11 storage."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Callable, Iterator, Mapping

from services.contracts.validation import ContractError
from services.market_data.storage import require_shadow_root

from .contracts import (
    current_strategy_assessment,
    current_strategy_lifecycle,
    plain,
    validate_strategy_evidence_assessment,
    validate_strategy_lifecycle_event,
    validate_strategy_proposal,
    validate_strategy_registry_snapshot,
)


_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be a stable ID")
    digest = value.rsplit(":", 1)[-1]
    if not _DIGEST.fullmatch(digest):
        raise ContractError(f"{field} must end in a lowercase SHA-256")
    return digest


def _bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(plain(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    except (TypeError, ValueError) as exc:
        raise ContractError("M11 record must be canonical JSON") from exc


@contextmanager
def _lock(root: Path, key: str) -> Iterator[None]:
    lock_dir = root / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    path = lock_dir / (key + ".lock")
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class PlaybookShadowStore:
    """Persist the three M11 authority records and optional derived snapshots."""

    def __init__(self, root: str | Path, *, workspace_root: str | Path | None = None) -> None:
        self.root = require_shadow_root(root, workspace_root=workspace_root)

    @staticmethod
    def _read(path: Path, validator: Callable[[Mapping[str, Any]], None]) -> Mapping[str, Any]:
        try:
            mode = path.lstat().st_mode
            raw = path.read_bytes()
        except OSError as exc:
            raise ContractError("M11 stored record cannot be inspected") from exc
        if path.is_symlink() or not stat.S_ISREG(mode):
            raise ContractError("M11 stored record must be a regular file")
        try:
            payload = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ContractError(f"non-finite JSON {value}")))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError("M11 stored record is not valid JSON") from exc
        if not isinstance(payload, Mapping):
            raise ContractError("M11 stored record must be an object")
        validator(payload)
        if raw != _bytes(payload):
            raise ContractError("M11 stored record is not canonical JSON")
        return payload

    def _write(self, payload: Mapping[str, Any], *, target: Path, validator: Callable[[Mapping[str, Any]], None], id_field: str, fingerprint_field: str) -> Path:
        validator(payload)
        content = _bytes(payload)
        if target.exists() or target.is_symlink():
            existing = self._read(target, validator)
            if existing[id_field] == payload[id_field] and existing[fingerprint_field] == payload[fingerprint_field] and _bytes(existing) == content:
                return target
            raise ContractError("immutable M11 identity already exists with different content")
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            self._read(temporary, validator)
            try:
                os.link(temporary, target)
            except FileExistsError:
                existing = self._read(target, validator)
                if _bytes(existing) != content:
                    raise ContractError("concurrent immutable M11 write conflict")
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return target
        finally:
            if temporary.exists():
                temporary.unlink()

    def _collection(self, name: str, validator: Callable[[Mapping[str, Any]], None]) -> list[Mapping[str, Any]]:
        root = self.root / name
        if not root.exists():
            return []
        if root.is_symlink() or not root.is_dir():
            raise ContractError("M11 collection must be a real directory")
        return [self._read(path, validator) for path in sorted(root.glob("*.json"))]

    def write_proposal(self, payload: Mapping[str, Any]) -> Path:
        validate_strategy_proposal(payload)
        target = self.root / "proposals" / (_digest(payload["proposal_id"], "proposal_id") + ".json")
        with _lock(self.root, "proposals"):
            return self._write(payload, target=target, validator=validate_strategy_proposal, id_field="proposal_id", fingerprint_field="proposal_content_fingerprint")

    def write_assessment(self, payload: Mapping[str, Any]) -> Path:
        validate_strategy_evidence_assessment(payload)
        logical = _digest(payload["logical_assessment_id"], "logical_assessment_id")
        target = self.root / "assessments" / (_digest(payload["assessment_id"], "assessment_id") + ".json")
        with _lock(self.root, "assessment-" + logical):
            chain = [item for item in self._collection("assessments", validate_strategy_evidence_assessment) if item["logical_assessment_id"] == payload["logical_assessment_id"]]
            existing_ids = {item["assessment_id"] for item in chain}
            if payload["assessment_id"] not in existing_ids:
                leaf = current_strategy_assessment(chain) if chain else None
                if leaf is None and payload["supersedes_assessment_id"] is not None:
                    raise ContractError("assessment predecessor is not stored")
                if leaf is not None and payload["supersedes_assessment_id"] != leaf["assessment_id"]:
                    raise ContractError("assessment must supersede the current leaf")
                current_strategy_assessment([*chain, payload])
            return self._write(payload, target=target, validator=validate_strategy_evidence_assessment, id_field="assessment_id", fingerprint_field="assessment_content_fingerprint")

    def write_lifecycle_event(self, payload: Mapping[str, Any]) -> Path:
        validate_strategy_lifecycle_event(payload)
        proposal = _digest(payload["proposal_id"], "proposal_id")
        target = self.root / "lifecycle" / (_digest(payload["lifecycle_event_id"], "lifecycle_event_id") + ".json")
        with _lock(self.root, "lifecycle-" + proposal):
            chain = [item for item in self._collection("lifecycle", validate_strategy_lifecycle_event) if item["proposal_id"] == payload["proposal_id"]]
            existing_ids = {item["lifecycle_event_id"] for item in chain}
            if payload["lifecycle_event_id"] not in existing_ids:
                leaf = current_strategy_lifecycle(chain) if chain else None
                if leaf is None and payload["supersedes_lifecycle_event_id"] is not None:
                    raise ContractError("lifecycle predecessor is not stored")
                if leaf is not None and payload["supersedes_lifecycle_event_id"] != leaf["lifecycle_event_id"]:
                    raise ContractError("lifecycle event must supersede the current leaf")
                current_strategy_lifecycle([*chain, payload])
            return self._write(payload, target=target, validator=validate_strategy_lifecycle_event, id_field="lifecycle_event_id", fingerprint_field="lifecycle_content_fingerprint")

    def write_registry_snapshot(self, payload: Mapping[str, Any]) -> Path:
        validate_strategy_registry_snapshot(payload)
        target = self.root / "registry-snapshots" / (_digest(payload["registry_snapshot_id"], "registry_snapshot_id") + ".json")
        with _lock(self.root, "registry-snapshots"):
            return self._write(payload, target=target, validator=validate_strategy_registry_snapshot, id_field="registry_snapshot_id", fingerprint_field="registry_content_fingerprint")

    def read_authority(self) -> tuple[tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
        proposals = tuple(self._collection("proposals", validate_strategy_proposal))
        assessments = tuple(self._collection("assessments", validate_strategy_evidence_assessment))
        lifecycle = tuple(self._collection("lifecycle", validate_strategy_lifecycle_event))
        for proposal_id in {item["proposal_id"] for item in assessments}:
            current_strategy_assessment([item for item in assessments if item["proposal_id"] == proposal_id])
        for proposal_id in {item["proposal_id"] for item in lifecycle}:
            current_strategy_lifecycle([item for item in lifecycle if item["proposal_id"] == proposal_id])
        return proposals, assessments, lifecycle


__all__ = ["PlaybookShadowStore"]
