"""Test-only stdio adapter for real local Node archive / Python producer replay."""
import base64
import json
import sys
from services.publication.execution_history import (
    encode, encode_signal, execution_task_id, prepare_execution_pairs, restore_execution_history,
)


def b64(raw):
    return base64.b64encode(raw).decode()


def main():
    value = json.load(sys.stdin)
    if value['operation'] == 'fixture':
        from tests.test_m12_execution_history import ExecutionHistoryTests
        ExecutionHistoryTests.setUpClass()
        fixture = ExecutionHistoryTests()
        fixture.setUp()
        result = {'task_id': execution_task_id(fixture.fixture.signal),
                  'root_bytes': b64(encode_signal(fixture.fixture.signal)),
                  'request_bytes': b64(encode(fixture.request))}
    else:
        objects = {key: base64.b64decode(raw, validate=True) for key, raw in value['objects'].items()}
        snapshot = value['snapshot']
        if value['operation'] == 'prepare':
            request = json.loads(base64.b64decode(value['request_bytes'], validate=True))
            if value.get('late_retry'):
                request.update(entry_reads={}, generated_at='2026-09-04T23:59:00Z')
            pairs = prepare_execution_pairs(snapshot, objects, request)
            result = {'pairs': [{key: b64(item) if isinstance(item, bytes) else item
                                for key, item in pair.items()} for pair in pairs]}
        elif value['operation'] == 'restore':
            restored = restore_execution_history(snapshot, objects)
            result = {'confirmed_through': dict(restored.confirmed_through),
                      'holding_sessions': [state['holding_sessions'] for state in restored.states],
                      'entry_dates': [plan['entry_date'] for plan in restored.plans]}
        else:
            raise ValueError('unknown test operation')
    sys.stdout.buffer.write(encode(result))


if __name__ == '__main__':
    main()
