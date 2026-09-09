"""Existing workflow's research-mode boundary; default approval is absent."""
import argparse
import json
import os
from pathlib import Path
from research.backtest.account_runner import approved_scenario, execute
from research.backtest.run_store import ROOT, CANDIDATE_POLICY, HISTORICAL_CANDIDATE_POLICY, encode, seal, validate_request

OUT = ROOT/'work/research-attempt'


def run(*, check_only=False):
    inputs=json.loads(os.environ['RESEARCH_INPUTS'])
    request={k:inputs.get(k,'') for k in ('strategy','start','end')}
    identity={'run_id':os.environ['GITHUB_RUN_ID'],'attempt':os.environ['GITHUB_RUN_ATTEMPT'],
              'code_commit':os.environ['GITHUB_SHA']}
    phase="request"
    try:
        validate_request(request)
        if request['strategy'] == HISTORICAL_CANDIDATE_POLICY:
            raise ValueError('historical_policy_requires_original_code_use_current_for_new_runs')
        phase="approval"
        config=approved_scenario()
        if check_only:
            with open(os.environ['GITHUB_OUTPUT'],'a') as stream:stream.write('enabled=true\n')
            return
        phase="account"
        ledger=ROOT/'public/opportunity-ledger.json';kwargs={}
        if request['strategy']==CANDIDATE_POLICY:
            from research.backtest.cr056_history import prepare
            ledger,rankings=prepare(request,ROOT/'work/eodhd-cache',ROOT/'work/research-signals',identity['code_commit'])
            kwargs['rankings_path']=rankings
        execute(request,config,ROOT/'work/eodhd-cache',ledger,out=OUT,
                cache_key=os.environ['RESEARCH_CACHE_KEY'],**identity,**kwargs)
    except Exception as exc:
        # Preserve source failures and dependency/engine failures, without a
        # fabricated account metric. No traceback, token, or raw bars in output.
        reason=str(exc) if isinstance(exc,(ValueError,FileNotFoundError)) else type(exc).__name__
        receipt=seal({'schema_version':'legacy-research-run-v1','id':identity['run_id']+'-'+identity['attempt'],
                      'result_role':'legacy/research','status':'unavailable' if phase!='request' and isinstance(exc,(ValueError,FileNotFoundError)) else 'failed',
                      'request':request,'summary':{},'reason':reason,'report':None,'code_commit':identity['code_commit']})
        OUT.mkdir(parents=True,exist_ok=True);(OUT/'receipt.json').write_bytes(encode(receipt))
        if check_only:
            with open(os.environ['GITHUB_OUTPUT'],'a') as stream:stream.write('enabled=false\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args()
    run(check_only=args.check)
