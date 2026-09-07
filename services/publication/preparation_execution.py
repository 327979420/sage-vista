"""Fixed, bounded preparation computation; transport/runtime remain trusted."""
import hashlib
from pathlib import Path
import time

from services.contracts.validation import publication_preparation_input, membership_registration_input, execution_computation_input, _m12_json
from services.publication.authorization_process import AuthorizationValidationProcess


class PreparationExecutionError(RuntimeError):
    pass


class PreparationValidationProcess(AuthorizationValidationProcess):
    def _worker_path(self):
        return Path(__file__).resolve().with_name('preparation_validation_worker.py')


def execute_preparation_validation(input_bytes: bytes) -> bytes:
    """No supplied command, worker output or timing knobs; failures never retry."""
    return _execute(input_bytes, membership=False)


def execute_membership_validation(input_bytes: bytes) -> bytes:
    """The same fixed process; only the closed membership protocol is accepted."""
    return _execute(input_bytes, membership=True)


def execute_execution_validation(input_bytes: bytes) -> bytes:
    return _execute(input_bytes, membership=False, execution=True)


def _execute(input_bytes, *, membership, execution=False):
    try:
        value = execution_computation_input(input_bytes) if execution else (membership_registration_input(input_bytes) if membership else publication_preparation_input(input_bytes))
        protocol = 'm12-execution-validation/1' if execution else ('m12-membership-registration/1' if membership else 'm12-preparation-validation/1')
        started = previous = time.monotonic_ns()
        wall = time.time_ns() // 1_000_000
        expires = value['identity']['expires_at'] * 1000
        with PreparationValidationProcess(input_bytes) as child:
            while True:
                now, current_wall = time.monotonic_ns(), time.time_ns() // 1_000_000
                if now < previous or current_wall < wall or now - started >= 30_000_000_000 or current_wall >= expires:
                    raise ValueError('computation stopped')
                previous, wall = now, current_wall
                output = child.poll()
                if output is not None:
                    if len(output) > (2 * 1024 * 1024 if execution else 65536):
                        raise ValueError('result too large')
                    result = _m12_json(output)
                    if result.get('protocol') != protocol or result.get('input_sha256') != 'sha256:' + hashlib.sha256(input_bytes).hexdigest() or type(result.get('input_size_bytes')) is not int or result['input_size_bytes'] != len(input_bytes):
                        raise ValueError('result input binding differs')
                    end, end_wall = time.monotonic_ns(), time.time_ns() // 1_000_000
                    if end < previous or end - started >= 30_000_000_000 or end_wall < wall or end_wall >= expires:
                        raise ValueError('computation stopped')
                    return output  # Server must independently bind/recheck at use.
                time.sleep(0.01)
    except Exception:
        raise PreparationExecutionError('execution computation failed' if execution else ('membership computation failed' if membership else 'preparation computation failed')) from None
