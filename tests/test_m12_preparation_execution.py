"""Fixed process/source boundary, only synthetic inputs and local Git."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from services.publication import preparation_execution as module
from services.publication import preparation_validation_worker as worker
from services.publication.configuration import build_research_configuration, ROOT
from tests.test_m12_preparation_validation import fixture
from tests.test_m12_authorization_use import raw


class PreparationExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        cls.config = build_research_configuration(cls.commit)

    def input(self):
        return raw(fixture(self.commit, self.config, time.time_ns() // 1_000_000))

    def test_real_fixed_process_matches_input_and_checks_actual_checkout(self):
        data = self.input()
        worker._checkout(data)
        result = json.loads(module.execute_preparation_validation(data))
        self.assertEqual(result['input_sha256'], 'sha256:' + hashlib.sha256(data).hexdigest())
        self.assertEqual(result['preparation']['code_commit'], self.commit)
        with self.assertRaises(TypeError): module.execute_preparation_validation(data, command='other')

    def test_cancellation_reaps_real_child_on_fixed_budget(self):
        real = subprocess.Popen
        children = []
        def launch(command, **kwargs):
            self.assertEqual(command, [sys.executable, '-I', str(ROOT / 'services/publication/preparation_validation_worker.py')])
            self.assertEqual(kwargs['env'], {})
            child = real([sys.executable, '-I', '-c', 'import time;time.sleep(30)'], **kwargs)
            children.append(child)
            return child
        data = self.input()
        with patch('subprocess.Popen', side_effect=launch), patch.object(module.time, 'monotonic_ns', side_effect=[0, 1, 31_000_000_000]):
            with self.assertRaisesRegex(module.PreparationExecutionError, '^preparation computation failed$'):
                module.execute_preparation_validation(data)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)

    def test_wrong_output_binding_is_discarded_without_retry(self):
        class Child:
            def __init__(self, value): self.value = value
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def poll(self): return b'{"protocol":"m12-preparation-validation/1","input_sha256":"fake","input_size_bytes":1}'
        with patch.object(module, 'PreparationValidationProcess', Child):
            with self.assertRaises(module.PreparationExecutionError): module.execute_preparation_validation(self.input())

    def test_checkout_rejects_extra_files_changes_symlinks_and_wrong_head(self):
        required = ['services/publication/preparation_validation_worker.py', 'services/publication/authorization_imports.py',
                    'services/publication/preparation_validation.py', 'services/contracts/validation.py']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            entries = []
            for name in required:
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'# original\n')
                data = path.read_bytes(); digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
                entries.append(f'100644 blob {digest}\t{name}'.encode())
            response = {'head': self.commit.encode() + b'\n', 'extra': b'', 'tree': b'\0'.join(entries) + b'\0'}
            def git(*args): return response['head' if args[0] == 'rev-parse' else 'extra' if args[0] == 'ls-files' else 'tree']
            with patch.object(worker, 'ROOT', root), patch.object(worker, '_git', side_effect=git):
                data = self.input(); worker._checkout(data)
                response['extra'] = b'services/__pycache__/hidden.pyc\n'
                with self.assertRaises(ValueError): worker._checkout(data)
                response['extra'] = b''; response['head'] = b'a' * 40
                with self.assertRaises(ValueError): worker._checkout(data)
                response['head'] = self.commit.encode()
                path = root / required[0]; path.write_bytes(b'# changed\n')
                with self.assertRaises(ValueError): worker._checkout(data)
                path.unlink(); path.symlink_to(root / required[1])
                with self.assertRaises(ValueError): worker._checkout(data)


if __name__ == '__main__': unittest.main()
