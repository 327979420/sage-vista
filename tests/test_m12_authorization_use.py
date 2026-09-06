"""Necessary current-use checks over synthetic trusted index/config byte inputs."""
from copy import deepcopy
import hashlib
import json
import unittest

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError, publication_preparation_authorization
from services.publication.authorization import build_publication_authorization
from tests.test_m12_authorization import approval, authorization_ref

DAY = '2026-09-08'
CHECKED = '2026-09-09T03:59:59Z'  # Still September 8 in New York.
CONFIG = {'scope': 'complex_multifactor_main', 'synthetic_policy': 'not a production configuration'}


def raw(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode() + b'\n'


def archive(data, key=None):
    digest = hashlib.sha256(data).hexdigest()
    return {'key': key or 'raw/' + digest, 'sha256': 'sha256:' + digest, 'size_bytes': len(data)}


def fixture(actions=('grant',), *, valid_until=None, config=CONFIG):
    records = []
    for action in actions:
        evidence = approval()
        evidence['history'] = deepcopy(records)
        evidence['request'].update(action=action, config_ref={'id': 'configuration', 'content_fingerprint': canonical_fingerprint(config)},
            valid_until=valid_until, prior_authorization_ref=authorization_ref(records[-1]) if records else None,
            permissions=[] if action == 'revoke' else ['prepare', 'publish', 'notify', 'rollback'])
        records.append(build_publication_authorization(evidence, generated_at='2026-09-08T00:00:00Z'))
    originals = [raw(record) for record in records]
    entries = [{'reference': authorization_ref(record), 'previous_ref': record['prior_authorization_ref'],
                'archive': archive(data, 'authority/' + record['content_fingerprint'][7:] + '.json')}
               for record, data in zip(records, originals)]
    config_bytes = raw(config)
    return {'current_history': {'revision': len(records), 'head': entries[-1]['reference'] if entries else None, 'history': entries},
            'history_bytes': originals, 'config_ref': {'id': 'configuration', 'content_fingerprint': canonical_fingerprint(config)},
            'config_archive': archive(config_bytes), 'config_bytes': config_bytes, 'code_commit': 'a' * 40,
            'as_of': DAY, 'checked_at': CHECKED}


class AuthorizationUseTests(unittest.TestCase):
    def test_current_grant_binds_config_actual_bytes_code_and_complete_index(self):
        evidence = fixture()
        result = publication_preparation_authorization(evidence)
        self.assertEqual(result['authorization_ref'], evidence['current_history']['head'])
        self.assertEqual(result['config_archive'], archive(evidence['config_bytes']))
        self.assertEqual(result['history_revision'], 1)
        self.assertNotIn('authorized', result)
        self.assertNotIn('permissions', result)
        result['authorization_ref']['id'] = 'mutated'
        self.assertNotEqual(result['authorization_ref'], evidence['current_history']['head'])

    def test_revoke_is_immediate_and_old_grant_is_not_selected(self):
        with self.assertRaisesRegex(ContractError, 'current head'):
            publication_preparation_authorization(fixture(('grant', 'revoke')))
        self.assertEqual(publication_preparation_authorization(fixture(('grant', 'revoke', 'grant')))['history_revision'], 3)

    def test_empty_or_incomplete_wrong_head_duplicate_or_reordered_chain_fails(self):
        with self.assertRaises(ContractError):
            publication_preparation_authorization(fixture(()))
        changes = [lambda e: e['history_bytes'].pop(), lambda e: e['current_history']['history'].pop(),
                   lambda e: e['current_history'].update(revision=True),
                   lambda e: e['current_history'].update(head=e['current_history']['history'][0]['reference']),
                   lambda e: e['history_bytes'].reverse(),
                   lambda e: e['history_bytes'].__setitem__(1, e['history_bytes'][0])]
        for change in changes:
            evidence = fixture(('grant', 'revoke', 'grant'))
            change(evidence)
            with self.subTest(change=change), self.assertRaises(ContractError):
                publication_preparation_authorization(evidence)

    def test_mismatched_raw_history_hash_or_resealed_prior_relationship_fails(self):
        evidence = fixture(('grant', 'revoke', 'grant'))
        for key, value in [('sha256', 'sha256:' + '0' * 64), ('size_bytes', True), ('key', 'raw/' + '0' * 64)]:
            wrong = deepcopy(evidence)
            wrong['current_history']['history'][0]['archive'][key] = value
            with self.subTest(key=key), self.assertRaises(ContractError):
                publication_preparation_authorization(wrong)
        wrong = deepcopy(evidence)
        wrong['history_bytes'][0] = wrong['history_bytes'][0] + b' '
        with self.assertRaises(ContractError): publication_preparation_authorization(wrong)

    def test_current_other_config_or_code_never_falls_back(self):
        for change in [lambda e: e.update(code_commit='b' * 40), lambda e: e['config_ref'].update(id='alias')]:
            evidence = fixture(); change(evidence)
            with self.assertRaises(ContractError): publication_preparation_authorization(evidence)
        # A valid index headed by another approved configuration is not permission for CONFIG.
        other = fixture(config={'scope': 'other approved synthetic configuration'})
        for key in ('config_ref', 'config_archive', 'config_bytes'): other[key] = fixture()[key]
        with self.assertRaises(ContractError): publication_preparation_authorization(other)

    def test_expiry_uses_both_target_and_current_new_york_date(self):
        evidence = fixture(valid_until=DAY)
        publication_preparation_authorization(evidence)
        evidence['checked_at'] = '2026-09-09T04:00:00Z'
        with self.assertRaisesRegex(ContractError, 'target and current dates'):
            publication_preparation_authorization(evidence)  # Old D remains in range; now is not.
        evidence = fixture()
        evidence['as_of'] = '2026-09-07'
        with self.assertRaises(ContractError): publication_preparation_authorization(evidence)
        evidence = fixture(); evidence['checked_at'] = '2026-09-08T03:59:59Z'
        with self.assertRaises(ContractError): publication_preparation_authorization(evidence)

    def test_future_target_record_or_noncanonical_checked_time_fails(self):
        for stamp in ['2026-09-07T23:00:00Z', '2026-09-09T03:59:59+00:00', '2026-09-09T03:59:59.000Z', '0001-01-01T00:00:00Z']:
            evidence = fixture(); evidence['checked_at'] = stamp
            with self.assertRaises(ContractError): publication_preparation_authorization(evidence)
        evidence = fixture(); evidence['as_of'] = '2026-09-09'
        with self.assertRaises(ContractError): publication_preparation_authorization(evidence)
        evidence = fixture()
        record = json.loads(evidence['history_bytes'][0]); record['generated_at'] = '2026-09-10T00:00:00Z'
        data = raw(record); evidence['history_bytes'][0] = data
        evidence['current_history']['history'][0]['archive'] = archive(data, evidence['current_history']['history'][0]['archive']['key'])
        with self.assertRaisesRegex(ContractError, 'future'): publication_preparation_authorization(evidence)

    def test_configuration_actual_hash_semantic_fingerprint_and_strict_json(self):
        for data in [b'{}', b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b'[]', b'']:
            evidence = fixture(); evidence.update(config_bytes=data, config_archive=archive(data))
            with self.subTest(data=data), self.assertRaises(ContractError): publication_preparation_authorization(evidence)
        evidence = fixture(); evidence['config_bytes'] += b' '
        with self.assertRaises(ContractError): publication_preparation_authorization(evidence)
        evidence = fixture(); evidence['config_archive']['size_bytes'] = True
        with self.assertRaises(ContractError): publication_preparation_authorization(evidence)
        evidence = fixture(); evidence['config_bytes'] = bytearray(evidence['config_bytes'])
        with self.assertRaises(ContractError): publication_preparation_authorization(evidence)

    def test_whitespace_changes_raw_archive_but_not_approved_config_semantics(self):
        evidence = fixture(); original = publication_preparation_authorization(evidence)
        data = json.dumps(CONFIG, indent=2).encode()
        evidence.update(config_bytes=data, config_archive=archive(data))
        current = publication_preparation_authorization(evidence)
        self.assertEqual(original['config_ref'], current['config_ref'])
        self.assertNotEqual(original['config_archive'], current['config_archive'])

    def test_evidence_is_exact_and_check_does_not_mutate_input(self):
        evidence = fixture(); before = deepcopy(evidence)
        publication_preparation_authorization(evidence)
        self.assertEqual(evidence, before)
        for key in list(evidence):
            wrong = deepcopy(evidence); del wrong[key]
            with self.assertRaises(ContractError): publication_preparation_authorization(wrong)
        evidence['operation'] = 'publish'
        with self.assertRaises(ContractError): publication_preparation_authorization(evidence)


if __name__ == '__main__':
    unittest.main()
