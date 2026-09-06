import io
import json
import unittest
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from email.message import Message
from http.client import IncompleteRead
from unittest.mock import patch

from services.scanner import eodhd
from services.market_data.membership_collection import collect_membership, MembershipCollectionError

START = datetime(2026, 9, 8, 23, 47, tzinfo=timezone.utc)
END = datetime(2026, 9, 9, 0, 17, tzinfo=timezone.utc)
AS_OF = '2026-09-08'
RAW = b'[{"Code":"A","Type":"Common Stock","Exchange":"NYSE","Name":"A Inc","Country":"USA","Currency":"USD"}]\n'
EVIDENCE = b'synthetic trusted acquisition evidence, not a production permit'


class Response(io.BytesIO):
    def __init__(self, raw=RAW, status=200, headers=None):
        super().__init__(raw)
        self.status, self.url = status, None
        self.headers = Message()
        for k, v in (headers if headers is not None else [('Content-Length', str(len(raw)))]):
            self.headers[k] = v

    def geturl(self):
        return self.url


class MemoryArchive:
    # Synthetic private binding only; real R2 already has a separate adapter.
    def __init__(self):
        self.objects = {}
        self.calls = []

    def put(self, key, raw, expected):
        self.calls.append(('put', key))
        self.objects.setdefault(key, raw)

    def read(self, key, expected):
        self.calls.append(('read', key))
        return self.objects[key]


class MembershipCollectionTests(unittest.TestCase):
    def collect(self, response=None, *, archive=None, end=END, authorize=None, opener=None):
        response = response if response is not None else Response()
        archive = archive or MemoryArchive()
        def open_request(request):
            self.assertIn(EVIDENCE, archive.objects.values())  # Saved BEFORE network.
            self.assertEqual(archive.calls[-1][0], 'read')
            parts = urllib.parse.urlsplit(request.full_url)
            self.assertEqual(parts.scheme, 'https')
            self.assertEqual(parts.netloc, 'eodhd.com')
            self.assertEqual(parts.path, '/api/exchange-symbol-list/US')
            self.assertEqual(urllib.parse.parse_qs(parts.query),
                             {'delisted': ['0'], 'fmt': ['json'], 'api_token': ['private-token']})
            self.assertEqual(request.get_header('Accept-encoding'), 'identity')
            response.url = request.full_url
            return response
        if authorize is None:
            def authorize(**request):
                self.assertEqual(request, {'as_of': AS_OF, 'request_url': eodhd.MEMBERSHIP_URL})
                return EVIDENCE
        with patch.object(eodhd, 'token', return_value='private-token'), \
             patch.object(eodhd, '_membership_open', side_effect=opener or open_request) as network, \
             patch.object(eodhd, 'datetime') as clock:
            clock.now.side_effect = [START, end]
            result = collect_membership(AS_OF, authorize=authorize, archive=archive)
            network.assert_called_once()
        self.assertTrue(response.closed if opener is None else True)
        record = json.loads(archive.objects[result.observation_key])
        self.assertNotIn('private-token', json.dumps(record))
        return result, record, archive

    def test_fixed_request_archives_exact_bytes_authority_and_observation(self):
        result, record, archive = self.collect()
        self.assertIsNone(result.failure)
        self.assertEqual(result.parsed.raw_bytes, RAW)
        self.assertEqual(record['acquisition_evidence']['size_bytes'], len(EVIDENCE))
        self.assertEqual(archive.objects[record['response']['key']], RAW)
        self.assertEqual(record['http_status'], 200)
        self.assertTrue(record['eof'])
        self.assertEqual(record['started_at'], START.isoformat())
        self.assertEqual(record['completed_at'], END.isoformat())
        self.assertEqual([v[0] for v in archive.calls], ['put', 'read'] * 3)
        self.assertNotIn('complete', record)
        self.assertNotIn('universe_id', record)

    def test_json_failure_saved_before_parser_and_observation_retained(self):
        from services.market_data import membership_collection as module
        archive = MemoryArchive()
        actual = module.parse_us_symbol_response
        def parse(raw, **kwargs):
            self.assertIn(raw, archive.objects.values())
            self.assertEqual(archive.calls[-1][0], 'read')
            return actual(raw, **kwargs)
        with patch.object(module, 'parse_us_symbol_response', side_effect=parse):
            result, record, _ = self.collect(Response(b'[{'), archive=archive)
        self.assertEqual(result.failure, 'membership_response_json_invalid')
        self.assertIsNone(result.parsed)
        self.assertEqual(record['response']['size_bytes'], 2)

    def test_non_200_and_http_error_preserve_body_with_no_retry(self):
        for status in (302, 401, 429, 503):
            with self.subTest(status=status):
                response = urllib.error.HTTPError('https://eodhd.com/private', status, 'secret', Message(), io.BytesIO(b'private error body'))
                def opener(request):
                    response.url = request.full_url
                    raise response
                result, record, archive = self.collect(opener=opener)
                self.assertEqual(result.failure, 'http_status_rejected')
                self.assertEqual(record['http_status'], status)
                self.assertEqual(archive.objects[record['response']['key']], b'private error body')
                self.assertTrue(response.closed)

    def test_partial_stream_preserved_and_not_completed(self):
        response = Response()
        with patch.object(response, 'read', side_effect=[RAW[:10], IncompleteRead(RAW[10:20], 99)]):
            result, record, archive = self.collect(response)
        self.assertEqual(result.failure, 'http_incomplete_read')
        self.assertFalse(record['eof'])
        self.assertEqual(archive.objects[record['response']['key']], RAW[:20])

    def test_timeout_after_bytes_keeps_partial_and_no_qualifying_result(self):
        response = Response()
        with patch.object(response, 'read', side_effect=[RAW[:10], TimeoutError('private-token')]):
            result, record, archive = self.collect(response)
        self.assertEqual(result.failure, 'http_transport_failed')
        self.assertFalse(record['eof'])
        self.assertIsNone(result.parsed)
        self.assertEqual(archive.objects[record['response']['key']], RAW[:10])

    def test_connection_failure_archives_empty_received_body(self):
        def opener(request):
            raise urllib.error.URLError('private-token')
        result, record, archive = self.collect(opener=opener)
        self.assertEqual(result.failure, 'http_transport_failed')
        self.assertIsNone(record['http_status'])
        self.assertFalse(record['eof'])
        self.assertEqual(archive.objects[record['response']['key']], b'')

    def test_bad_framing_or_encoding_cannot_become_success(self):
        cases = [([('Content-Length', '1')], 'http_length_mismatch'),
                 ([('Content-Length', '1'), ('Content-Length', '2')], 'http_length_invalid'),
                 ([('Content-Length', '-1')], 'http_length_invalid'),
                 ([('Content-Encoding', 'gzip')], 'http_encoding_invalid'),
                 ([('Transfer-Encoding', 'chunked'), ('Content-Length', str(len(RAW)))], 'http_encoding_invalid')]
        for headers, expected in cases:
            with self.subTest(headers=headers):
                result, record, archive = self.collect(Response(headers=headers))
                self.assertEqual(result.failure, expected)
                self.assertEqual(archive.objects[record['response']['key']], RAW)
                self.assertIsNone(result.parsed)

    def test_eof_without_content_length_is_allowed_with_valid_json(self):
        result, record, _ = self.collect(Response(headers=[]))
        self.assertIsNone(result.failure)
        self.assertIsNone(record['content_length'])
        self.assertTrue(record['eof'])

    def test_size_bound_and_budget_keep_received_prefix_as_partial(self):
        with patch.object(eodhd, 'MEMBERSHIP_MAX_BYTES', 10):
            result, record, archive = self.collect()
        self.assertEqual(result.failure, 'http_body_too_large')
        self.assertFalse(record['eof'])
        self.assertEqual(archive.objects[record['response']['key']], RAW[:11])
        with patch.object(eodhd.time, 'monotonic', side_effect=[0, 121]):
            result, record, _ = self.collect()
        self.assertEqual(result.failure, 'http_read_budget_exhausted')
        self.assertFalse(record['eof'])

    def test_cross_new_york_date_retains_raw_and_rejects_parse(self):
        result, record, archive = self.collect(end=datetime(2026, 9, 9, 4, tzinfo=timezone.utc))
        self.assertEqual(result.failure, 'membership_observation_date_invalid')
        self.assertEqual(archive.objects[record['response']['key']], RAW)

    def test_acquisition_denied_or_authority_archive_failed_never_calls_source(self):
        for evidence in (None, b'', 'unverified-reference'):
            with self.subTest(evidence=evidence), patch.object(eodhd, '_membership_open') as network:
                with self.assertRaisesRegex(MembershipCollectionError, '^membership_acquisition_not_ready$'):
                    collect_membership(AS_OF, authorize=lambda **_: evidence, archive=MemoryArchive())
                network.assert_not_called()
        archive = MemoryArchive()
        with patch.object(archive, 'read', return_value=b'wrong'), patch.object(eodhd, '_membership_open') as network:
            with self.assertRaisesRegex(MembershipCollectionError, '^membership_acquisition_not_ready$'):
                collect_membership(AS_OF, authorize=lambda **_: EVIDENCE, archive=archive)
            network.assert_not_called()

    def test_archive_failures_keep_orphans_and_do_not_return_material(self):
        for call in (2, 3):
            archive = MemoryArchive()
            original = archive.read
            count = 0
            def bad_read(*args):
                nonlocal count
                count += 1
                return b'wrong' if count == call else original(*args)
            with self.subTest(call=call), patch.object(archive, 'read', side_effect=bad_read):
                with self.assertRaisesRegex(MembershipCollectionError, '^membership_archive_failed$'):
                    self.collect(archive=archive)
                self.assertIn(RAW, archive.objects.values())

    def test_repeat_retains_original_objects_and_adds_distinct_observation(self):
        archive = MemoryArchive()
        first, _, _ = self.collect(archive=archive)
        original = dict(archive.objects)
        second, _, _ = self.collect(archive=archive, end=datetime(2026, 9, 9, 0, 18, tzinfo=timezone.utc))
        self.assertNotEqual(first.observation_key, second.observation_key)
        self.assertEqual(len(archive.objects), 4)
        for key, raw in original.items():
            self.assertEqual(archive.objects[key], raw)

    def test_default_transport_disables_redirect_and_environment_proxy(self):
        redirect = eodhd._NoMembershipRedirect()
        self.assertIsNone(redirect.redirect_request(None, None, 302, 'redirect', {}, 'https://evil.test'))
        with patch.object(eodhd.urllib.request, 'build_opener') as build:
            eodhd._membership_open('request')
            handlers = build.call_args.args
            self.assertEqual(handlers[0].proxies, {})
            self.assertIsInstance(handlers[1], eodhd._NoMembershipRedirect)
            build.return_value.open.assert_called_once_with('request', timeout=30)


if __name__ == '__main__':
    unittest.main()
