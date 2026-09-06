"""Internal fixed-source acquisition with mandatory private audit readback.

No runtime factory is installed. `authorize` and `archive` are trusted server
capabilities, never CLI parameters. authorize must verify actual acquisition
permission for the request/date and return its immutable evidence bytes. A
nonempty caller-supplied string or provider token is not such verification.
The R2 transport bridge and authenticated production wiring are separate work.
"""
from dataclasses import dataclass
import hashlib
import json
from typing import Protocol

from services.contracts.market_data import require_date
from services.scanner.eodhd import MEMBERSHIP_URL, observe_active_us_symbols
from .eodhd_membership import MembershipSourceError, ParsedMembership, parse_us_symbol_response


class PrivateArchive(Protocol):
    """Same byte semantics as publication/archive.mjs, without a local store.

    Implementations must write-if-absent, retain old objects, and expose actual
    byte reads. The collector independently verifies each readback below.
    """
    def put(self, key: str, raw: bytes, expected: dict): ...
    def read(self, key: str, expected: dict) -> bytes: ...


@dataclass(frozen=True)
class CollectedMembership:
    observation_key: str
    observation_sha256: str
    parsed: ParsedMembership | None
    failure: str | None


class MembershipCollectionError(RuntimeError):
    pass


def _save(archive, raw):
    fingerprint = 'sha256:' + hashlib.sha256(raw).hexdigest()
    key = 'raw/' + fingerprint[7:]
    expected = {'sha256': fingerprint, 'size_bytes': len(raw)}
    archive.put(key, raw, dict(expected))
    stored = archive.read(key, dict(expected))
    if type(stored) is not bytes or stored != raw:
        raise MembershipCollectionError('membership_archive_readback_failed')
    return {'key': key, **expected}


def collect_membership(as_of: str, *, authorize, archive: PrivateArchive) -> CollectedMembership:
    """Archive every received response before handing it to the sole parser.

    A successful result is unregistered acquisition evidence, not formal
    coverage, a trading-calendar check, or public data-display permission.
    No retries: the scheduler must preserve each attempt and apply its budget.
    """
    require_date(as_of, 'as_of')
    try:
        evidence = authorize(as_of=as_of, request_url=MEMBERSHIP_URL)
        if type(evidence) is not bytes or not 0 < len(evidence) <= 1024 * 1024:
            raise ValueError('acquisition evidence required')
        authority = _save(archive, evidence)
    except Exception:
        raise MembershipCollectionError('membership_acquisition_not_ready') from None
    observation = observe_active_us_symbols()
    try:
        raw = _save(archive, observation.raw)
        failure = observation.failure
        if failure is None and not observation.eof:
            failure = 'http_incomplete_read'
        parsed = None
        if failure is None:
            try:
                parsed = parse_us_symbol_response(observation.raw, as_of=as_of,
                    started_at=observation.started_at, completed_at=observation.completed_at)
            except MembershipSourceError as error:
                failure = str(error)
        body = {
            'kind': 'eodhd_us_membership_observation', 'version': 1,
            'as_of': as_of, 'request': {'method': 'GET', 'url': MEMBERSHIP_URL,
                'accept': 'application/json', 'accept_encoding': 'identity'},
            'acquisition_evidence': authority,
            'started_at': observation.started_at.isoformat(),
            'completed_at': observation.completed_at.isoformat(),
            'http_status': observation.status, 'content_length': observation.content_length,
            'eof': observation.eof, 'failure': failure, 'response': raw,
            'parsed_policy_version': parsed.policy_version if parsed else None,
        }
        encoded = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                             allow_nan=False).encode('utf-8')
        record = _save(archive, encoded)
    except Exception:
        # Any partially stored immutable objects remain; no success is returned.
        raise MembershipCollectionError('membership_archive_failed') from None
    return CollectedMembership(record['key'], record['sha256'], parsed, failure)
