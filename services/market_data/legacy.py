"""The single read-only adapter for legacy ``work/eodhd-cache`` JSON files.

M02 A-C does not discover, refresh or rewrite a cache directory.  A caller must
name one existing file and an explicit ``as_of``.  The adapter verifies that the
source bytes are identical after reading before returning any rows.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Mapping, Any

from services.contracts.validation import ContractError

from .normalization import adjusted_point_in_time_rows, bars_fingerprint


LEGACY_ADAPTER_VERSION = "legacy-adapter-eodhd-cache-1.0.0"


@dataclass(frozen=True)
class LegacyCacheRead:
    path: str
    adapter_version: str
    source_fingerprint: str
    point_in_time_fingerprint: str
    as_of: str
    max_returned_date: str | None
    rows: tuple[Mapping[str, Any], ...]


def read_legacy_cache(path: str | Path, *, as_of: str) -> LegacyCacheRead:
    """Read one old cache file without writing, downloading or guessing facts."""

    source = Path(path)
    if source.suffix != ".json" or not source.is_file():
        raise ContractError("legacy cache path must name an existing JSON file")
    before = source.read_bytes()
    try:
        payload = json.loads(before)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("legacy cache is not valid JSON") from exc
    if not isinstance(payload, list):
        raise ContractError("legacy cache root must be a list of raw bars")
    rows = adjusted_point_in_time_rows(payload, as_of=as_of)
    after = source.read_bytes()
    if after != before:
        raise ContractError("legacy cache changed during a supposedly read-only adaptation")
    source_fingerprint = "sha256:" + hashlib.sha256(before).hexdigest()
    return LegacyCacheRead(
        path=str(source),
        adapter_version=LEGACY_ADAPTER_VERSION,
        source_fingerprint=source_fingerprint,
        point_in_time_fingerprint=bars_fingerprint(rows),
        as_of=as_of,
        max_returned_date=rows[-1]["date"] if rows else None,
        rows=rows,
    )
