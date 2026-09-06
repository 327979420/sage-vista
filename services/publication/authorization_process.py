"""Private, cancellable fixed validation process; caller owns polling/cleanup.

Use as a context manager. This class schedules no heartbeat or autonomous timer.
The trusted supervisor must poll and cancel on lease/identity failure.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024


class AuthorizationValidationProcessError(RuntimeError):
    """Fixed error messages only; private input/stdout/stderr are never echoed."""


class AuthorizationValidationProcess:
    def __init__(self, input_bytes: bytes):
        if type(input_bytes) is not bytes or not 0 < len(input_bytes) <= MAX_INPUT_BYTES:
            raise AuthorizationValidationProcessError('validation process input invalid')
        self._process = None
        self._input = None
        self._output = None
        self._state = 'starting'
        try:
            # TemporaryFile is private and automatically removed. File-backed
            # stdio avoids a full pipe blocking the supervisor during renewal.
            self._input = tempfile.TemporaryFile(mode='w+b')
            self._output = tempfile.TemporaryFile(mode='w+b')
            self._input.write(input_bytes)
            self._input.flush()
            self._input.seek(0)
            worker = Path(__file__).resolve().with_name('authorization_validation_worker.py')
            self._process = subprocess.Popen(
                [sys.executable, '-I', str(worker)], cwd=str(worker.parents[2]),
                stdin=self._input, stdout=self._output, stderr=subprocess.DEVNULL,
                env={}, close_fds=True, shell=False,
            )
            self._input.close()
            self._input = None
            self._state = 'running'
        except Exception:
            self._state = 'failed'
            self._dispose()
            raise AuthorizationValidationProcessError('validation process start failed') from None

    def _dispose(self):
        try:
            try:
                if self._process is not None:
                    if self._process.poll() is None:
                        try:
                            self._process.kill()
                        except ProcessLookupError:
                            pass
                    self._process.wait()  # Reap even when exit raced with cancellation.
                    self._process = None
            finally:
                for name in ('_input', '_output'):
                    stream = getattr(self, name)
                    if stream is not None:
                        stream.close()
                        setattr(self, name, None)
        except Exception:
            raise AuthorizationValidationProcessError('validation process cleanup failed') from None

    def poll(self):
        """None while running, immutable stdout once; failure never yields bytes."""
        if self._state != 'running':
            raise AuthorizationValidationProcessError('validation process not running')
        try:
            size = os.fstat(self._output.fileno()).st_size
            if size > MAX_OUTPUT_BYTES:
                raise ValueError('output too large')
            result = self._process.poll()
            if result is None:
                return None
            if result != 0:
                raise ValueError('worker failed')
            self._output.seek(0)
            raw = self._output.read(MAX_OUTPUT_BYTES + 1)
            if not 0 < len(raw) <= MAX_OUTPUT_BYTES:
                raise ValueError('output incomplete')
            self._state = 'completed'
            self._dispose()
            return raw
        except Exception:
            self._state = 'failed'
            self._dispose()
            raise AuthorizationValidationProcessError('validation process failed') from None

    def cancel(self):
        if self._state in ('starting', 'running'):
            self._state = 'cancelled'
        self._dispose()

    def __enter__(self):
        if self._state != 'running':
            raise AuthorizationValidationProcessError('validation process not running')
        return self

    def __exit__(self, *_):
        self.cancel()
