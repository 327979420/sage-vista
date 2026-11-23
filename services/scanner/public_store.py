"""Read and write public JSON archives that Git stores gzip-compressed.

GitHub rejects any pushed file above 100 MiB. Archives listed under
``storedCompressed`` in services/automation/public-archive-policy.json are kept
in Git as ``<name>.gz`` (gzip -9, mtime 0, so unchanged content gives the same
bytes). Their JSON content is unchanged: callers keep passing the logical path,
for example ``public/signal-history.json``, and read or write the same bytes as
before. Every other path is read and written exactly as a plain file.
"""
import gzip
import json
import os
import pathlib

_POLICY = json.loads((pathlib.Path(__file__).resolve().parents[1]
                      / "automation/public-archive-policy.json").read_text())
STORED_COMPRESSED = frozenset(_POLICY.get("storedCompressed", ()))


def stored_path(path):
    """Return the file that actually holds ``path`` on disk and in Git."""
    path = pathlib.Path(path)
    return path.with_name(path.name + ".gz") if path.name in STORED_COMPRESSED else path


def _source(path):
    path = pathlib.Path(path)
    stored = stored_path(path)
    if stored == path:
        return path, False
    if stored.exists() and path.exists():
        # Refuse to guess: one of the two copies is stale.
        raise RuntimeError(f"Both {path} and {stored} exist; keep only {stored.name}")
    if stored.exists():
        return stored, True
    # Older commits, fixtures and work/ copies may still hold plain JSON.
    return path, False


def exists(path):
    source, _ = _source(path)
    return source.exists()


def read_bytes(path):
    source, compressed = _source(path)
    raw = source.read_bytes()
    return gzip.decompress(raw) if compressed else raw


def read_text(path):
    return read_bytes(path).decode("utf-8")


def read_json(path):
    return json.loads(read_bytes(path))


def compress(content):
    return gzip.compress(content, compresslevel=9, mtime=0)


def write_bytes(path, content):
    """Write ``content`` for ``path``; archives land as ``<name>.gz`` only."""
    path = pathlib.Path(path)
    stored = stored_path(path)
    if stored == path:
        path.write_bytes(content)
        return path
    encoded = compress(content)
    if gzip.decompress(encoded) != content:
        raise RuntimeError(f"Compressed copy does not round-trip: {path}")
    temporary = stored.with_name(stored.name + ".tmp")
    temporary.write_bytes(encoded)
    os.replace(temporary, stored)
    if path.exists():
        path.unlink()
    return stored


def write_text(path, text):
    return write_bytes(path, text.encode("utf-8"))


def replace(source, target):
    """Move a finished file into place, using its stored form for archives."""
    target = pathlib.Path(target)
    target_stored = stored_path(target)
    os.replace(stored_path(source), target_stored)
    if target_stored != target and target.exists():
        target.unlink()
    return target_stored
