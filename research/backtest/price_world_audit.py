"""Read-only input consistency diagnostics. Does not alter signals or rules."""
import json
import copy
from pathlib import Path
from research.backtest.run_store import encode,sha256
from services.scanner.cr056_inputs import normalized_comparison_rows
from services.scanner.support_risk import signal_support_plan
from research.backtest.account_runner import account

def main():
    root=Path('research/backtest/output');cache=Path('work/eodhd-cache')
    old=json.loads((root/'reusable-runs/34240123213-1/receipt.json').read_bytes())
    level=json.loads((root/'reusable-runs/35048162507-1/receipt.json').read_bytes())
    identities={x['identity']['symbol']:x['identity'] for x in level['observation']['sources']}
    records=[];account_rows={};events=[];aligned=[];known_differences=[]
    for t in old['trades']:
        symbol=t['symbol'];rawbytes=(cache/(symbol+'.json')).read_bytes();raw=json.loads(rawbytes)
        past=normalized_comparison_rows([x for x in raw if x['date']<=t['signal_date']],as_of=t['signal_date'])
        prior=t['signal_snapshot']['selection']['support_plan'];fresh=signal_support_plan(past)
        window=[x for x in raw if old['request']['start']<=x['date']<=old['request']['end']]
        account_rows[symbol]=normalized_comparison_rows(window,as_of=old['request']['end'])
        event={k:t[k] for k in ('event_id','symbol','signal_date')};event['selection']=copy.deepcopy(t['signal_snapshot']['selection'])
        events.append(event);updated=copy.deepcopy(event);updated['selection']['support_plan']=fresh;aligned.append(updated)
        price_by_date={x['date']:x for x in account_rows[symbol]}
        known_differences.append({'symbol':symbol,'date':t['signal_date'],'field':'adjusted_close','old':prior['signal_close'],'new':fresh['signal_close'],'evidence':'frozen_support_signal_close; both rounded to 4 decimals'})
        if 'entry_price' in t:
            known_differences.append({'symbol':symbol,'date':t['entry_date'],'field':'adjusted_open','old':t['entry_price'],'new':price_by_date[t['entry_date']]['open'],'evidence':'original_receipt_entry_price'})
        fields=['signal_close','level','source','structural_stop','candidates','volume_profile']
        records.append({'symbol':symbol,'signal_date':t['signal_date'],'old_support':prior,'recomputed_support':fresh,
          'equal_fields':{k:prior.get(k)==fresh.get(k) for k in fields},
          'full_support_equal':prior==fresh,'window_hash_equal':sha256(encode(window))==old['source']['windows_sha256'][symbol],
          'current_source_hash':sha256(rawbytes),'matches_observation_source':sha256(rawbytes)==identities.get(symbol,{}).get('source'),
          'history_first':past[0]['date'],'history_rows':len(past),
          'close_ratio_new_over_old':fresh['signal_close']/prior['signal_close']})
    out=Path('work/account-ledger-attempt');out.mkdir(parents=True,exist_ok=True)
    spy=json.loads((cache/'SPY.json').read_bytes())
    sessions=[x['date'] for x in spy if old['request']['start']<=x['date']<=old['request']['end']]
    mixed=account(events,account_rows,sessions,old['scenario'])
    consistent_support=account(aligned,account_rows,sessions,old['scenario'])
    impacts=[]
    original={t['event_id']:t for t in old['trades']}
    for a,b in zip(mixed[2],consistent_support[2]):
        assert a['event_id']==b['event_id']
        fields=('status','quantity','entry_price','net_pnl','entry_fees','exit_fees','reason','execution')
        impacts.append({'symbol':a['symbol'],'original':{k:original[a['event_id']].get(k) for k in fields},'mixed':{k:a.get(k) for k in fields},'support_aligned_diagnostic':{k:b.get(k) for k in fields}})
    (out/'decision-impact.json').write_bytes(encode({'role':'diagnostic_only_not_validated_strategy','signal_and_rank_held_fixed':True,'new_parameters':False,'known_price_comparisons':known_differences,'trades':impacts,'original_final_equity':old['daily_account'][-1]['equity'],'mixed_final_equity':float(mixed[0].iloc[-1]),'support_aligned_diagnostic_final_equity':float(consistent_support[0].iloc[-1]),'elv_current_adjusted_window':account_rows['ELV'],'old_raw_window_available':False}))
    (out/'price-world-audit.json').write_bytes(encode({'source_account':old['id'],'source_account_hash':old['content_sha256'],'observation_hash':level['content_sha256'],'records':records,
      'limits':['Recomputed support uses current full history: history length changes may alter EMA seeds or profile.','Signal score/eligibility is not revalidated by a support match.','Historical provider revisions are not reconstructed by as_of filtering.','Prior-high is not an input to this legacy account.']}))
    print(json.dumps([{'symbol':r['symbol'],'same_window':r['window_hash_equal'],'same_support':r['full_support_equal'],'same_close':r['equal_fields']['signal_close'],'old_level':r['old_support'].get('level'),'new_level':r['recomputed_support'].get('level')} for r in records]))
if __name__=='__main__':main()
