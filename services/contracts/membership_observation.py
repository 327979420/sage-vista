"""Original collector bytes and a trusted frozen index; no IO or authority.

Called only through validation.py. The index must come from the coordinator's
complete persisted observation root, not from the caller's chosen byte list.
"""
from datetime import datetime
import hashlib

from .validation import ContractError, _m12_exact, _m12_json
from .market_data import FORMAL_FORWARD_AFTER, require_date


def _raw_descriptor(value, data, *, limit):
    _m12_exact(value, {'key', 'sha256', 'size_bytes'}, 'membership raw descriptor')
    if type(data) is not bytes or not 0 < len(data) <= limit:
        raise ContractError('membership original bytes unavailable')
    fingerprint = 'sha256:' + hashlib.sha256(data).hexdigest()
    if (value['key'] != 'raw/' + fingerprint[7:] or value['sha256'] != fingerprint
            or type(value['size_bytes']) is not int or value['size_bytes'] != len(data)):
        raise ContractError('membership original bytes differ from archive descriptor')
    return {'key': value['key'], 'sha256': fingerprint, 'size_bytes': len(data)}


def _observation_source(value):
    from services.market_data.eodhd_membership import MAX_RESPONSE_BYTES, POLICY_VERSION, parse_us_symbol_response
    from services.scanner.eodhd import MEMBERSHIP_URL

    _m12_exact(value, {'observation_bytes', 'response_bytes', 'acquisition_bytes'}, 'membership source originals')
    raw = value['observation_bytes']
    if type(raw) is not bytes or not 0 < len(raw) <= 16384:
        raise ContractError('membership observation bytes unavailable')
    body = _m12_json(raw)
    _m12_exact(body, {'kind', 'version', 'as_of', 'request', 'acquisition_evidence', 'started_at',
        'completed_at', 'http_status', 'content_length', 'eof', 'failure', 'response',
        'parsed_policy_version'}, 'membership observation')
    if (body['kind'] != 'eodhd_us_membership_observation' or type(body['version']) is not int
            or body['version'] != 1 or body['parsed_policy_version'] != POLICY_VERSION):
        raise ContractError('membership observation version differs')
    if body['request'] != {'method': 'GET', 'url': MEMBERSHIP_URL, 'accept': 'application/json',
                           'accept_encoding': 'identity'}:
        raise ContractError('membership fixed source request differs')
    if (type(body['http_status']) is not int or body['http_status'] != 200
            or body['eof'] is not True or body['failure'] is not None):
        raise ContractError('membership source acquisition was unsuccessful')
    _raw_descriptor(body['response'], value['response_bytes'], limit=MAX_RESPONSE_BYTES)
    _raw_descriptor(body['acquisition_evidence'], value['acquisition_bytes'], limit=1024 * 1024)
    length = body['content_length']
    if length is not None and (type(length) is not int or length != len(value['response_bytes'])):
        raise ContractError('membership source framing differs')
    try:
        started, completed = (datetime.fromisoformat(body[key]) for key in ('started_at', 'completed_at'))
    except (TypeError, ValueError) as exc:
        raise ContractError('membership source observation time invalid') from exc
    # Original parser checks UTC, same New York as_of, ordering, all rows and
    # filter vocabulary. Replaying bytes cannot mint acquisition permission.
    return parse_us_symbol_response(value['response_bytes'], as_of=body['as_of'],
                                    started_at=started, completed_at=completed)


def _observation_history(evidence, *, as_of):
    as_of = require_date(as_of, 'as_of')
    if as_of <= FORMAL_FORWARD_AFTER:
        raise ContractError('membership identity cannot backfill legacy dates')
    _m12_exact(evidence, {'current_index', 'observations'}, 'membership identity evidence')
    index = evidence['current_index']
    _m12_exact(index, {'revision', 'head', 'history'}, 'membership complete observation index')
    history, originals, revision = index['history'], evidence['observations'], index['revision']
    if (type(revision) is not int or revision < 1 or type(history) is not list
            or type(originals) is not list or len(history) != revision or len(originals) != revision):
        raise ContractError('membership observation history incomplete')
    result, seen, previous_day = [], set(), FORMAL_FORWARD_AFTER
    for descriptor, value in zip(history, originals):
        parsed = _observation_source(value)
        archived = _raw_descriptor(descriptor, value['observation_bytes'], limit=16384)
        if archived['key'] in seen or not previous_day < parsed.as_of <= as_of:
            raise ContractError('membership observation dates conflict or regress')
        result.append((parsed, archived))
        seen.add(archived['key'])
        previous_day = parsed.as_of
    if index['head'] != result[-1][1] or previous_day != as_of:
        raise ContractError('membership observation head or target day differs')
    return result
