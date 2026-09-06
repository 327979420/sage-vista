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


def _registration_input(raw):
    from .validation import PREPARATION_INPUT_MAX_BYTES, _m12_decode_base64, publication_preparation_input
    if type(raw) is not bytes or not 0 < len(raw) <= PREPARATION_INPUT_MAX_BYTES:
        raise ContractError('membership registration input size invalid')
    wire = _m12_json(raw)
    _m12_exact(wire, {'protocol', 'identity', 'preparation_base64', 'expected_index',
        'candidate_archive', 'acquisition_archive', 'observations_base64'}, 'membership registration wire')
    if wire['protocol'] != 'm12-membership-registration/1':
        raise ContractError('membership registration protocol invalid')
    prepared = publication_preparation_input(_m12_decode_base64(wire['preparation_base64']))
    if wire['identity'] != prepared['identity']:
        raise ContractError('membership registration identity differs from preparation')
    expected = wire['expected_index']
    _m12_exact(expected, {'revision', 'head', 'history'}, 'membership registration expected index')
    if (type(expected['revision']) is not int or expected['revision'] < 0
            or type(expected['history']) is not list or len(expected['history']) != expected['revision']
            or expected['head'] != (expected['history'][-1] if expected['history'] else None)):
        raise ContractError('membership registration expected index incomplete')
    if type(wire['observations_base64']) is not list:
        raise ContractError('membership registration original bytes missing')
    originals = []
    for item in wire['observations_base64']:
        _m12_exact(item, {'observation_bytes', 'response_bytes', 'acquisition_bytes'}, 'membership encoded originals')
        originals.append({key: _m12_decode_base64(value) for key, value in item.items()})
    candidate = wire['candidate_archive']
    history = list(expected['history'])
    if candidate != expected['head']:
        history.append(candidate)
    proposed = {'revision': len(history), 'head': candidate, 'history': history}
    evidence = {'current_index': proposed, 'observations': originals}
    restored = _observation_history(evidence, as_of=prepared['evidence']['as_of'])
    current = _m12_json(originals[-1]['observation_bytes'])
    if current['acquisition_evidence'] != wire['acquisition_archive']:
        raise ContractError('membership candidate license differs from fixed capability')
    _raw_descriptor(wire['acquisition_archive'], originals[-1]['acquisition_bytes'], limit=1024 * 1024)
    return {'identity': prepared['identity'], 'preparation': prepared, 'expected_index': expected,
            'candidate_archive': candidate, 'membership_evidence': evidence,
            'latest_observation_completed_at': max(parsed.completed_at for parsed, _ in restored)}
