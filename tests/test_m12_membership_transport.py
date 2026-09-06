import base64
from copy import deepcopy
import hashlib
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_m12_authorization_transport import Response, ENV, ORIGIN
from services.publication import authorization_transport as http
from services.publication.membership_transport import MembershipArchiveTransport, MembershipTransportError, PROTOCOL
from services.scanner.eodhd import MEMBERSHIP_URL, MEMBERSHIP_MAX_BYTES

RAW = b'a'
DESC = {'key': 'raw/' + hashlib.sha256(RAW).hexdigest(), 'sha256': 'sha256:' + hashlib.sha256(RAW).hexdigest(), 'size_bytes': 1}
EXPECTED = {k: DESC[k] for k in ('sha256', 'size_bytes')}
READ = {'protocol': PROTOCOL, **DESC, 'bytes_base64': base64.b64encode(RAW).decode()}
PERMIT = {**READ, 'as_of': '2026-09-08', 'request_url': MEMBERSHIP_URL}


class Opener:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def open(self, request, timeout):
        self.calls.append(request)
        if '.actions.githubusercontent.com/' in request.full_url:
            value = {'value': f'fresh{len(self.calls)}.token.signature'}
        else:
            value = self.responses.pop(0)
            if isinstance(value, Exception):
                raise value
        return Response(json.dumps(value).encode(), request.full_url)


class MembershipTransportTests(unittest.TestCase):
    def client(self, *responses):
        opener = Opener(responses)
        return MembershipArchiveTransport(ORIGIN, ENV, opener=opener), opener

    def test_three_fixed_routes_use_fresh_tokens_and_exact_bytes(self):
        client, opener = self.client(PERMIT, {'protocol': PROTOCOL, **DESC}, READ)
        self.assertEqual(client.authorize(as_of='2026-09-08', request_url=MEMBERSHIP_URL), RAW)
        self.assertEqual(client.put(DESC['key'], RAW, EXPECTED), DESC)
        self.assertEqual(client.read(DESC['key'], EXPECTED), RAW)
        requests = opener.calls[1::2]
        self.assertEqual([req.full_url for req in requests], [ORIGIN + '/v1/membership/' + op for op in ('permit', 'put', 'read')])
        self.assertEqual(len({req.get_header('Authorization') for req in requests}), 3)
        self.assertEqual(json.loads(requests[1].data), READ)

    def test_input_substitution_is_rejected_before_network(self):
        client, opener = self.client()
        for key, expected in [('authority/' + 'a' * 64, EXPECTED), (DESC['key'], {**EXPECTED, 'size_bytes': True}),
                              (DESC['key'], {**EXPECTED, 'extra': 1})]:
            with self.assertRaises(MembershipTransportError):
                client.put(key, RAW, expected)
        with self.assertRaises(MembershipTransportError):
            client.put(DESC['key'], bytearray(RAW), EXPECTED)
        with self.assertRaises(MembershipTransportError):
            client.authorize(as_of='2026-09-08', request_url=MEMBERSHIP_URL + '&type=common_stock')
        self.assertEqual(opener.calls, [])

    def test_mismatched_permit_and_read_responses_fail_closed(self):
        for operation, original in [('permit', PERMIT), ('read', READ)]:
            changes = [{'protocol': 'other'}, {'size_bytes': True}, {'bytes_base64': 'Yg=='},
                       {'bytes_base64': 'YQ==\n'}, {'extra': 'unknown'}, {'key': 'raw/' + 'b' * 64}]
            if operation == 'permit':
                changes += [{'as_of': '2026-09-09'}, {'request_url': 'https://other.test'}]
            for change in changes:
                with self.subTest(operation=operation, change=change):
                    client, opener = self.client({**deepcopy(original), **change})
                    with self.assertRaises(MembershipTransportError):
                        if operation == 'permit':
                            client.authorize(as_of='2026-09-08', request_url=MEMBERSHIP_URL)
                        else:
                            client.read(DESC['key'], EXPECTED)
                    self.assertEqual(len(opener.calls), 2)

    def test_put_ack_requires_exact_integer_descriptor_and_no_automatic_retry(self):
        for value in [{'protocol': PROTOCOL, **DESC, 'size_bytes': True}, {'protocol': PROTOCOL, **DESC, 'extra': 1},
                      TimeoutError('secret-provider-token')]:
            client, opener = self.client(value)
            with self.assertRaises(MembershipTransportError) as error:
                client.put(DESC['key'], RAW, EXPECTED)
            self.assertNotIn('secret', str(error.exception))
            self.assertEqual(len(opener.calls), 2)

    def test_default_channel_reuses_isolated_worker(self):
        client = MembershipArchiveTransport(ORIGIN, ENV)
        with patch.object(http, '_isolated_request', side_effect=[b'{"value":"fresh.token.signature"}', json.dumps(READ).encode()]) as worker:
            self.assertEqual(client.read(DESC['key'], EXPECTED), RAW)
        self.assertEqual(worker.call_args_list[1].args[0], ORIGIN + '/v1/membership/read')
        self.assertEqual(worker.call_args_list[1].kwargs['limit'], http.ARCHIVE_RESPONSE_LIMIT)

    def test_worker_new_envelope_budget_does_not_relax_old_operation_limit(self):
        def invoke(limit):
            payload = http._body({'url': ORIGIN + '/v1/membership/put', 'token': 'synthetic', 'limit': limit,
                                  'data_base64': base64.b64encode(b'x' * 600).decode()})
            stdout = io.BytesIO()
            with patch.object(http.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(payload))), \
                 patch.object(http.sys, 'stdout', SimpleNamespace(buffer=stdout)), \
                 patch.object(http, 'PREPARE_LIMIT', 512), patch.object(http, '_blocking_request', return_value=b'{}') as call:
                status = http._http_worker_main()
            return status, call.call_count, stdout.getvalue()
        self.assertEqual(invoke(131072), (1, 0, b''))
        self.assertEqual(invoke(http.ARCHIVE_RESPONSE_LIMIT), (0, 1, b'{}'))

    def test_max_captured_body_fits_both_base64_envelopes_and_oversize_rejected(self):
        raw = b'x' * (MEMBERSHIP_MAX_BYTES + 1)
        digest = hashlib.sha256(raw).hexdigest()
        entry = {'key': 'raw/' + digest, 'sha256': 'sha256:' + digest, 'size_bytes': len(raw)}
        client, _ = self.client({'protocol': PROTOCOL, **entry})
        # Actual largest client JSON serialization, but no real network.
        client.put(entry['key'], raw, {k: entry[k] for k in ('sha256', 'size_bytes')})
        data = http._body({'protocol': PROTOCOL, **entry, 'bytes_base64': base64.b64encode(raw).decode()})
        envelope = http._body({'url': ORIGIN + '/v1/membership/put', 'token': 'x' * 65536,
                              'limit': http.ARCHIVE_RESPONSE_LIMIT, 'data_base64': base64.b64encode(data).decode()})
        self.assertLess(len(data), http.ARCHIVE_RESPONSE_LIMIT)
        self.assertLess(len(envelope), http.ARCHIVE_WORKER_LIMIT)
        with self.assertRaises(MembershipTransportError):
            client.put(entry['key'], raw, {'sha256': entry['sha256'], 'size_bytes': len(raw) + 1})


if __name__ == '__main__':
    unittest.main()
