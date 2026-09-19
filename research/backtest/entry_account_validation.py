"""Only monthly readiness changes. Both books use the unchanged V0 account."""
import argparse
from bisect import bisect_left
from collections import defaultdict,Counter
import copy
import csv
import gzip
import json
import math
import os
from pathlib import Path
from statistics import mean,median
import subprocess

from research.backtest.account_runner import account,attach_signal_audit,scenario_values
from research.backtest.account_ledger import validate_ledger_receipt
from research.backtest.entry_confirmation_report import read_analysis
from research.backtest.price_identity import digest,freeze_manifest,bind,require_consistent_baseline
from research.backtest.run_store import encode,sha256,validate_receipt,POLICY
from research.backtest.selection_observation import START,ASOF
from research.backtest.observation_continuation import SOURCE_HASH
from services.scanner.cr056_inputs import normalized_comparison_rows
from services.scanner.support_risk import signal_support_plan
from services.factors.cr056 import collect_entry_facts

ENTRY_FOLDER=Path('research/backtest/output/entry-confirmation/35425024708-1')
ENTRY_HASH='998f7b9566da39ab3a478f7c69d00d22e12fac55e4e76429d8b2a52db44ea053'
ENGINE_FILES=('research/backtest/account_runner.py','research/backtest/account_ledger.py','research/backtest/quantstats_report.py','services/scanner/support_risk.py')
VERSION='monthly-support-account-ab-v1'


def engine_identity():
    hashes={}
    for name in ENGINE_FILES:
        raw=Path(name).read_bytes()
        if raw!=subprocess.check_output(['git','show','918b2e7:'+name]):raise ValueError('formal_engine_changed:'+name)
        hashes[name]=sha256(raw)
    return hashes


def frozen_ranks(events):
    groups=defaultdict(list);result={}
    for e in events:groups[e['signal_date']].append(e)
    for day,values in groups.items():
        from services.scanner.cr056_runner import rank_reviews
        reviews=[{'instrument_id':e['symbol'],'episode_id':e['episode_id'],'score':{'total_score':e['score'],'timeframes':{tf:{'normalized':v/100} for tf,v in e['timeframe_scores'].items()}}} for e in values]
        for r in rank_reviews(reviews):result[r['episode_id']]=r['rank']
    return result


def order_inputs(candidates,opportunities):
    a=copy.deepcopy(candidates);b=[];states={}
    byid={o['episode_id']:o for o in opportunities}
    for e in candidates:
        if e['selection']['opportunity_timeframe']!='monthly_completed':b.append(copy.deepcopy(e));continue
        op=byid[e['event_id']];saved=op['methods']['support'];trigger=saved.get('trigger_date')
        state={'event_id':e['event_id'],'symbol':e['symbol'],'setup_date':e['signal_date'],
               'wait_end':op['wait_end'],'trigger_date':trigger,'saved_status':saved['status'],
               'state':'ORDER_PENDING' if trigger else 'EXPIRED' if saved['status']=='waiting_censored' else 'INVALIDATED',
               'source_evidence_sha256':digest(saved),'source_timeline':op['source_timeline']}
        if not trigger and saved['status'] not in ('waiting_censored','invalidated'):raise ValueError('unsupported_confirmation_state')
        if trigger:
            if not e['signal_date']<=trigger<=op['wait_end']:raise ValueError('trigger_outside_setup_window')
            ready=copy.deepcopy(e);ready['signal_date']=trigger;b.append(ready)
        states[e['event_id']]=state
    return a,b,states


def validate_inputs(candidates,a,b,states):
    base={e['event_id']:e for e in candidates};aa={e['event_id']:e for e in a};bb={e['event_id']:e for e in b}
    if len(base)!=len(candidates) or len(aa)!=len(a) or len(bb)!=len(b) or aa!=base:raise ValueError('candidate_control_mismatch')
    if not set(bb)<=set(base):raise ValueError('new_challenger_candidate')
    for eid,e in base.items():
        monthly=e['selection']['opportunity_timeframe']=='monthly_completed'
        if not monthly:
            if bb.get(eid)!=e:raise ValueError('non_monthly_changed')
        elif eid in bb:
            expected=copy.deepcopy(e);expected['signal_date']=states[eid]['trigger_date']
            if bb[eid]!=expected:raise ValueError('challenger_changed_more_than_entry_timing')
        elif states[eid]['state'] not in ('EXPIRED','INVALIDATED'):raise ValueError('unexplained_missing_order')
    return True


def validate_comparison(data,books):
    manifest=data['price_manifest'];symbols=set(manifest['files'])-{'SPY'}
    validate_inputs(data['candidates'],data['orders']['A'],data['orders']['B'],data['monthly_states'])
    if data['engine_identity']['A']!=data['engine_identity']['B']:raise ValueError('account_engine_mismatch')
    if data['scenarios']['A']!=data['scenarios']['B']:raise ValueError('account_config_mismatch')
    if scenario_values(data['scenarios']['A'])!={'initial_cash':100000,'allocation_fraction':.1,'max_positions':10,'cost_rate':.001,'fractional_shares':False}:raise ValueError('formal_v0_config_changed')
    supports={e['event_id']:e['selection']['support_plan'] for e in data['candidates']}
    for side in ('A','B'):
        value=books[side];contract=data['contracts'][side]
        if contract['manifest']!=manifest:raise ValueError('manifest_changed')
        require_consistent_baseline(contract)
        for role in ('setup','execution'):
            binding=contract[role]
            if binding!=bind(binding['payload'],manifest,symbols=symbols,verified=True):raise ValueError('source_binding_mismatch:'+role)
        if contract['setup']['payload']!=data['candidates']:raise ValueError('setup_source_mismatch')
        if contract['signal']['payload']!=data['orders'][side]:raise ValueError('signal_source_mismatch')
        if contract['support']['payload']!=supports:raise ValueError('support_source_mismatch')
        if contract['execution']['payload']!=value['trades']:raise ValueError('execution_source_mismatch')
        if contract['account']['payload']!={'book_sha256':digest(value)}:raise ValueError('account_source_mismatch')
        validate_ledger_receipt({'scenario':data['scenarios'][side],'portfolio_ledger':value['ledger'],'daily_account':value['daily_account']})
        lookup={e['event_id']:e for e in data['orders'][side]}
        for trade in value['trades']:
            event=lookup.get(trade['event_id'])
            if not event or trade['signal_snapshot']['selection']!=event['selection'] or trade['signal_date']!=event['signal_date']:raise ValueError('actual_trade_source_mismatch')
            if trade['status'] in ('open','closed') and trade['entry_date']<=trade['signal_date']:raise ValueError('fill_before_signal')
    return True


def periods(flags):
    result=[];current=None
    for day,hit in flags:
        if hit:
            if current is None:current={'start':day,'end':day,'sessions':0};result.append(current)
            current['end']=day;current['sessions']+=1
        else:current=None
    return result


def account_metrics(value,config):
    book=value['ledger'];days=book['days'];metrics=dict(book['metrics'])
    cap=config['max_positions'];maxflags=[(d['date'],len(d['starting_positions'])+len(d['executed_buys'])>=cap) for d in days]
    idle=[(d['date'],not d['positions']) for d in days]
    metrics.update(ending_portfolio_value=days[-1]['ending_portfolio_value'],daily_sessions=len(days),
        average_cash_balance=mean(d['ending_cash'] for d in days),
        average_open_positions=mean(len(d['positions']) for d in days),
        completely_idle_cash_sessions=sum(flag for _,flag in idle),
        completely_idle_cash_fraction=mean(flag for _,flag in idle),
        max_positions_sessions=sum(flag for _,flag in maxflags),max_positions_periods=periods(maxflags),
        longest_all_cash_period=max(periods(idle),key=lambda p:p['sessions']) if any(f for _,f in idle) else None,
        maximum_single_stock_account_weight=max((p['market_value']/d['ending_portfolio_value'] for d in days for p in d['positions']),default=0))
    return metrics


def attribute(candidates,states,books,rows,targets,sessions):
    trades={side:{t['event_id']:t for t in books[side]['trades']} for side in ('A','B')}
    days={side:{d['date']:d for d in books[side]['ledger']['days']} for side in ('A','B')}
    decisions={side:{x['event_id']:x for d in books[side]['ledger']['days'] for x in d['decisions']} for side in ('A','B')}
    outputs=[];links=defaultdict(list);capacity=[]
    entered=lambda t:t.get('status') in ('closed','open')
    for e in candidates:
        eid=e['event_id'];a=trades['A'].get(eid,{});b=trades['B'].get(eid,{})
        if e['selection']['opportunity_timeframe']=='monthly_completed' or not entered(b) or entered(a):continue
        da=decisions['A'].get(eid,{});db=decisions['B'].get(eid,{})
        if da.get('reason') not in ('position_limit','cash_or_whole_share_insufficient'):continue
        day=b['entry_date'];linked=[]
        for p in days['A'][day]['starting_positions']:
            key=p['event_id'];wait=states.get(key)
            if wait and wait['setup_date']<day<=wait['wait_end'] and (not wait['trigger_date'] or wait['trigger_date']>=day):linked.append(key);links[key].append(eid)
        capacity.append({'event_id':eid,'symbol':e['symbol'],'entry_date':day,'pnl_B':b['net_pnl'],
                         'A_decision':da,'B_decision':db,'overlapping_monthly_waits':linked,
                         'causality':'entry-only AB identifies total path effect; overlapping waits are non-unique possible capital sources'})
    for e in candidates:
        eid=e['event_id'];a=trades['A'].get(eid,{});b=trades['B'].get(eid,{})
        ea,eb=entered(a),entered(b);pa=a.get('net_pnl',0) if ea else 0;pb=b.get('net_pnl',0) if eb else 0
        monthly=e['selection']['opportunity_timeframe']=='monthly_completed'
        if not monthly and ea and eb and any(a.get(k)!=b.get(k) for k in ('entry_date','entry_price','quantity','execution','net_pnl')):raise ValueError('nonmonthly_shared_fill_changed')
        category=('monthly' if monthly else 'daily_weekly')+('_both' if ea and eb else '_A_only' if ea else '_B_only' if eb else '_neither')
        row={'event_id':eid,'ticker':e['symbol'],'timeframe':e['selection']['opportunity_timeframe'],
             'original_setup_date':e['signal_date'],'rank':e['selection']['rank'],
             'baseline_entry_date':a.get('entry_date') if ea else None,'challenger_fill_date':b.get('entry_date') if eb else None,
             'baseline_entry_price':a.get('entry_price') if ea else None,'challenger_entry_price':b.get('entry_price') if eb else None,
             'baseline_status':a.get('status','absent'),'challenger_status':b.get('status','no_trigger'),
             'baseline_exit':a.get('execution') if ea else None,'challenger_exit':b.get('execution') if eb else None,
             'baseline_pnl':pa,'challenger_pnl':pb,'pnl_difference':pb-pa,'category':category,
             'challenger_skipped':not eb,'skip_reason':b.get('reason') if not eb else None,
             'baseline_decision':decisions['A'].get(eid),'challenger_decision':decisions['B'].get(eid)}
        if monthly:
            wait=states[eid];trigger=wait['trigger_date'];prices={r['date']:r for r in rows[e['symbol']]}
            trigger_wait=bisect_left(sessions,trigger)-bisect_left(sessions,e['signal_date']) if trigger else None
            fill_wait=bisect_left(sessions,b['entry_date'])-bisect_left(sessions,e['signal_date']) if eb else None
            end=trigger or wait['wait_end'];reference=sessions[bisect_left(sessions,e['signal_date'])+1]
            dates=[d for d in sessions if reference<=d<=end];complete=all(d in prices for d in dates)
            path=[prices[d] for d in dates if d in prices];target=targets.get(eid,{}).get('target',{})
            reference_price=prices[reference]['open'] if reference in prices else None
            row.update(challenger_trigger_date=trigger,waiting_days=fill_wait,days_to_confirmation=trigger_wait,
                waiting_state=wait['state'],skip_reason=row['skip_reason'] or (wait['state'] if not eb else None),
                trigger_before_execution=bool(trigger),
                preconfirmation_mfe=max([0]+[r['high']/reference_price-1 for r in path]) if complete and reference_price else None,
                preconfirmation_end_return=path[-1]['close']/reference_price-1 if path and reference_price and complete else (0 if not dates else None),
                touched_prior_high_before_confirmation=any(r['high']>=target['price'] for r in path) if target.get('status')=='target_available' and complete else None,
                released_capital_trade_ids=links[eid],
                shared_support=e['selection']['support_plan'],
                missed_baseline_result=('profit' if pa>0 else 'loss' if pa<0 else 'zero') if ea and not eb else None,
                baseline_pnl_realised=a.get('status')=='closed' if ea else None)
        outputs.append(row)
    categories={k:sum(r['pnl_difference'] for r in outputs if r['category']==k) for k in sorted({r['category'] for r in outputs})}
    difference=books['B']['ledger']['days'][-1]['ending_portfolio_value']-books['A']['ledger']['days'][-1]['ending_portfolio_value']
    if not math.isclose(sum(categories.values()),difference,abs_tol=1e-6):raise ValueError('pnl_attribution_does_not_reconcile')
    return outputs,categories,capacity


def stability(books):
    results=[]
    for start,end in [('2005-09-12','2009-12-31'),('2010-01-01','2014-12-31'),('2015-01-01','2019-12-31'),('2020-01-01','2025-12-31'),('2026-01-01',ASOF)]:
        row={'start':start,'end':end}
        for side in ('A','B'):
            ds=[d for d in books[side]['ledger']['days'] if start<=d['date']<=end]
            if not ds:continue
            first=ds[0]['starting_portfolio_value'];last=ds[-1]['ending_portfolio_value'];peak=first;dd=0
            for d in ds:peak=max(peak,d['ending_portfolio_value']);dd=min(dd,d['ending_portfolio_value']/peak-1)
            row[side]={'starting_value':first,'ending_value':last,'pnl':last-first,'return':last/first-1,'drawdown_within_period':dd,
                       'buys':sum(len(d['executed_buys']) for d in ds),'average_capital_utilisation':mean(d['capital_utilisation'] for d in ds)}
        row['pnl_difference']=row['B']['pnl']-row['A']['pnl'];results.append(row)
    return results


def write_csv(path,records):
    keys=list(dict.fromkeys(k for r in records for k in r))
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        w.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in records)


def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',default='work/eodhd-cache');p.add_argument('--output',default='work/entry-account-validation');args=p.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    registry=json.loads(Path('research/backtest/v0-baseline.json').read_bytes());baseline=json.loads(Path(registry['receipt']).read_bytes());validate_receipt(baseline)
    if registry['status']!='accepted' or baseline['content_sha256']!=registry['content_sha256']:raise ValueError('formal_v0_required')
    scenario=baseline['scenario'];engine=engine_identity()
    parent=json.loads(Path('research/backtest/output/reusable-runs/35048162507-1/receipt.json').read_bytes());validate_receipt(parent)
    raw=read_analysis(ENTRY_FOLDER)
    if sha256(raw)!=ENTRY_HASH or parent['content_sha256']!=SOURCE_HASH:raise ValueError('frozen_source_mismatch')
    study=json.loads(raw);ops=study['opportunities'];sources={s['identity']['symbol']:s['identity'] for s in parent['observation']['sources']}
    symbols=sorted({o['symbol'] for o in ops});rows={};files={};cache=Path(args.cache)
    for symbol in symbols+['SPY']:
        path=cache/(symbol+'.json');content=path.read_bytes();values=json.loads(content)
        if symbol=='SPY':
            if {sources[s]['spy'] for s in symbols}!={sha256(encode(values))}:raise ValueError('spy_identity_mismatch')
        elif sha256(content)!=sources[symbol]['source']:raise ValueError('price_identity_mismatch:'+symbol)
        normalized=normalized_comparison_rows(values,as_of=ASOF);rows[symbol]=normalized
        files[symbol]={'raw_sha256':sha256(content),'normalized_sha256':digest(normalized),'first':normalized[0]['date'],'last':normalized[-1]['date']}
    manifest=freeze_manifest(files,source={'parent':SOURCE_HASH,'entry_study':ENTRY_HASH,'cache':'observation-history-v1-34766761296-1'})
    (out/'price-manifest.json').write_bytes(encode(manifest));print('Price identities verified: '+str(len(files)),flush=True)
    original={e['episode_id']:e for e in parent['events']};ranks=frozen_ranks(parent['events']);candidates=[]
    for op in ops:
        e=original[op['episode_id']];past=[r for r in rows[e['symbol']] if r['date']<=e['signal_date']]
        if not past or past[-1]['date']!=e['signal_date'] or past[-1]['close']!=e['signal_close']:raise ValueError('setup_price_mismatch')
        selection={'rank':ranks[e['episode_id']],'technical_score':e['score'],'timeframe_scores':e['timeframe_scores'],
            'model_version':e['entry_gate']['policy_version'],'policy_fingerprint':e['entry_gate']['policy_fingerprint'],
            'execution_policy_version':POLICY,'opportunity_timeframe':op['timeframe'],
            'original_setup_date':e['signal_date'],'support_as_of':e['signal_date'],'support_plan':signal_support_plan(past),
            'source_episode_sha256':digest(e),'rank_basis':'existing comparator on saved same-day nominations; full historical watchlist unavailable'}
        candidates.append({'event_id':e['episode_id'],'symbol':e['symbol'],'signal_date':e['signal_date'],'selection':selection})
        if op['timeframe']=='monthly_completed' and op['methods']['support'].get('trigger_date'):
            trigger=op['methods']['support']['trigger_date'];prefix=[r for r in rows[e['symbol']] if r['date']<=trigger]
            facts=collect_entry_facts(prefix,as_of=trigger,complete_session=True)['frames']['daily']
            if facts!=op['methods']['support']['trigger_evidence'] or not facts['support_reversal']:raise ValueError('daily_trigger_not_reproduced')
    candidates.sort(key=lambda e:(e['signal_date'],e['selection']['rank'],e['event_id']))
    a,b,states=order_inputs(candidates,ops);validate_inputs(candidates,a,b,states)
    sessions=[r['date'] for r in rows['SPY'] if START<=r['date']<=ASOF]
    window={s:[r for r in rows[s] if START<=r['date']<=ASOF] for s in symbols};books={};metrics={};contracts={}
    supports={e['event_id']:e['selection']['support_plan'] for e in candidates}
    for side,events in [('A',a),('B',b)]:
        print('Running unchanged account '+side+' with '+str(len(events))+' ready orders',flush=True)
        equity,returns,trades,ledger=account(events,window,sessions,scenario,with_ledger=True);attach_signal_audit(trades,events)
        books[side]={'trades':trades,'ledger':ledger,'daily_account':[{'date':d,'equity':float(v),'return':float(r)} for d,v,r in zip(sessions,equity,returns)]}
        metrics[side]=account_metrics(books[side],scenario)
        contracts[side]={'manifest':manifest,
            'setup':bind(candidates,manifest,symbols=symbols,verified=True),'signal':bind(events,manifest,symbols=symbols,verified=True),
            'support':bind(supports,manifest,symbols=symbols,verified=True),'execution':bind(trades,manifest,symbols=symbols,verified=True),
            'account':bind({'book_sha256':digest(books[side])},manifest,symbols=symbols,verified=True)}
        (out/(side+'-book.json.gz')).write_bytes(gzip.compress(encode(books[side]),mtime=0))
        print(side+' ending value '+str(metrics[side]['ending_portfolio_value']),flush=True)
    for s,meta in files.items():
        if sha256((cache/(s+'.json')).read_bytes())!=meta['raw_sha256']:raise ValueError('prices_changed_during_run')
    prior=Path('research/backtest/output/prior-high/35059821246-1/analysis.json');prior_manifest=json.loads(prior.with_name('manifest.json').read_bytes())
    if sha256(prior.read_bytes())!=prior_manifest['files']['analysis.json']:raise ValueError('prior_high_source_mismatch')
    prior_data=json.loads(prior.read_bytes())
    if prior_data['source_hash']!=SOURCE_HASH:raise ValueError('prior_high_parent_mismatch')
    targets={e['episode_id']:e for e in prior_data['events']}
    attribution,categories,capacity=attribute(candidates,states,books,rows,targets,sessions)
    monthly=[r for r in attribution if r['timeframe']=='monthly_completed']
    waiting=[r['days_to_confirmation'] for r in monthly if r['days_to_confirmation'] is not None]
    fill_wait=[r['waiting_days'] for r in monthly if r['waiting_days'] is not None]
    entry={'monthly_setups':len(monthly),'direct_entries_A':sum(r['baseline_status'] in ('open','closed') for r in monthly),
        'triggered_B':len(waiting),'filled_B':len(fill_wait),'expired':sum(r['waiting_state']=='EXPIRED' for r in monthly),'invalidated':sum(r['waiting_state']=='INVALIDATED' for r in monthly),
        'confirmation_wait_mean':mean(waiting) if waiting else None,'confirmation_wait_median':median(waiting) if waiting else None,
        'actual_fill_wait_mean':mean(fill_wait) if fill_wait else None,'actual_fill_wait_median':median(fill_wait) if fill_wait else None,
        'missed_baseline_results':dict(Counter(r['missed_baseline_result'] for r in monthly if r['missed_baseline_result'])),
        'prior_high_available':sum(r['touched_prior_high_before_confirmation'] is not None for r in monthly),
        'prior_high_touched_before_confirmation':sum(r['touched_prior_high_before_confirmation'] is True for r in monthly),
        'later_nonmonthly_fills_enabled_by_capacity':len(capacity),
        'later_capacity_pnl_B':sum(r['pnl_B'] for r in capacity),
        'B_skip_reasons':dict(Counter(r['skip_reason'] for r in monthly if r['challenger_skipped']))}
    data={'version':VERSION,'status':'completed','role':'strict_saved_cohort_AB_not_full_strategy_baseline',
        'run':os.environ.get('GITHUB_RUN_ID','local')+'-'+os.environ.get('GITHUB_RUN_ATTEMPT','1'),'commit':os.environ.get('GITHUB_SHA'),
        'formal_v0_unchanged':registry,'source_hash':SOURCE_HASH,'entry_source_hash':ENTRY_HASH,
        'engine_identity':{'A':engine,'B':engine},'scenarios':{'A':scenario,'B':scenario},'price_manifest':manifest,
        'candidates':candidates,'orders':{'A':a,'B':b},'monthly_states':states,'contracts':contracts,
        'metrics':metrics,'entry_confirmation':entry,'attribution_categories':categories,'attribution':attribution,
        'capacity_effects':capacity,'stability':stability(books),'period':{'start':sessions[0],'end':sessions[-1],'sessions':len(sessions)},
        'decision':'PENDING_REVIEW',
        'limitations':['saved nominee cohort only, not full historical watchlist','same conservative 64 merged events excluded in both books','single previously examined history, no independent holdout','fixed $10000 nominal position; no fresh setups after 2025-09-11','no new holding rule or support refresh; actual fills drive existing 40-session exits']}
    validate_comparison(data,books)
    (out/'comparison.json.gz').write_bytes(gzip.compress(encode(data),mtime=0))
    (out/'summary.json').write_bytes(encode({k:data[k] for k in ('version','status','run','commit','period','metrics','entry_confirmation','attribution_categories','stability','decision','limitations')}))
    write_csv(out/'monthly-attribution.csv',monthly);write_csv(out/'all-trade-attribution.csv',attribution)
    write_csv(out/'daily-comparison.csv',[{'date':d,'A_equity':aa['equity'],'B_equity':bb['equity'],'difference':bb['equity']-aa['equity']} for d,aa,bb in zip(sessions,books['A']['daily_account'],books['B']['daily_account'])])
    (out/'manifest.json').write_bytes(encode({'run':data['run'],'price_version':manifest['price_version'],'files':{p.name:sha256(p.read_bytes()) for p in out.iterdir() if p.is_file() and p.name!='manifest.json'}}))
    print(json.dumps({'status':'completed','A':metrics['A']['ending_portfolio_value'],'B':metrics['B']['ending_portfolio_value'],'monthly':entry}),flush=True)

if __name__=='__main__':main()
