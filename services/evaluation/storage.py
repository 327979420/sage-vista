"""Append-only, shadow-only storage for immutable M10-A records."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from threading import Lock
from typing import Any, Callable, Iterator, Mapping

from services.contracts.validation import ContractError
from services.market_data.storage import require_shadow_root

from .contracts import (
    RESULT_TYPES,
    current_experiment_run,
    current_result,
    validate_experiment_run,
    validate_result,
)


_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_THREAD_LOCKS: dict[str, Lock] = {}
_THREAD_LOCKS_GUARD = Lock()


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


@contextmanager
def _chain_lock(root: Path, contract_name: str, logical_result_id: str) -> Iterator[None]:
    """Serialize one logical chain across threads and local worker processes."""

    key = f"{root}:{contract_name}:{logical_result_id}"
    with _THREAD_LOCKS_GUARD:
        thread_lock = _THREAD_LOCKS.setdefault(key, Lock())
    lock_root = Path(tempfile.gettempdir()) / "sage-vista-m10-chain-locks"
    lock_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_name = hashlib.sha256(key.encode()).hexdigest() + ".lock"
    with thread_lock:
        descriptor = os.open(
            lock_root / lock_name,
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


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

    def _result_records(
        self, contract_name: str
    ) -> list[tuple[Path, Mapping[str, Any]]]:
        directory = self.root / "results" / contract_name
        if not directory.exists():
            return []
        if directory.is_symlink() or not directory.is_dir():
            raise ContractError("M10 result collection must be a real directory")
        validator = lambda item: validate_result(contract_name, item)
        return [
            (path, self._load_existing(path, validator=validator))
            for path in sorted(directory.glob("*.json"))
        ]

    def write_result(
        self, contract_name: str, payload: Mapping[str, Any]
    ) -> Path:
        if contract_name not in RESULT_TYPES:
            raise ContractError("unknown M10 result contract")
        validate_result(contract_name, payload)
        id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
        target = (
            self.root
            / "results"
            / contract_name
            / (_id_digest(payload.get(id_field), field=id_field) + ".json")
        )
        logical_result_id = str(payload["logical_result_id"])
        _id_digest(logical_result_id, field="logical_result_id")
        with _chain_lock(self.root, contract_name, logical_result_id):
            records = self._result_records(contract_name)
            chain = [
                record
                for _, record in records
                if record["logical_result_id"] == logical_result_id
            ]
            leaf = current_result(contract_name, chain) if chain else None
            existing_ids = [str(record[id_field]) for record in chain]
            if str(payload[id_field]) in existing_ids:
                return self._write(
                    payload,
                    target=target,
                    validator=lambda item: validate_result(contract_name, item),
                    id_field=id_field,
                    fingerprint_field=fingerprint_field,
                )

            if leaf is not None:
                if payload["supersedes_result_id"] != leaf[id_field]:
                    raise ContractError(
                        "M10 revision must supersede the unique current result"
                    )
            elif payload["supersedes_result_id"] is not None:
                raise ContractError("M10 revision predecessor does not exist")

            current_result(contract_name, [*chain, payload])
            return self._write(
                payload,
                target=target,
                validator=lambda item: validate_result(contract_name, item),
                id_field=id_field,
                fingerprint_field=fingerprint_field,
            )

    def write_run_receipt(self, payload: Mapping[str, Any]) -> Path:
        validate_experiment_run(payload)
        target = (
            self.root
            / "runs"
            / (
                _id_digest(
                    payload.get("run_receipt_id"), field="run_receipt_id"
                )
                + ".json"
            )
        )
        run_id = str(payload["run_id"])
        _id_digest(run_id, field="run_id")
        with _chain_lock(self.root, "ExperimentRun", run_id):
            directory = self.root / "runs"
            receipts: list[Mapping[str, Any]] = []
            if directory.exists():
                if directory.is_symlink() or not directory.is_dir():
                    raise ContractError("M10 run collection must be a real directory")
                for path in sorted(directory.glob("*.json")):
                    receipt = self._load_existing(
                        path, validator=validate_experiment_run
                    )
                    if receipt["run_id"] == run_id:
                        receipts.append(receipt)

            existing_ids = {
                str(receipt["run_receipt_id"]) for receipt in receipts
            }
            if str(payload["run_receipt_id"]) in existing_ids:
                return self._write(
                    payload,
                    target=target,
                    validator=validate_experiment_run,
                    id_field="run_receipt_id",
                    fingerprint_field="run_content_fingerprint",
                )

            leaf = current_experiment_run(receipts) if receipts else None
            if leaf is not None:
                if payload["supersedes_run_receipt_id"] != leaf["run_receipt_id"]:
                    raise ContractError(
                        "ExperimentRun revision must supersede the current receipt"
                    )
            elif payload["supersedes_run_receipt_id"] is not None:
                raise ContractError("ExperimentRun receipt predecessor does not exist")

            current_experiment_run([*receipts, payload])
            return self._write(
                payload,
                target=target,
                validator=validate_experiment_run,
                id_field="run_receipt_id",
                fingerprint_field="run_content_fingerprint",
            )


__all__ = ["EvaluationShadowStore"]
