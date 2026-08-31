"""Shared validated atomic JSON storage for M02 shadow repositories."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping

from services.contracts.validation import ContractError


def atomic_write_validated_json(
    path: Path,
    payload: Mapping[str, Any],
    *,
    validator: Callable[[Mapping[str, Any]], None],
    before_replace: Callable[[Path, Path], None] | None = None,
) -> None:
    """Write complete validated bytes, then perform the only atomic replacement.

    Callers provide their contract validator.  A serialization, validation or
    injected replacement failure leaves the previous target bytes untouched.
    """

    try:
        content = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode() + b"\n"
    except (TypeError, ValueError) as exc:
        raise ContractError("shadow repository state must be canonical JSON") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            staged = json.loads(temporary.read_bytes())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError("staged shadow repository state is not valid JSON") from exc
        if not isinstance(staged, Mapping):
            raise ContractError("staged shadow repository state must be an object")
        validator(staged)
        if before_replace is not None:
            before_replace(path, temporary)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()
