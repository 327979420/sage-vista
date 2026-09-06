"""Real child lifecycle with trusted fake I/O; no real network or approval."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from services.publication import authorization_supervision as module
from services.publication.authorization_supervision import execute_supervised_authorization_validation as execute
from services.publication.authorization_supervision import AuthorizationSupervisionError as SupervisionError


def stamp(milliseconds):
    return (datetime.now(timezone.utc) + timedelta(milliseconds=milliseconds)).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


class Transport:
    def __init__(self, expiry=None):
        self.expiry = expiry or stamp(5000)
        self.calls, self.threads = [], []
        self.on_renew = None
        self.on_status = None
        self.on_return = None
        self.prepared = None
        self.returned = None
        lease = {'epoch': '11111111-1111-4111-8111-111111111111', 'fence': 1}
        # Preparation wire shape only; child command substitution is test-only.
        raw = json.dumps({'protocol': 'm12-authorization-validation/1', 'approval_evidence_ref': {},
                          'approval_archive': {'bundle_base64': base64.b64encode(b'{}').decode(), 'objects': {}},
                          'validation_ticket': lease, 'history_base64': []}).encode()
        self.prepared = {'dispatch_id': '22222222-2222-4222-8222-222222222222', 'lease_token': lease,
                         'input_bytes': raw, 'input_sha256': 'sha256:' + hashlib.sha256(raw).hexdigest(), 'input_size_bytes': len(raw)}

    def record(self, name):
        self.calls.append(name); self.threads.append(threading.get_ident())

    def prepare(self):
        self.record('prepare'); return self.prepared

    def status(self):
        self.record('status')
        if self.on_status: self.on_status()
        return {'validation_expires_at': self.expiry}

    def renew(self):
        self.record('renew')
        if self.on_renew: self.on_renew()
        return {'validation_expires_at': self.expiry}

    def return_result(self, dispatch, lease, raw):
        self.record('return'); self.returned = (dispatch, lease, raw)
        if self.on_return: return self.on_return()
        return b'{"state":"opaque"}'


class SupervisionTests(unittest.TestCase):
    def setUp(self):
        self.children = []
        self.enterContext(patch.object(module, 'HEARTBEAT_SECONDS', 0.04))
        self.enterContext(patch.object(module, 'CONTROL_WAIT_SECONDS', 0.2))
        self.enterContext(patch.object(module, 'POLL_SECONDS', 0.005))

    def worker(self, delay=30):
        real = subprocess.Popen
        def launch(command, **kwargs):
            child = real([sys.executable, '-I', '-c', f"import sys,time;time.sleep({delay});sys.stdout.buffer.write(b'complete')"], **kwargs)
            self.children.append(child)
            return child
        self.enterContext(patch('subprocess.Popen', side_effect=launch))

    def assert_stopped(self, transport):
        with self.assertRaisesRegex(SupervisionError, '^validation supervision stopped$'): execute(transport)
        self.assertNotIn('return', transport.calls)
        self.assertTrue(self.children)
        self.assertTrue(all(child.returncode is not None for child in self.children))

    def test_periodic_renewal_serial_io_and_final_status_before_unchanged_return(self):
        self.worker(0.18); transport = Transport()
        self.assertEqual(execute(transport), b'{"state":"opaque"}')
        self.assertGreaterEqual(transport.calls.count('renew'), 2)
        self.assertEqual(transport.calls[:2], ['prepare', 'status'])
        self.assertEqual(transport.calls[-2:], ['status', 'return'])
        self.assertEqual(len(set(transport.threads)), 1)
        self.assertNotEqual(transport.threads[0], threading.get_ident())
        self.assertEqual(transport.returned, (transport.prepared['dispatch_id'], transport.prepared['lease_token'], b'complete'))
        self.assertTrue(all(child.returncode == 0 for child in self.children))

    def test_renewal_failure_cancels_real_computation_without_return(self):
        self.worker(); transport = Transport()
        def fail(): raise OSError('private renewal error')
        transport.on_renew = fail
        self.assert_stopped(transport)
        self.assertEqual(transport.calls.count('renew'), 1)

    def test_stalled_renewal_computation_is_killed_before_io_thread_returns(self):
        self.worker(); transport = Transport(); observed = []
        def blocked():
            self.children[0].wait(timeout=3)
            observed.append(self.children[0].returncode)
        transport.on_renew = blocked
        self.assert_stopped(transport)
        self.assertTrue(observed)
        self.assertEqual(transport.calls.count('renew'), 1)

    def test_frozen_deadline_cancels_during_inflight_io(self):
        self.worker(); transport = Transport(stamp(160)); observed = []
        self.enterContext(patch.object(module, 'CONTROL_WAIT_SECONDS', 2))
        def blocked():
            self.children[0].wait(timeout=3); observed.append(True)
        transport.on_renew = blocked
        self.assert_stopped(transport)
        self.assertTrue(observed)

    def test_completed_output_is_discarded_when_inflight_renewal_later_fails(self):
        self.worker(0.07); transport = Transport()
        def delayed_failure():
            time.sleep(0.12)
            raise OSError('renewal failed after computation finished')
        transport.on_renew = delayed_failure
        self.assert_stopped(transport)
        self.assertEqual(self.children[0].returncode, 0)

    def test_final_status_failure_discards_completed_output(self):
        self.worker(0); transport = Transport()
        def check():
            if transport.calls.count('status') == 2: raise OSError('invalidated')
        transport.on_status = check
        self.assert_stopped(transport)

    def test_uncertain_return_is_attempted_once_without_retry(self):
        self.worker(0); transport = Transport()
        def fail(): raise OSError('private uncertain result')
        transport.on_return = fail
        with self.assertRaisesRegex(SupervisionError, '^validation supervision stopped$'): execute(transport)
        self.assertEqual(transport.calls.count('return'), 1)
        self.assertTrue(all(child.returncode is not None for child in self.children))

    def test_invalid_preparation_fails_before_worker_or_status(self):
        self.worker(); transport = Transport(); transport.prepared['input_sha256'] = 'changed'
        with self.assertRaises(SupervisionError): execute(transport)
        self.assertEqual(self.children, [])
        self.assertEqual(transport.calls, ['prepare'])

    def test_changed_frozen_deadline_cannot_extend_computation(self):
        self.worker(); transport = Transport()
        transport.on_renew = lambda: setattr(transport, 'expiry', stamp(6000))
        self.assert_stopped(transport)

    def test_total_monotonic_budget_cancels_even_when_wall_clock_has_not_expired(self):
        self.worker(); transport = Transport()
        self.enterContext(patch.object(module, 'JOB_SECONDS', 0.12))
        self.assert_stopped(transport)

    def test_wall_clock_reversal_cancels_active_computation(self):
        self.worker(); transport = Transport(); wall = [time.time_ns()]
        self.enterContext(patch.object(module.time, 'time_ns', side_effect=lambda: wall[0]))
        transport.on_renew = lambda: wall.__setitem__(0, wall[0] - 1_000_000)
        self.assert_stopped(transport)


if __name__ == '__main__': unittest.main()
