"""Shadow-only construction and storage of point-in-time universe snapshots."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence

from services.contracts.market_data import (
    UNIVERSE_SCHEMA_VERSION,
    normalize_universe_members,
    normalize_universe_qualifications,
    select_universe_snapshot,
    universe_snapshot_id,
    validate_universe_snapshot,
)
from services.contracts.validation import ContractError

from .storage import atomic_write_validated_json, require_shadow_root


UNIVERSE_ID = re.compile(r"^universe:sha256:([0-9a-f]{64})$")


def build_universe_snapshot(
    *,
    as_of: str,
    generated_at: str,
    source_version: Mapping[str, Any],
    eligibility_rule_version: str,
    effective_from: str,
    path_status: str,
    coverage_status: str,
    members: Sequence[Mapping[str, Any]],
    qualifications: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build one immutable identity from membership and same-day eligibility evidence.

    All evidence is injected.  The builder never discovers a current ticker
    list, so a missing historical membership source cannot become a fabricated
    formal snapshot or introduce survivorship bias.
    """

    normalized_members = normalize_universe_members(members)
    normalized_qualifications = normalize_universe_qualifications(qualifications)
    payload: dict[str, Any] = {
        "schema_version": UNIVERSE_SCHEMA_VERSION,
        "as_of": as_of,
        "generated_at": generated_at,
        "source_version": dict(source_version),
        "future_data_used": False,
        "members": normalized_members,
        "qualifications": normalized_qualifications,
        "eligibility_rule_version": eligibility_rule_version,
        "effective_from": effective_from,
        "path_status": path_status,
        "coverage_status": coverage_status,
    }
    payload["universe_id"] = universe_snapshot_id(
        as_of=as_of,
        effective_from=effective_from,
        source_version=source_version,
        eligibility_rule_version=eligibility_rule_version,
        members=normalized_members,
        qualifications=normalized_qualifications,
        path_status=path_status,
        coverage_status=coverage_status,
    )
    validate_universe_snapshot(payload)
    return payload


def _reject_json_constant(value: str) -> None:
    raise ContractError(f"universe snapshot contains a non-JSON numeric value: {value}")


class UniverseSnapshotStore:
    """Persist immutable snapshots only in a test temp tree or approved work/ shadow tree."""

    def __init__(
        self,
        root: str | Path,
        *,
        workspace_root: str | Path | None = None,
        before_replace: Callable[[Path, Path], None] | None = None,
    ) -> None:
        self._root = require_shadow_root(root, workspace_root=workspace_root)
        self._before_replace = before_replace
        self._snapshot_dir = self._root / "snapshots"

    @staticmethod
    def _digest(universe_id: Any) -> str:
        match = UNIVERSE_ID.fullmatch(universe_id) if isinstance(universe_id, str) else None
        if not match:
            raise ContractError("universe_id is unsafe or non-canonical")
        return match.group(1)

    def _snapshot_path(self, universe_id: Any) -> Path:
        path = (self._snapshot_dir / (self._digest(universe_id) + ".json")).resolve()
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise ContractError("universe snapshot path escapes its configured root") from exc
        return path

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_bytes(), parse_constant=_reject_json_constant)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError("universe snapshot is not valid JSON") from exc
        if not isinstance(payload, Mapping):
            raise ContractError("universe snapshot root must be an object")
        validate_universe_snapshot(payload)
        return dict(payload)

    def save(self, snapshot: Mapping[str, Any]) -> Path:
        """Validate before writing and never replace an already identified historical fact."""

        validate_universe_snapshot(snapshot)
        path = self._snapshot_path(snapshot["universe_id"])
        if path.exists():
            existing = self._load(path)
            if existing["universe_id"] != snapshot["universe_id"]:
                raise ContractError("stored universe identity conflicts with requested snapshot")
            return path
        atomic_write_validated_json(
            path,
            snapshot,
            validator=validate_universe_snapshot,
            before_replace=self._before_replace,
        )
        return path

    def snapshots(self) -> tuple[Mapping[str, Any], ...]:
        """Load every validated immutable snapshot without inferring missing dates."""

        if not self._snapshot_dir.exists():
            return ()
        return tuple(self._load(path) for path in sorted(self._snapshot_dir.glob("*.json")))

    def select(self, *, as_of: str, path_status: str = "formal") -> Mapping[str, Any]:
        """Return the newest eligible point-in-time snapshot or universe_unavailable.

        Selection only examines saved evidence whose own dates are not after the
        query.  It has no fallback to today's active list, which is the key
        guard against future information and survivorship bias.
        """

        selected = select_universe_snapshot(
            self.snapshots(), as_of=as_of, path_status=path_status
        )
        return selected
