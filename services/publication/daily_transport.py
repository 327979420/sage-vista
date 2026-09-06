"""Fixed daily prepare/check/return followed by the existing membership bridge.

Construct only in a trusted runner. Server identity, selected evidence and live
license checks remain authoritative; an acknowledgement is not a license.
"""
import base64
from copy import deepcopy
import hashlib

from services.contracts.validation import publication_preparation_input, membership_registration_input
from services.publication.membership_transport import MembershipArchiveTransport, _descriptor
from services.publication.authorization_transport import ARCHIVE_RESPONSE_LIMIT, _body, _json, _lease
from services.publication.preparation_execution import execute_preparation_validation, execute_membership_validation

PROTOCOL = 'm12-daily-preparation/1'
REGISTRATION = 'm12-membership-registration/1'


class DailyTransportError(RuntimeError):
    pass


class DailyPreparationTransport(MembershipArchiveTransport):
    def __init__(self, coordinator_origin, actions_environment, *, opener=None):
        super().__init__(coordinator_origin, actions_environment, opener=opener)
        self._context = dict(actions_environment)
        self._state = 'new'
        self._last_written = None
        self._prepared_target = None

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
        value = self._member_call(super().put, key, raw, expected)
        self._last_written = deepcopy(value)
        return value

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
            self._check_identity(value['identity'])
            result = execute_preparation_validation(raw)
            output_hash = 'sha256:' + hashlib.sha256(result).hexdigest()
            output_archive = {'key': 'raw/' + output_hash[7:], 'sha256': output_hash, 'size_bytes': len(result)}
            returned = _json(self._request(self._origin + '/v1/preparation/return', self._token(), data=_body({
                'protocol': PROTOCOL, 'input_sha256': reply['input_sha256'], 'lease_token': lease,
                'result_base64': base64.b64encode(result).decode()}), limit=131072))
            expected = {'protocol': PROTOCOL, 'input_sha256': reply['input_sha256'], 'output_archive': output_archive}
            if type(returned.get('output_archive', {}).get('size_bytes')) is not int or returned != expected:
                raise ValueError('return acknowledgement differs')
            self._prepared_target = deepcopy({k: value['evidence'][k] for k in ('as_of', 'config_ref', 'config_archive')})
            self._state = 'ready'
            return deepcopy({'as_of': value['evidence']['as_of'], 'input_sha256': reply['input_sha256'], 'output_archive': output_archive})
        except Exception:
            self._state = 'failed'
            raise DailyTransportError('daily preparation failed') from None


    def _check_identity(self, identity):
        env = self._context
        job = {'repository_id': env['GITHUB_REPOSITORY_ID'], 'workflow_ref': env['GITHUB_WORKFLOW_REF'],
            'workflow_commit': env['GITHUB_WORKFLOW_SHA'], 'run_id': env['GITHUB_RUN_ID'],
            'run_attempt': int(env['GITHUB_RUN_ATTEMPT']), 'environment': 'production'}
        if identity['job'] != job or identity['actor_id'] != env['GITHUB_ACTOR_ID'] or identity['code_commit'] != env['GITHUB_SHA'] or identity['subject'] != f"repo:{env['GITHUB_REPOSITORY']}:environment:production":
            raise ValueError('prepare belongs to another execution')

    def register_membership(self, observation_key, observation_sha256):
        if self._state != 'ready':
            raise DailyTransportError('daily preparation is not ready')
        self._state = 'registering'
        try:
            candidate = deepcopy(self._last_written)
            if not candidate or candidate['key'] != observation_key or candidate['sha256'] != observation_sha256 or not 0 < candidate['size_bytes'] <= 16384:
                raise ValueError('observation differs from actual last archive')
            reply = _json(self._request(self._origin + '/v1/membership/registration/prepare', self._token(),
                data=_body({'protocol': REGISTRATION, 'candidate_archive': candidate}), limit=ARCHIVE_RESPONSE_LIMIT))
            if set(reply) != {'protocol', 'input_sha256', 'input_size_bytes', 'input_base64'} or reply['protocol'] != REGISTRATION:
                raise ValueError('registration envelope differs')
            raw = base64.b64decode(reply['input_base64'], validate=True)
            if base64.b64encode(raw).decode() != reply['input_base64'] or type(reply['input_size_bytes']) is not int or reply['input_size_bytes'] != len(raw) or reply['input_sha256'] != 'sha256:' + hashlib.sha256(raw).hexdigest():
                raise ValueError('registration bytes differ')
            value = membership_registration_input(raw)
            self._check_identity(value['identity'])
            evidence = value['preparation']['evidence']
            if candidate != value['candidate_archive'] or {k: evidence[k] for k in self._prepared_target} != self._prepared_target:
                raise ValueError('registration target differs')
            result = execute_membership_validation(raw)
            output_hash = 'sha256:' + hashlib.sha256(result).hexdigest()
            output = {'key': 'raw/' + output_hash[7:], 'sha256': output_hash, 'size_bytes': len(result)}
            current = deepcopy(value['expected_index'])
            if current['head'] != candidate:
                current = {'revision': current['revision'] + 1, 'head': candidate, 'history': current['history'] + [candidate]}
            returned = _json(self._request(self._origin + '/v1/membership/registration/return', self._token(),
                data=_body({'protocol': REGISTRATION, 'input_sha256': reply['input_sha256'],
                    'result_base64': base64.b64encode(result).decode()}), limit=131072))
            expected = {'protocol': REGISTRATION, 'input_sha256': reply['input_sha256'], 'output_archive': output, 'current_index': current}
            # Receipt projection only: the server alone performs the CAS.
            root = returned['current_index']
            if type(root['revision']) is not int or type(root['history']) is not list:
                raise ValueError('registration index types differ')
            for item in [returned['output_archive'], root['head'], *root['history']]:
                if set(item) != {'key', 'sha256', 'size_bytes'}:
                    raise ValueError('registration descriptor fields differ')
                _descriptor(item['key'], {k: item[k] for k in ('sha256', 'size_bytes')})
            if returned != expected:
                raise ValueError('registration acknowledgement differs')
            self._state = 'registered'
            return deepcopy(returned)
        except Exception:
            self._state = 'failed'
            raise DailyTransportError('daily membership registration failed') from None
