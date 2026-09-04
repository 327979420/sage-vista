"""Append-only, shadow-only storage for immutable M10-A records."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
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
from services.contracts.market_data import canonical_fingerprint
from services.market_data.storage import require_shadow_root

from .baseline import (
    BASELINE_SOURCE_VERSION,
    validate_internal_baseline_source_version,
)
from .aggregate import (
    READONLY_ENGINE_NAME,
    validate_readonly_receipt_identity,
    validate_readonly_run_conservation,
)
from .contracts import (
    M10_C_SOURCE_VERSION,
    PORTFOLIO_RUN_SCHEMA_VERSION,
    RESEARCH_AGGREGATE_SCHEMA_VERSION,
    RESULT_TYPES,
    current_experiment_run,
    current_result,
    validate_experiment_run,
    validate_m10c_source_version,
    validate_result,
)
from .checkpoint import (
    current_research_run_checkpoint,
    validate_research_run_checkpoint,
)
from .config import (
    config_resume_scope_fingerprint,
    is_m10e_receipt_candidate,
    validate_m10e_receipt_identity,
    validate_research_run_config,
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


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        from types import MappingProxyType

        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
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


def _is_internal_baseline_receipt(payload: Mapping[str, Any]) -> bool:
    from .baseline import BASELINE_ENGINE_NAME

    return payload["engine"]["name"] == BASELINE_ENGINE_NAME


def _declares_internal_baseline_source(payload: Mapping[str, Any]) -> bool:
    """Classify M10-B source records; validation remains centralized."""

    source = payload.get("source_version")
    if not isinstance(source, Mapping):
        return False
    value = source.get("evaluation_contracts")
    return isinstance(value, str) and value.startswith("m10-b-internal-")


def _declares_m10c_source(payload: Mapping[str, Any]) -> bool:
    source = payload.get("source_version")
    return isinstance(source, Mapping) and source.get(
        "evaluation_contracts"
    ) == M10_C_SOURCE_VERSION


def _declares_m10c_source_family(payload: Mapping[str, Any]) -> bool:
    source = payload.get("source_version")
    value = source.get("evaluation_contracts") if isinstance(source, Mapping) else None
    return isinstance(value, str) and value.startswith("m10-c-readonly-")


def _is_m10c_receipt_candidate(payload: Mapping[str, Any]) -> bool:
    engine = payload.get("engine")
    return _declares_m10c_source_family(payload) or (
        isinstance(engine, Mapping) and engine.get("name") == READONLY_ENGINE_NAME
    )


def _is_managed_receipt(payload: Mapping[str, Any]) -> bool:
    return _is_internal_baseline_receipt(payload) or _is_m10c_receipt_candidate(payload)


def _checkpoint_result_refs(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    return sorted(
        [
            {
                "id": str(item["id"]),
                "content_fingerprint": str(item["content_fingerprint"]),
            }
            for item in payload["result_refs"]
        ],
        key=lambda item: (item["id"], item["content_fingerprint"]),
    )


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


@contextmanager
def _inventory_lock(root: Path) -> Iterator[None]:
    """Serialize every inventory-changing write with one atomic snapshot.

    Lock order is always inventory -> run outcome set -> result/run chain.
    Callers holding a narrower lock must never acquire this lock.
    """

    with _chain_lock(root, "EvaluationInventory", "all-records"):
        yield


@dataclass(frozen=True)
class EvaluationInventorySnapshot:
    """One immutable, fully validated point-in-time view of the M10 store."""

    evidence: Mapping[str, Any]
    result_records: tuple[tuple[str, Mapping[str, Any]], ...]
    run_receipts: tuple[Mapping[str, Any], ...]
    checkpoints: tuple[Mapping[str, Any], ...] = ()


class _EvaluationInventoryWriter:
    """Capability object valid only while the store inventory lock is held."""

    def __init__(self, store: "EvaluationShadowStore") -> None:
        self._store = store
        self._active = True

    def _require_active(self) -> None:
        if not self._active:
            raise ContractError("M10 inventory transaction is no longer active")

    def close(self) -> None:
        self._active = False

    def write_result(
        self,
        contract_name: str,
        payload: Mapping[str, Any],
        *,
        source_records: Any = None,
    ) -> Path:
        self._require_active()
        return self._store._write_result_inventory_locked(
            contract_name, payload, source_records=source_records
        )

    def write_run_receipt(self, payload: Mapping[str, Any]) -> Path:
        self._require_active()
        return self._store._write_run_receipt_inventory_locked(payload)

    def write_research_config(self, payload: Mapping[str, Any]) -> Path:
        self._require_active()
        return self._store._write_research_config_inventory_locked(payload)

    def result_references_for_run(self, run_id: str) -> list[dict[str, str]]:
        self._require_active()
        _id_digest(run_id, field="run_id")
        return self._store._result_references_for_run_unlocked(run_id)

    def write_checkpoint(self, payload: Mapping[str, Any]) -> Path:
        self._require_active()
        return self._store._write_checkpoint_inventory_locked(payload)


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

    def _run_receipts(self, run_id: str) -> list[Mapping[str, Any]]:
        directory = self.root / "runs"
        if not directory.exists():
            return []
        if directory.is_symlink() or not directory.is_dir():
            raise ContractError("M10 run collection must be a real directory")
        receipts: list[Mapping[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            receipt = self._load_existing(path, validator=validate_experiment_run)
            if receipt["run_id"] == run_id:
                receipts.append(receipt)
        return receipts

    def _checkpoints(self, run_id: str) -> list[Mapping[str, Any]]:
        directory = self.root / "checkpoints"
        if not directory.exists():
            return []
        if directory.is_symlink() or not directory.is_dir():
            raise ContractError("M10 checkpoint collection must be a real directory")
        checkpoints: list[Mapping[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            checkpoint = self._load_existing(
                path, validator=validate_research_run_checkpoint
            )
            if checkpoint["run_id"] == run_id:
                checkpoints.append(checkpoint)
        return checkpoints

    def _research_config(self, config_id: str) -> Mapping[str, Any]:
        digest = _id_digest(config_id, field="config_id")
        path = self.root / "configs" / (digest + ".json")
        if not path.exists() or path.is_symlink():
            raise ContractError("M10-E persisted ResearchRunConfig is unavailable")
        config = self._load_existing(path, validator=validate_research_run_config)
        if config["config_id"] != config_id:
            raise ContractError("M10-E config filename does not match its identity")
        return config

    def _result_records_for_run(
        self, run_id: str
    ) -> list[tuple[str, Mapping[str, Any]]]:
        records: list[tuple[str, Mapping[str, Any]]] = []
        for contract_name in RESULT_TYPES:
            records.extend(
                (contract_name, record)
                for _, record in self._result_records(contract_name)
                if record["run_id"] == run_id
            )
        return records

    def _results_for_run(self, run_id: str) -> list[Mapping[str, Any]]:
        return [record for _, record in self._result_records_for_run(run_id)]

    @staticmethod
    def _strict_directory_entries(directory: Path) -> list[Path]:
        if directory.is_symlink() or not directory.is_dir():
            raise ContractError("M10 inventory collection must be a real directory")
        try:
            return sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise ContractError("M10 inventory collection cannot be enumerated") from exc

    @classmethod
    def _inventory_record(
        cls,
        path: Path,
        *,
        validator: Callable[[Mapping[str, Any]], None],
    ) -> tuple[Mapping[str, Any], bytes]:
        if path.is_symlink() or path.suffix != ".json":
            raise ContractError("M10 inventory contains an unsupported entry")
        try:
            mode = path.lstat().st_mode
            raw = path.read_bytes()
        except OSError as exc:
            raise ContractError("M10 inventory record cannot be read") from exc
        if not stat.S_ISREG(mode):
            raise ContractError("M10 inventory record must be a regular JSON file")
        try:
            payload = json.loads(raw, parse_constant=_reject_json_constant)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError("M10 inventory record is not valid JSON") from exc
        if not isinstance(payload, Mapping):
            raise ContractError("M10 inventory record must be an object")
        validator(payload)
        if raw != _canonical_bytes(payload):
            raise ContractError("M10 inventory record is not canonical JSON")
        return payload, raw

    def _capture_inventory_unlocked(self) -> EvaluationInventorySnapshot:
        """Read and validate every record while the caller owns inventory lock."""

        if self.root.exists():
            if self.root.is_symlink() or not self.root.is_dir():
                raise ContractError("M10 inventory root must be a real directory")
            unknown_root = {
                item.name
                for item in self._strict_directory_entries(self.root)
                if item.name not in {"results", "runs", "checkpoints", "configs"}
            }
            if unknown_root:
                raise ContractError("M10 inventory contains unknown top-level entries")

        entries: list[dict[str, Any]] = []
        result_records: list[tuple[str, Mapping[str, Any]]] = []
        run_receipts: list[Mapping[str, Any]] = []
        checkpoints: list[Mapping[str, Any]] = []
        seen_stable_ids: set[str] = set()

        configs_root = self.root / "configs"
        if configs_root.exists():
            for path in self._strict_directory_entries(configs_root):
                payload, _ = self._inventory_record(
                    path, validator=validate_research_run_config
                )
                if path.stem != _id_digest(payload["config_id"], field="config_id"):
                    raise ContractError("M10-E config filename does not match its ID")

        results_root = self.root / "results"
        if results_root.exists():
            known_contracts = set(RESULT_TYPES)
            for contract_dir in self._strict_directory_entries(results_root):
                if contract_dir.name not in known_contracts:
                    raise ContractError("M10 inventory contains an unknown result contract")
                contract_name = contract_dir.name
                id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
                for path in self._strict_directory_entries(contract_dir):
                    payload, raw = self._inventory_record(
                        path,
                        validator=lambda item, name=contract_name: validate_result(name, item),
                    )
                    stable_id = str(payload[id_field])
                    if path.stem != _id_digest(stable_id, field=id_field):
                        raise ContractError("M10 result filename does not match its stable ID")
                    if stable_id in seen_stable_ids:
                        raise ContractError("M10 inventory contains a duplicate stable ID")
                    seen_stable_ids.add(stable_id)
                    result_records.append((contract_name, _freeze(_plain(payload))))
                    entries.append({
                        "relative_path": path.relative_to(self.root).as_posix(),
                        "record_kind": "result",
                        "contract_name": contract_name,
                        "schema_version": str(payload["schema_version"]),
                        "stable_id": stable_id,
                        "logical_id": str(payload["logical_result_id"]),
                        "supersedes_id": payload["supersedes_result_id"],
                        "run_id": str(payload["run_id"]),
                        "content_fingerprint": str(payload[fingerprint_field]),
                        "file_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
                        "byte_count": len(raw),
                        "payload": _plain(payload),
                    })

        runs_root = self.root / "runs"
        if runs_root.exists():
            for path in self._strict_directory_entries(runs_root):
                payload, raw = self._inventory_record(
                    path, validator=validate_experiment_run
                )
                stable_id = str(payload["run_receipt_id"])
                if path.stem != _id_digest(stable_id, field="run_receipt_id"):
                    raise ContractError("M10 run filename does not match its receipt ID")
                if stable_id in seen_stable_ids:
                    raise ContractError("M10 inventory contains a duplicate stable ID")
                seen_stable_ids.add(stable_id)
                run_receipts.append(_freeze(_plain(payload)))
                entries.append({
                    "relative_path": path.relative_to(self.root).as_posix(),
                    "record_kind": "run_receipt",
                    "contract_name": "ExperimentRun",
                    "schema_version": str(payload["schema_version"]),
                    "stable_id": stable_id,
                    "logical_id": str(payload["run_id"]),
                    "supersedes_id": payload["supersedes_run_receipt_id"],
                    "run_id": str(payload["run_id"]),
                    "content_fingerprint": str(payload["run_content_fingerprint"]),
                    "file_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
                    "byte_count": len(raw),
                    "payload": _plain(payload),
                })

        grouped_results: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
        for contract_name, payload in result_records:
            grouped_results.setdefault(
                (contract_name, str(payload["logical_result_id"])), []
            ).append(payload)
        for (contract_name, _), chain in grouped_results.items():
            current_result(contract_name, chain)

        grouped_receipts: dict[str, list[Mapping[str, Any]]] = {}
        for receipt in run_receipts:
            grouped_receipts.setdefault(str(receipt["run_id"]), []).append(receipt)
        for run_id, receipts in grouped_receipts.items():
            leaf = current_experiment_run(receipts)
            stored_records = [
                item for item in result_records if str(item[1]["run_id"]) == run_id
            ]
            stored_results = [item for _, item in stored_records]
            self._validate_internal_run_sources(receipts, stored_results)
            self._validate_m10c_run_sources(receipts, stored_records)
            if _is_managed_receipt(leaf) and leaf["status"] == "completed":
                actual = self._result_references_for_run_records(stored_records)
                expected = sorted(
                    _plain(leaf["result_refs"]),
                    key=lambda item: (item["id"], item["content_fingerprint"]),
                )
                if actual != expected:
                    raise ContractError(
                        "completed ExperimentRun does not match inventory results"
                    )

        checkpoints_root = self.root / "checkpoints"
        if checkpoints_root.exists():
            grouped_checkpoints: dict[str, list[Mapping[str, Any]]] = {}
            for path in self._strict_directory_entries(checkpoints_root):
                payload, _ = self._inventory_record(
                    path, validator=validate_research_run_checkpoint
                )
                if path.stem != _id_digest(
                    payload["checkpoint_id"], field="checkpoint_id"
                ):
                    raise ContractError("M10 checkpoint filename does not match its ID")
                checkpoints.append(_freeze(_plain(payload)))
                grouped_checkpoints.setdefault(str(payload["run_id"]), []).append(payload)
            for chain in grouped_checkpoints.values():
                current_research_run_checkpoint(chain)
            for run_id, receipts in grouped_receipts.items():
                if not any(is_m10e_receipt_candidate(item) for item in receipts):
                    continue
                if any(not is_m10e_receipt_candidate(item) for item in receipts):
                    raise ContractError("M10-E inventory run crosses producers")
                for receipt in receipts:
                    validate_m10e_receipt_identity(receipt)
                config = self._research_config(
                    str(receipts[0]["config_ref"]["config_id"])
                )
                if any(
                    item["config_ref"]["config_id"] != config["config_id"]
                    or item["config_ref"]["content_fingerprint"]
                    != config["config_content_fingerprint"]
                    for item in receipts
                ):
                    raise ContractError("M10-E receipt chain differs from its saved config")
                leaf = current_experiment_run(receipts)
                if leaf["status"] != "pending":
                    self._validate_m10e_terminal_evidence(
                        leaf,
                        receipts,
                        grouped_checkpoints.get(run_id, []),
                        allow_existing_terminal=True,
                    )

        ordered_entries = sorted(
            entries,
            key=lambda item: (
                item["record_kind"], item["contract_name"], item["stable_id"],
                item["relative_path"],
            ),
        )
        inventory_content = {"entries": ordered_entries}
        fingerprint = canonical_fingerprint(inventory_content)
        evidence = {
            "source_inventory_id": "source-inventory:" + fingerprint,
            "source_inventory_fingerprint": fingerprint,
            "entries": ordered_entries,
        }
        return EvaluationInventorySnapshot(
            evidence=_freeze(evidence),
            result_records=tuple(result_records),
            run_receipts=tuple(run_receipts),
            checkpoints=tuple(checkpoints),
        )

    def capture_inventory(self) -> EvaluationInventorySnapshot:
        """Return one atomic, validated inventory without persisting a second index."""

        with _inventory_lock(self.root):
            return self._capture_inventory_unlocked()

    @contextmanager
    def inventory_write_transaction(self) -> Iterator[_EvaluationInventoryWriter]:
        """Serialize a complete logical batch against inventory snapshots.

        All callers acquire the store-wide inventory lock first.  The existing
        run outcome-set and result/receipt chain locks remain narrower and are
        acquired only by the transaction writer, preserving one lock order.
        """

        with _inventory_lock(self.root):
            writer = _EvaluationInventoryWriter(self)
            try:
                yield writer
            finally:
                writer.close()

    @staticmethod
    def _validate_internal_run_sources(
        receipts: list[Mapping[str, Any]],
        results: list[Mapping[str, Any]],
    ) -> None:
        """Reject any mixed source set for a persisted internal-baseline run."""

        internal = [item for item in receipts if _is_internal_baseline_receipt(item)]
        internal_results = [
            item for item in results if _declares_internal_baseline_source(item)
        ]
        if not internal and not internal_results:
            return
        if len(internal) != len(receipts):
            raise ContractError("M10-B run receipt chain crosses producers")
        expected = {"evaluation_contracts": BASELINE_SOURCE_VERSION}
        for item in [*internal, *results]:
            validate_internal_baseline_source_version(item)
            if _plain(item["source_version"]) != expected:
                raise ContractError("M10-B persisted run mixes source versions")

    @staticmethod
    def _validate_m10c_run_sources(
        receipts: list[Mapping[str, Any]],
        results: list[tuple[str, Mapping[str, Any]]],
    ) -> None:
        m10c_receipts = [item for item in receipts if _is_m10c_receipt_candidate(item)]
        m10c_results = [item for item in results if _declares_m10c_source_family(item[1])]
        if not m10c_receipts and not m10c_results:
            return
        if len(m10c_receipts) != len(receipts) or len(m10c_results) != len(results):
            raise ContractError("M10-C persisted run crosses producers")
        for receipt in receipts:
            validate_readonly_receipt_identity(receipt)
        for contract_name, result in results:
            validate_m10c_source_version(result)
            expected_version = (
                PORTFOLIO_RUN_SCHEMA_VERSION
                if contract_name == "PortfolioRun"
                else RESEARCH_AGGREGATE_SCHEMA_VERSION
                if contract_name == "ResearchAggregate"
                else None
            )
            if result.get("schema_version") != expected_version:
                raise ContractError("M10-C storage accepts only new 2.1 result contracts")

    def write_result(
        self,
        contract_name: str,
        payload: Mapping[str, Any],
        *,
        source_records: Any = None,
    ) -> Path:
        with _inventory_lock(self.root):
            return self._write_result_inventory_locked(
                contract_name, payload, source_records=source_records
            )

    def _write_result_inventory_locked(
        self,
        contract_name: str,
        payload: Mapping[str, Any],
        *,
        source_records: Any = None,
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
        run_id = str(payload["run_id"])
        _id_digest(run_id, field="run_id")
        with _chain_lock(self.root, "ExperimentRunOutcomeSet", run_id):
            receipts = self._run_receipts(run_id)
            stored_records = self._result_records_for_run(run_id)
            stored_results = [item for _, item in stored_records]
            self._validate_internal_run_sources(
                receipts, [*stored_results, payload]
            )
            self._validate_m10c_run_sources(
                receipts, [*stored_records, (contract_name, payload)]
            )
            run_leaf = current_experiment_run(receipts) if receipts else None
            if _declares_m10c_source(payload) and (
                run_leaf is None
                or not _declares_m10c_source(run_leaf)
                or run_leaf["status"] != "pending"
            ):
                if target.exists() or target.is_symlink():
                    return self._write(
                        payload,
                        target=target,
                        validator=lambda item: validate_result(contract_name, item),
                        id_field=id_field,
                        fingerprint_field=fingerprint_field,
                )
                raise ContractError("M10-C result requires its persisted pending receipt")
            if _declares_m10c_source(payload):
                if source_records is None:
                    raise ContractError(
                        "M10-C public storage requires complete source outcomes"
                    )
                validate_readonly_run_conservation(
                    run_leaf, contract_name, payload, source_records
                )
            if (
                run_leaf is not None
                and _is_managed_receipt(run_leaf)
                and run_leaf["status"] != "pending"
            ):
                if target.exists() or target.is_symlink():
                    return self._write(
                        payload,
                        target=target,
                        validator=lambda item: validate_result(contract_name, item),
                        id_field=id_field,
                        fingerprint_field=fingerprint_field,
                    )
                raise ContractError("terminal ExperimentRun cannot accept new results")

            with _chain_lock(self.root, contract_name, logical_result_id):
                records = self._result_records(contract_name)
                chain = [
                    record
                    for _, record in records
                    if record["logical_result_id"] == logical_result_id
                ]
                self._validate_internal_run_sources([], [*chain, payload])
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

    @staticmethod
    def _result_references_for_run_records(
        records: list[tuple[str, Mapping[str, Any]]],
    ) -> list[dict[str, str]]:
        references: list[dict[str, str]] = []
        for contract_name, record in records:
            id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
            references.append({
                "id": str(record[id_field]),
                "content_fingerprint": str(record[fingerprint_field]),
            })
        return sorted(
            references,
            key=lambda item: (item["id"], item["content_fingerprint"]),
        )

    def _result_references_for_run_unlocked(
        self, run_id: str
    ) -> list[dict[str, str]]:
        return self._result_references_for_run_records(
            self._result_records_for_run(run_id)
        )

    def _all_result_references_unlocked(self) -> list[dict[str, str]]:
        records: list[tuple[str, Mapping[str, Any]]] = []
        for contract_name in RESULT_TYPES:
            records.extend(
                (contract_name, record)
                for _, record in self._result_records(contract_name)
            )
        return self._result_references_for_run_records(records)

    def _validate_m10e_checkpoint_conservation(
        self,
        checkpoint: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> None:
        expected_units = [item["work_unit_id"] for item in config["work_units"]]
        if (
            checkpoint["config_id"] != config["config_id"]
            or checkpoint["config_content_fingerprint"]
            != config["config_content_fingerprint"]
            or checkpoint["config_scope_fingerprint"]
            != config_resume_scope_fingerprint(config)
            or checkpoint["result_family"] != config["output_contract"]["name"]
            or list(checkpoint["expected_work_units"]) != expected_units
        ):
            raise ContractError("M10-E checkpoint differs from its saved config")
        expected_contract = str(config["output_contract"]["name"])
        expected_schema = str(config["output_contract"]["schema_version"])
        expected_source = {"evaluation_contracts": config["producer_source_version"]}
        expected_per_unit = int(config["expected_results"]["per_work_unit_count"])
        stored_by_ref: dict[tuple[str, str], tuple[str, Mapping[str, Any]]] = {}
        for contract_name in RESULT_TYPES:
            id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
            for _, result in self._result_records(contract_name):
                stored_by_ref[(str(result[id_field]), str(result[fingerprint_field]))] = (
                    contract_name,
                    result,
                )
        refs_by_unit: dict[str, list[Mapping[str, Any]]] = {
            unit: [] for unit in expected_units
        }
        for ref in checkpoint["result_refs"]:
            refs_by_unit[str(ref["work_unit_id"])].append(ref)
        completed = set(checkpoint["completed_work_units"])
        units = {str(item["work_unit_id"]): item for item in config["work_units"]}
        for unit_id in expected_units:
            refs = refs_by_unit[unit_id]
            expected_count = expected_per_unit if unit_id in completed else 0
            if len(refs) != expected_count:
                raise ContractError("M10-E checkpoint result count violates its config")
            unit_results: list[Mapping[str, Any]] = []
            for ref in refs:
                key = (str(ref["id"]), str(ref["content_fingerprint"]))
                stored = stored_by_ref.get(key)
                if stored is None:
                    raise ContractError("checkpoint references a result not present in storage")
                contract_name, result = stored
                unit_results.append(result)
                if (
                    contract_name != expected_contract
                    or result["schema_version"] != expected_schema
                    or _plain(result["source_version"]) != expected_source
                    or result["path_status"] != config["path_status"]
                    or result["result_role"] != config["result_role"]
                    or result["partition_role"] != config["partition_role"]
                ):
                    raise ContractError("M10-E checkpoint contains an out-of-scope result")
                child_receipts = self._run_receipts(str(result["run_id"]))
                if not child_receipts:
                    raise ContractError("M10-E result has no persisted producer run")
                child_leaf = current_experiment_run(child_receipts)
                child_roots = [
                    item for item in child_receipts
                    if item["status"] == "pending"
                    and item["supersedes_run_receipt_id"] is None
                ]
                if len(child_roots) != 1 or child_leaf["status"] != "completed":
                    raise ContractError("M10-E result producer run is not complete")
                child_pending = child_roots[0]
                if (
                    _plain(child_pending["input_refs"])
                    != _plain(units[unit_id]["input_refs"])
                    or _plain(child_pending["policy_refs"])
                    != _plain(config["policy_refs"])
                    or child_pending["code_commit"] != config["code_commit"]
                    or _plain(child_pending["source_version"]) != expected_source
                ):
                    raise ContractError("M10-E result producer evidence differs from its work unit")
                child_refs = {
                    (item["id"], item["content_fingerprint"])
                    for item in child_leaf["result_refs"]
                }
                if key not in child_refs:
                    raise ContractError("M10-E result is absent from its producer receipt")
            if len({str(item["logical_result_id"]) for item in unit_results}) != len(unit_results):
                raise ContractError("M10-E work unit contains duplicate logical results")
            if expected_contract == "ForwardOutcome" and unit_id in completed:
                actual_windows = sorted(int(item["window_sessions"]) for item in unit_results)
                if actual_windows != list(config["expected_results"]["forward_windows"]):
                    raise ContractError("M10-E Forward work unit does not contain every configured window")

    def _validate_m10e_terminal_evidence(
        self,
        payload: Mapping[str, Any],
        receipts: list[Mapping[str, Any]],
        checkpoints: list[Mapping[str, Any]],
        *,
        allow_existing_terminal: bool,
    ) -> None:
        """Bind an M10-E terminal receipt to stored progress and child results."""

        validate_m10e_receipt_identity(payload)
        if any(not is_m10e_receipt_candidate(item) for item in receipts):
            raise ContractError("M10-E receipt chain crosses producers")
        for receipt in receipts:
            validate_m10e_receipt_identity(receipt)
        roots = [
            item for item in receipts
            if item["status"] == "pending"
            and item["supersedes_run_receipt_id"] is None
        ]
        if len(roots) != 1:
            raise ContractError("M10-E terminal receipt requires one persisted pending root")
        pending = roots[0]
        leaf = current_experiment_run(receipts)
        existing = any(
            item["run_receipt_id"] == payload["run_receipt_id"]
            for item in receipts
        )
        if existing:
            if not allow_existing_terminal or leaf["run_receipt_id"] != payload["run_receipt_id"]:
                raise ContractError("M10-E terminal receipt conflicts with the stored chain")
        elif leaf["status"] != "pending":
            raise ContractError("M10-E terminal receipt must supersede the pending leaf")
        if payload["supersedes_run_receipt_id"] != pending["run_receipt_id"]:
            raise ContractError("M10-E terminal receipt must directly supersede its pending root")
        if not checkpoints:
            raise ContractError("M10-E terminal receipt requires a persisted checkpoint")
        checkpoint = current_research_run_checkpoint(checkpoints)
        config = self._research_config(str(pending["config_ref"]["config_id"]))
        self._validate_m10e_checkpoint_conservation(checkpoint, config)
        expected_status = payload["status"]
        if checkpoint["status"] != expected_status:
            raise ContractError("M10-E terminal receipt status differs from its checkpoint")
        if (
            checkpoint["run_id"] != payload["run_id"]
            or checkpoint["config_id"] != pending["config_ref"]["config_id"]
            or checkpoint["config_content_fingerprint"]
            != pending["config_ref"]["content_fingerprint"]
            or checkpoint["input_set_fingerprint"] != pending["input_set_fingerprint"]
            or checkpoint["path_status"] != pending["path_status"]
            or checkpoint["result_role"] != pending["result_role"]
            or checkpoint["partition_role"] != pending["partition_role"]
            or checkpoint["code_commit"] != pending["code_commit"]
        ):
            raise ContractError("M10-E checkpoint differs from its pending receipt")
        checkpoint_refs = _checkpoint_result_refs(checkpoint)
        receipt_refs = sorted(
            _plain(payload["result_refs"]),
            key=lambda item: (item["id"], item["content_fingerprint"]),
        )
        if checkpoint_refs != receipt_refs:
            raise ContractError("M10-E terminal receipt does not conserve checkpoint results")
        saved_refs = {
            (item["id"], item["content_fingerprint"])
            for item in self._all_result_references_unlocked()
        }
        if any(
            (item["id"], item["content_fingerprint"]) not in saved_refs
            for item in receipt_refs
        ):
            raise ContractError("M10-E terminal receipt references an unstored result")

    def result_references_for_run(
        self, run_id: str
    ) -> list[dict[str, str]]:
        """Return one atomic result-reference view for a run."""

        _id_digest(run_id, field="run_id")
        with _inventory_lock(self.root):
            return self._result_references_for_run_unlocked(run_id)

    def write_run_receipt(self, payload: Mapping[str, Any]) -> Path:
        with _inventory_lock(self.root):
            return self._write_run_receipt_inventory_locked(payload)

    def write_research_config(self, payload: Mapping[str, Any]) -> Path:
        with _inventory_lock(self.root):
            return self._write_research_config_inventory_locked(payload)

    def _write_research_config_inventory_locked(
        self, payload: Mapping[str, Any]
    ) -> Path:
        validate_research_run_config(payload)
        if Path(payload["storage"]["root_path"]).resolve() != self.root.resolve():
            raise ContractError("ResearchRunConfig storage root differs from this store")
        target = self.root / "configs" / (
            _id_digest(payload["config_id"], field="config_id") + ".json"
        )
        with _chain_lock(self.root, "ResearchRunConfig", str(payload["config_id"])):
            return self._write(
                payload,
                target=target,
                validator=validate_research_run_config,
                id_field="config_id",
                fingerprint_field="config_content_fingerprint",
            )

    def write_checkpoint(self, payload: Mapping[str, Any]) -> Path:
        with _inventory_lock(self.root):
            return self._write_checkpoint_inventory_locked(payload)

    def _write_checkpoint_inventory_locked(
        self, payload: Mapping[str, Any]
    ) -> Path:
        validate_research_run_checkpoint(payload)
        run_id = str(payload["run_id"])
        _id_digest(run_id, field="run_id")
        target = self.root / "checkpoints" / (
            _id_digest(payload["checkpoint_id"], field="checkpoint_id") + ".json"
        )
        with _chain_lock(self.root, "ResearchRunCheckpoint", run_id):
            receipts = self._run_receipts(run_id)
            if not receipts:
                raise ContractError("M10-E checkpoint requires its persisted pending receipt")
            if any(not is_m10e_receipt_candidate(item) for item in receipts):
                raise ContractError("M10-E checkpoint run crosses producers")
            for receipt in receipts:
                validate_m10e_receipt_identity(receipt)
            run_leaf = current_experiment_run(receipts)
            pending_roots = [
                item for item in receipts
                if item["status"] == "pending"
                and item["supersedes_run_receipt_id"] is None
            ]
            if len(pending_roots) != 1 or run_leaf["status"] != "pending":
                raise ContractError("M10-E checkpoint requires the unique pending run leaf")
            pending = pending_roots[0]
            config = self._research_config(str(payload["config_id"]))
            if (
                payload["config_id"] != pending["config_ref"]["config_id"]
                or payload["config_content_fingerprint"]
                != pending["config_ref"]["content_fingerprint"]
                or payload["input_set_fingerprint"] != pending["input_set_fingerprint"]
                or payload["path_status"] != pending["path_status"]
                or payload["result_role"] != pending["result_role"]
                or payload["partition_role"] != pending["partition_role"]
                or payload["code_commit"] != pending["code_commit"]
            ):
                raise ContractError("M10-E checkpoint differs from its pending receipt")
            chain = self._checkpoints(run_id)
            existing = {str(item["checkpoint_id"]): item for item in chain}
            checkpoint_id = str(payload["checkpoint_id"])
            if checkpoint_id in existing:
                return self._write(
                    payload,
                    target=target,
                    validator=validate_research_run_checkpoint,
                    id_field="checkpoint_id",
                    fingerprint_field="checkpoint_content_fingerprint",
                )
            leaf = current_research_run_checkpoint(chain) if chain else None
            if leaf is None:
                if payload["supersedes_checkpoint_id"] is not None:
                    raise ContractError("checkpoint predecessor does not exist")
            elif payload["supersedes_checkpoint_id"] != leaf["checkpoint_id"]:
                raise ContractError("checkpoint must supersede the unique current leaf")
            if leaf is not None and leaf["status"] == "completed":
                raise ContractError("completed research run cannot accept a new checkpoint")
            current_research_run_checkpoint([*chain, payload])
            self._validate_m10e_checkpoint_conservation(payload, config)
            return self._write(
                payload,
                target=target,
                validator=validate_research_run_checkpoint,
                id_field="checkpoint_id",
                fingerprint_field="checkpoint_content_fingerprint",
            )

    def _write_run_receipt_inventory_locked(
        self, payload: Mapping[str, Any]
    ) -> Path:
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
        with _chain_lock(self.root, "ExperimentRunOutcomeSet", run_id):
            receipts = self._run_receipts(run_id)
            stored_records = self._result_records_for_run(run_id)
            stored_results = [item for _, item in stored_records]
            if is_m10e_receipt_candidate(payload):
                validate_m10e_receipt_identity(payload)
                config = self._research_config(str(payload["config_ref"]["config_id"]))
                if (
                    payload["config_ref"]["content_fingerprint"]
                    != config["config_content_fingerprint"]
                    or payload["code_commit"] != config["code_commit"]
                    or _plain(payload["policy_refs"]) != _plain(config["policy_refs"])
                    or _plain(payload["input_refs"])
                    != sorted(
                        [
                            _plain(ref)
                            for unit in config["work_units"]
                            for ref in unit["input_refs"]
                        ],
                        key=lambda item: (item["id"], item["content_fingerprint"]),
                    )
                ):
                    raise ContractError("M10-E receipt differs from its saved config")
                if any(not is_m10e_receipt_candidate(item) for item in receipts):
                    raise ContractError("M10-E receipt chain crosses producers")
                if payload["status"] != "pending":
                    self._validate_m10e_terminal_evidence(
                        payload,
                        receipts,
                        self._checkpoints(run_id),
                        allow_existing_terminal=True,
                    )
            if _is_internal_baseline_receipt(payload):
                validate_internal_baseline_source_version(payload)
                self._validate_internal_run_sources(
                    [*receipts, payload], stored_results
                )
            if _is_m10c_receipt_candidate(payload):
                validate_readonly_receipt_identity(payload)
                self._validate_m10c_run_sources(
                    [*receipts, payload], stored_records
                )
            if (
                _is_managed_receipt(payload)
                and payload["status"] == "completed"
            ):
                expected = sorted(
                    _plain(payload["result_refs"]),
                    key=lambda item: (item["id"], item["content_fingerprint"]),
                )
                if self._result_references_for_run_unlocked(run_id) != expected:
                    raise ContractError(
                        "completed ExperimentRun does not match stored results"
                    )
                if _is_m10c_receipt_candidate(payload):
                    pending_roots = [
                        item for item in receipts
                        if item["status"] == "pending"
                        and item["supersedes_run_receipt_id"] is None
                    ]
                    if len(pending_roots) != 1 or len(stored_records) != 1:
                        raise ContractError(
                            "completed M10-C run requires one pending root and one result"
                        )
                    stored_contract, stored_result = stored_records[0]
                    if _plain(stored_result["source_version"]) != {
                        "evaluation_contracts": M10_C_SOURCE_VERSION,
                    }:
                        raise ContractError(
                            "completed M10-C run contains an unmanaged result"
                        )

            with _chain_lock(self.root, "ExperimentRun", run_id):
                existing_ids = {
                    str(receipt["run_receipt_id"]) for receipt in receipts
                }
                leaf = current_experiment_run(receipts) if receipts else None
                if str(payload["run_receipt_id"]) in existing_ids:
                    if (
                        _is_managed_receipt(payload)
                        and payload["status"] == "completed"
                    ):
                        by_id = {
                            str(receipt["run_receipt_id"]): receipt
                            for receipt in receipts
                        }
                        prior_id = payload["supersedes_run_receipt_id"]
                        if (
                            leaf is None
                            or leaf["run_receipt_id"] != payload["run_receipt_id"]
                            or prior_id is None
                            or prior_id not in by_id
                            or by_id[prior_id]["status"] != "pending"
                        ):
                            raise ContractError(
                                "completed internal baseline run requires its persisted pending root"
                            )
                    return self._write(
                        payload,
                        target=target,
                        validator=validate_experiment_run,
                        id_field="run_receipt_id",
                        fingerprint_field="run_content_fingerprint",
                    )

                if (
                    _is_managed_receipt(payload)
                    and payload["status"] == "completed"
                    and (
                        leaf is None
                        or leaf["status"] != "pending"
                        or payload["supersedes_run_receipt_id"]
                        != leaf["run_receipt_id"]
                    )
                ):
                    raise ContractError(
                        "completed internal baseline run must supersede the persisted pending leaf"
                    )
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


__all__ = ["EvaluationInventorySnapshot", "EvaluationShadowStore"]
