"""Append-only, shadow-only storage for M07 ranking snapshots."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from services.contracts.validation import ContractError
from services.market_data.storage import require_shadow_root

from .producer import validate_ranking_snapshot


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            _plain(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode() + b"\n"
    except (TypeError, ValueError) as exc:
        raise ContractError("M07 snapshot must be canonical JSON") from exc


class RankingSnapshotStore:
    """Write each content-addressed snapshot once; never replace existing bytes."""

    def __init__(self, root: str | Path, *, workspace_root: str | Path | None = None):
        self.root = require_shadow_root(root, workspace_root=workspace_root)

    def path_for(self, snapshot: Mapping[str, Any]) -> Path:
        validate_ranking_snapshot(snapshot)
        name = str(snapshot["ranking_snapshot_id"]).removeprefix("ranking:sha256:") + ".json"
        return self.root / str(snapshot["as_of"]) / str(snapshot["ranking_role"]) / name

    def write(self, snapshot: Mapping[str, Any]) -> Path:
        """Stage validated bytes and atomically link only when the target is absent."""

        target = self.path_for(snapshot)
        content = _canonical_bytes(snapshot)
        if target.exists():
            existing = json.loads(target.read_bytes())
            validate_ranking_snapshot(existing)
            if existing["ranking_content_fingerprint"] == snapshot["ranking_content_fingerprint"]:
                return target
            raise ContractError("immutable ranking snapshot already exists with different bytes")
        if snapshot["ranking_role"] == "authoritative" and target.parent.exists():
            for existing_path in target.parent.glob("*.json"):
                existing = json.loads(existing_path.read_bytes())
                validate_ranking_snapshot(existing)
                if existing["ranking_snapshot_id"] != snapshot["ranking_snapshot_id"]:
                    raise ContractError("an authoritative ranking already exists for this date and scope")
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=target.name + ".", suffix=".tmp", dir=target.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            staged = json.loads(temporary.read_bytes())
            if not isinstance(staged, Mapping):
                raise ContractError("staged M07 snapshot must be an object")
            validate_ranking_snapshot(staged)
            try:
                os.link(temporary, target)
            except FileExistsError:
                existing = json.loads(target.read_bytes())
                validate_ranking_snapshot(existing)
                if existing["ranking_content_fingerprint"] != snapshot["ranking_content_fingerprint"]:
                    raise ContractError("concurrent immutable ranking snapshot conflict")
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return target
        finally:
            if temporary.exists():
                temporary.unlink()


__all__ = ["RankingSnapshotStore"]
