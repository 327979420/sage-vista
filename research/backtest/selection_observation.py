"""Versioned no-trade observations using the production gate and scorer."""
import argparse
import calendar
import csv
import gzip
import html
import io
import json
import os
import time
from bisect import bisect_left
from datetime import date, timedelta
from pathlib import Path
from statistics import median
from research.backtest.run_store import ROOT, encode, sha256, seal, trade_csv
from research.backtest.cr056_history import ticket_dates
from services.scanner.cr056_inputs import normalized_comparison_rows
from services.scanner.cr056_runner import run_snapshot
from services.contracts.cr056_policy import POLICY_VERSION, POLICY_FINGERPRINT

STRATEGY = 'cr056-selection-observation-v1'
START, END, ASOF = '2005-09-12', '2025-09-11', '2026-09-11'
WINDOWS = {'daily': [('5d',5,'d'),('10d',10,'d'),('20d',20,'d')],
 'weekly_completed':[('5w',5,'w'),('10w',10,'w'),('20w',20,'w')],
 'monthly_completed':[('3m',3,'m'),('6m',6,'m'),('9m',9,'m'),('12m',12,'m')]}
LABELS = {'daily':'日线','weekly_completed':'周线','monthly_completed':'月线'}


def target_day(day, count, unit, sessions):
    i=bisect_left(sessions,day)
    if unit=='d':j=i+count
    else:
        d=date.fromisoformat(day)
        if unit=='w':d+=timedelta(weeks=count)
        else:
            n=d.year*12+d.month-1+count;y,m=divmod(n,12);m+=1
            d=date(y,m,min(d.day,calendar.monthrange(y,m)[1]))
        j=bisect_left(sessions,d.isoformat())
    return sessions[j] if j<len(sessions) else None


def observe(event, rows, spy):
    sessions=sorted(spy);prices={r['date']:r for r in rows};day=event['signal_date'];base=prices[day]['close']
    outcomes={}
    for frames in WINDOWS.values():
        for name,n,u in frames:
            target=target_day(day,n,u,sessions)
            required=sessions[bisect_left(sessions,day)+1:bisect_left(sessions,target)+1] if target else []
            if target is None:outcomes[name]={'status':'immature'};continue
            if any(d not in prices for d in required):outcomes[name]={'status':'missing_prices','target_date':target};continue
            path=[prices[d] for d in required]
            gain=prices[target]['close']/base-1;benchmark=spy[target]['close']/spy[day]['close']-1
            outcomes[name]={'status':'complete','target_date':target,'return':gain,'spy_return':benchmark,'excess':gain-benchmark,
              'mfe':max(r['high'] for r in path)/base-1,'mae':min(r['low'] for r in path)/base-1,
              'days_to_10pct':next((i for i,r in enumerate(path,1) if r['close']>=base*1.1),None)}
    return {**event,'signal_close':base,'outcomes':outcomes}


def choose(gate,scores):
    paths=[p for p in gate['paths'] if p.get('structure_floor') and p['timeframe'] in scores]
    if not paths:return None
    priority={'daily':0,'weekly_completed':1,'monthly_completed':2}
    tf=max({p['timeframe'] for p in paths},key=lambda t:(scores[t],priority[t]))
    return tf,min(p['structure_floor'] for p in paths if p['timeframe']==tf)


def prepare_history():
    """Refresh whole source vintages, never splice differently adjusted tails."""
    from services.scanner.eodhd import prices
    cache=ROOT/'work/eodhd-cache';state_path=ROOT/'work/observation-history.json'
    state=json.loads(state_path.read_bytes()) if state_path.exists() else {'as_of':ASOF,'from':'2000-01-01','sources':{}}
    if state['as_of']!=ASOF:raise ValueError('research_history_vintage_changed')
    paths=[p for p in sorted(cache.glob('*.json')) if p.stem.replace('-','').replace('.','').isalnum()]
    requested=0
    for p in paths:
        raw=p.read_bytes();prior=state['sources'].get(p.stem)
        if prior and prior['sha256']==sha256(raw):continue
        old=json.loads(raw)
        # Only a previously verified full-history request proves later listing.
        # A truncated daily cache cannot establish a listing date.
        if old and old[0]['date']<='2000-01-03' and old[-1]['date']>=ASOF:
            rows=[r for r in old if r['date']<=ASOF];source='reused_long_cache'
        else:
            if requested>=2500:raise ValueError('history_request_budget_exhausted')
            rows=prices(p.stem,'2000-01-01',ASOF);requested+=1;source='full_history_provider_request'
            time.sleep(.25)
        if not isinstance(rows,list) or not rows:raise ValueError('history_provider_empty_'+p.stem)
        normalized_comparison_rows(rows,as_of=ASOF)
        days=[r['date'] for r in rows]
        if days!=sorted(set(days)) or days[-1]>ASOF:raise ValueError('history_invalid_or_stale_'+p.stem)
        content=encode(rows);temp=p.with_suffix('.tmp');temp.write_bytes(content);temp.replace(p)
        state['sources'][p.stem]={'sha256':sha256(content),'first':days[0],'last':days[-1],'sessions':len(days),'source':source}
        temp=state_path.with_suffix('.tmp');temp.write_bytes(encode(state));temp.replace(state_path)
        print(f'History {len(state["sources"])}/{len(paths)} {p.stem}: {days[0]} to {days[-1]}',flush=True)
    spy=state['sources'].get('SPY',{})
    if spy.get('first','9999')>START or spy.get('last','')<ASOF:raise ValueError('twenty_year_reference_history_missing')
    audit=ROOT/'work/observation/history-coverage.json';audit.parent.mkdir(parents=True,exist_ok=True)
    audit.write_bytes(encode(state))


def checkpoint_bytes(value):
    body={k:v for k,v in value.items() if k!='checkpoint_sha256'}
    return gzip.compress(encode({**body,'checkpoint_sha256':sha256(encode(body))}),mtime=0)


def shard(index,total,pilot=False):
    if POLICY_VERSION != 'cr056-policy-3.5.0-candidate':raise ValueError('experiment_requires_frozen_3_5_policy')
    cache=ROOT/'work/eodhd-cache';out=ROOT/'work/observation';out.mkdir(parents=True,exist_ok=True)
    spyraw=json.loads((cache/'SPY.json').read_bytes())
    spyrows=normalized_comparison_rows([r for r in spyraw if r['date']<=ASOF],as_of=ASOF)
    spy={r['date']:r for r in spyrows}
    start,end=('2025-01-02','2025-01-31') if pilot else (START,END)
    if min(spy)>start or max(spy)<ASOF:raise ValueError('reference_calendar_not_covered')
    paths=[p for p in sorted(cache.glob('*.json')) if p.stem.replace('-','').replace('.','').isalnum()]
    if pilot:paths=paths[:8]
    code=os.environ['GITHUB_SHA'];completed=[];started=time.monotonic();timing=[]
    for pos,p in enumerate(paths):
        if pos%total!=index:continue
        symbol_started=time.monotonic()
        raw=p.read_bytes();identity={'symbol':p.stem,'source':sha256(raw),'spy':sha256(encode(spyraw)),'code':code,'policy':POLICY_FINGERPRINT,'start':start,'end':end,'asof':ASOF}
        key=sha256(encode(identity));file=out/(p.stem+'.json.gz')
        if file.exists():
            saved=json.loads(gzip.decompress(file.read_bytes()))
            body={k:v for k,v in saved.items() if k!='checkpoint_sha256'}
            if saved.get('checkpoint_sha256')!=sha256(encode(body)):raise ValueError('checkpoint_integrity_failed')
            if saved.get('identity')!=identity:raise ValueError('checkpoint_identity_changed')
        else:saved={'identity':identity,'events':[],'done_through':'','active':None,'used':[],'complete':False,'evaluated':0,'unavailable':0}
        if saved['complete']:completed.append(p.stem);continue
        rows=normalized_comparison_rows([r for r in json.loads(raw) if r['date']<=ASOF],as_of=ASOF)
        if any(r['date'] not in spy for r in rows):
            saved['excluded']='calendar_mismatch';rows=[]
        saved['history_coverage']={'first':rows[0]['date'] if rows else None,'last':rows[-1]['date'] if rows else None,'sessions':len(rows)}
        print(f'{p.stem} cache coverage: {saved["history_coverage"]}',flush=True)
        stage=out/'stage';stage.mkdir(exist_ok=True)
        for old in stage.glob('*.json'):old.unlink()
        for row_index,row in enumerate(rows):
            day=row['date']
            if not start<=day<=end or day<=saved['done_through']:continue
            if time.monotonic()-started>14400:raise TimeoutError('observation_checkpoint_budget_resume')
            past=rows[:row_index+1]
            if row_index%50==0:
                temp=file.with_suffix('.tmp');temp.write_bytes(checkpoint_bytes(saved));temp.replace(file)
            if saved['active']:
                active=saved['active']
                if not any(r['close']<active['floor'] for r in past if r['date']>active['day']):
                    saved['done_through']=day
                    continue
                saved['active']=None
            if not next(iter(ticket_dates(past,day,day)),None):
                saved['done_through']=day
                continue
            rawpast=[r for r in json.loads(raw) if r['date']<=day]
            data={p.stem:rawpast,'SPY':[r for r in spyraw if r['date']<=day]}
            hashes={}
            for symbol,values in data.items():
                content=encode(values);(stage/(symbol+'.json')).write_bytes(content);hashes[symbol]=sha256(content)
            inputs={'as_of':day,'result_role':'legacy_comparison_input_repair','repaired':[{'symbol':s,'repaired_sha256':h,'source_sha256':identity['source'] if s==p.stem else identity['spy']} for s,h in hashes.items()], 'repaired_count':len(hashes),'excluded_count':0,'excluded':[]}
            report=run_snapshot(stage,as_of=day,history={'days':[]},code_commit=code,input_report=inputs)
            review=next((r for r in report['reviews'] if r['symbol']==p.stem),None)
            saved['evaluated']=saved.get('evaluated',0)+1
            if not review or review['status'] == 'unavailable':
                saved['unavailable']=saved.get('unavailable',0)+1
                reasons=review.get('reason_codes',[]) if review else ['review_missing']
                for reason in reasons:saved.setdefault('unavailable_reasons',{})[reason]=saved.setdefault('unavailable_reasons',{}).get(reason,0)+1
                if saved['unavailable']<=2:print(f'{p.stem} {day} unavailable: {reasons}',flush=True)
            if review and review['status']=='excluded':
                saved['rule_excluded']=saved.get('rule_excluded',0)+1
            if review and review.get('rank') is not None and review.get('score',{}).get('total_score') is not None and review.get('entry_gate',{}).get('eligible'):
                gate=review['entry_gate'];scores={k:100*v['normalized'] for k,v in review['score']['timeframes'].items()}
                picked=choose(gate,scores)
                new={p['structure_key'] for p in gate['paths']}-set(saved['used'])
                if picked and new:
                    tf,floor=picked;event={'symbol':p.stem,'signal_date':day,'episode_id':sha256(encode([key,day])),'timeframe':tf,'floor':floor,'score':review['score']['total_score'],'timeframe_scores':scores,'entry_gate':gate,'reasons':review['reason_codes']}
                    saved['events'].append(observe(event,rows,spy));saved['active']={'floor':floor,'day':day};saved['used']=sorted(set(saved['used'])|{p['structure_key'] for p in gate['paths']})
            saved['done_through']=day
            temp=file.with_suffix('.tmp');temp.write_bytes(checkpoint_bytes(saved));temp.replace(file)
        saved['complete']=True
        if not rows:saved.setdefault('excluded','no_rows')
        file.write_bytes(checkpoint_bytes(saved));completed.append(p.stem)
        timing.append({'symbol':p.stem,'seconds':time.monotonic()-symbol_started,'sessions':sum(start<=r['date']<=end for r in rows)})
        print(f'{p.stem}: {len(saved["events"])} opportunities; {len(completed)} symbols completed',flush=True)
    if pilot:
        checks=[json.loads(gzip.decompress((out/(symbol+'.json.gz')).read_bytes())) for symbol in completed]
        if not any(v.get('evaluated',0)>v.get('unavailable',0) for v in checks):raise ValueError('pilot_no_evaluable_candidates')
    (out/f'manifest-{index}.json').write_bytes(encode({'shard':index,'total':total,'symbols':completed,'pilot':pilot,'timing':timing,'cache_symbols':len(list(cache.glob('*.json'))),'code':code,'policy':POLICY_FINGERPRINT}))


def summarize(events):
    groups={}
    for e in events:
        band='<30' if e['score']<30 else '30–45' if e['score']<45 else '45–60' if e['score']<60 else '≥60'
        paths='+'.join(sorted({p['path'] for p in e['entry_gate']['paths']}))
        for label in ('全部', '分数 '+band,'年份 '+e['signal_date'][:4],'门票 '+paths):
            for window,_,_ in WINDOWS[e['timeframe']]:groups.setdefault((e['timeframe'],label,window),[]).append(e)
    result=[]
    for (tf,label,window),items in sorted(groups.items()):
        full=[e for e in items if e['outcomes'][window]['status']=='complete'];o=[e['outcomes'][window] for e in full]
        result.append({'timeframe':tf,'group':label,'window':window,'samples':len(items),'complete':len(full),'symbols':len({e['symbol'] for e in full}),
         'median_return':median(x['return'] for x in o) if o else None,'win_rate':sum(x['return']>0 for x in o)/len(o) if o else None,
         'median_excess':median(x['excess'] for x in o) if o else None,'median_mae':median(x['mae'] for x in o) if o else None,
         'median_mfe':median(x['mfe'] for x in o) if o else None,'interpretation':'探索，不能自动晋级；需分年与集中度复核'})
    return result


def aggregate(total):
    folder=ROOT/'work/observation';manifests=[json.loads(p.read_bytes()) for p in folder.glob('manifest-*.json')]
    if sorted(m['shard'] for m in manifests)!=list(range(total)):raise ValueError('incomplete_shards')
    symbols=[s for m in manifests for s in m['symbols']]
    if len(set(symbols))!=len(symbols):raise ValueError('duplicate_symbols')
    if len({m['code'] for m in manifests})!=1 or len({m['policy'] for m in manifests})!=1:raise ValueError('mixed_shard_identity')
    events=[];sources=[]
    for symbol in sorted(symbols):
        p=folder/(symbol+'.json.gz');v=json.loads(gzip.decompress(p.read_bytes()))
        if v.get('checkpoint_sha256')!=sha256(encode({k:x for k,x in v.items() if k!='checkpoint_sha256'})):raise ValueError('checkpoint_integrity_failed')
        if not v['complete'] or v['identity']['policy']!=POLICY_FINGERPRINT or v['identity']['code']!=os.environ['GITHUB_SHA']:raise ValueError('mixed_or_incomplete_checkpoint')
        events.extend(v['events']);sources.append({'identity':v['identity'],'checkpoint_sha256':sha256(p.read_bytes()),'excluded':v.get('excluded'),'evaluated':v.get('evaluated',0),'unavailable':v.get('unavailable',0)})
    if len({s['identity']['spy'] for s in sources})!=1:raise ValueError('mixed_reference_sources')
    groups=summarize(events)
    def percent(v):return '—' if v is None else f'{v*100:.2f}%'
    lines=['<html lang="zh"><meta charset="utf-8"><style>body{font:16px system-ui;padding:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:8px}</style><h1>3.5选股观察：不模拟买卖</h1>',f'<p>{START} 至 {END} 触发，观察截至 {ASOF}。{len(events)}次机会，{len(symbols)}只缓存股票。</p>', '<p>涨跌从信号确认收盘起算；不是交易收益。当前缓存股票池有幸存者及覆盖偏差，历史复权修订未证明。主导周期由有门票周期的未加权分数确定。小样本仅供探索，既有已见年份不称独立验证。</p><table><tr><th>周期/分组</th><th>期限</th><th>完整/总样本</th><th>股票数</th><th>中位涨跌</th><th>上涨比例</th><th>相对SPY</th><th>途中最低相对起点</th><th>途中最高相对起点</th></tr>']
    for g in groups:lines.append('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in [LABELS[g['timeframe']]+' / '+g['group'],g['window'],f'{g["complete"]}/{g["samples"]}',g['symbols'],*[percent(g[k]) for k in ('median_return','win_rate','median_excess','median_mae','median_mfe')]])+'</tr>')
    lines.append('</table><h2>代表案例：按主要期限的结果选取，不用于证明策略有效</h2>')
    for tf,window in [('daily','10d'),('weekly_completed','10w'),('monthly_completed','6m')]:
        cases=sorted([e for e in events if e['timeframe']==tf and e['outcomes'][window]['status']=='complete'],key=lambda e:e['outcomes'][window]['return'])
        for i in sorted({0,len(cases)//2,len(cases)-1}) if cases else []:
            e=cases[i];o=e['outcomes'][window]
            lines.append('<p>'+html.escape(f"{LABELS[tf]} {e['symbol']} · {e['signal_date']} · 当时总分{e['score']:.2f} · {window}涨跌{percent(o['return'])} · 同期SPY{percent(o['spy_return'])} · 途中最低{percent(o['mae'])}。")+'</p>')
    lines.append('<p>后续用途：比较期限与类型，提出入场/退出实验；不能按期间最高价假定卖出。完整CSV与收据保留所有窗口和当时分项，可重新汇总而无需重新选股。</p></html>')
    report=''.join(lines).encode();runid=os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT']
    receipt=seal({'schema_version':'legacy-research-run-v1','id':runid,'result_role':'legacy/research','status':'completed', 'request':{'strategy':STRATEGY,'start':START,'end':END},'summary':{'opportunities':len(events),'symbols':len(symbols)},'code_commit':os.environ['GITHUB_SHA'],'report':{'path':runid+'/report.html','sha256':sha256(report)},'observation':{'policy':POLICY_VERSION,'fingerprint':POLICY_FINGERPRINT,'as_of':ASOF,'groups':groups,'sources':sources},'events':events})
    receipt['downloads']={'trades_csv':{'path':runid+'/trades.csv','sha256':sha256(trade_csv(receipt))}}
    receipt=seal(receipt)
    out=ROOT/'work/research-attempt';out.mkdir(parents=True,exist_ok=True);(out/'report.html').write_bytes(report);(out/'receipt.json').write_bytes(encode(receipt))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--shard',type=int,default=0);p.add_argument('--total',type=int,default=1);p.add_argument('--pilot',action='store_true');p.add_argument('--aggregate',action='store_true');p.add_argument('--prepare-history',action='store_true');a=p.parse_args()
    if a.prepare_history:prepare_history();raise SystemExit(0)
    aggregate(a.total) if a.aggregate else shard(a.shard,a.total,a.pilot)
