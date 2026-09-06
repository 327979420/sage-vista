"""Private local journal and controlled client recovery, no real HTTP."""
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_m12_authorization_transport import ENV, ORIGIN, LEASE, DISPATCH, PREPARED, Opener, encoded
from services.publication import authorization_recovery as module
from services.publication.authorization_recovery import RecoverableAuthorizationTransport as Client
from services.publication.authorization_recovery import AuthorizationRecoveryJournal as Journal
from services.publication.authorization_transport import AuthorizationTransportError


def output():
    authorization = b'{}'  # Transport metadata sample, not business authorization.
    receipt = {'input_sha256': PREPARED['input_sha256'], 'input_size_bytes': PREPARED['input_size_bytes'],
               'validated_at': '2026-09-06T00:00:00.000Z', 'authorization_archive': {
                   'key': 'authority/' + 'a' * 64 + '.json', 'sha256': 'sha256:' + hashlib.sha256(authorization).hexdigest(), 'size_bytes': len(authorization)}}
    return encoded({'authorization_base64': base64.b64encode(authorization).decode(), 'receipt_base64': base64.b64encode(encoded(receipt)).decode()})


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory(prefix='m12-recovery-'))
        self.opener = Opener()
        self.client = Client(ORIGIN, ENV, recovery_directory=self.directory, opener=self.opener)
        self.client.prepare()

    def returned(self):
        self.client.return_result(DISPATCH, LEASE, output())
        return self.client.recovery_id

    def recovery_client(self, recovery_id, mutate=None, origin=ORIGIN):
        handle = Journal(self.directory).read(recovery_id)
        response = {'protocol': 'm12-authorization-job/1', 'dispatch_id': DISPATCH, 'state': 'archived_return_verified',
                    'authorization_archive': handle['authorization_archive'], 'validation_receipt_archive': handle['validation_receipt_archive'],
                    'input_sha256': handle['input_sha256'], 'recorded_at': handle['validated_at']}
        if mutate: mutate(response)
        opener = Opener(); opener.queue = [{'raw': encoded({'value': 'fresh.token.signature'})}, {'raw': encoded(response)}]
        return Client(origin, ENV, recovery_directory=self.directory, opener=opener), opener, response

    def test_handle_durable_and_read_verified_before_return_http_without_tokens_or_private_body(self):
        original = self.opener.open
        observed = []
        def open_request(request, timeout):
            if request.full_url.endswith('/return'):
                handle = Journal(self.directory).read(self.client.recovery_id)
                observed.append(handle)
            return original(request, timeout)
        self.opener.open = open_request
        recovery_id = self.returned()
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]['dispatch_id'], DISPATCH)
        raw = (Path(self.directory) / (recovery_id + '.json')).read_bytes()
        for private in [b'fake-request-credential', b'second.token.signature', b'input_bytes', b'result_base64']:
            self.assertNotIn(private, raw)
        self.assertEqual(list(Path(self.directory).glob('.pending-*')), [])

    def test_lost_return_uses_new_client_only_for_exact_historical_recovery(self):
        self.opener.queue[-1] = OSError('lost response')
        with self.assertRaises(AuthorizationTransportError): self.returned()
        recovery_id = self.client.recovery_id
        self.assertIsNotNone(recovery_id)
        with self.assertRaises(AuthorizationTransportError): self.client.recover(recovery_id)
        client, opener, response = self.recovery_client(recovery_id)
        self.assertEqual(json.loads(client.recover(recovery_id)), response)
        self.assertEqual(len(opener.calls), 2)
        self.assertEqual(opener.calls[1].full_url, ORIGIN + '/v1/authorization/recover')
        payload = json.loads(opener.calls[1].data)
        self.assertEqual(set(payload), {'protocol', 'dispatch_id', 'receipt_key'})
        self.assertEqual(payload['receipt_key'], response['validation_receipt_archive']['key'])
        with self.assertRaises(AuthorizationTransportError): client.recover(recovery_id)
        with self.assertRaises(AuthorizationTransportError): client.prepare()

    def test_journal_failure_refuses_return_before_token_or_http(self):
        with patch.object(module.os, 'fsync', side_effect=OSError('private path failure')):
            with self.assertRaisesRegex(AuthorizationTransportError, '^validation recovery preparation failed$'):
                self.returned()
        self.assertEqual(len(self.opener.calls), 2)
        self.assertIsNone(self.client.recovery_id)
        self.assertEqual(list(Path(self.directory).iterdir()), [])

    def test_immutable_replay_corruption_and_symlink_fail_without_overwrite(self):
        recovery_id = self.returned(); journal = Journal(self.directory)
        handle = journal.read(recovery_id)
        self.assertEqual(journal.save(handle), recovery_id)
        path = Path(self.directory) / (recovery_id + '.json')
        path.write_bytes(b'corrupt')
        with self.assertRaises(AuthorizationTransportError): journal.read(recovery_id)
        with self.assertRaises(AuthorizationTransportError): journal.save(handle)
        self.assertEqual(path.read_bytes(), b'corrupt')
        path.unlink()
        target = Path(self.directory) / 'unrelated'; target.write_bytes(b'preserve')
        path.symlink_to(target)
        with self.assertRaises(AuthorizationTransportError): journal.read(recovery_id)
        with self.assertRaises(AuthorizationTransportError): journal.save(handle)
        self.assertEqual(target.read_bytes(), b'preserve')

    def test_exact_response_bindings_and_historical_only_state(self):
        recovery_id = self.returned()
        patches = [lambda v: v.update(state='registered'), lambda v: v.update(valid=True), lambda v: v.update(input_sha256='sha256:' + '0'*64),
                   lambda v: v['authorization_archive'].update(size_bytes=True), lambda v: v.update(recorded_at='2026-09-05T00:00:00.000Z'),
                   lambda v: v['validation_receipt_archive'].update(key='raw/' + '0'*64)]
        for change in patches:
            client, opener, _ = self.recovery_client(recovery_id, change)
            with self.assertRaisesRegex(AuthorizationTransportError, '^validation recovery failed$'): client.recover(recovery_id)
            with self.assertRaises(AuthorizationTransportError): client.recover(recovery_id)
            self.assertEqual(len(opener.calls), 2)

    def test_origin_or_identifier_mismatch_fails_before_any_network(self):
        recovery_id = self.returned()
        client, opener, _ = self.recovery_client(recovery_id, origin='https://other.example.test')
        with self.assertRaises(AuthorizationTransportError): client.recover(recovery_id)
        self.assertEqual(opener.calls, [])
        client, opener, _ = self.recovery_client(recovery_id)
        with self.assertRaises(AuthorizationTransportError): client.recover('../other')
        self.assertEqual(opener.calls, [])

    def test_invalid_result_or_other_session_does_not_create_handle_or_send_return(self):
        for raw in [b'{"valid":true}', bytearray(output())]:
            client = Client(ORIGIN, ENV, recovery_directory=self.directory, opener=Opener()); client.prepare()
            with self.assertRaises(AuthorizationTransportError): client.return_result(DISPATCH, LEASE, raw)
            self.assertIsNone(client.recovery_id)
        with self.assertRaises(AuthorizationTransportError): self.client.return_result(DISPATCH, {**LEASE, 'fence': 2}, output())
        self.assertEqual(list(Path(self.directory).iterdir()), [])
        self.assertEqual(len(self.opener.calls), 2)

    def test_missing_or_failed_recovery_response_never_authorizes_resend(self):
        recovery_id = self.returned()
        client, opener, _ = self.recovery_client(recovery_id)
        opener.queue[-1] = {'status': 409, 'raw': b'{"error":"job_not_ready"}'}
        with self.assertRaises(AuthorizationTransportError): client.recover(recovery_id)
        with self.assertRaises(AuthorizationTransportError): client.return_result(DISPATCH, LEASE, output())
        self.assertEqual(len(opener.calls), 2)
        self.assertIsNotNone(Journal(self.directory).read(recovery_id))


if __name__ == '__main__': unittest.main()
