"""Append-only, shadow-only storage for M08 plans and exit states."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping

from services.contracts.validation import ContractError
from services.market_data.storage import require_shadow_root

from .producer import validate_exit_state, validate_trade_plan


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(_plain(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    except (TypeError, ValueError) as exc:
        raise ContractError("M08 shadow artifact must be canonical JSON") from exc


class ExecutionShadowStore:
    def __init__(self, root: str | Path, *, workspace_root: str | Path | None = None):
        self.root = require_shadow_root(root, workspace_root=workspace_root)

    def _write(self, payload: Mapping[str, Any], *, kind: str, stable_id: str, validator: Callable[[Mapping[str, Any]], None], fingerprint_field: str) -> Path:
        validator(payload)
        name = stable_id.rsplit(":", 1)[-1] + ".json"
        target = self.root / kind / str(payload["as_of"]) / name
        content = _bytes(payload)
        if target.exists():
            existing = json.loads(target.read_bytes())
            validator(existing)
            if existing[fingerprint_field] == payload[fingerprint_field]:
                return target
            raise ContractError("immutable M08 artifact exists with different content")
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=name + ".", suffix=".tmp", dir=target.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            staged = json.loads(temporary.read_bytes())
            validator(staged)
            try:
                os.link(temporary, target)
            except FileExistsError:
                existing = json.loads(target.read_bytes())
                validator(existing)
                if existing[fingerprint_field] != payload[fingerprint_field]:
                    raise ContractError("concurrent immutable M08 artifact conflict")
            return target
        finally:
            if temporary.exists():
                temporary.unlink()

    def write_plan(self, plan: Mapping[str, Any]) -> Path:
        return self._write(plan, kind="plans", stable_id=str(plan["plan_id"]), validator=validate_trade_plan, fingerprint_field="plan_content_fingerprint")

    def write_exit_state(self, state: Mapping[str, Any]) -> Path:
        return self._write(state, kind="exit-states", stable_id=str(state["exit_state_id"]), validator=validate_exit_state, fingerprint_field="exit_state_content_fingerprint")


__all__ = ["ExecutionShadowStore"]
