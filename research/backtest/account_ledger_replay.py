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
    rows={}
    for symbol,expected in r['source']['windows_sha256'].items():
        raw=[p for p in json.loads((cache/(symbol+'.json')).read_bytes()) if start<=p['date']<=end]
        if sha256(encode(raw))!=expected:raise ValueError('frozen_price_window_mismatch:'+symbol)
        rows[symbol]=normalized_comparison_rows(raw,as_of=end)
    spy=[p for p in json.loads((cache/'SPY.json').read_bytes()) if start<=p['date']<=end]
    sessions=[p['date'] for p in normalized_comparison_rows(spy,as_of=end)]
    if sha256(encode(sessions))!=r['source']['reference_sessions_sha256']:raise ValueError('calendar_mismatch')
    equity,returns,trades,book=account(events,rows,sessions,r['scenario'],with_ledger=True)
    if len(equity)!=len(r['daily_account']):raise ValueError('account_length_mismatch')
    for d,v in zip(r['daily_account'],equity):close(d['equity'],float(v),'frozen_equity')
    old={t['event_id']:t for t in r['trades']}
    for t in trades:
        for key in ('status','quantity','net_pnl','entry_fees','exit_fees','reason'):
            a,b=t.get(key),old[t['event_id']].get(key)
            if isinstance(a,(int,float)) and isinstance(b,(int,float)):close(a,b,'frozen_trade_'+key)
            elif a!=b:raise ValueError('frozen_trade_mismatch:'+key)
    book['provenance']={'source_receipt':r['id'],'source_hash':r['content_sha256'],'run':os.environ.get('GITHUB_RUN_ID'),'code':os.environ.get('GITHUB_SHA'),'exact_price_window_hashes':True,'original_equity_and_trades_reproduced':True}
    (out/'daily-portfolio-ledger.json').write_bytes(encode(book))
    (out/'report.html').write_text(render_ledger(book))
    (out/'manifest.json').write_bytes(encode({'provenance':book['provenance'],'files':{f.name:sha256(f.read_bytes()) for f in (out/'daily-portfolio-ledger.json',out/'report.html')}}))
    print(json.dumps({'sessions':len(sessions),'events':len(events),'ending_value':float(equity.iloc[-1]),'parity':True}))

if __name__=='__main__':main()
