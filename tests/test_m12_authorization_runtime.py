"""Fixed-entry checks use local Git and substituted I/O, never live Actions."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from services.publication import authorization_runtime as runtime

ROOT = Path(__file__).resolve().parents[1]


class Flags:
    def __init__(self, isolated):
        self.original = sys.flags
        self.isolated = isolated

    def __getattr__(self, name):
        return getattr(self.original, name)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'checkout'
        self.root.mkdir()
        self.parent = self.root.parent / 'runner-temp'
        self.parent.mkdir()
        for path, body in {
            runtime.CONFIG: json.dumps({'protocol': 'm12-authorization-runtime/1', 'enabled': True,
                                       'coordinator_origin': 'https://coordinator.example.com'}),
            runtime.WORKFLOW: 'fixed workflow',
            'services/publication/authorization_runtime.py': 'fixed runtime',
            'services/contracts/validation.py': 'fixed validator',
        }.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body)
        self.git('init', '-q')
        self.commit()
        self.env = {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
                    'GITHUB_REF': 'refs/heads/main', 'GITHUB_REF_TYPE': 'branch',
                    'GITHUB_REF_PROTECTED': 'true', 'GITHUB_RUN_ATTEMPT': '1',
                    'RUNNER_ENVIRONMENT': 'github-hosted', 'RUNNER_OS': 'Linux',
                    'GITHUB_REPOSITORY': 'example/sage-vista', 'GITHUB_REPOSITORY_ID': '123',
                    'GITHUB_ACTOR_ID': '789', 'GITHUB_RUN_ID': '456',
                    'GITHUB_WORKFLOW_REF': f'example/sage-vista/{runtime.WORKFLOW}@refs/heads/main',
                    'GITHUB_SHA': self.git('rev-parse', 'HEAD').strip(),
                    'GITHUB_WORKSPACE': str(self.root), 'RUNNER_TEMP': str(self.parent)}
        self.env['GITHUB_WORKFLOW_SHA'] = self.env['GITHUB_SHA']
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(runtime, 'ROOT', self.root))
        self.stack.enter_context(patch.dict(os.environ, self.env, clear=True))
        self.stack.enter_context(patch.object(sys, 'path', list(sys.path)))
        self.stack.enter_context(patch.object(sys, 'dont_write_bytecode', True))

    def git(self, *args):
        return subprocess.run(['/usr/bin/git', *args], cwd=self.root, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()

    def commit(self):
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')

    def interpreter(self):
        self.stack.enter_context(patch.object(sys, 'flags', Flags(1)))
        self.stack.enter_context(patch.object(sys, 'version_info', (3, 12, 12)))

    def network(self):
        factory = self.stack.enter_context(patch(
            'services.publication.authorization_recovery.RecoverableAuthorizationTransport'))
        execute = self.stack.enter_context(patch(
            'services.publication.authorization_supervision.execute_supervised_authorization_validation'))
        return factory, execute

    def test_disabled_real_cli_and_argument_rejection(self):
        script = ROOT / 'services/publication/authorization_runtime.py'
        result = subprocess.run([sys.executable, '-I', '-B', str(script)], env={},
                                capture_output=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, b'authorization_runtime_disabled\n', b''))
        result = subprocess.run([sys.executable, '-I', '-B', str(script), '--origin=private'],
                                env={}, capture_output=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (1, b'', b'authorization_runtime_failed\n'))

    def test_context_and_committed_source_accepted(self):
        runtime._checkout(self.env)
        self.assertEqual(runtime._configuration()['coordinator_origin'], 'https://coordinator.example.com')

    def test_changed_context_rejected_before_client(self):
        self.interpreter()
        factory, execute = self.network()
        changes = {'GITHUB_ACTIONS': 'false', 'GITHUB_EVENT_NAME': 'pull_request',
                   'GITHUB_REF': 'refs/heads/other', 'GITHUB_REF_TYPE': 'tag',
                   'GITHUB_REF_PROTECTED': 'false', 'GITHUB_RUN_ATTEMPT': '2',
                   'RUNNER_ENVIRONMENT': 'self-hosted', 'RUNNER_OS': 'Windows',
                   'GITHUB_REPOSITORY_ID': '0', 'GITHUB_ACTOR_ID': '', 'GITHUB_RUN_ID': '../x',
                   'GITHUB_REPOSITORY': 'x', 'GITHUB_WORKFLOW_REF': 'other',
                   'GITHUB_WORKFLOW_SHA': 'a'*40, 'GITHUB_SHA': 'b'*40,
                   'GITHUB_WORKSPACE': str(self.parent)}
        for key, value in changes.items():
            with self.subTest(key=key), patch.dict(os.environ, {key: value}):
                with self.assertRaises(runtime.AuthorizationRuntimeError): runtime.run()
        factory.assert_not_called()
        execute.assert_not_called()

    def test_changed_source_even_assume_unchanged_and_extra_import_rejected(self):
        path = self.root / 'services/contracts/validation.py'
        self.git('update-index', '--assume-unchanged', 'services/contracts/validation.py')
        path.write_text('substitute validator')
        with self.assertRaises(runtime.AuthorizationRuntimeError): runtime._checkout(self.env)
        path.write_text('fixed validator')
        extra = self.root / 'services/private.pyc'
        extra.write_bytes(b'substitute bytecode')
        with self.assertRaises(runtime.AuthorizationRuntimeError): runtime._checkout(self.env)
        extra.unlink()
        path.unlink()
        path.symlink_to(self.root / runtime.CONFIG)
        with self.assertRaises(runtime.AuthorizationRuntimeError): runtime._checkout(self.env)

    def test_staged_configuration_not_same_as_source_commit(self):
        path = self.root / runtime.CONFIG
        path.write_text(path.read_text().replace('coordinator.example', 'other.example'))
        self.git('add', runtime.CONFIG)
        with self.assertRaises(runtime.AuthorizationRuntimeError): runtime._checkout(self.env)

    def test_config_closed_keys_types_duplicates(self):
        path = self.root / runtime.CONFIG
        for raw in ['{}', '[]', '{"protocol":"m12-authorization-runtime/1","enabled":0,"coordinator_origin":null}',
                    '{"protocol":"m12-authorization-runtime/1","enabled":false,"coordinator_origin":"x"}',
                    '{"enabled":false,"enabled":true}', 'x'*4097]:
            with self.subTest(raw=raw[:50]):
                path.write_text(raw)
                with self.assertRaises((ValueError, runtime.AuthorizationRuntimeError)): runtime._configuration()

    def test_wrong_interpreter_and_bad_temp_stop_before_network(self):
        factory, _ = self.network()
        with patch.object(sys, 'flags', Flags(0)):
            with self.assertRaises(runtime.AuthorizationRuntimeError): runtime.run()
        with patch.object(sys, 'flags', Flags(1)), patch.object(sys, 'version_info', (3, 12, 11)):
            with self.assertRaises(runtime.AuthorizationRuntimeError): runtime.run()
        self.interpreter()
        for value in ['', 'relative', str(self.root), str(self.parent / 'absent')]:
            with self.subTest(value=value), patch.dict(os.environ, {'RUNNER_TEMP': value}):
                with self.assertRaises(runtime.AuthorizationRuntimeError): runtime.run()
        factory.assert_not_called()

    def test_fixed_factory_supervisor_only_no_caller_override(self):
        self.interpreter()
        factory, execute = self.network()
        client = Mock()
        factory.return_value = client
        with patch.dict(os.environ, {'M12_COORDINATOR_ORIGIN': 'https://evil.example',
                                     'PYTHONPATH': '/bad', 'M12_COMMAND': 'false'}):
            self.assertEqual(runtime.run(), 'validation_return_received_pending_registration')
        args, kwargs = factory.call_args
        self.assertEqual(args[0], 'https://coordinator.example.com')
        self.assertEqual(kwargs, {'recovery_directory': self.parent / 'm12-authorization-456-1'})
        self.assertEqual(len(args), 2)  # No injected opener or validator.
        execute.assert_called_once_with(client)
        client.recover.assert_not_called()

    def test_uncertain_return_only_queries_with_new_client_once(self):
        self.interpreter()
        factory, execute = self.network()
        first, second = Mock(recovery_id='a'*64), Mock()
        factory.side_effect = [first, second]
        execute.side_effect = RuntimeError('private payload')
        self.assertEqual(runtime.run(), 'historical_return_verified_pending_registration')
        self.assertEqual(factory.call_count, 2)
        execute.assert_called_once_with(first)
        second.recover.assert_called_once_with('a'*64)
        second.prepare.assert_not_called()
        second.return_result.assert_not_called()

    def test_no_saved_handle_no_recovery_and_recovery_failure_no_resend(self):
        self.interpreter()
        factory, execute = self.network()
        execute.side_effect = RuntimeError('private payload')
        factory.return_value = Mock(recovery_id=None)
        with self.assertRaises(runtime.AuthorizationRuntimeError): runtime.run()
        self.assertEqual(factory.call_count, 1)
        first, second = Mock(recovery_id='a'*64), Mock()
        second.recover.side_effect = RuntimeError('private payload')
        factory.side_effect = [first, second]
        with patch.object(sys, 'argv', ['fixed']), patch('sys.stderr') as error, patch('sys.stdout') as output:
            self.assertEqual(runtime.main(), 1)
            self.assertNotIn('private payload', str(error.mock_calls))
            output.write.assert_not_called()
        second.recover.assert_called_once()
        second.return_result.assert_not_called()

    def test_actual_worker_keeps_checkout_free_of_bytecode(self):
        # Real fixed worker/imports, malformed input; no synthetic code execution.
        shutil.copytree(ROOT / 'services', self.root / 'services', dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        worker = self.root / 'services/publication/authorization_validation_worker.py'
        result = subprocess.run([sys.executable, '-I', str(worker)], input=b'{}', env={},
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b'')
        self.assertEqual(result.stderr, b'')
        self.assertEqual(list((self.root / 'services').rglob('*.pyc')), [])

    def test_real_isolated_runtime_ignores_unverified_root_modules_and_packages(self):
        shutil.copytree(ROOT / 'services', self.root / 'services', dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        self.commit()
        self.env['GITHUB_SHA'] = self.env['GITHUB_WORKFLOW_SHA'] = self.git('rev-parse', 'HEAD').strip()
        script = '''
import os, pathlib, runpy, sys
root = pathlib.Path(sys.argv[1])
namespace = runpy.run_path(str(root / 'services/publication/authorization_runtime.py'))
namespace['_checkout'](dict(os.environ))
assert 'base64' not in sys.modules
# Test-only local interpreter version override; no injected factory or imports.
sys.version_info = (3, 12, 12)
try:
    namespace['run']()
except Exception as exc:
    assert type(exc).__name__ == 'AuthorizationTransportError', repr(exc)
    assert str(exc) == 'validation transport URL invalid', repr(exc)
else:
    raise AssertionError('missing Actions credentials must fail before network')
assert 'services.publication.authorization_supervision' in sys.modules
assert 'services.publication.authorization_recovery' in sys.modules
assert str(root) not in sys.path
assert list(sys.modules['services'].__path__) == [str(root / 'services')]
import base64, urllib, importlib.util
assert not pathlib.Path(base64.__file__).is_relative_to(root)
assert not pathlib.Path(urllib.__file__).is_relative_to(root)
assert importlib.util.find_spec('m12_unverified_top_level') is None
print('CHECKOUT_AND_SCOPED_IMPORTS_PASSED')
'''
        for shadows in (False, True):
            if shadows:
                for name in ('base64.py', 'm12_unverified_top_level.py', 'services.py', 'urllib/__init__.py'):
                    path = self.root / name
                    path.parent.mkdir(exist_ok=True)
                    path.write_text("raise RuntimeError('UNVERIFIED_ROOT_MODULE_EXECUTED')\n")
            with self.subTest(shadows=shadows):
                result = subprocess.run([sys.executable, '-I', '-B', '-c', script, str(self.root)],
                                        cwd=self.root, env={**self.env, 'PYTHONPATH': str(self.root)},
                                        capture_output=True, timeout=15)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (0, b'CHECKOUT_AND_SCOPED_IMPORTS_PASSED\n', b''))

    def test_fixed_worker_and_http_process_ignore_root_shadowing(self):
        shutil.copytree(ROOT / 'services', self.root / 'services', dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        marker = self.root / 'untrusted-code-executed'
        for name in ('base64.py', 'ssl.py', 'urllib/__init__.py', 'services.py'):
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(f"open({str(marker)!r}, 'w').write('executed')\nraise RuntimeError('ROOT_SHADOW')\n")
        for entry in ('authorization_validation_worker.py', 'authorization_transport.py'):
            with self.subTest(entry=entry):
                result = subprocess.run([sys.executable, '-I', '-B', str(self.root / 'services/publication' / entry)],
                                        input=b'{}', cwd=self.root,
                                        env={'PYTHONPATH': str(self.root)}, capture_output=True, timeout=15)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (1, b'', b''))
                self.assertFalse(marker.exists())
        self.assertEqual(list((self.root / 'services').rglob('*.pyc')), [])

    def test_scoped_bootstrap_rejects_preexisting_different_services_path(self):
        script = '''
import runpy, sys, types
services = types.ModuleType('services')
services.__path__ = ['/unverified/services']
sys.modules['services'] = services
try:
    runpy.run_path(sys.argv[1])
except RuntimeError as exc:
    assert str(exc) == 'authorization services import root invalid'
else:
    raise AssertionError('foreign namespace accepted')
assert sys.modules['services'] is services
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-c', script,
                                 str(ROOT / 'services/publication/authorization_imports.py')],
                                env={}, capture_output=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b'', b''))


if __name__ == '__main__': unittest.main()
