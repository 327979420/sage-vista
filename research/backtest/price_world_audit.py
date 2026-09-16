"""Read-only input consistency diagnostics. Does not alter signals or rules."""
import json
from pathlib import Path
from research.backtest.run_store import encode,sha256
from services.scanner.cr056_inputs import normalized_comparison_rows
from services.scanner.support_risk import signal_support_plan

def main():
    root=Path('research/backtest/output');cache=Path('work/eodhd-cache')
    old=json.loads((root/'reusable-runs/34240123213-1/receipt.json').read_bytes())
    level=json.loads((root/'reusable-runs/35048162507-1/receipt.json').read_bytes())
    identities={x['identity']['symbol']:x['identity'] for x in level['observation']['sources']}
    records=[]
    for t in old['trades']:
        symbol=t['symbol'];rawbytes=(cache/(symbol+'.json')).read_bytes();raw=json.loads(rawbytes)
        past=normalized_comparison_rows([x for x in raw if x['date']<=t['signal_date']],as_of=t['signal_date'])
        prior=t['signal_snapshot']['selection']['support_plan'];fresh=signal_support_plan(past)
        window=[x for x in raw if old['request']['start']<=x['date']<=old['request']['end']]
        fields=['signal_close','level','source','structural_stop','candidates','volume_profile']
        records.append({'symbol':symbol,'signal_date':t['signal_date'],'old_support':prior,'recomputed_support':fresh,
          'equal_fields':{k:prior.get(k)==fresh.get(k) for k in fields},
          'full_support_equal':prior==fresh,'window_hash_equal':sha256(encode(window))==old['source']['windows_sha256'][symbol],
          'current_source_hash':sha256(rawbytes),'matches_observation_source':sha256(rawbytes)==identities.get(symbol,{}).get('source'),
          'history_first':past[0]['date'],'history_rows':len(past),
          'close_ratio_new_over_old':fresh['signal_close']/prior['signal_close']})
    out=Path('work/account-ledger-attempt');out.mkdir(parents=True,exist_ok=True)
    (out/'price-world-audit.json').write_bytes(encode({'source_account':old['id'],'source_account_hash':old['content_sha256'],'observation_hash':level['content_sha256'],'records':records,
      'limits':['Recomputed support uses current full history: history length changes may alter EMA seeds or profile.','Signal score/eligibility is not revalidated by a support match.','Historical provider revisions are not reconstructed by as_of filtering.','Prior-high is not an input to this legacy account.']}))
    print(json.dumps([{'symbol':r['symbol'],'same_window':r['window_hash_equal'],'same_support':r['full_support_equal'],'same_close':r['equal_fields']['signal_close'],'old_level':r['old_support'].get('level'),'new_level':r['recomputed_support'].get('level')} for r in records]))
if __name__=='__main__':main()
