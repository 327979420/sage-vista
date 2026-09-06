"""Supervise fixed validation with serial authenticated I/O; no workflow entry.

Only the supervisor thread touches the process. A single I/O thread owns all
transport calls. Neither a transport replacement nor timing knobs are RPC input.
"""
from concurrent.futures import ThreadPoolExecutor
import time

from services.publication.authorization_execution import validation_job_preparation
from services.publication.authorization_process import AuthorizationValidationProcess
from services.publication.authorization_transport import _stamp

HEARTBEAT_SECONDS = 60
CONTROL_WAIT_SECONDS = 60
JOB_SECONDS = 600
POLL_SECONDS = 0.1


class AuthorizationSupervisionError(RuntimeError):
    """Fixed error, no private evidence or remote response in diagnostics."""


class _Budget:
    def __init__(self):
        self.mono = time.monotonic_ns()
        self.wall = time.time_ns() // 1_000_000
        self.end = self.mono + JOB_SECONDS * 1_000_000_000
        self.wall_end = None
        self.stamp = None

    def check(self):
        mono, wall = time.monotonic_ns(), time.time_ns() // 1_000_000
        if (mono < self.mono or wall < self.wall or wall < 0 or mono >= self.end or
                (self.wall_end is not None and wall >= self.wall_end)):
            raise AuthorizationSupervisionError('validation supervision stopped')
        self.mono, self.wall = mono, wall
        return mono

    def control(self, response):
        # B3l has validated this authenticated response against frozen input.
        # Reuse its timestamp parser, never infer authorization or business validity.
        stamp = response['validation_expires_at']
        expiry = _stamp(stamp)
        self.check()
        if self.stamp is None:
            self.stamp, self.wall_end = stamp, expiry
            self.end = min(self.end, self.mono + (expiry - self.wall) * 1_000_000)
        elif stamp != self.stamp:
            raise AuthorizationSupervisionError('validation supervision stopped')
        self.check()


def _await_control(future, budget):
    end = budget.check() + CONTROL_WAIT_SECONDS * 1_000_000_000
    while True:
        if budget.check() >= end:
            raise AuthorizationSupervisionError('validation supervision stopped')
        if future.done():
            result = future.result()
            budget.check()
            return result
        time.sleep(POLL_SECONDS)


def execute_supervised_authorization_validation(transport) -> bytes:
    """Fixed worker + 60-second renewal; failures discard output without retry.

    Thread shutdown waits for in-flight I/O after cancelling computation. It
    cannot retract remote effects or interrupt OS process creation/reaping.
    """
    try:
        budget = _Budget()
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix='m12-authorization-io') as io:
            prepared = validation_job_preparation(_await_control(io.submit(transport.prepare), budget))
            budget.control(_await_control(io.submit(transport.status), budget))
            next_renewal = budget.check() + HEARTBEAT_SECONDS * 1_000_000_000
            with AuthorizationValidationProcess(prepared['input_bytes']) as child:
                pending, renewal_end, output = None, None, None
                while True:
                    now = budget.check()
                    if pending is not None:
                        if now >= renewal_end:
                            raise AuthorizationSupervisionError('validation supervision stopped')
                        if pending.done():
                            budget.control(pending.result())
                            pending = None
                    if output is None:
                        output = child.poll()
                    if output is not None and pending is None:
                        break
                    if pending is None and now >= next_renewal:
                        renewal_end = next_renewal + CONTROL_WAIT_SECONDS * 1_000_000_000
                        if now >= renewal_end:
                            raise AuthorizationSupervisionError('validation supervision stopped')
                        pending = io.submit(transport.renew)
                        next_renewal += HEARTBEAT_SECONDS * 1_000_000_000
                    time.sleep(POLL_SECONDS)
                budget.control(_await_control(io.submit(transport.status), budget))
                response = _await_control(io.submit(transport.return_result,
                    prepared['dispatch_id'], prepared['lease_token'], output), budget)
                if type(response) is not bytes:
                    raise AuthorizationSupervisionError('validation supervision stopped')
                return response  # Opaque; does not claim registration.
    except Exception:
        raise AuthorizationSupervisionError('validation supervision stopped') from None
