"""Rebuild the bounded frozen V0 and promote only after source/parity checks."""
import copy
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from research.backtest.price_identity import validate_manifest,digest,bind,validate_baseline_receipt
from research.backtest.run_store import encode,sha256,seal,validate_receipt,trade_csv
from research.backtest.account_runner import account,attach_signal_audit
from research.backtest.account_ledger import render_ledger
from research.backtest.quantstats_report import render_daily_report
from services.scanner.cr056_inputs import normalized_comparison_rows
from research.backtest.elv_price_alignment import ROOT,LEGACY

VERSION='sha256:c287c7b91604d5881e04e5929cf55b848550febd17603284b7d45eed96220a7a'

def verified_prices(cache,manifest):
    if validate_manifest(manifest)!=VERSION:raise ValueError('wrong_frozen_vintage')
    result={}
    for symbol,meta in manifest['files'].items():
        raw=(cache/(symbol+'.json')).read_bytes()
        if sha256(raw)!=meta['raw_sha256']:raise ValueError('raw_price_changed:'+symbol)
        values=json.loads(raw);rows=normalized_comparison_rows(values,as_of=values[-1]['date'])
        if digest(rows)!=meta['normalized_sha256']:raise ValueError('normalized_price_changed:'+symbol)
        result[symbol]=rows
    return result

def main():
    out=ROOT/'work/v0-baseline';out.mkdir(parents=True,exist_ok=True)
    frozen=ROOT/'work/v0-frozen';manifest=json.loads((frozen/'price-manifest.json').read_bytes())
    rows=verified_prices(frozen/'prices',manifest)
    old=json.loads((ROOT/'research/backtest/output/reusable-runs/34240123213-1/receipt.json').read_bytes());validate_receipt(old)
    symbols=sorted(set(rows)-{'SPY'})
    if set(symbols)!={t['symbol'] for t in old['trades']}:raise ValueError('universe_changed')
    legacy=ROOT/'work/v0-legacy-code';legacy.mkdir(parents=True,exist_ok=True)
    subprocess.run(['tar','-x','-C',str(legacy)],input=subprocess.check_output(['git','archive',LEGACY,'services','research','config']),check=True)
    shutil.copyfile(frozen/'price-manifest.json',frozen/'prices/price-manifest.json')
    probes=[]
    for index in range(2):
        folder=out/f'probe-{index}';folder.mkdir(exist_ok=True)
        cmd=[sys.executable,str(ROOT/'research/backtest/v0_candidate_probe.py'),str(frozen/'prices'),str(folder)]+(['reverse'] if index else [])
        subprocess.run(cmd,cwd=legacy,env={**os.environ,'PYTHONPATH':str(legacy)},check=True)
        probes.append((folder/'candidates.json').read_bytes())
        shutil.rmtree(folder/'stage')
    if probes[0]!=probes[1]:raise ValueError('candidate_regeneration_not_stable')
    regenerated=json.loads(probes[0]);events=regenerated['events'];sessions=regenerated['sessions']
    if any(t['signal_snapshot']['selection']['policy_fingerprint']!=regenerated['policy_fingerprint'] for t in old['trades']):raise ValueError('policy_changed')
    if sha256(encode(sessions))!=old['source']['reference_sessions_sha256']:raise ValueError('calendar_changed')
    window={s:[r for r in rows[s] if old['request']['start']<=r['date']<=old['request']['end']] for s in symbols}
    equity,returns,trades,book=account(events,window,sessions,old['scenario'],with_ledger=True)
    attach_signal_audit(trades,events)
    contract={'manifest':manifest,'signal':bind(events,manifest,symbols=symbols,verified=True),
        'support':bind({e['symbol']:e['selection']['support_plan'] for e in events},manifest,symbols=symbols,verified=True),
        'account':bind(book,manifest,symbols=symbols,verified=True)}
    # Repeat after calculation to catch altered prices during the run.
    verified_prices(frozen/'prices',manifest)
    run=os.environ['GITHUB_RUN_ID']+'-'+os.environ.get('GITHUB_RUN_ATTEMPT','1')
    summary=render_daily_report(equity,returns,old['scenario']['initial_cash'],out/'report.html',title='Frozen 18-stock V0 baseline')
    closed=[t for t in trades if t['status']=='closed'];summary['win_rate']=sum(t['net_pnl']>0 for t in closed)/len(closed) if closed else None
    receipt={'schema_version':'legacy-research-run-v1','id':run,'result_role':'legacy/research','status':'completed','request':old['request'],
        'code_commit':os.environ['GITHUB_SHA'],'baseline_eligible':True,'baseline_status':'formal','baseline_scope':'V0_frozen_18_stock_2026_02_only_not_M10_production',
        'scenario':old['scenario'],'summary':summary,'price_consistency':contract,'portfolio_ledger':book,
        'daily_account':[{'date':d,'equity':float(v),'return':float(r)} for d,v,r in zip(sessions,equity,returns)],'trades':trades,
        'reproduction':{'runs':2,'full_candidate_bytes_equal':True,'candidate_sha256':sha256(probes[0]),'selection_code':LEGACY,'price_version':VERSION},
        'report':{'path':run+'/report.html','sha256':sha256((out/'report.html').read_bytes())},'synthetic':False}
    validate_baseline_receipt(receipt);receipt=seal(receipt)
    (out/'receipt.json').write_bytes(encode(receipt));(out/'candidates.json').write_bytes(probes[0]);(out/'price-manifest.json').write_bytes(encode(manifest))
    (out/'trades.csv').write_bytes(trade_csv(receipt));(out/'daily-ledger.html').write_text(render_ledger(book))
    old_events=[{'event_id':t['event_id'],'symbol':t['symbol'],'signal_date':t['signal_date'],'selection':t['signal_snapshot']['selection']} for t in old['trades']]
    mixed=account(old_events,window,sessions,old['scenario'],with_ledger=True)
    new_by={e['symbol']:e for e in events};old_by={e['symbol']:e for e in old_events}
    mixed_trades={t['symbol']:t for t in mixed[2]};new_trades={t['symbol']:t for t in trades}
    comparison=[];trade_fields=('status','quantity','entry_date','entry_price','execution','net_pnl','reason')
    for s in symbols:
        a=old_by.get(s);b=new_by.get(s);sa=a['selection'] if a else {};sb=b['selection'] if b else {}
        comparison.append({'ticker':s,'old_signal_date':a['signal_date'] if a else None,'new_signal_date':b['signal_date'] if b else None,
            'old_eligibility':bool(a),'new_eligibility':bool(b),'old_score':sa.get('technical_score'),'new_score':sb.get('technical_score'),
            'old_rank':sa.get('rank'),'new_rank':sb.get('rank'),'old_support':sa.get('support_plan'),'new_support':sb.get('support_plan'),
            'trade_changed_vs_mixed':any(mixed_trades.get(s,{}).get(k)!=new_trades.get(s,{}).get(k) for k in trade_fields),
            'old_trade':mixed_trades.get(s),'new_trade':new_trades.get(s)})
    (out/'comparison.json').write_bytes(encode(comparison))
    with (out/'comparison.csv').open('w',newline='') as f:
        keys=['ticker','old_signal_date','new_signal_date','old_eligibility','new_eligibility','old_score','new_score','old_rank','new_rank','old_support','new_support','trade_changed_vs_mixed']
        writer=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');writer.writeheader();writer.writerows(comparison)
    (out/'manifest.json').write_bytes(encode({'run':run,'price_version':VERSION,'files':{p.name:sha256(p.read_bytes()) for p in out.iterdir() if p.is_file() and p.name!='manifest.json'}}))
    print(json.dumps({'run':run,'events':len(events),'baseline_eligible':True,'ending_equity':summary['ending_equity'],'changed_trade_symbols':[r['ticker'] for r in comparison if r['trade_changed_vs_mixed']]}))

if __name__=='__main__':main()
