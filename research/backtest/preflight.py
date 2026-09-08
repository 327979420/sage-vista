"""Manual research input check. Account execution intentionally remains closed."""
import json
import os
from pathlib import Path
from research.backtest.run_store import encode, seal, validate_request


def prepare(request, *, run_id, attempt, code_commit):
    # Retain the submitted fields on failure; never copy arbitrary environment
    # variables or unknown inputs into a public receipt.
    retained = {k: v for k, v in request.items() if k in ('strategy', 'start', 'end')}
    try:
        validate_request(request)
    except ValueError as exc:
        status, reason = 'failed', str(exc)
    else:
        status, reason = 'unavailable', 'account_parameters_not_approved'
    return seal({'schema_version': 'legacy-research-run-v1',
                 'id': f'{run_id}-{attempt}', 'result_role': 'legacy/research',
                 'status': status, 'reason': reason, 'code_commit': code_commit,
                 'request': retained, 'summary': {}, 'report': None})


if __name__ == '__main__':
    receipt = prepare(json.loads(os.environ['RESEARCH_INPUTS']),
                      run_id=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                      code_commit=os.environ['GITHUB_SHA'])
    target = Path('work/research-attempt/receipt.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encode(receipt))
    print(json.dumps({'id': receipt['id'], 'status': receipt['status'], 'reason': receipt['reason']}))
