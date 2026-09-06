"""Fixed process lifecycle tests; subprocess substitutions are test-only."""
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from services.publication import authorization_process as module
from services.publication.authorization_process import AuthorizationValidationProcess as Process
from services.publication.authorization_process import AuthorizationValidationProcessError as ProcessError


def finished(process):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = process.poll()
        if result is not None:
            return result
        time.sleep(0.005)
    raise AssertionError('test child did not finish')


class ValidationProcessTests(unittest.TestCase):
    def test_fixed_isolation_private_files_no_environment_or_caller_command(self):
        real = subprocess.Popen
        captured = []
        def launch(command, **kwargs):
            self.assertEqual(command, [sys.executable, '-I', str(Path(module.__file__).with_name('authorization_validation_worker.py').resolve())])
            self.assertEqual(kwargs['env'], {})
            self.assertIs(kwargs['shell'], False)
            self.assertIs(kwargs['close_fds'], True)
            self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)
            self.assertEqual(kwargs['cwd'], str(Path(module.__file__).resolve().parents[2]))
            for stream in (kwargs['stdin'], kwargs['stdout']):
                self.assertEqual(stat.S_IMODE(os.fstat(stream.fileno()).st_mode), 0o600)
            self.assertEqual(kwargs['stdin'].read(), b'private-invalid-input')
            kwargs['stdin'].seek(0)
            captured.extend([kwargs['stdin'], kwargs['stdout']])
            return real(command, **kwargs)
        with patch.object(module.subprocess, 'Popen', side_effect=launch):
            with Process(b'private-invalid-input') as process:
                with self.assertRaisesRegex(ProcessError, '^validation process failed$'): finished(process)
        self.assertTrue(all(stream.closed for stream in captured))
        with self.assertRaises(TypeError): Process(b'input', command='other')

    def launch_script(self, script):
        real = subprocess.Popen
        return patch.object(module.subprocess, 'Popen', side_effect=lambda command, **kwargs: real([sys.executable, '-I', '-c', script], **kwargs))

    def test_cancel_discards_partial_output_and_reaps_running_child(self):
        with self.launch_script("import sys,time;sys.stdout.buffer.write(b'partial');sys.stdout.flush();time.sleep(30)"):
            with Process(b'input') as process:
                child, output = process._process, process._output
                deadline = time.monotonic() + 5
                while os.fstat(output.fileno()).st_size == 0 and time.monotonic() < deadline: time.sleep(0.005)
                self.assertEqual(os.fstat(output.fileno()).st_size, 7)
                self.assertIsNone(process.poll())
                process.cancel()
                self.assertIsNotNone(child.returncode)
                with self.assertRaises(ProcessLookupError): os.kill(child.pid, 0)
                self.assertTrue(output.closed)
                with self.assertRaises(ProcessError): process.poll()
                process.cancel()  # Idempotent cleanup.

    def test_context_exception_cancels_child_and_preserves_caller_error(self):
        with self.launch_script('import time;time.sleep(30)'):
            with self.assertRaisesRegex(ValueError, 'caller aborted'):
                with Process(b'input') as process:
                    child = process._process
                    raise ValueError('caller aborted')
            self.assertIsNotNone(child.returncode)
            with self.assertRaises(ProcessLookupError): os.kill(child.pid, 0)

    def test_nonzero_empty_and_oversized_output_fail_without_returning_bytes(self):
        scripts = ["import sys;sys.stdout.write('partial');sys.exit(1)", 'pass',
                   f"import sys;sys.stdout.buffer.write(b'x'*{module.MAX_OUTPUT_BYTES + 1})"]
        for script in scripts:
            with self.subTest(script=script), self.launch_script(script):
                with Process(b'input') as process:
                    with self.assertRaisesRegex(ProcessError, '^validation process failed$'): finished(process)
                    self.assertIsNone(process._process)
                    self.assertIsNone(process._output)

    def test_completed_bytes_are_unchanged_and_delivered_only_once(self):
        with self.launch_script("import sys;sys.stdout.buffer.write(b'original\\n')"):
            with Process(b'input') as process:
                self.assertEqual(finished(process), b'original\n')
                with self.assertRaises(ProcessError): process.poll()
                self.assertIsNone(process._output)

    def test_start_failure_is_sanitized_and_closes_both_files(self):
        real = module.tempfile.TemporaryFile
        streams = []
        def temporary(*args, **kwargs):
            value = real(*args, **kwargs); streams.append(value); return value
        with patch.object(module.tempfile, 'TemporaryFile', side_effect=temporary), patch.object(module.subprocess, 'Popen', side_effect=OSError('private-start-failure')):
            with self.assertRaisesRegex(ProcessError, '^validation process start failed$'): Process(b'input')
        self.assertEqual(len(streams), 2)
        self.assertTrue(all(value.closed for value in streams))

    def test_invalid_input_refused_before_any_process(self):
        with patch.object(module.subprocess, 'Popen') as launch:
            for raw in ['', b'', bytearray(b'input'), b'x' * (module.MAX_INPUT_BYTES + 1)]:
                with self.assertRaises(ProcessError): Process(raw)
            launch.assert_not_called()

    def test_actual_isolated_worker_rejects_bad_input_without_stdout_or_stderr(self):
        worker = str(Path(module.__file__).with_name('authorization_validation_worker.py').resolve())
        for raw in [b'', b'private-invalid-input', b'{"valid":true}']:
            result = subprocess.run([sys.executable, '-I', worker], input=raw, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, env={}, timeout=5, check=False)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, b'')
            self.assertEqual(result.stderr, b'')


if __name__ == '__main__':
    unittest.main()
