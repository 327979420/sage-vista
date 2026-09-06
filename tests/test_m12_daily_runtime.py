"""Disabled real entry and synthetic checkout guard; never call a supplier."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from services.publication import daily_runtime as module


def environment(root):
    return {'GITHUB_SHA': 'a' * 40, 'GITHUB_REPOSITORY': 'example/sage', 'GITHUB_ACTIONS': 'true',
        'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF': 'refs/heads/main', 'GITHUB_REF_TYPE': 'branch',
        'GITHUB_REF_PROTECTED': 'true', 'GITHUB_RUN_ATTEMPT': '1', 'RUNNER_ENVIRONMENT': 'github-hosted',
        'RUNNER_OS': 'Linux', 'GITHUB_WORKFLOW_REF': 'example/sage/' + module.WORKFLOW + '@refs/heads/main',
        'GITHUB_WORKFLOW_SHA': 'a' * 40, 'GITHUB_REPOSITORY_ID': '123', 'GITHUB_RUN_ID': '456',
        'GITHUB_ACTOR_ID': '789', 'GITHUB_WORKSPACE': str(root)}


class DailyRuntimeTests(unittest.TestCase):
    def test_real_entry_and_workflow_remain_disabled(self):
        with patch.object(module, '_checkout') as checkout:
            self.assertEqual(module.run(), 'daily_runtime_disabled')
        checkout.assert_not_called()
        result = subprocess.run([sys.executable, '-I', '-B', str(module.ROOT / module.ENTRY)],
            cwd='/tmp', env={}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'daily_runtime_disabled\n')
        workflow = (module.ROOT / module.WORKFLOW).read_text()
        for text in ['if: ${{ false }}', 'environment: production', 'fetch-depth: 0', "python-version: '3.12.12'", 'persist-credentials: false', 'python -I -B']:
            self.assertIn(text, workflow)
        self.assertNotIn('schedule:', workflow)
        self.assertNotIn('inputs:', workflow)
        extra = subprocess.run([sys.executable, '-I', '-B', str(module.ROOT / module.ENTRY), '--as-of=2026-09-06'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        self.assertNotEqual(extra.returncode, 0)
        self.assertEqual(extra.stdout, b'')

    def test_configuration_rejects_duplicates_unknowns_nonboolean_and_disabled_origin(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(module, 'ROOT', Path(directory)):
            path = Path(directory) / module.CONFIG; path.parent.mkdir()
            for value in [b'{"enabled":false,"enabled":true}', json.dumps({'protocol': 'm12-daily-runtime/1', 'enabled': 0, 'coordinator_origin': None}).encode(),
                json.dumps({'protocol': 'm12-daily-runtime/1', 'enabled': False, 'coordinator_origin': 'https://other.invalid'}).encode(), b'{}']:
                path.write_bytes(value)
                with self.assertRaises((ValueError, module.DailyRuntimeError)): module._configuration()

    def test_context_and_all_source_paths_are_bound_before_business_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            entries = []
            for name in [module.ENTRY, module.CONFIG, module.WORKFLOW, 'services/contracts/validation.py']:
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'fixed source\n')
                data = path.read_bytes(); blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
                entries.append(f'100644 blob {blob}\t{name}'.encode())
            state = {'extra': b''}
            def git(*args):
                if args[0] == 'rev-parse': return b'a' * 40
                if args[0] == 'ls-files': return state['extra']
                return b'\0'.join(entries) + b'\0'
            with patch.object(module, 'ROOT', root), patch.object(module, '_git', side_effect=git):
                env = environment(root); module._checkout(env)
                for key, value in [('GITHUB_REF', 'refs/heads/other'), ('GITHUB_REF_PROTECTED', 'false'), ('GITHUB_RUN_ATTEMPT', '2'),
                    ('RUNNER_ENVIRONMENT', 'self-hosted'), ('GITHUB_WORKFLOW_SHA', 'b' * 40), ('GITHUB_EVENT_NAME', 'pull_request')]:
                    with self.assertRaises(module.DailyRuntimeError): module._checkout({**env, key: value})
                state['extra'] = b'services/__pycache__/other.pyc'
                with self.assertRaises(module.DailyRuntimeError): module._checkout(env)
                state['extra'] = b''
                (root / module.CONFIG).write_bytes(b'changed')
                with self.assertRaises(module.DailyRuntimeError): module._checkout(env)

    def test_enabled_entry_rejects_nonfixed_interpreter_before_checkout(self):
        with patch.object(module, '_configuration', return_value={'enabled': True}), patch.object(module, '_checkout') as checkout:
            with self.assertRaisesRegex(module.DailyRuntimeError, 'interpreter'): module.run()
        checkout.assert_not_called()

    def test_enabled_composition_orders_checks_and_intake_without_live_dependencies(self):
        from types import SimpleNamespace
        from services.publication import daily_transport
        from services.market_data import membership_collection
        events = []
        class Client:
            def __init__(self, origin, env):
                events.append('client'); self.origin = origin
            def prepare_and_validate(self): events.append('prepare'); return {'as_of': '2026-09-06'}
            def authorize(self, **_): raise AssertionError('test collector is replaced')
            def register_membership(self, key, digest):
                events.append('register'); assert key == 'observed' and digest == 'hash'
        def collect(as_of, *, authorize, archive):
            events.append('collect')
            self.assertEqual(as_of, '2026-09-06')
            self.assertIsInstance(archive, Client)
            return SimpleNamespace(failure=None, parsed=object(), observation_key='observed', observation_sha256='hash')
        flags = SimpleNamespace(**{key: getattr(sys.flags, key) for key in dir(sys.flags) if not key.startswith('_') and isinstance(getattr(sys.flags, key), int)})
        flags.isolated = 1
        env = {**environment(module.ROOT), 'EODHD_API_TOKEN': 'synthetic-only'}
        with patch.object(module, '_configuration', return_value={'enabled': True, 'coordinator_origin': 'https://coordinator.invalid'}), \
             patch.object(module, '_checkout', side_effect=lambda _: events.append('checkout')), \
             patch.object(module.sys, 'flags', flags), patch.object(module.sys, 'version_info', (3, 12, 12)), \
             patch.dict(module.os.environ, env, clear=True), patch.object(module.runpy, 'run_path'), \
             patch.object(daily_transport, 'DailyPreparationTransport', Client), patch.object(membership_collection, 'collect_membership', side_effect=collect):
            self.assertEqual(module.run(), 'daily_membership_registered_not_formal')
        self.assertEqual(events, ['checkout', 'client', 'prepare', 'checkout', 'collect', 'checkout', 'register', 'checkout'])


if __name__ == '__main__': unittest.main()
