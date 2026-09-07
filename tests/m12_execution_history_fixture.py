"""Test-only stdio adapter for real local Node archive / Python producer replay."""
import faulthandler
faulthandler.enable()
faulthandler.dump_traceback_later(5, repeat=True)

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
    if value['operation'] == 'diagnostic_stall':
        import time
        faulthandler.dump_traceback_later(0.1)
        time.sleep(60)
        raise RuntimeError('diagnostic stall should have been killed')
    if value['operation'] == 'source_fixture':
        from tests.test_m12_execution_inventory import ExecutionInventoryTests
        ExecutionInventoryTests.setUpClass()
        fixture = ExecutionInventoryTests()
        fixture.setUp()
        if value.get('prior_source'):
            import subprocess
            from services.publication.configuration import build_research_configuration
            from services.publication.execution_inventory import encode_execution_source_root
            from services.publication.execution_history import _signal
            prior = subprocess.check_output(['git', 'rev-parse', 'HEAD~1'], text=True).strip()
            fixture.root_bytes = encode_execution_source_root(build_research_configuration(prior).raw_bytes, encode(fixture.inputs))
            fixture.snapshot['root']['task_id'] = execution_task_id(_signal(fixture.root_bytes))
        result = {'task_id': fixture.snapshot['root']['task_id'], 'root_bytes': b64(fixture.root_bytes),
            'commit': fixture.commit, 'request_bytes': b64(encode({'as_of': '2026-09-01', 'sessions_by_instrument': {},
                'entry_reads': {}, 'completed_reads': {}, 'generated_at': '2026-09-01T23:15:00Z'}))}
    elif value['operation'] == 'fixed_execution':
        from services.publication.preparation_execution import execute_execution_validation
        result = {'output_bytes': b64(execute_execution_validation(base64.b64decode(value['input_bytes'], validate=True)))}
    elif value['operation'] == 'trade_fixture':
        from tests.test_m12_execution_history import ExecutionHistoryTests
        from tests.test_m12_execution_continuation import sessions
        from tests.test_market_data_consumers import DAY
        ExecutionHistoryTests.setUpClass()
        fixture = ExecutionHistoryTests()
        fixture.setUp()
        requests = [dict(as_of=DAY, sessions_by_instrument={}, entry_reads={},
                         completed_reads={}, generated_at=DAY + 'T23:00:00Z')]
        for days in (1, 40):
            dates = sessions(days)
            requests.append({**fixture.request, 'as_of': dates[-1],
                'sessions_by_instrument': {fixture.fixture.instrument: dates},
                'completed_reads': {fixture.fixture.instrument: fixture.fixture.read(
                    tuple({**fixture.fixture.entry, 'date': day} for day in dates))},
                'generated_at': dates[-1] + 'T23:00:00Z'})
        result = {'task_id': execution_task_id(fixture.fixture.signal),
                  'root_bytes': b64(encode_signal(fixture.fixture.signal)),
                  'requests': [b64(encode(request)) for request in requests]}
    elif value['operation'] == 'fixture':
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
        elif value['operation'] == 'trade_evaluate':
            from tests.test_m12_trade_evaluation import RegisteredTradeEvaluationTests
            from services.evaluation.runner import store_baseline_evaluation_batch
            from services.evaluation.storage import EvaluationShadowStore
            RegisteredTradeEvaluationTests.setUpClass()
            fixture = RegisteredTradeEvaluationTests()
            fixture.setUp()
            fixture.history.snapshot, fixture.history.objects = snapshot, objects
            previous = [json.loads(base64.b64decode(raw, validate=True))
                        for raw in value.get('previous_outcome_bytes', ())]
            evaluated = fixture.evaluate(previous=previous)
            store = EvaluationShadowStore(value['shadow_root'])
            paths = store_baseline_evaluation_batch(store, evaluated.batch)
            result = {'task_id': evaluated.task_id, 'state': evaluated.state,
                'reason': evaluated.reason, 'dependency_bytes': b64(evaluated.dependency_bytes),
                'batch': evaluated.batch, 'outcome_bytes': [b64(encode(item)) for item in evaluated.batch.outcomes],
                'paths': [str(path) for path in paths],
                'refs': store.result_references_for_run(evaluated.batch.pending_run_receipt['run_id'])}
        elif value['operation'] == 'restore':
            restored = restore_execution_history(snapshot, objects)
            result = {'confirmed_through': dict(restored.confirmed_through),
                      'holding_sessions': [state['holding_sessions'] for state in restored.states],
                      'entry_dates': [plan['entry_date'] for plan in restored.plans]}
        else:
            raise ValueError('unknown test operation')
    sys.stdout.buffer.write(encode(result))
    sys.stdout.buffer.flush()
    faulthandler.cancel_dump_traceback_later()


if __name__ == '__main__':
    main()
