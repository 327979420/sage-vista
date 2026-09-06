"""Controlled HTTPS opener tests; no real network or TLS handshake."""
import base64
from copy import deepcopy
from email.message import Message
import hashlib
import io
import json
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, build_opener
from urllib.response import addinfourl
import unittest

from services.publication.authorization_transport import AuthorizationHttpsTransport, AuthorizationTransportError, PREPARE_LIMIT, _NoRedirect


ORIGIN = 'https://coordinator.example.test'
OIDC = 'https://run.actions.githubusercontent.com/token?api-version=2.0'
ENV = {'GITHUB_ACTIONS': 'true', 'ACTIONS_ID_TOKEN_REQUEST_URL': OIDC, 'ACTIONS_ID_TOKEN_REQUEST_TOKEN': 'fake-request-credential'}
LEASE = {'epoch': '11111111-1111-4111-8111-111111111111', 'fence': 1}
DISPATCH = '22222222-2222-4222-8222-222222222222'
RAW = b'{"opaque":"transport-only-input"}'
PREPARED = {'protocol': 'm12-authorization-job/1', 'dispatch_id': DISPATCH, 'lease_token': LEASE,
            'input_sha256': 'sha256:' + hashlib.sha256(RAW).hexdigest(), 'input_size_bytes': len(RAW),
            'input_base64': base64.b64encode(RAW).decode('ascii')}


def encoded(value):
    return json.dumps(value).encode()


class Response(io.BytesIO):
    def __init__(self, raw, url, status=200, headers=None):
        super().__init__(raw)
        self.status, self.url = status, url
        self.headers = Message()
        for key, value in (headers or [('Content-Type', 'application/json'), ('Content-Length', str(len(raw)))]):
            self.headers[key] = value

    def geturl(self):
        return self.url


class Opener:
    def __init__(self):
        self.calls = []
        self.queue = [{'raw': encoded({'value': 'first.token.signature'})}, {'raw': encoded(PREPARED)},
                      {'raw': encoded({'value': 'second.token.signature'})}, {'raw': b'{"state":"pending"}'}]

    def open(self, request, timeout):
        self.calls.append(request)
        assert timeout == 30
        args = self.queue.pop(0)
        if isinstance(args, Exception):
            raise args
        return Response(url=args.get('url', request.full_url), **{k: v for k, v in args.items() if k != 'url'})


def fixture():
    opener = Opener()
    return AuthorizationHttpsTransport(ORIGIN, ENV, opener=opener), opener


class AuthorizationTransportTests(unittest.TestCase):
    def test_real_urllib_redirect_handler_never_forwards_credentials(self):
        calls = []

        class NetworkStub(HTTPSHandler):
            def https_open(self, request):
                calls.append(request.full_url)
                headers = Message()
                headers['Location'] = 'https://attacker.example/token'
                response = addinfourl(io.BytesIO(b''), headers, request.full_url, 302)
                response.msg = 'Found'
                return response

        opener = build_opener(ProxyHandler({}), NetworkStub(), _NoRedirect())
        transport = AuthorizationHttpsTransport(ORIGIN, ENV, opener=opener)
        with self.assertRaises(AuthorizationTransportError):
            transport.prepare()
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith(OIDC))

    def test_fixed_origins_audience_headers_and_unchanged_result_bytes(self):
        transport, opener = fixture()
        prepared = transport.prepare()
        result = b'{"actual":"stdout"}\n'
        response = transport.return_result(DISPATCH, LEASE, result)
        self.assertEqual(response, b'{"state":"pending"}')
        self.assertEqual(prepared['input_bytes'], RAW)
        self.assertEqual(len(opener.calls), 4)
        self.assertEqual([request.get_method() for request in opener.calls], ['GET', 'POST', 'GET', 'POST'])
        self.assertEqual(parse_qs(urlsplit(opener.calls[0].full_url).query), {'api-version': ['2.0'], 'audience': ['sage-vista-publication']})
        self.assertEqual(opener.calls[0].get_header('Authorization'), 'Bearer fake-request-credential')
        self.assertEqual(opener.calls[1].get_header('Authorization'), 'Bearer first.token.signature')
        self.assertEqual(opener.calls[3].get_header('Authorization'), 'Bearer second.token.signature')
        self.assertEqual(opener.calls[1].full_url, ORIGIN + '/v1/authorization/prepare')
        self.assertEqual(opener.calls[1].data, b'{}')
        self.assertEqual(opener.calls[3].full_url, ORIGIN + '/v1/authorization/return')
        submitted = json.loads(opener.calls[3].data)
        self.assertEqual(set(submitted), {'protocol', 'dispatch_id', 'lease_token', 'result_base64'})
        self.assertEqual(submitted['dispatch_id'], DISPATCH)
        self.assertEqual(submitted['lease_token'], LEASE)
        self.assertEqual(base64.b64decode(submitted['result_base64']), result)

    def test_untrusted_or_noncanonical_urls_and_runtime_configuration_refused(self):
        for origin in ['http://coordinator.example.test', 'https://user@coordinator.example.test', ORIGIN + '/path',
                       ORIGIN + '?query=1', ORIGIN + '#fragment', 'https://coordinator.example.test:443',
                       'https://127.0.0.1', 'https://localhost', 'https://coordinator.example.test\\evil', ORIGIN + '\n']:
            with self.subTest(origin=origin), self.assertRaises(AuthorizationTransportError):
                AuthorizationHttpsTransport(origin, ENV)
        for patch in [{'GITHUB_ACTIONS': 'false'}, {'ACTIONS_ID_TOKEN_REQUEST_TOKEN': ''},
                      {'ACTIONS_ID_TOKEN_REQUEST_TOKEN': 'bad\r\nheader'}, {'ACTIONS_ID_TOKEN_REQUEST_URL': 'https://attacker.example/token'},
                      {'ACTIONS_ID_TOKEN_REQUEST_URL': 'https://run.actions.githubusercontent.com.attacker.test/token'},
                      {'ACTIONS_ID_TOKEN_REQUEST_URL': OIDC + '&audience=other'}]:
            with self.subTest(patch=patch), self.assertRaises(AuthorizationTransportError):
                AuthorizationHttpsTransport(ORIGIN, {**ENV, **patch})

    def test_constructor_copies_runtime_and_prepared_values_do_not_mutate_session(self):
        environment = dict(ENV)
        opener = Opener()
        transport = AuthorizationHttpsTransport(ORIGIN, environment, opener=opener)
        environment['ACTIONS_ID_TOKEN_REQUEST_TOKEN'] = 'mutated'
        prepared = transport.prepare()
        prepared['lease_token']['fence'] = 2
        with self.assertRaises(AuthorizationTransportError):
            transport.return_result(DISPATCH, prepared['lease_token'], b'output')
        self.assertEqual(len(opener.calls), 2)
        transport.return_result(DISPATCH, LEASE, b'output')
        self.assertEqual(opener.calls[0].get_header('Authorization'), 'Bearer fake-request-credential')

    def test_redirect_status_changed_url_mime_encoding_and_incomplete_response_refused(self):
        for patch in [{'status': 302}, {'url': 'https://attacker.example/token'}, {'status': 204},
                      {'headers': [('Content-Type', 'text/html')]}, {'headers': [('Content-Type', 'application/json'), ('Content-Encoding', 'gzip')]},
                      {'headers': [('Content-Type', 'application/json'), ('Content-Length', '9999')]},
                      {'headers': [('Content-Type', 'application/json'), ('Content-Length', '1'), ('Content-Length', '2')]},
                      {'raw': b''}]:
            transport, opener = fixture()
            opener.queue[0].update(patch)
            with self.subTest(patch=patch), self.assertRaises(AuthorizationTransportError):
                transport.prepare()
            self.assertEqual(len(opener.calls), 1)

    def test_token_json_duplicates_nonfinite_and_header_payloads_refused(self):
        for raw in [b'{"value":"a.b.c","value":"a.b.c"}', b'{"value":NaN}', b'{"other":true}',
                    b'{"value":"bad header\\r\\n"}', b'{"value":"not-a-jwt"}', b'[]', b'\xff']:
            transport, opener = fixture()
            opener.queue[0]['raw'] = raw
            with self.subTest(raw=raw), self.assertRaises(AuthorizationTransportError):
                transport.prepare()
            self.assertEqual(len(opener.calls), 1)

    def test_preparation_closed_fields_bytes_hash_and_lease_refused(self):
        variants = []
        for key, value in [('protocol', 'other'), ('dispatch_id', 'not-id'), ('input_base64', 'e31='), ('input_size_bytes', True),
                           ('input_sha256', 'sha256:' + '0' * 64), ('lease_token', {**LEASE, 'fence': True}), ('extra', True)]:
            changed = deepcopy(PREPARED)
            changed[key] = value
            variants.append(changed)
        missing = deepcopy(PREPARED)
        del missing['lease_token']
        variants.append(missing)
        for value in variants:
            transport, opener = fixture()
            opener.queue[1]['raw'] = encoded(value)
            with self.subTest(value=value), self.assertRaises(AuthorizationTransportError):
                transport.prepare()
            with self.assertRaises(AuthorizationTransportError):
                transport.prepare()
            self.assertEqual(len(opener.calls), 2)

    def test_response_limits_fail_before_exposing_partial_preparation(self):
        for index, limit in [(0, 131072), (1, PREPARE_LIMIT)]:
            transport, opener = fixture()
            opener.queue[index]['headers'] = [('Content-Type', 'application/json'), ('Content-Length', str(limit + 1))]
            with self.assertRaises(AuthorizationTransportError):
                transport.prepare()
        transport, opener = fixture()
        opener.queue[0] = {'raw': b'x' * 131073, 'headers': [('Content-Type', 'application/json')]}
        with self.assertRaises(AuthorizationTransportError):
            transport.prepare()

    def test_return_requires_own_session_and_cannot_be_repeated(self):
        transport, opener = fixture()
        with self.assertRaises(AuthorizationTransportError):
            transport.return_result(DISPATCH, LEASE, b'output')
        self.assertEqual(len(opener.calls), 0)
        transport.prepare()
        for dispatch, lease, raw in [('33333333-3333-4333-8333-333333333333', LEASE, b'output'),
                                     (DISPATCH, {**LEASE, 'fence': 2}, b'output'), (DISPATCH, LEASE, bytearray(b'output'))]:
            with self.assertRaises(AuthorizationTransportError):
                transport.return_result(dispatch, lease, raw)
        self.assertEqual(len(opener.calls), 2)
        transport.return_result(DISPATCH, LEASE, b'output')
        with self.assertRaises(AuthorizationTransportError):
            transport.return_result(DISPATCH, LEASE, b'output')
        self.assertEqual(len(opener.calls), 4)

    def test_uncertain_network_failures_are_sanitized_and_never_retried(self):
        for failed in [0, 1, 2, 3]:
            transport, opener = fixture()
            opener.queue[failed] = OSError('SECRET-credential response body https://private.example')
            if failed >= 2:
                transport.prepare()
            with self.assertRaises(AuthorizationTransportError) as error:
                transport.prepare() if failed < 2 else transport.return_result(DISPATCH, LEASE, b'output')
            self.assertEqual(str(error.exception), 'validation transport request failed')
            with self.assertRaises(AuthorizationTransportError):
                transport.prepare() if failed < 2 else transport.return_result(DISPATCH, LEASE, b'output')
            self.assertEqual(len(opener.calls), failed + 1)

    def test_ambiguous_return_response_is_not_success(self):
        for raw in [b'not-json', b'[]', b'{"state":"a","state":"b"}']:
            transport, opener = fixture()
            opener.queue[3]['raw'] = raw
            transport.prepare()
            with self.assertRaises(AuthorizationTransportError):
                transport.return_result(DISPATCH, LEASE, b'output')
            with self.assertRaises(AuthorizationTransportError):
                transport.return_result(DISPATCH, LEASE, b'output')
            self.assertEqual(len(opener.calls), 4)


if __name__ == '__main__':
    unittest.main()
