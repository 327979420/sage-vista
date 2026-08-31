"""Build a non-production M01 shadow ReleaseManifest."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import AbstractSet, Iterable, Mapping

from .adapters import AdaptedArtifact, adapt_legacy_bytes
from .validation import ContractError, FROZEN_RELEASE_NAMES, validate_contract


ROLE_BY_NAME: dict[str, tuple[str, ...]] = {
    "update-status.json": ("web", "discord", "audit"),
    "unified-v2-latest.json": ("web", "discord", "audit"),
    "daily-factor-snapshot.json": ("web", "audit"),
    "favorite-pattern.json": ("web", "audit"),
    "market-etf-watch.json": ("web", "audit"),
    "industry-radar.json": ("web", "audit"),
    "opportunity-ledger.json": ("audit",),
    "opportunity-ledger-latest.json": ("web", "audit"),
    "signal-history.json": ("audit",),
    "signal-history-summary.json": ("web", "audit"),
    "factor-registry.json": ("web", "audit"),
    "rare-opportunity-radar.json": ("web", "discord", "audit"),
    "decision-summary.json": ("web", "audit"),
    "resonance-tracker.json": ("audit",),
    "unified-v2-rankings.json": ("audit",),
}

if frozenset(ROLE_BY_NAME) != FROZEN_RELEASE_NAMES:
    raise RuntimeError("manifest role registry must match the frozen release membership")


def _canonical(value: Mapping[str, object]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as exc:
        raise ContractError("manifest evidence must be canonical JSON") from exc


def _entry_from_bytes(
    *,
    name: str,
    raw: bytes,
    adapted: AdaptedArtifact,
    release_date: str,
) -> dict[str, object]:
    """Build the only accepted metadata view of one exact file byte snapshot."""

    roles = ROLE_BY_NAME.get(name)
    if roles is None:
        raise ContractError(f"{name} is not in the frozen shadow release set")
    entry: dict[str, object] = {
        "path": name,
        "contract_types": list(adapted.contract_types),
        "schema_version": adapted.schema_version,
        "adapter_version": adapted.adapter_version,
        "source_version": dict(adapted.source_version),
        "temporal_class": adapted.temporal_class,
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "required": True,
        "roles": list(roles),
        "validation_scope": adapted.validation_scope,
        "adapter_warnings": list(adapted.warnings),
    }
    if adapted.temporal_class == "daily_snapshot":
        entry["as_of"] = adapted.as_of
        entry["future_data_used"] = adapted.future_data_used
    elif adapted.temporal_class == "versioned_config":
        entry["registry_version"] = adapted.source_version["registry"]
    elif adapted.temporal_class == "research_summary":
        if adapted.coverage_end is None or adapted.coverage_end > release_date:
            raise ContractError("research summary coverage ends after the release date")
        entry["coverage_end"] = adapted.coverage_end
        entry["source_experiment"] = adapted.source_experiment
        entry["prohibited_uses"] = ["scan", "score", "rank"]
    return entry


def _validate_registry_references(
    items: Iterable[tuple[Path, bytes, AdaptedArtifact]],
) -> None:
    """Check factor-registry references using the same immutable bytes as hashes."""

    item_list = list(items)
    registry = next((item for _, _, item in item_list if item.path == "factor-registry.json"), None)
    if registry is None:
        return
    registry_version = registry.source_version["registry"]
    items_by_name = {item.path: (path, raw, item) for path, raw, item in item_list}
    factor_item = items_by_name.get("daily-factor-snapshot.json")
    if factor_item is not None and factor_item[2].source_version.get("registry") != registry_version:
        raise ContractError("factor registry version does not match daily factor snapshot")
    for name in ("unified-v2-latest.json", "unified-v2-rankings.json"):
        item = items_by_name.get(name)
        if item is None:
            continue
        payload = json.loads(item[1])
        versions = payload.get("factor_registry_versions")
        if (
            not isinstance(versions, list)
            or not versions
            or any(not isinstance(version, str) for version in versions)
        ):
            raise ContractError(f"factor registry versions are invalid in {name}")
        if registry_version not in versions:
            raise ContractError(f"factor registry version is not referenced by {name}")


def build_shadow_manifest(
    paths: Iterable[Path],
    generated_at: str | None = None,
    *,
    allow_partial: bool = False,
    known_experiment_ids: AbstractSet[str] | None = None,
) -> dict[str, object]:
    """Build and validate a shadow manifest from exact legacy file bytes."""

    entries: list[dict[str, object]] = []
    path_list = sorted(paths, key=lambda item: item.name)
    names = {path.name for path in path_list}
    if not allow_partial and names != FROZEN_RELEASE_NAMES:
        missing = sorted(FROZEN_RELEASE_NAMES - names)
        extra = sorted(names - FROZEN_RELEASE_NAMES)
        raise ContractError(f"shadow release membership mismatch; missing={missing}, extra={extra}")
    # Read every source once.  Metadata and hashes must describe the exact same
    # byte snapshot, even if another process updates the source concurrently.
    adapted_items = [
        (path, raw, adapt_legacy_bytes(path.name, raw))
        for path in path_list
        for raw in (path.read_bytes(),)
    ]
    daily_dates = {
        item.as_of for _, _, item in adapted_items if item.temporal_class == "daily_snapshot"
    }
    if len(daily_dates) != 1:
        raise ContractError(f"shadow release dates do not match: {sorted(daily_dates)}")
    release_date = next(iter(daily_dates))

    _validate_registry_references(adapted_items)

    for path, raw, adapted in adapted_items:
        entry = _entry_from_bytes(
            name=path.name,
            raw=raw,
            adapted=adapted,
            release_date=release_date,
        )
        entries.append(entry)
    if not entries:
        raise ContractError("shadow manifest requires at least one file")
    entries = sorted(entries, key=lambda entry: str(entry["path"]))
    payload_for_id = {"as_of": release_date, "files": entries}
    release_id = "sha256:" + hashlib.sha256(_canonical(payload_for_id)).hexdigest()
    manifest: dict[str, object] = {
        "schema_version": "1.0.0",
        "release_id": release_id,
        "as_of": release_date,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_version": {"generator": "m01-shadow-manifest-1.0.0"},
        "future_data_used": False,
        "files": entries,
        "shadow_only": True,
    }
    validate_contract(
        "ReleaseManifest",
        manifest,
        known_experiment_ids=known_experiment_ids,
        allow_partial_manifest=allow_partial,
    )
    return manifest


def write_shadow_manifest(
    manifest: Mapping[str, object],
    output_path: Path,
    repo_root: Path,
    *,
    known_experiment_ids: AbstractSet[str] | None = None,
    allow_partial: bool = False,
) -> None:
    """Write only below work/; production public/ is always rejected."""

    resolved_root = repo_root.resolve()
    resolved_output = output_path.resolve()
    allowed = (resolved_root / "work").resolve()
    if allowed not in resolved_output.parents:
        raise ContractError("shadow manifest may only be written below work/")
    if manifest.get("shadow_only") is not True:
        raise ContractError("shadow writer requires shadow_only=true")
    validate_contract(
        "ReleaseManifest",
        manifest,
        known_experiment_ids=known_experiment_ids,
        allow_partial_manifest=allow_partial,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, output_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def verify_shadow_manifest(
    manifest: Mapping[str, object],
    source_dir: Path,
    *,
    known_experiment_ids: AbstractSet[str] | None = None,
    allow_partial: bool = False,
) -> None:
    """Verify that every declared file still has the exact recorded bytes."""

    if manifest.get("shadow_only") is not True:
        raise ContractError("shadow verifier requires shadow_only=true")
    validate_contract(
        "ReleaseManifest",
        manifest,
        known_experiment_ids=known_experiment_ids,
        allow_partial_manifest=allow_partial,
    )
    resolved_source = source_dir.resolve()
    verified_items: list[tuple[Path, bytes, AdaptedArtifact]] = []
    for entry in manifest["files"]:
        path = (resolved_source / str(entry["path"])).resolve()
        if resolved_source not in path.parents:
            raise ContractError(f"manifest file escapes source directory: {entry['path']}")
        if not path.is_file():
            raise ContractError(f"manifest file is missing: {entry['path']}")
        raw = path.read_bytes()
        if len(raw) != entry["size_bytes"]:
            raise ContractError(f"manifest file size mismatch: {entry['path']}")
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ContractError(f"manifest file hash mismatch: {entry['path']}")
        adapted = adapt_legacy_bytes(path.name, raw)
        expected = _entry_from_bytes(
            name=path.name,
            raw=raw,
            adapted=adapted,
            release_date=str(manifest["as_of"]),
        )
        for field, expected_value in expected.items():
            if entry.get(field) != expected_value:
                raise ContractError(
                    f"manifest metadata does not match file {entry['path']}: {field}"
                )
        verified_items.append((path, raw, adapted))
    _validate_registry_references(verified_items)
