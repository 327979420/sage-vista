"""Private recovery journal and one-shot historical client; never replays output."""
import base64
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile

from services.publication.authorization_transport import (
    AuthorizationHttpsTransport, AuthorizationTransportError, PROTOCOL, UUID,
    _body, _json, _lease, _stamp, _url,
)

RECOVERY_PROTOCOL = 'm12-authorization-recovery/1'
HASH = re.compile(r'sha256:[a-f0-9]{64}')


def _location(value, kind):
    if (type(value) is not dict or set(value) != {'key', 'sha256', 'size_bytes'} or
            not isinstance(value['sha256'], str) or not HASH.fullmatch(value['sha256']) or
            type(value['size_bytes']) is not int or not 0 < value['size_bytes'] <= 2 * 1024 * 1024):
        raise ValueError('archive descriptor invalid')
    key = value['key']
    if (not isinstance(key, str) or (kind == 'raw' and key != 'raw/' + value['sha256'][7:]) or
            (kind == 'authority' and not re.fullmatch(r'authority/[a-f0-9]{64}\.json', key))):
        raise ValueError('archive key invalid')


def _handle(value):
    if (type(value) is not dict or set(value) != {'protocol', 'origin', 'dispatch_id', 'input_sha256',
            'authorization_archive', 'validation_receipt_archive', 'validated_at'} or value['protocol'] != RECOVERY_PROTOCOL or
            not isinstance(value['dispatch_id'], str) or not UUID.fullmatch(value['dispatch_id']) or
            not isinstance(value['input_sha256'], str) or not HASH.fullmatch(value['input_sha256'])):
        raise ValueError('recovery handle invalid')
    origin = _url(value['origin'])
    if origin.path or origin.query:
        raise ValueError('recovery origin invalid')
    _location(value['authorization_archive'], 'authority')
    _location(value['validation_receipt_archive'], 'raw')
    _stamp(value['validated_at'])
    return deepcopy(value)


def _decode(value):
    if not isinstance(value, str): raise ValueError('base64 invalid')
    raw = base64.b64decode(value, validate=True)
    if base64.b64encode(raw).decode('ascii') != value: raise ValueError('base64 invalid')
    return raw


def _make_handle(origin, prepared, raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 2 * 1024 * 1024:
        raise ValueError('result bytes invalid')
    output = _json(raw)
    if set(output) != {'authorization_base64', 'receipt_base64'}: raise ValueError('output fields invalid')
    authorization, receipt_bytes = _decode(output['authorization_base64']), _decode(output['receipt_base64'])
    receipt = _json(receipt_bytes)
    archived = receipt['authorization_archive']
    if (receipt['input_sha256'] != prepared['input_sha256'] or type(receipt['input_size_bytes']) is not int or
            receipt['input_size_bytes'] != prepared['input_size_bytes'] or
            archived['sha256'] != 'sha256:' + hashlib.sha256(authorization).hexdigest() or
            type(archived['size_bytes']) is not int or archived['size_bytes'] != len(authorization)):
        raise ValueError('result metadata mismatch')
    receipt_hash = hashlib.sha256(receipt_bytes).hexdigest()
    return _handle({'protocol': RECOVERY_PROTOCOL, 'origin': origin, 'dispatch_id': prepared['dispatch_id'],
        'input_sha256': prepared['input_sha256'], 'authorization_archive': archived,
        'validation_receipt_archive': {'key': 'raw/' + receipt_hash, 'sha256': 'sha256:' + receipt_hash, 'size_bytes': len(receipt_bytes)},
        'validated_at': receipt['validated_at']})


class AuthorizationRecoveryJournal:
    def __init__(self, directory):
        try:
            root = Path(directory)
            root.mkdir(mode=0o700, exist_ok=True)
            if root.is_symlink() or not root.is_dir() or root.stat().st_uid != os.getuid() or stat.S_IMODE(root.stat().st_mode) & 0o077:
                raise ValueError('private directory required')
            self._root = root.resolve(strict=True)
        except Exception:
            raise AuthorizationTransportError('validation recovery journal unavailable') from None

    def read(self, recovery_id):
        try:
            if not isinstance(recovery_id, str) or not re.fullmatch(r'[a-f0-9]{64}', recovery_id):
                raise ValueError('id invalid')
            fd = os.open(self._root / (recovery_id + '.json'), os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid():
                    raise ValueError('private file required')
                raw = stream.read(8193)
            if len(raw) > 8192 or hashlib.sha256(raw).hexdigest() != recovery_id:
                raise ValueError('handle bytes invalid')
            value = _handle(_json(raw))
            if _body(value) != raw: raise ValueError('handle encoding invalid')
            return value
        except Exception:
            raise AuthorizationTransportError('validation recovery journal invalid') from None

    def save(self, handle):
        temporary = None
        try:
            value = _handle(handle)
            raw = _body(value)
            if len(raw) > 8192: raise ValueError('handle too large')
            recovery_id = hashlib.sha256(raw).hexdigest()
            with tempfile.NamedTemporaryFile(mode='wb', dir=self._root, prefix='.pending-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, self._root / (recovery_id + '.json'))  # Atomic no-overwrite install.
            except FileExistsError:
                pass  # Existing exact bytes must pass the same readback below.
            # Persist the journal's own directory entry too. Always repeat this
            # chain: a previous failed save may have left both directory and
            # final file present without a completed parent-directory sync.
            for directory in (self._root, self._root.parent):
                directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(directory_fd)
                finally: os.close(directory_fd)
            if self.read(recovery_id) != value: raise ValueError('handle conflict')
            return recovery_id
        except Exception:
            raise AuthorizationTransportError('validation recovery journal write failed') from None
        finally:
            if temporary is not None:
                try: temporary.unlink(missing_ok=True)
                except OSError:
                    raise AuthorizationTransportError('validation recovery journal cleanup failed') from None


class RecoverableAuthorizationTransport(AuthorizationHttpsTransport):
    """Runtime factory must use this journaled client; no arbitrary resume data."""
    def __init__(self, coordinator_origin, actions_environment, *, recovery_directory, opener=None):
        super().__init__(coordinator_origin, actions_environment, opener=opener)
        self._journal = AuthorizationRecoveryJournal(recovery_directory)
        self._recovery_id = None

    @property
    def recovery_id(self):
        return self._recovery_id

    def return_result(self, dispatch_id, lease_token, result_bytes):
        try:
            if (self._state != 'prepared' or dispatch_id != self._prepared['dispatch_id'] or
                    _lease(lease_token) != self._prepared['lease_token']):
                raise ValueError('return session mismatch')
            handle = _make_handle(self._origin, self._prepared, result_bytes)
            self._recovery_id = self._journal.save(handle)  # Durable local readback before any return HTTP.
        except Exception:
            self._state = 'failed'
            raise AuthorizationTransportError('validation recovery preparation failed') from None
        return super().return_result(dispatch_id, lease_token, result_bytes)

    def recover(self, recovery_id):
        if self._state != 'new':
            raise AuthorizationTransportError('validation recovery requires a new session')
        self._state = 'recovering'
        try:
            handle = self._journal.read(recovery_id)
            if handle['origin'] != self._origin: raise ValueError('origin mismatch')
            payload = {'protocol': PROTOCOL, 'dispatch_id': handle['dispatch_id'],
                       'receipt_key': handle['validation_receipt_archive']['key']}
            raw = self._request(self._origin + '/v1/authorization/recover', self._token(), data=_body(payload), limit=131072)
            response = _json(raw)
            _location(response.get('authorization_archive'), 'authority')
            _location(response.get('validation_receipt_archive'), 'raw')
            if (set(response) != {'protocol', 'dispatch_id', 'state', 'authorization_archive', 'validation_receipt_archive', 'input_sha256', 'recorded_at'} or
                    response['protocol'] != PROTOCOL or response['state'] != 'archived_return_verified' or
                    any(response[field] != handle[field] for field in ('dispatch_id', 'authorization_archive', 'validation_receipt_archive', 'input_sha256')) or
                    _stamp(response['recorded_at']) < _stamp(handle['validated_at'])):
                raise ValueError('recovery response mismatch')
            self._state = 'recovered'
            return raw  # Historical archive verification only, never permission.
        except Exception:
            self._state = 'failed'
            raise AuthorizationTransportError('validation recovery failed') from None
