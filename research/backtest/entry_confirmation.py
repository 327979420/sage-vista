"""Frozen-event entry timing study. No selection, provider calls or account changes."""
import argparse
import csv
import json
import os
import random
from bisect import bisect_left
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import mean, median

from research.backtest.run_store import encode, sha256, validate_receipt
from research.backtest.selection_observation import ASOF, target_day
from research.backtest.observation_continuation import SOURCE_HASH
from research.backtest.observation_classification import classify
from services.scanner.cr056_inputs import normalized_comparison_rows
from services.factors.cr056 import collect_entry_facts
from services.contracts.cr056_policy import POLICY_FINGERPRINT

VERSION = 'entry-confirmation-v1'
METHODS = ('direct', 'breakout', 'support', 'momentum')
NAMES = dict(direct='直接买入', breakout='等日线突破', support='等支撑反转', momentum='等回踩动能恢复')
TF = dict(daily='日线', weekly_completed='周线', monthly_completed='月线')
LIMITS = dict(daily=(60,'d'), weekly_completed=(20,'w'), monthly_completed=(12,'m'))
TRANSITIONS = {
 'DETECTED': {'ACTIVE_SETUP'}, 'ACTIVE_SETUP': {'WAITING_FOR_DAILY_CONFIRMATION'},
 'WAITING_FOR_DAILY_CONFIRMATION': {'ENTRY_READY','INVALIDATED','EXPIRED'},
 'ENTRY_READY': {'ORDER_PENDING'}, 'ORDER_PENDING': {'OPEN_POSITION','INVALIDATED'},
 'OPEN_POSITION': {'EXIT_READY'}, 'EXIT_READY': {'CLOSED'}, 'CLOSED': set(),
 'EXPIRED': set(), 'INVALIDATED': set()}


def transition(log, state, day):
    if log and state not in TRANSITIONS[log[-1]['state']]:
        raise ValueError('invalid_state_transition')
    if log and day < log[-1]['date']: raise ValueError('backwards_state_time')
    log.append({'state':state,'date':day})


def triggers(frame):
    return {'direct':True, 'breakout':bool(frame.get('breakout')),
            'support':bool(frame.get('support_reversal')),
            'momentum':bool(frame.get('pullback_momentum',{}).get('confirmed'))}


def combine(events, sessions):
    """Deterministic common-cohort reservation, not production portfolio dedup."""
    result=[]
    for e in sorted(events,key=lambda e:(e['signal_date'],e['episode_id'])):
        if result and e['signal_date'] <= result[-1]['reserved_through']:
            result[-1]['source_events'].append(e)
            continue
        label=classify(e)['research_label']
        end=target_day(e['signal_date'],*LIMITS[label],sessions) or sessions[-1]
        reserve=target_day(end,30,'d',sessions) or sessions[-1]
        result.append({'symbol':e['symbol'],'episode_id':e['episode_id'],
                       'signal_date':e['signal_date'],'timeframe':label,
                       'wait_end':end,'reserved_through':reserve,'source_events':[e]})
    return result


def forward(prices, spy, sessions, fill, n):
    k=bisect_left(sessions,fill); dates=sessions[k:k+n]
    if len(dates)!=n:return {'status':'immature'}
    if any(d not in prices for d in dates):return {'status':'missing_prices'}
    base=prices[fill]['open']; rows=[prices[d] for d in dates]
    gain=rows[-1]['close']/base-1
    return {'status':'complete','end':dates[-1],'return':gain,
            'excess':gain-(spy[dates[-1]]['close']/spy[fill]['open']-1),
            'mae':min(0,min(r['low'] for r in rows)/base-1),
            'mfe':max(0,max(r['high'] for r in rows)/base-1)}


def replay(op, rows, spy, targets, facts_cache):
    prices={r['date']:r for r in rows}; index={r['date']:i for i,r in enumerate(rows)}
    sessions=sorted(spy); start=op['signal_date']; dates=[d for d in sessions if start<=d<=op['wait_end']]
    results={m:{'method':m,'status':'waiting_censored','states':[{'state':'DETECTED','date':start}]} for m in METHODS}
    for v in results.values():
        transition(v['states'],'ACTIVE_SETUP',start);transition(v['states'],'WAITING_FOR_DAILY_CONFIRMATION',start)
    sources={}; source_log=[]; frame_cache={}; pending={}; applied=[]
    bydate=defaultdict(list)
    for e in op['source_events']:bydate[e['signal_date']].append(e)
    for day in dates:
        if not any(v['status']=='waiting_censored' for v in results.values()) and not pending:break
        if day not in prices:
            for v in results.values():
                if v['status'] in ('waiting_censored','order_pending'):v['status']='missing_prices'
            pending.clear()
            break
        # Orders use only yesterday's active sources; today's close cannot cancel an earlier fill.
        for method, order in list(pending.items()):
            v=results[method]
            if prices[day]['open'] < min(p['structure_floor'] for p in order):
                v['status']='gap_invalidated';transition(v['states'],'INVALIDATED',day)
            else:
                v.update(status='filled',fill_date=day,fill_price=prices[day]['open'],
                         wait_days=bisect_left(sessions,day)-bisect_left(sessions,start),
                         outcomes={str(n):forward(prices,spy,sessions,day,n) for n in (5,10,20,30)})
                transition(v['states'],'OPEN_POSITION',day)
                end=v['outcomes']['30'].get('end')
                if end:
                    transition(v['states'],'EXIT_READY',end);transition(v['states'],'CLOSED',end)
            del pending[method]
        if not any(v['status']=='waiting_censored' for v in results.values()):break
        if day not in facts_cache:
            facts_cache[day]=collect_entry_facts(rows[:index[day]+1],as_of=day,complete_session=True,frame_cache=frame_cache)['frames']
        frames=facts_cache[day]
        for e in bydate[day]:
            applied.append(e['episode_id'])
            for p in e['entry_gate']['paths']:
                if p.get('structure_floor') and p['structure_key'] not in sources:
                    sources[p['structure_key']]={**p,'active':True,'detected_at':day}
                    source_log.append({'event':e['episode_id'],'date':day,'timeframe':p['timeframe'],'structure_key':p['structure_key']})
        for p in sources.values():
            f=frames[p['timeframe']]
            if p['active'] and f.get('completed_through') and f['completed_through']>p['confirmed_through'] and f['close']<p['structure_floor']:
                p.update(active=False,invalidated_at=day)
        active=[p for p in sources.values() if p['active']]
        hit=triggers(frames['daily'])
        for method,v in results.items():
            if v['status']!='waiting_censored':continue
            if not active:
                v['status']='invalidated';transition(v['states'],'INVALIDATED',day)
            elif hit[method]:
                v.update(status='order_pending',trigger_date=day,trigger_evidence=frames['daily'],
                         sources_at_trigger=sorted({p['timeframe'] for p in active}))
                transition(v['states'],'ENTRY_READY',day);transition(v['states'],'ORDER_PENDING',day)
                pending[method]=[dict(p) for p in active]
    # A confirmation at the last study close still executes on the following session.
    for method, order in pending.items():
        v=results[method]; k=bisect_left(sessions,v['trigger_date'])+1
        day=sessions[k] if k<len(sessions) else None
        if day is None or day not in prices:v['status']='missing_execution_price';continue
        if prices[day]['open']<min(p['structure_floor'] for p in order):
            v['status']='gap_invalidated';transition(v['states'],'INVALIDATED',day);continue
        v.update(status='filled',fill_date=day,fill_price=prices[day]['open'],wait_days=k-bisect_left(sessions,start),
                 outcomes={str(n):forward(prices,spy,sessions,day,n) for n in (5,10,20,30)})
        transition(v['states'],'OPEN_POSITION',day)
        if v['outcomes']['30'].get('end'):
            transition(v['states'],'EXIT_READY',v['outcomes']['30']['end']);transition(v['states'],'CLOSED',v['outcomes']['30']['end'])
    target=targets.get(op['episode_id'],{}).get('target',{})
    reference_day=target_day(start,1,'d',sessions)
    for v in results.values():
        fill=v.get('fill_date'); stop=fill or op['wait_end']
        waiting=[prices[d] for d in sessions if reference_day and reference_day<=d<stop and d in prices]
        if not fill and stop in prices:waiting.append(prices[stop])
        complete_wait=bool(reference_day) and all(d in prices for d in sessions if reference_day<=d<=stop)
        v['missed_prior_high']=None
        if target.get('status')=='target_available' and complete_wait:
            v['missed_prior_high']=any(r['high']>=target['price'] for r in waiting) or bool(fill and prices[fill]['open']>=target['price'])
        if reference_day in prices:
            ref=prices[reference_day]['open']
            v['waiting_mfe']=max([0]+[r['high']/ref-1 for r in waiting]) if complete_wait else None
            v['waiting_end_return']=(prices[fill]['open']/ref-1 if fill else prices[stop]['close']/ref-1) if stop in prices and complete_wait else None
    return {k:v for k,v in op.items() if k!='source_events'} | {
        'merged_event_ids':[e['episode_id'] for e in op['source_events']], 'applied_event_ids':applied,
        'source_timeline':source_log,'sources':list(sources.values()),'methods':results}


def worker(task):
    symbol, events, identity, cache, spy, targets, out, code = task
    path=Path(cache)/(symbol+'.json'); raw=path.read_bytes()
    if sha256(raw)!=identity['source']:raise ValueError('price_identity_mismatch:'+symbol)
    key={'version':VERSION,'source':SOURCE_HASH,'price':identity['source'],'code':code,
         'policy':POLICY_FINGERPRINT,'events':[e['episode_id'] for e in events]}
    check=Path(out)/'checkpoints'/(symbol+'.json')
    if check.exists():
        saved=json.loads(check.read_bytes())
        if saved['identity']!=key or saved['sha256']!=sha256(encode(saved['opportunities'])):raise ValueError('checkpoint_mismatch')
        return saved['opportunities']
    rows=normalized_comparison_rows(json.loads(raw),as_of=ASOF); prices={r['date']:r for r in rows}
    for e in events:
        if prices[e['signal_date']]['close']!=e['signal_close']:raise ValueError('signal_price_mismatch')
    facts={}; result=[replay(op,rows,spy,targets,facts) for op in combine(events,sorted(spy))]
    check.write_bytes(encode({'identity':key,'opportunities':result,'sha256':sha256(encode(result))}))
    return result


def bootstrap(pairs, field):
    clusters=defaultdict(list)
    for symbol,values in pairs:clusters[symbol].append(values[field])
    keys=sorted(clusters)
    if len(keys)<2:return None
    rng=random.Random(190926);samples=[]
    for _ in range(1000):
        values=[v for key in rng.choices(keys,k=len(keys)) for v in clusters[key]]
        samples.append(median(values))
    samples.sort();return [samples[24],samples[974]]


def summarize(ops, timeframe, method, n, period='all'):
    selected=[o for o in ops if o['timeframe']==timeframe and (period=='all' or int(period[:4])<=int(o['signal_date'][:4])<=int(period[-4:]))]
    records=[o['methods'][method] for o in selected]; filled=[r for r in records if r['status']=='filled']
    outcomes=[r['outcomes'][str(n)] for r in filled if r['outcomes'][str(n)]['status']=='complete']
    pairs=[]
    for o in selected:
        a=o['methods']['direct'].get('outcomes',{}).get(str(n),{});b=o['methods'][method].get('outcomes',{}).get(str(n),{})
        if a.get('status')==b.get('status')=='complete':pairs.append((o['symbol'],{k:b[k]-a[k] for k in ('return','mae','mfe','excess')}))
    result={'timeframe':timeframe,'method':method,'days':n,'period':period,'setups':len(selected),
        'statuses':dict(Counter(r['status'] for r in records)),'filled':len(filled),'complete':len(outcomes),
        'sample_warning':len(outcomes)<30,'wait_mean':mean(r['wait_days'] for r in filled) if filled else None,
        'wait_median':median(r['wait_days'] for r in filled) if filled else None,
        'filled_within':{str(d):sum(r['wait_days']<=d for r in filled) for d in (20,30,60)},
        'target_available':sum(r['missed_prior_high'] is not None for r in records),
        'missed_prior_high':sum(r['missed_prior_high'] is True for r in records),
        'missed_no_fill':sum(r['missed_prior_high'] is True and r['status']!='filled' for r in records),
        'paired_n':len(pairs),'paired_symbols':len({s for s,_ in pairs})}
    for k in ('return','excess','mae','mfe'):
        result[k+'_median']=median(x[k] for x in outcomes) if outcomes else None
        result['paired_'+k]=median(v[k] for _,v in pairs) if pairs else None
        if period=='all' and method!='direct':result['paired_'+k+'_ci95']=bootstrap(pairs,k)
    result['return_mean']=mean(x['return'] for x in outcomes) if outcomes else None
    result['win_rate']=mean(x['return']>0 for x in outcomes) if outcomes else None
    for field in ('waiting_mfe','waiting_end_return'):
        vals=[r[field] for r in records if r.get(field) is not None]
        result[field+'_median']=median(vals) if vals else None
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',default='work/eodhd-cache');p.add_argument('--output',default='work/entry-confirmation');p.add_argument('--workers',type=int,default=2);a=p.parse_args()
    baseline=json.loads(Path('research/backtest/v0-baseline.json').read_bytes())
    if baseline['status']!='accepted':raise ValueError('formal_v0_required')
    accepted=json.loads(Path(baseline['receipt']).read_bytes());validate_receipt(accepted)
    if accepted['content_sha256']!=baseline['content_sha256']:raise ValueError('baseline_receipt_mismatch')
    parent=json.loads(Path('research/backtest/output/reusable-runs/35048162507-1/receipt.json').read_bytes());validate_receipt(parent)
    if parent['content_sha256']!=SOURCE_HASH:raise ValueError('wrong_parent')
    identities={s['identity']['symbol']:s['identity'] for s in parent['observation']['sources']}
    raw=json.loads((Path(a.cache)/'SPY.json').read_bytes())
    if {x['spy'] for x in identities.values()}!={sha256(encode(raw))}:raise ValueError('spy_identity_mismatch')
    spy={r['date']:r for r in normalized_comparison_rows(raw,as_of=ASOF)}
    prior=Path('research/backtest/output/prior-high/35059821246-1/analysis.json')
    manifest=json.loads(prior.with_name('manifest.json').read_bytes())
    if sha256(prior.read_bytes())!=manifest['files']['analysis.json']:raise ValueError('prior_high_identity_mismatch')
    prior_data=json.loads(prior.read_bytes())
    if prior_data['source_hash']!=SOURCE_HASH:raise ValueError('wrong_prior_high_parent')
    targets={e['episode_id']:e for e in prior_data['events']}
    groups=defaultdict(list)
    for e in parent['events']:
        if classify(e)['research_label']:groups[e['symbol']].append(e)
    code=sha256(encode({str(f):sha256(f.read_bytes()) for f in [Path(__file__),Path('services/factors/cr056.py'),Path('services/scanner/detectors.py'),Path('services/scanner/macd_factor_backtest.py'),Path('services/contracts/cr056_policy.py')]}))
    out=Path(a.output);(out/'checkpoints').mkdir(parents=True,exist_ok=True)
    tasks=[(s,es,identities[s],a.cache,spy,targets,str(out),code) for s,es in sorted(groups.items())]
    ops=[]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for i,batch in enumerate(pool.map(worker,tasks),1):
            ops.extend(batch)
            if i%10==0:print(f'{i}/{len(tasks)} stocks; {len(ops)} unified opportunities',flush=True)
    stats=[summarize(ops,tf,m,n,period) for tf in TF for m in METHODS for n in (5,10,20,30) for period in ('all','2005-2009','2010-2014','2015-2019','2020-2025')]
    result={'version':VERSION,'status':'completed','account_baseline_unchanged':baseline,'parent_sha256':SOURCE_HASH,
            'code_sha256':code,'commit':os.environ.get('GITHUB_SHA'),'policy':POLICY_FINGERPRINT,
            'prior_high_sha256':sha256(prior.read_bytes()),'stock_count':len(groups),
            'raw_events':sum(map(len,groups.values())),'opportunities':ops,'statistics':stats,
            'price_sources':{s:identities[s] for s in groups}}
    (out/'analysis.json').write_bytes(encode(result))
    flat=[{k:(json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v) for k,v in row.items()} for row in stats]
    keys=sorted(set().union(*(r.keys() for r in flat)))
    with (out/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(flat)
    (out/'manifest.json').write_bytes(encode({'files':{p.name:sha256(p.read_bytes()) for p in out.iterdir() if p.is_file() and p.name!='manifest.json'},'commit':os.environ.get('GITHUB_SHA')}))
    print(json.dumps({'status':'completed','raw_events':result['raw_events'],'opportunities':len(ops)},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
