"""C1b private archive bridge over the existing isolated Actions HTTPS channel.

Trusted runtime origin/environment only. No production factory or retries.
Server policy is never sent by the client; acquisition evidence remains opaque
original bytes, not a locally inferred permission or formal source proof.
"""
import base64
import hashlib
import re

from services.scanner.eodhd import MEMBERSHIP_URL, MEMBERSHIP_MAX_BYTES
from services.contracts.market_data import require_date
from .authorization_transport import ActionsHttpsChannel, ARCHIVE_RESPONSE_LIMIT, _body, _json

PROTOCOL = 'm12-membership-archive/1'


class MembershipTransportError(RuntimeError):
    pass


def _descriptor(key, expected):
    if (type(key) is not str or not re.fullmatch(r'raw/[a-f0-9]{64}', key) or
            type(expected) is not dict or set(expected) != {'sha256', 'size_bytes'} or
            expected['sha256'] != 'sha256:' + key[4:] or type(expected['size_bytes']) is not int or
            not 0 <= expected['size_bytes'] <= MEMBERSHIP_MAX_BYTES + 1):
        raise MembershipTransportError('membership_descriptor_invalid')
    return {'key': key, **expected}


def _bytes(value):
    encoded = value['bytes_base64']
    if type(encoded) is not str or len(encoded) > 4 * ((MEMBERSHIP_MAX_BYTES + 3) // 3):
        raise ValueError('invalid bytes')
    raw = base64.b64decode(encoded, validate=True)
    if (base64.b64encode(raw).decode('ascii') != encoded or len(raw) != value['size_bytes'] or
            'sha256:' + hashlib.sha256(raw).hexdigest() != value['sha256']):
        raise ValueError('invalid fingerprint')
    return raw


class MembershipArchiveTransport(ActionsHttpsChannel):
    def _rpc(self, operation, fields):
        try:
            data = _body({'protocol': PROTOCOL, **fields})
            if len(data) > ARCHIVE_RESPONSE_LIMIT:
                raise ValueError('request too large')
            response = self._request(self._origin + '/v1/membership/' + operation, self._token(),
                                     data=data, limit=ARCHIVE_RESPONSE_LIMIT)
            return _json(response)
        except Exception:
            raise MembershipTransportError('membership_transport_failed') from None

    def authorize(self, *, as_of, request_url):
        require_date(as_of, 'as_of')
        if request_url != MEMBERSHIP_URL:
            raise MembershipTransportError('membership_request_invalid')
        value = self._rpc('permit', {'as_of': as_of, 'request_url': MEMBERSHIP_URL})
        try:
            if (set(value) != {'protocol', 'as_of', 'request_url', 'key', 'sha256', 'size_bytes', 'bytes_base64'} or
                    value['protocol'] != PROTOCOL or value['as_of'] != as_of or value['request_url'] != request_url):
                raise ValueError('permit mismatch')
            _descriptor(value['key'], {k: value[k] for k in ('sha256', 'size_bytes')})
            if not 0 < value['size_bytes'] <= 1024 * 1024:
                raise ValueError('permit size')
            return _bytes(value)
        except Exception:
            raise MembershipTransportError('membership_permit_response_invalid') from None

    def put(self, key, raw, expected):
        entry = _descriptor(key, expected)
        if (type(raw) is not bytes or len(raw) != entry['size_bytes'] or
                'sha256:' + hashlib.sha256(raw).hexdigest() != entry['sha256']):
            raise MembershipTransportError('membership_put_bytes_invalid')
        value = self._rpc('put', {**entry, 'bytes_base64': base64.b64encode(raw).decode('ascii')})
        try:
            _descriptor(value.get('key'), {k: value.get(k) for k in ('sha256', 'size_bytes')})
        except MembershipTransportError:
            raise MembershipTransportError('membership_put_response_invalid') from None
        if value != {'protocol': PROTOCOL, **entry}:
            raise MembershipTransportError('membership_put_response_invalid')
        return dict(entry)

    def read(self, key, expected):
        entry = _descriptor(key, expected)
        value = self._rpc('read', entry)
        try:
            _descriptor(value.get('key'), {k: value.get(k) for k in ('sha256', 'size_bytes')})
            if (set(value) != {'protocol', 'key', 'sha256', 'size_bytes', 'bytes_base64'} or
                    {k: v for k, v in value.items() if k != 'bytes_base64'} != {'protocol': PROTOCOL, **entry}):
                raise ValueError('read mismatch')
            return _bytes(value)
        except Exception:
            raise MembershipTransportError('membership_read_response_invalid') from None
