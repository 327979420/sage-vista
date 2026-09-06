"""Synthetic grants and identities, actual fixed local Git; no live authority."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
from zoneinfo import ZoneInfo

from services.contracts.validation import (ContractError, publication_preparation_input,
    publication_preparation_check, publication_preparation_completion)
from services.publication.configuration import build_research_configuration, read_configuration_sources, ROOT
from services.publication.preparation_validation import validate_preparation_input
from services.publication.authorization import build_publication_authorization
from tests.test_m12_authorization import approval, authorization_ref
from tests.test_m12_authorization_use import archive, raw


def fixture(commit, config, now, *, revoke=False):
    stamp = datetime.fromtimestamp(now // 1000, timezone.utc)
    day = stamp.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    generated = stamp.isoformat(timespec='seconds').replace('+00:00', 'Z')
    records = []
    for action in (('grant', 'revoke') if revoke else ('grant',)):
        a = approval()
        a['history'] = deepcopy(records)
        a['request'].update(code_commit=commit, config_ref=dict(config.config_ref), effective_from=day,
            action=action, permissions=[] if action == 'revoke' else ['prepare', 'publish', 'notify', 'rollback'],
            prior_authorization_ref=authorization_ref(records[-1]) if records else None)
        records.append(build_publication_authorization(a, generated_at=generated))
    originals = [raw(record) for record in records]
    history = [{'reference': authorization_ref(record), 'previous_ref': record['prior_authorization_ref'],
                'archive': archive(data, 'authority/' + record['content_fingerprint'][7:] + '.json')}
               for record, data in zip(records, originals)]
    identity = {'job': {'repository_id': '123', 'workflow_ref': 'repo/workflow@refs/heads/main',
        'workflow_commit': 'b' * 40, 'run_id': '456', 'run_attempt': 1, 'environment': 'production'},
        'code_commit': commit, 'actor_id': '789', 'subject': 'synthetic', 'token_id': 'test-only',
        'issued_at': now // 1000 - 60, 'expires_at': now // 1000 + 300}
    evidence = {'current_history': {'revision': len(records), 'head': history[-1]['reference'], 'history': history},
        'history_base64': [base64.b64encode(data).decode() for data in originals],
        'config_ref': dict(config.config_ref), 'config_archive': archive(config.raw_bytes),
        'config_base64': base64.b64encode(config.raw_bytes).decode(), 'code_commit': commit,
        'as_of': day, 'checked_at': generated}
    return {'protocol': 'm12-preparation-validation/1', 'identity': identity, 'evidence': evidence}


class PreparationValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        cls.config = build_research_configuration(cls.commit)
        cls.sources = read_configuration_sources(cls.commit)
        cls.now = time.time_ns() // 1_000_000
        cls.wire = fixture(cls.commit, cls.config, cls.now)

    def test_combined_check_and_input_binding_use_actual_git_config(self):
        data = raw(self.wire)
        times = iter([self.now, self.now + 1])
        result = json.loads(validate_preparation_input(data, clock=lambda: next(times)))
        self.assertEqual(result['input_sha256'], 'sha256:' + hashlib.sha256(data).hexdigest())
        self.assertEqual(result['input_size_bytes'], len(data))
        self.assertEqual(result['preparation']['config_ref'], dict(self.config.config_ref))
        self.assertEqual(result['preparation']['authorization_ref'], self.wire['evidence']['current_history']['head'])
        self.assertNotIn('authorized', result)
        self.assertNotIn('permissions', result['preparation'])

    def test_revoke_and_altered_original_fail_combined_entry(self):
        wire = fixture(self.commit, self.config, self.now, revoke=True)
        with self.assertRaisesRegex(ContractError, 'current head'):
            publication_preparation_check(publication_preparation_input(raw(wire)), self.sources, started_ms=self.now, completed_ms=self.now)
        value = publication_preparation_input(raw(self.wire))
        value['evidence']['history_bytes'][0] += b' '
        with self.assertRaises(ContractError): publication_preparation_check(value, self.sources, started_ms=self.now, completed_ms=self.now)

    def test_config_even_with_matching_grant_cannot_change_approved_policy(self):
        from types import SimpleNamespace
        body = json.loads(self.config.raw_bytes); body['qualification']['min_history_sessions'] = 10
        changed = raw(body)
        from services.contracts.market_data import canonical_fingerprint
        fingerprint = canonical_fingerprint(body)
        config = SimpleNamespace(raw_bytes=changed, config_ref={'id': 'publication-config:' + fingerprint, 'content_fingerprint': fingerprint})
        wire = fixture(self.commit, config, self.now)
        with self.assertRaisesRegex(ContractError, 'frozen policy'):
            publication_preparation_check(publication_preparation_input(raw(wire)), self.sources, started_ms=self.now, completed_ms=self.now)

    def test_identity_code_source_and_exact_configuration_ref_cannot_diverge(self):
        wire = deepcopy(self.wire); wire['identity']['code_commit'] = 'a' * 40
        with self.assertRaises(ContractError): publication_preparation_input(raw(wire))
        sources = deepcopy(self.sources); sources['code_commit'] = 'a' * 40
        with self.assertRaises(ContractError): publication_preparation_check(publication_preparation_input(raw(self.wire)), sources, started_ms=self.now, completed_ms=self.now)
        from types import SimpleNamespace
        alias = SimpleNamespace(raw_bytes=self.config.raw_bytes, config_ref={**self.config.config_ref, 'id': 'alias'})
        wire = fixture(self.commit, alias, self.now)
        with self.assertRaisesRegex(ContractError, 'exact Ref'):
            publication_preparation_check(publication_preparation_input(raw(wire)), self.sources, started_ms=self.now, completed_ms=self.now)

    def test_strict_wire_and_identity_structure(self):
        for encoded in (b'{}', b'{"protocol":1,"protocol":2}', b'{"a":NaN}', bytearray(raw(self.wire))):
            with self.assertRaises(ContractError): publication_preparation_input(encoded)
        for change in [lambda w: w.update(protocol='other'), lambda w: w.update(authorized=True),
            lambda w: w['evidence'].update(config_base64='Zg==\n'), lambda w: w['evidence'].update(config_base64='Zh=='),
            lambda w: w['evidence'].update(history_base64={}), lambda w: w['identity'].update(expires_at=True),
            lambda w: w['identity']['job'].update(run_attempt=0), lambda w: w['identity'].update(actor_id='alias')]:
            wire = deepcopy(self.wire); change(wire)
            with self.assertRaises(ContractError): publication_preparation_input(raw(wire))

    def test_computation_window_rejects_expiry_clock_reversal_and_future_observation(self):
        value = publication_preparation_input(raw(self.wire))
        expires = value['identity']['expires_at'] * 1000
        for start, end in [(self.now, expires), (self.now, self.now - 1), (self.now - 2000, self.now), (True, self.now), (self.now, 10**30)]:
            with self.assertRaises(ContractError): publication_preparation_completion(value, started_ms=start, completed_ms=end)
        times = iter([self.now, expires])
        with self.assertRaises(ContractError): validate_preparation_input(raw(self.wire), clock=lambda: next(times))

    def test_completion_rechecks_grant_expiry_across_new_york_midnight(self):
        start = int(datetime(2026, 9, 9, 3, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
        wire = fixture(self.commit, self.config, start)
        value = publication_preparation_input(raw(wire))
        record = json.loads(value['evidence']['history_bytes'][0])
        a = approval(); a['request'].update({key: record[key] for key in a['request']})
        a['request']['valid_until'] = '2026-09-08'
        record = build_publication_authorization(a, generated_at='2026-09-09T03:59:59Z')
        data = raw(record); entry = {'reference': authorization_ref(record), 'previous_ref': None,
            'archive': archive(data, 'authority/' + record['content_fingerprint'][7:] + '.json')}
        value['evidence'].update(history_bytes=[data], current_history={'revision': 1, 'head': entry['reference'], 'history': [entry]})
        publication_preparation_check(value, self.sources, started_ms=start, completed_ms=start)
        with self.assertRaisesRegex(ContractError, 'effective'):
            publication_preparation_completion(value, started_ms=start, completed_ms=start + 1000)

    def test_fixed_isolated_worker_roundtrip_and_failure_has_no_private_output(self):
        worker = ROOT / 'services/publication/preparation_validation_worker.py'
        wire = fixture(self.commit, self.config, time.time_ns() // 1_000_000)
        data = raw(wire)
        result = subprocess.run([sys.executable, '-I', '-B', str(worker)], input=data,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd='/tmp', env={}, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['input_sha256'], 'sha256:' + hashlib.sha256(data).hexdigest())
        bad = subprocess.run([sys.executable, '-I', '-B', str(worker)], input=b'private invalid bytes',
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd='/tmp', env={}, timeout=20)
        self.assertNotEqual(bad.returncode, 0)
        self.assertEqual((bad.stdout, bad.stderr), (b'', b''))


if __name__ == '__main__': unittest.main()
