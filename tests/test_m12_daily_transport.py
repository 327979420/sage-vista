"""Synthetic channel/worker output tests; real worker linkage covered in Node."""
import base64
from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import patch

from services.publication.daily_transport import DailyPreparationTransport, DailyTransportError, PROTOCOL
from services.publication import daily_transport as module
from test_m12_authorization_transport import ENV, ORIGIN
from test_m12_membership_transport import Opener
from test_m12_authorization_use import fixture


def samples():
    e = fixture()
    raw_history, raw_config = e.pop('history_bytes'), e.pop('config_bytes')
    identity = {'job': {'repository_id': '123', 'workflow_ref': 'repo/workflow@refs/heads/main', 'workflow_commit': 'b' * 40,
        'run_id': '456', 'run_attempt': 1, 'environment': 'production'}, 'code_commit': 'a' * 40,
        'actor_id': '789', 'subject': 'repo:example/sage:environment:production', 'token_id': 'synthetic',
        'issued_at': 1, 'expires_at': 9999999999}
    raw = json.dumps({'protocol': 'm12-preparation-validation/1', 'identity': identity,
        'evidence': {**e, 'history_base64': [base64.b64encode(b).decode() for b in raw_history], 'config_base64': base64.b64encode(raw_config).decode()}}).encode()
    fingerprint = 'sha256:' + hashlib.sha256(raw).hexdigest()
    prepared = {'protocol': PROTOCOL, 'lease_token': {'epoch': '11111111-1111-4111-8111-111111111111', 'fence': 1},
        'input_sha256': fingerprint, 'input_size_bytes': len(raw), 'input_base64': base64.b64encode(raw).decode()}
    output = b'synthetic fixed worker bytes'
    out = 'sha256:' + hashlib.sha256(output).hexdigest()
    returned = {'protocol': PROTOCOL, 'input_sha256': fingerprint,
        'output_archive': {'key': 'raw/' + out[7:], 'sha256': out, 'size_bytes': len(output)}}
    env = {**ENV, 'GITHUB_REPOSITORY': 'example/sage', 'GITHUB_REPOSITORY_ID': '123', 'GITHUB_WORKFLOW_REF': identity['job']['workflow_ref'],
        'GITHUB_WORKFLOW_SHA': 'b' * 40, 'GITHUB_SHA': 'a' * 40, 'GITHUB_RUN_ID': '456', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_ACTOR_ID': '789'}
    return raw, prepared, output, returned, env


class DailyTransportTests(unittest.TestCase):
    def test_fixed_paths_fresh_tokens_and_actual_output_binding(self):
        raw, prepared, output, returned, env = samples()
        opener = Opener([prepared, returned])
        client = DailyPreparationTransport(ORIGIN, env, opener=opener)
        with patch.object(module, 'execute_preparation_validation', return_value=output) as execute:
            result = client.prepare_and_validate()
        execute.assert_called_once_with(raw)
        self.assertEqual(result['as_of'], '2026-09-08')
        self.assertEqual(result['output_archive'], returned['output_archive'])
        requests = opener.calls[1::2]
        self.assertEqual([r.full_url for r in requests], [ORIGIN + '/v1/preparation/' + p for p in ('prepare', 'return')])
        self.assertNotEqual(requests[0].get_header('Authorization'), requests[1].get_header('Authorization'))
        self.assertEqual(base64.b64decode(json.loads(requests[1].data)['result_base64']), output)
        with self.assertRaises(DailyTransportError): client.prepare_and_validate()

    def test_foreign_identity_or_bad_prepare_never_runs_worker(self):
        for mutation in ('actor', 'input_hash', 'unknown', 'bool_size'):
            raw, prepared, output, returned, env = samples()
            if mutation == 'actor': env['GITHUB_ACTOR_ID'] = '790'
            if mutation == 'input_hash': prepared['input_sha256'] = 'sha256:' + '0' * 64
            if mutation == 'unknown': prepared['command'] = 'other'
            if mutation == 'bool_size': prepared['input_size_bytes'] = True
            client = DailyPreparationTransport(ORIGIN, env, opener=Opener([prepared]))
            with patch.object(module, 'execute_preparation_validation') as execute:
                with self.assertRaises(DailyTransportError): client.prepare_and_validate()
            execute.assert_not_called()
            with self.assertRaises(DailyTransportError): client.prepare_and_validate()

    def test_bad_or_uncertain_return_closes_client_and_never_retries(self):
        for changed in ('hash', 'size', 'outage'):
            raw, prepared, output, returned, env = samples()
            if changed == 'hash': returned['input_sha256'] = 'sha256:' + '0' * 64
            if changed == 'size': returned['output_archive']['size_bytes'] = True
            if changed == 'outage': returned = OSError('private detail')
            opener = Opener([prepared, returned])
            client = DailyPreparationTransport(ORIGIN, env, opener=opener)
            with patch.object(module, 'execute_preparation_validation', return_value=output):
                with self.assertRaisesRegex(DailyTransportError, '^daily preparation failed$'): client.prepare_and_validate()
            with self.assertRaises(DailyTransportError): client.prepare_and_validate()
            self.assertEqual(len(opener.calls), 4)
            with self.assertRaises(DailyTransportError): client._rpc('permit', {})

    def test_no_member_request_before_preparation_or_after_transport_failure(self):
        raw, prepared, output, returned, env = samples()
        opener = Opener([prepared, returned, OSError('failed')])
        client = DailyPreparationTransport(ORIGIN, env, opener=opener)
        with self.assertRaises(DailyTransportError): client._rpc('permit', {})
        self.assertFalse(opener.calls)
        with patch.object(module, 'execute_preparation_validation', return_value=output): client.prepare_and_validate()
        with self.assertRaises(DailyTransportError): client._rpc('permit', {})
        before = len(opener.calls)
        with self.assertRaises(DailyTransportError): client._rpc('permit', {})
        self.assertEqual(len(opener.calls), before)

    def test_malformed_membership_response_also_closes_ready_client(self):
        _, prepared, output, returned, env = samples()
        opener = Opener([prepared, returned, {}])
        client = DailyPreparationTransport(ORIGIN, env, opener=opener)
        with patch.object(module, 'execute_preparation_validation', return_value=output): client.prepare_and_validate()
        from services.scanner.eodhd import MEMBERSHIP_URL
        with self.assertRaises(DailyTransportError): client.authorize(as_of='2026-09-08', request_url=MEMBERSHIP_URL)
        calls = len(opener.calls)
        with self.assertRaises(DailyTransportError): client.authorize(as_of='2026-09-08', request_url=MEMBERSHIP_URL)
        self.assertEqual(len(opener.calls), calls)


if __name__ == '__main__': unittest.main()
