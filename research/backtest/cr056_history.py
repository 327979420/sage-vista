"""Adapt cached historical shared entry tickets to the existing CR056 scorer/account.

No downloads, current watch imports, alternative scorer, or production writes.
The experiment starts an empty nomination cohort; old results stay immutable.
"""
from bisect import bisect_right
from pathlib import Path
import hashlib
import json
import os
from research.backtest.run_store import ROOT, encode, sha256, POLICY
from services.contracts.cr056_policy import POLICY_VERSION, POLICY_FINGERPRINT
from services.scanner.cr056_inputs import normalized_comparison_rows
from services.gates.baseline import MIN_HISTORY_SESSIONS, MIN_CLOSE, MIN_DOLLAR_VOLUME
from services.factors.cr056 import collect_direction_facts, collect_entry_facts
from services.selectors.cr056 import assess_permission, assess_entry
from services.scanner.cr056_runner import run_snapshot
from services.scanner.support_risk import signal_support_plan


def ticket_dates(rows, start, end):
    # Cheap shared geometry first, full multi-factor scoring only for gate hits.
    for i,r in enumerate(rows):
        if (i < MIN_HISTORY_SESSIONS-1 or not start <= r['date'] <= end
                or r['close'] < MIN_CLOSE or r['close']*r['volume'] < MIN_DOLLAR_VOLUME):
            continue
        if assess_entry(collect_entry_facts(rows[:i+1],as_of=r['date'],complete_session=True))['eligible']:
            yield r['date']



def prepare(request, cache_dir, work, code_commit):
    cache=Path(cache_dir);work=Path(work);work.mkdir(parents=True,exist_ok=True)
    raw_reference=json.loads((cache/'SPY.json').read_bytes())
    start,end=request['start'],request['end']
    if not raw_reference or raw_reference[0]['date']>start or raw_reference[-1]['date']<end:
        raise ValueError('requested_reference_calendar_not_covered')
    sessions=[r['date'] for r in raw_reference if start<=r['date']<=end]
    if len(sessions)<2:raise ValueError('insufficient_reference_sessions')
    rows_by_symbol={};raw_by_symbol={};dates_by_symbol={};sources={};tickets={d:[] for d in sessions};excluded={};calendar=set(r['date'] for r in raw_reference)
    code={str(p.relative_to(ROOT)):sha256(p.read_bytes()) for folder in ('services','research/backtest') for p in sorted((ROOT/folder).rglob('*.py'))}
    for path in sorted(cache.glob('*.json')):
        symbol=path.stem
        if not symbol.replace('-','').replace('.','').isalnum():continue
        raw=path.read_bytes();sources[symbol]=sha256(raw)
        try:
            bounded=[r for r in json.loads(raw) if r['date']<=end]
            rows=normalized_comparison_rows(bounded,as_of=end)
            dates=[r['date'] for r in rows]
            if dates!=sorted(set(dates)):raise ValueError('duplicate_or_unsorted_sessions')
            if any(d not in calendar for d in dates):raise ValueError('asset_calendar_mismatch')
            if len(rows)<MIN_HISTORY_SESSIONS:raise ValueError('history_below_420')
            rows_by_symbol[symbol]=rows;raw_by_symbol[symbol]=bounded;dates_by_symbol[symbol]=dates
            ticket_key=sha256(encode({'source':sources[symbol],'start':start,'end':end,'policy':POLICY_FINGERPRINT,'code':code}))
            ticket_file=work/f'tickets-{symbol}.json'
            saved=json.loads(ticket_file.read_bytes()) if ticket_file.exists() else {}
            ticket_body={k:v for k,v in saved.items() if k!='sha256'}
            if saved.get('key')==ticket_key and saved.get('sha256')==sha256(encode(ticket_body)):
                dates_for_symbol=saved['dates']
            else:
                dates_for_symbol=list(ticket_dates(rows,start,end))
                ticket_body={'key':ticket_key,'dates':dates_for_symbol}
                temp=ticket_file.with_suffix('.tmp');temp.write_bytes(encode({**ticket_body,'sha256':sha256(encode(ticket_body))}));os.replace(temp,ticket_file)
            for d in dates_for_symbol:tickets[d].append(symbol)
        except (ValueError,TypeError,KeyError) as exc:excluded[symbol]=str(exc)
    if 'SPY' not in rows_by_symbol:raise ValueError('reference_normalization_failed')
    # Bind checkpoint to all code that can affect selection and to source bytes.
    identity=sha256(encode({'request':request,'policy':POLICY_FINGERPRINT,'sources':sources,'code':code,'cohort':'empty_at_window_start'}))
    checkpoint=work/'checkpoint.json'
    state={'identity':identity,'days':[],'events':[],'nominated':[],'exclusions':excluded,'coverage':{'first':start,'last':end},'sources':sources}
    if checkpoint.exists():
        saved=json.loads(checkpoint.read_bytes())
        if saved.get('identity') != identity:
            raise ValueError('checkpoint_policy_or_sources_changed_start_new_run')
        if saved.get('identity')==identity:
            body={k:v for k,v in saved.items() if k!='checkpoint_sha256'}
            if saved.get('checkpoint_sha256')!=sha256(encode(body)):raise ValueError('checkpoint_integrity_failed')
            if [d['date'] for d in saved['days']]!=sessions[:len(saved['days'])]:raise ValueError('checkpoint_session_order_failed')
            state=body
    nominated=set(state['nominated']);done={d['date'] for d in state['days']}
    stage=work.parent/'research-current-inputs';stage.mkdir(parents=True,exist_ok=True)
    for day in sessions:
        if day in done:continue
        eligible=[];unavailable={};rejected=0;missing_sessions=[]
        for symbol,rows in rows_by_symbol.items():
            dates=dates_by_symbol[symbol]
            # Count gaps explicitly rather than calling a missing bar "no signal".
            if dates[0]<=day and day not in dates:missing_sessions.append(symbol)
        for symbol in tickets[day]:
            if symbol in nominated:continue
            rows=rows_by_symbol[symbol];dates=dates_by_symbol[symbol]
            past=rows[:bisect_right(dates,day)]
            try:
                permission=assess_permission(collect_direction_facts(past,as_of=day,complete_session=True))
                if permission['eligible']:eligible.append(symbol)
                else:rejected+=1
            except (ValueError,TypeError,KeyError,ZeroDivisionError) as exc:unavailable[symbol]=str(exc)
        names=set(eligible)|{'SPY'}
        daily_hashes={}
        for symbol in names:
            bounded=raw_by_symbol[symbol][:bisect_right(dates_by_symbol[symbol],day)]
            content=encode(bounded);(stage/f'{symbol}.json').write_bytes(content);daily_hashes[symbol]=sha256(content)
        input_report={'as_of':day,'result_role':'legacy_comparison_input_repair','repaired':[{'symbol':s,'repaired_sha256':daily_hashes[s],'source_sha256':sources[s]} for s in sorted(names)],'repaired_count':len(names),'excluded_count':0,'excluded':{}}
        report=run_snapshot(stage,as_of=day,history={'days':[]},code_commit=code_commit,input_report=input_report)
        selected=[r for r in report['reviews'] if r['symbol'] in eligible and r.get('score',{}).get('total_score') is not None]
        selected.sort(key=lambda r:r['rank'])
        ranking=[]
        for rank,r in enumerate(selected,1):
            symbol=r['symbol'];nominated.add(symbol)
            rows=rows_by_symbol[symbol];past=rows[:bisect_right([x['date'] for x in rows],day)]
            selection={'rank':rank,'technical_score':r['score']['total_score'],'model_version':POLICY_VERSION,'execution_policy_version':POLICY,
                       'policy_fingerprint':POLICY_FINGERPRINT,'score_fingerprint':r['score']['score_fingerprint'],
                       'timeframe_scores':{k:100*v['normalized'] for k,v in r['score']['timeframes'].items()},
                       'entry_gate':r.get('entry_gate'), 'reasons':r['reason_codes'],'support_plan':signal_support_plan(past)}
            ranking.append({'symbol':symbol,**selection})
            state['events'].append({'event_id':f'CR056-{symbol}-{day}','symbol':symbol,'signal_date':day,'selection':selection})
        unavailable.update({r['symbol']:','.join(r['reason_codes']) for r in report['reviews'] if r['symbol'] in eligible and r['status']=='unavailable'})
        state['days'].append({'date':day,'model_version':POLICY_VERSION,'candidate_count':len(ranking),'ranking':ranking,'entry_tickets':len(tickets[day]),'policy_fingerprint':POLICY_FINGERPRINT,'direction_rejected':rejected,'unavailable':unavailable,'missing_session_symbols':missing_sessions,'source_snapshot':report['snapshot_fingerprint']})
        state['nominated']=sorted(nominated)
        sealed={**state,'checkpoint_sha256':sha256(encode(state))}
        tmp=checkpoint.with_suffix('.tmp');tmp.write_bytes(encode(sealed));os.replace(tmp,checkpoint)
        print(f'CR056 history {day}: tickets={len(tickets[day])}, nominations={len(ranking)}, completed={len(state["days"])}/{len(sessions)}',flush=True)
    ledger={'coverage':state['coverage'],'events':state['events']}
    ranking={'future_data_used':False,'days':state['days'],'history_role':'observed_cache_empty_initial_cohort','sources_sha256':sha256(encode(sources)),'excluded_sources':excluded}
    ledger_path=work/'signals.json';ranking_path=work/'rankings.json'
    ledger_path.write_bytes(encode(ledger));ranking_path.write_bytes(encode(ranking))
    return ledger_path,ranking_path
