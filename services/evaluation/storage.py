"""Append-only, shadow-only storage for immutable M10-A records."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Callable, Mapping

from services.contracts.validation import ContractError
from services.market_data.storage import require_shadow_root

from .contracts import RESULT_TYPES, validate_experiment_run, validate_result


_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            _plain(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode() + b"\n"
    except (TypeError, ValueError) as exc:
        raise ContractError("M10 record must be canonical JSON") from exc


def _id_digest(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be a stable content-addressed ID")
    digest = value.rsplit(":", 1)[-1]
    if not _DIGEST.fullmatch(digest):
        raise ContractError(f"{field} must end in a lowercase SHA-256 digest")
    return digest


def _reject_json_constant(value: str) -> None:
    raise ContractError(f"stored M10 record contains non-finite JSON: {value}")


class EvaluationShadowStore:
    """Create immutable result and run-receipt files under an approved shadow root."""

    def __init__(
        self, root: str | Path, *, workspace_root: str | Path | None = None
    ) -> None:
        self.root = require_shadow_root(root, workspace_root=workspace_root)

    @staticmethod
    def _load_existing(
        path: Path, *, validator: Callable[[Mapping[str, Any]], None]
    ) -> Mapping[str, Any]:
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            raise ContractError("existing M10 record cannot be inspected") from exc
        if not stat.S_ISREG(mode):
            raise ContractError("existing M10 record must be a regular file")
        try:
            payload = json.loads(
                path.read_bytes(), parse_constant=_reject_json_constant
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError("existing M10 record is not valid JSON") from exc
        if not isinstance(payload, Mapping):
            raise ContractError("existing M10 record must be an object")
        validator(payload)
        return payload

    def _write(
        self,
        payload: Mapping[str, Any],
        *,
        target: Path,
        validator: Callable[[Mapping[str, Any]], None],
        id_field: str,
        fingerprint_field: str,
    ) -> Path:
        validator(payload)
        content = _canonical_bytes(payload)
        if target.exists() or target.is_symlink():
            existing = self._load_existing(target, validator=validator)
            if (
                existing.get(id_field) == payload.get(id_field)
                and existing.get(fingerprint_field) == payload.get(fingerprint_field)
            ):
                return target
            raise ContractError("immutable M10 record already exists with different content")

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
            staged = json.loads(
                temporary.read_bytes(), parse_constant=_reject_json_constant
            )
            if not isinstance(staged, Mapping):
                raise ContractError("staged M10 record must be an object")
            validator(staged)
            try:
                os.link(temporary, target)
            except FileExistsError:
                existing = self._load_existing(target, validator=validator)
                if (
                    existing.get(id_field) != payload.get(id_field)
                    or existing.get(fingerprint_field) != payload.get(fingerprint_field)
                ):
                    raise ContractError("concurrent immutable M10 record conflict")
            directory_fd = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return target
        finally:
            if temporary.exists():
                temporary.unlink()

    def write_result(
        self, contract_name: str, payload: Mapping[str, Any]
    ) -> Path:
        if contract_name not in RESULT_TYPES:
            raise ContractError("unknown M10 result contract")
        id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
        target = (
            self.root
            / "results"
            / contract_name
            / (_id_digest(payload.get(id_field), field=id_field) + ".json")
        )
        return self._write(
            payload,
            target=target,
            validator=lambda item: validate_result(contract_name, item),
            id_field=id_field,
            fingerprint_field=fingerprint_field,
        )

    def write_run_receipt(self, payload: Mapping[str, Any]) -> Path:
        target = (
            self.root
            / "runs"
            / (_id_digest(payload.get("run_id"), field="run_id") + ".json")
        )
        return self._write(
            payload,
            target=target,
            validator=validate_experiment_run,
            id_field="run_id",
            fingerprint_field="run_content_fingerprint",
        )


__all__ = ["EvaluationShadowStore"]
