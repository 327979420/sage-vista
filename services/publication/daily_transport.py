"""Fixed daily prepare/check/return followed by the existing membership bridge.

Construct only in a trusted runner. Server identity, selected evidence and live
license checks remain authoritative; an acknowledgement is not a license.
"""
import base64
from copy import deepcopy
import hashlib

from services.contracts.validation import publication_preparation_input
from services.publication.membership_transport import MembershipArchiveTransport
from services.publication.authorization_transport import ARCHIVE_RESPONSE_LIMIT, _body, _json, _lease
from services.publication.preparation_execution import execute_preparation_validation

PROTOCOL = 'm12-daily-preparation/1'


class DailyTransportError(RuntimeError):
    pass


class DailyPreparationTransport(MembershipArchiveTransport):
    def __init__(self, coordinator_origin, actions_environment, *, opener=None):
        super().__init__(coordinator_origin, actions_environment, opener=opener)
        self._context = dict(actions_environment)
        self._state = 'new'

    def _rpc(self, operation, fields):
        if self._state != 'ready':
            raise DailyTransportError('daily preparation is not ready')
        try:
            return super()._rpc(operation, fields)
        except Exception:
            self._state = 'failed'
            raise DailyTransportError('daily membership request failed') from None

    def _member_call(self, method, *args, **kwargs):
        try:
            return method(*args, **kwargs)
        except Exception:
            self._state = 'failed'
            raise DailyTransportError('daily membership request failed') from None

    def authorize(self, *, as_of, request_url):
        return self._member_call(super().authorize, as_of=as_of, request_url=request_url)

    def put(self, key, raw, expected):
        return self._member_call(super().put, key, raw, expected)

    def read(self, key, expected):
        return self._member_call(super().read, key, expected)

    def prepare_and_validate(self):
        if self._state != 'new':
            raise DailyTransportError('daily preparation already attempted')
        self._state = 'preparing'
        try:
            reply = _json(self._request(self._origin + '/v1/preparation/prepare', self._token(),
                data=_body({'protocol': PROTOCOL}), limit=ARCHIVE_RESPONSE_LIMIT))
            if set(reply) != {'protocol', 'lease_token', 'input_sha256', 'input_size_bytes', 'input_base64'} or reply['protocol'] != PROTOCOL:
                raise ValueError('prepare envelope differs')
            lease = _lease(reply['lease_token'])
            raw = base64.b64decode(reply['input_base64'], validate=True)
            if base64.b64encode(raw).decode() != reply['input_base64'] or type(reply['input_size_bytes']) is not int or reply['input_size_bytes'] != len(raw) or reply['input_sha256'] != 'sha256:' + hashlib.sha256(raw).hexdigest():
                raise ValueError('prepare bytes differ')
            value = publication_preparation_input(raw)
            identity = value['identity']
            env = self._context
            job = {'repository_id': env['GITHUB_REPOSITORY_ID'], 'workflow_ref': env['GITHUB_WORKFLOW_REF'],
                'workflow_commit': env['GITHUB_WORKFLOW_SHA'], 'run_id': env['GITHUB_RUN_ID'],
                'run_attempt': int(env['GITHUB_RUN_ATTEMPT']), 'environment': 'production'}
            if identity['job'] != job or identity['actor_id'] != env['GITHUB_ACTOR_ID'] or identity['code_commit'] != env['GITHUB_SHA'] or identity['subject'] != f"repo:{env['GITHUB_REPOSITORY']}:environment:production":
                raise ValueError('prepare belongs to another execution')
            result = execute_preparation_validation(raw)
            output_hash = 'sha256:' + hashlib.sha256(result).hexdigest()
            output_archive = {'key': 'raw/' + output_hash[7:], 'sha256': output_hash, 'size_bytes': len(result)}
            returned = _json(self._request(self._origin + '/v1/preparation/return', self._token(), data=_body({
                'protocol': PROTOCOL, 'input_sha256': reply['input_sha256'], 'lease_token': lease,
                'result_base64': base64.b64encode(result).decode()}), limit=131072))
            expected = {'protocol': PROTOCOL, 'input_sha256': reply['input_sha256'], 'output_archive': output_archive}
            if type(returned.get('output_archive', {}).get('size_bytes')) is not int or returned != expected:
                raise ValueError('return acknowledgement differs')
            self._state = 'ready'
            return deepcopy({'as_of': value['evidence']['as_of'], 'input_sha256': reply['input_sha256'], 'output_archive': output_archive})
        except Exception:
            self._state = 'failed'
            raise DailyTransportError('daily preparation failed') from None
