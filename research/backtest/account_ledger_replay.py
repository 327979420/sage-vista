"""Reproduce a frozen legacy account with exact window hashes, adding a daily book."""
import json
import os
from pathlib import Path
from research.backtest.run_store import validate_receipt,encode,sha256
from research.backtest.account_runner import account
from research.backtest.account_ledger import render_ledger,close
from services.scanner.cr056_inputs import normalized_comparison_rows


def main():
    source=Path('research/backtest/output/reusable-runs/34240123213-1/receipt.json')
    r=json.loads(source.read_bytes());validate_receipt(r)
    cache=Path('work/eodhd-cache');out=Path('work/account-ledger-attempt');out.mkdir(parents=True,exist_ok=True)
    start,end=r['request']['start'],r['request']['end']
    events=[{'event_id':t['event_id'],'symbol':t['symbol'],'signal_date':t['signal_date'],'selection':t['signal_snapshot']['selection']} for t in r['trades']]
    rows={};window_hashes={};changed=[]
    for symbol,expected in r['source']['windows_sha256'].items():
        raw=[p for p in json.loads((cache/(symbol+'.json')).read_bytes()) if start<=p['date']<=end]
        window_hashes[symbol]=sha256(encode(raw))
        if window_hashes[symbol]!=expected:changed.append(symbol)
        rows[symbol]=normalized_comparison_rows(raw,as_of=end)
    spy=[p for p in json.loads((cache/'SPY.json').read_bytes()) if start<=p['date']<=end]
    sessions=[p['date'] for p in normalized_comparison_rows(spy,as_of=end)]
    if sha256(encode(sessions))!=r['source']['reference_sessions_sha256']:raise ValueError('calendar_mismatch')
    equity,returns,trades,book=account(events,rows,sessions,r['scenario'],with_ledger=True)
    if len(equity)!=len(r['daily_account']):raise ValueError('account_length_mismatch')
    if not changed:
        for d,v in zip(r['daily_account'],equity):close(d['equity'],float(v),'frozen_equity')
    old={t['event_id']:t for t in r['trades']}
    for t in ([] if changed else trades):
        for key in ('status','quantity','net_pnl','entry_fees','exit_fees','reason'):
            a,b=t.get(key),old[t['event_id']].get(key)
            if isinstance(a,(int,float)) and isinstance(b,(int,float)):close(a,b,'frozen_trade_'+key)
            elif a!=b:raise ValueError('frozen_trade_mismatch:'+key)
    book['provenance']={'source_receipt':r['id'],'source_hash':r['content_sha256'],'run':os.environ.get('GITHUB_RUN_ID'),'code':os.environ.get('GITHUB_SHA'),'price_cache':'observation-history-v1-34766761296-1','price_window_hashes':window_hashes,'changed_price_symbols':changed,'exact_price_window_hashes':not changed,'original_equity_and_trades_reproduced':not changed,'experiment_kind':'same_frozen_signals_revised_prices' if changed else 'exact_replay','source_ending_value':r['daily_account'][-1]['equity']}
    (out/'daily-portfolio-ledger.json').write_bytes(encode(book))
    report=render_ledger(book)
    if changed:
        report=report.replace('<h1>每天的钱去了哪里？</h1>','<h1>每天的钱去了哪里？</h1><p><strong>这是新对照：沿用旧候选与旧规则，使用现存行情。'+str(len(changed))+'只股票的价格文件与旧版本不同，不能视作旧结果的原样复现；也不是新版分周期策略。</strong></p>')
    (out/'report.html').write_text(report)
    (out/'manifest.json').write_bytes(encode({'provenance':book['provenance'],'files':{f.name:sha256(f.read_bytes()) for f in (out/'daily-portfolio-ledger.json',out/'report.html')}}))
    print(json.dumps({'sessions':len(sessions),'events':len(events),'ending_value':float(equity.iloc[-1]),'original_parity':not changed,'changed_price_symbols':changed,'daily_vectorbt_reconciliation':True}))

if __name__=='__main__':main()
