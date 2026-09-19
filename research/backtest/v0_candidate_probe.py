"""Run in the original 2.0 checkout: fixed universe, empty initial cohort."""
import json
import sys
from pathlib import Path
from services.scanner.cr056_inputs import normalized_comparison_rows
from services.scanner.cr056_runner import run_snapshot
from services.scanner.support_risk import signal_support_plan
from services.contracts.cr056_policy import POLICY_FINGERPRINT, POLICY_VERSION
from research.backtest.run_store import encode, sha256, POLICY

cache, output = map(Path, sys.argv[1:3])
manifest=json.loads((cache/'price-manifest.json').read_bytes())
symbols=sorted(set(manifest['files'])-{'SPY'})
raw={s:json.loads((cache/(s+'.json')).read_bytes()) for s in symbols+['SPY']}
sessions=[r['date'] for r in raw['SPY'] if '2026-02-02'<=r['date']<='2026-02-27']
stage=output/'stage';stage.mkdir(parents=True,exist_ok=True)
nominated=set();events=[];days=[]
for day in sessions:
    sources=[]
    for symbol in sorted(raw,reverse=len(sys.argv)>3):
        content=encode([r for r in raw[symbol] if r['date']<=day])
        (stage/(symbol+'.json')).write_bytes(content)
        sources.append({'symbol':symbol,'repaired_sha256':sha256(content),'source_sha256':manifest['files'][symbol]['raw_sha256']})
    sources.sort(key=lambda r:r['symbol'])
    report=run_snapshot(stage,as_of=day,history={'days':[]},code_commit='8532d13a8bf7bcb0fc9a6b7bd60b3ccacce0c160',input_report={
        'as_of':day,'result_role':'legacy_comparison_input_repair','repaired':sources,'repaired_count':len(sources),'excluded_count':0,'excluded':{}})
    reviews=[r for r in report['reviews'] if r['symbol'] in symbols]
    if any(r['status']=='unavailable' for r in reviews):raise ValueError('candidate_input_unavailable')
    selected=[r for r in reviews if r['new_nomination'] and r['symbol'] not in nominated]
    selected.sort(key=lambda r:(-r['score']['total_score'],-r['score']['timeframes']['monthly_completed']['normalized'],-r['score']['timeframes']['weekly_completed']['normalized'],r['instrument_id']))
    ranking=[]
    for rank,r in enumerate(selected,1):
        symbol=r['symbol'];score=r['score']
        past=normalized_comparison_rows([v for v in raw[symbol] if v['date']<=day],as_of=day)
        selection={'rank':rank,'technical_score':score['total_score'],'model_version':POLICY_VERSION,'execution_policy_version':POLICY,
            'policy_fingerprint':POLICY_FINGERPRINT,'score_fingerprint':score['score_fingerprint'],
            'timeframe_scores':{k:100*v['normalized'] for k,v in score['timeframes'].items()},'reasons':r['reason_codes'],'support_plan':signal_support_plan(past)}
        events.append({'event_id':f'CR056-{symbol}-{day}','symbol':symbol,'signal_date':day,'selection':selection})
        ranking.append({'symbol':symbol,**selection});nominated.add(symbol)
    days.append({'date':day,'ranking':ranking,'candidate_count':len(ranking),'checks':[
        {'symbol':r['symbol'],'rule_eligible':r['new_nomination'],'status':r['status'],'reason_codes':r['reason_codes'],'input_fingerprint':r.get('input_fingerprint')} for r in reviews]})
(output/'candidates.json').write_bytes(encode({'policy':POLICY_VERSION,'policy_fingerprint':POLICY_FINGERPRINT,'symbols':symbols,'sessions':sessions,'days':days,'events':events,'future_data_used':False}))
