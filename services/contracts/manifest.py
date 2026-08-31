"""Build a non-production M01 shadow ReleaseManifest."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import AbstractSet, Iterable, Mapping

from .adapters import adapt_legacy_file
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
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def build_shadow_manifest(
    paths: Iterable[Path],
    generated_at: str | None = None,
    *,
    allow_partial: bool = False,
    known_experiment_ids: AbstractSet[str] | None = None,
) -> dict[str, object]:
    """Build and validate a shadow manifest from exact legacy file bytes."""

    entries: list[dict[str, object]] = []
    dates: set[str] = set()
    path_list = sorted(paths, key=lambda item: item.name)
    names = {path.name for path in path_list}
    if not allow_partial and names != FROZEN_RELEASE_NAMES:
        missing = sorted(FROZEN_RELEASE_NAMES - names)
        extra = sorted(names - FROZEN_RELEASE_NAMES)
        raise ContractError(f"shadow release membership mismatch; missing={missing}, extra={extra}")
    adapted_items = [(path, adapt_legacy_file(path)) for path in path_list]
    daily_dates = {item.as_of for _, item in adapted_items if item.temporal_class == "daily_snapshot"}
    if len(daily_dates) != 1:
        raise ContractError(f"shadow release dates do not match: {sorted(daily_dates)}")
    release_date = next(iter(daily_dates))

    registry = next((item for _, item in adapted_items if item.path == "factor-registry.json"), None)
    if registry is not None:
        registry_version = registry.source_version["registry"]
        items_by_name = {item.path: (path, item) for path, item in adapted_items}
        factor_pair = items_by_name.get("daily-factor-snapshot.json")
        if factor_pair is not None and factor_pair[1].source_version.get("registry") != registry_version:
            raise ContractError("factor registry version does not match daily factor snapshot")
        for name in ("unified-v2-latest.json", "unified-v2-rankings.json"):
            pair = items_by_name.get(name)
            if pair is None:
                continue
            path, _ = pair
            payload = json.loads(path.read_bytes())
            versions = payload.get("factor_registry_versions", [])
            if registry_version not in versions:
                raise ContractError(f"factor registry version is not referenced by {name}")

    for path, adapted in adapted_items:
        roles = ROLE_BY_NAME.get(path.name)
        if roles is None:
            raise ContractError(f"{path.name} is not in the frozen shadow release set")
        raw = path.read_bytes()
        entry: dict[str, object] = {
                "path": path.name,
                "contract_types": list(adapted.contract_types),
                "schema_version": adapted.schema_version,
                "adapter_version": adapted.adapter_version,
                "source_version": dict(adapted.source_version),
                "temporal_class": adapted.temporal_class,
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "required": True,
                "roles": list(roles),
            }
        if adapted.temporal_class == "daily_snapshot":
            entry["as_of"] = adapted.as_of
            entry["future_data_used"] = adapted.future_data_used
            dates.add(str(adapted.as_of))
        elif adapted.temporal_class == "versioned_config":
            entry["registry_version"] = adapted.source_version["registry"]
        elif adapted.temporal_class == "research_summary":
            if adapted.coverage_end is None or adapted.coverage_end > release_date:
                raise ContractError("research summary coverage ends after the release date")
            entry["coverage_end"] = adapted.coverage_end
            entry["source_experiment"] = adapted.source_experiment
            entry["prohibited_uses"] = ["scan", "score", "rank"]
        entries.append(entry)
    if not entries:
        raise ContractError("shadow manifest requires at least one file")
    if len(dates) != 1:
        raise ContractError(f"shadow release dates do not match: {sorted(dates)}")
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


def write_shadow_manifest(manifest: Mapping[str, object], output_path: Path, repo_root: Path) -> None:
    """Write only below work/; production public/ is always rejected."""

    resolved_root = repo_root.resolve()
    resolved_output = output_path.resolve()
    allowed = (resolved_root / "work").resolve()
    if allowed not in resolved_output.parents:
        raise ContractError("shadow manifest may only be written below work/")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


def verify_shadow_manifest(
    manifest: Mapping[str, object],
    source_dir: Path,
    *,
    known_experiment_ids: AbstractSet[str] | None = None,
    allow_partial: bool = False,
) -> None:
    """Verify that every declared file still has the exact recorded bytes."""

    validate_contract(
        "ReleaseManifest",
        manifest,
        known_experiment_ids=known_experiment_ids,
        allow_partial_manifest=allow_partial,
    )
    resolved_source = source_dir.resolve()
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
