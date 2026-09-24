"""Frozen public release shared by unit tests.

Unit tests must exercise code against this fixed snapshot, never the moving
public/ output of the daily EOD job. Live-data invariants are enforced by
services.scanner.release_contract in the release path instead.
"""
from contextlib import contextmanager
import copy
import gzip
import json
from pathlib import Path
from unittest.mock import patch

from services.contracts.market_data import canonical_fingerprint

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FIXTURE = ROOT / 'tests' / 'fixtures' / 'public-2026-09-23'
PUBLIC_FIXTURE_DAY = '2026-09-23'


def fixture(name):
    path = PUBLIC_FIXTURE / name
    if not path.exists():
        return json.loads(gzip.decompress((PUBLIC_FIXTURE / f'{name}.gz').read_bytes()))
    return json.loads(path.read_bytes())


def reseal(payload):
    payload['content_fingerprint'] = canonical_fingerprint({k: v for k, v in payload.items() if k != 'content_fingerprint'})
    return payload


def changed(payload, mutate):
    """Return a mutated deep copy and prove the mutation really changed it."""
    result = copy.deepcopy(payload)
    mutate(result)
    if result == payload:
        raise AssertionError('tamper fixture did not change the payload')
    return result


@contextmanager
def local_public(assets):
    """Serve {file name: payload} for verifier reads of ROOT/public/<name>."""
    read_bytes = Path.read_bytes
    served = {ROOT / 'public' / name: json.dumps(value).encode() for name, value in assets.items()}

    def fake(path):
        return served[path] if path in served else read_bytes(path)
    with patch.object(Path, 'read_bytes', fake):
        yield
