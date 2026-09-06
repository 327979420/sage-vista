"""Actual local Git policy sources, no supplier calls or configuration writes."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from services.contracts.configuration import BASELINE_BLOBS, DEFINITION_COMMIT, POLICY_PINS
from services.contracts.validation import ContractError, publication_configuration_body, verify_publication_configuration
from services.publication import configuration as producer


def raw(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode() + b'\n'


class ConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=producer.ROOT, text=True).strip()
        cls.sources = producer.read_configuration_sources(cls.commit)
        cls.body = publication_configuration_body(cls.sources)

    def test_real_git_configuration_freezes_all_policies_versions_and_unavailable_boundaries(self):
        config = producer.build_research_configuration(self.commit)
        body = json.loads(config.raw_bytes)
        self.assertEqual(body, self.body)
        self.assertEqual(len(body['policies']), 9)
        for key, digest in POLICY_PINS.items(): self.assertEqual(body['policies'][key]['policy_fingerprint'], 'sha256:' + digest)
        self.assertEqual(body['policies']['M07.ranking']['rules']['selected_limit'], 5)
        self.assertEqual(body['policies']['M08.plan']['rules']['max_hold_sessions'], 40)
        self.assertEqual(body['policies']['M10.forward_window']['rules']['window_sessions'], [1, 5, 20, 60, 100])
        self.assertEqual(body['boundaries']['active_strategies'], [])
        self.assertEqual(body['boundaries']['portfolio'], 'unavailable')
        self.assertEqual(body['membership']['historical_membership_backfill'], False)
        self.assertEqual(body['qualification']['min_history_sessions'], 420)
        self.assertEqual(body['code_commit'], self.commit)
        self.assertEqual(body['definition_commit'], DEFINITION_COMMIT)
        self.assertEqual(len(body['definition_sources']), 113)
        self.assertLess(len(config.raw_bytes), 1024 * 1024)
        self.assertEqual(dict(config.config_ref), verify_publication_configuration(config.raw_bytes, self.sources))
        with self.assertRaises(TypeError): config.config_ref['id'] = 'other'
        with self.assertRaises(FrozenInstanceError): config.raw_bytes = b'{}'

    def test_source_pin_inventory_matches_actual_approved_git_tree(self):
        rows = subprocess.check_output(['git', '--no-replace-objects', 'ls-tree', '-r', DEFINITION_COMMIT, '--',
                                        'services', 'public/factor-registry.json', 'data/context/etf-registry-v1.json'], cwd=producer.ROOT, text=True)
        actual = {}
        for row in rows.splitlines():
            metadata, path = row.split('\t'); mode, kind, blob = metadata.split()
            if path in {'services/contracts/validation.py', 'services/scanner/eodhd.py'}: continue
            self.assertEqual(kind, 'blob'); actual[path] = (mode, blob)
        self.assertEqual(BASELINE_BLOBS, actual)

    def test_missing_extra_mutated_blob_mode_or_definition_label_cannot_pass(self):
        path = 'services/ranking/policies.py'
        for group in ('definition_sources', 'runtime_sources'):
            for mutation in ('missing', 'extra', 'bytes', 'mode', 'blob'):
                sources = deepcopy(self.sources)
                if mutation == 'missing': del sources[group][path]
                elif mutation == 'extra': sources[group]['other.py'] = sources[group][path]
                elif mutation == 'bytes': sources[group][path]['bytes'] += b'# altered'
                elif mutation == 'mode': sources[group][path]['mode'] = '120000'
                else: sources[group][path]['blob'] = '0' * 40
                with self.subTest(group=group, mutation=mutation), self.assertRaises(ContractError):
                    publication_configuration_body(sources)
        sources = deepcopy(self.sources); sources['definition_commit'] = self.commit
        with self.assertRaises(ContractError): publication_configuration_body(sources)

    def test_resealed_policy_and_boundary_changes_are_not_approved_configuration(self):
        for key in self.body['policies']:
            body = deepcopy(self.body)
            body['policies'][key]['rules']['extra'] = 'changed'
            with self.subTest(policy=key), self.assertRaises(ContractError): verify_publication_configuration(raw(body), self.sources)
        for key, value in [('active_strategies', ['fake']), ('portfolio', 'available'), ('context_ranking_effect', 'add_score')]:
            body = deepcopy(self.body); body['boundaries'][key] = value
            with self.assertRaises(ContractError): verify_publication_configuration(raw(body), self.sources)
        body = deepcopy(self.body); body['qualification']['min_history_sessions'] = 100
        with self.assertRaises(ContractError): verify_publication_configuration(raw(body), self.sources)

    def test_runtime_policy_object_cannot_drift_behind_unchanged_version(self):
        from services.ranking import policies
        changed = policies.build_policy(kind='score', version='1.0.0', name='technical_resonance_count', rules={'different': 1})
        with patch.object(policies, 'SCORE_POLICY', changed), self.assertRaisesRegex(ContractError, 'policy content drift'):
            publication_configuration_body(self.sources)

    def test_whitespace_is_same_config_but_other_explicit_commit_has_other_identity(self):
        plain = verify_publication_configuration(raw(self.body), self.sources)
        spaced = verify_publication_configuration(json.dumps(self.body, indent=2).encode(), self.sources)
        self.assertEqual(plain, spaced)
        other = producer.build_research_configuration(DEFINITION_COMMIT)
        self.assertNotEqual(dict(other.config_ref), plain)
        self.assertEqual(json.loads(other.raw_bytes)['code_commit'], DEFINITION_COMMIT)

    def test_invalid_unknown_commits_and_extra_root_argument_fail(self):
        for commit in ('HEAD', 'main', '--help', 'a' * 39, '../other'):
            with self.assertRaises(producer.ConfigurationSourceError): producer.build_research_configuration(commit)
        with self.assertRaises(producer.ConfigurationSourceError): producer.build_research_configuration('0' * 40)
        with self.assertRaises(TypeError): producer.build_research_configuration(self.commit, root=Path('/tmp'))

    def test_git_uses_fixed_root_no_replace_objects_no_lazy_network_or_inherited_credentials(self):
        with patch.object(producer.subprocess, 'run', return_value=SimpleNamespace(stdout=b'synthetic')) as call:
            self.assertEqual(producer._git('cat-file', 'blob', 'a' * 40), b'synthetic')
        args, kwargs = call.call_args
        self.assertEqual(args[0][:4], ['/usr/bin/git', '--no-replace-objects', '-C', str(producer.ROOT)])
        self.assertEqual(kwargs['env']['GIT_ALLOW_PROTOCOL'], '')
        self.assertEqual(kwargs['env']['GIT_NO_LAZY_FETCH'], '1')
        self.assertNotIn('EODHD_API_TOKEN', kwargs['env'])
        self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)
        with patch.object(producer.subprocess, 'run', side_effect=RuntimeError('private credential')):
            with self.assertRaisesRegex(producer.ConfigurationSourceError, '^configuration_git_source_unavailable$'):
                producer._git('cat-file', 'blob', 'a' * 40)

    def test_config_decoder_is_strict_and_cannot_drop_source_or_add_fields(self):
        for encoded in (b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', bytearray(raw(self.body))):
            with self.assertRaises(ContractError): verify_publication_configuration(encoded, self.sources)
        for mutation in ('missing', 'extra'):
            body = deepcopy(self.body)
            if mutation == 'missing': body['definition_sources'].pop()
            else: body['allowed_to_run'] = True
            with self.assertRaises(ContractError): verify_publication_configuration(raw(body), self.sources)


if __name__ == '__main__': unittest.main()
