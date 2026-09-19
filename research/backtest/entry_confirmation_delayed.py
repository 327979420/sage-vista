"""Post-run diagnostic: separate unchanged fills from actual delays; no new triggers."""
import argparse
import json
from pathlib import Path
from statistics import median
from research.backtest.entry_confirmation import TF,METHODS,bootstrap
from research.backtest.run_store import encode,sha256
from research.backtest.entry_confirmation_report import read_analysis


def main():
    p=argparse.ArgumentParser();p.add_argument('folder');a=p.parse_args();folder=Path(a.folder)
    raw=read_analysis(folder);parent=json.loads(raw)
    manifest=json.loads((folder/'manifest.json').read_bytes())
    if sha256(raw)!=manifest['files']['analysis.json']:raise ValueError('analysis_hash_mismatch')
    result={'role':'post_run_descriptive_diagnostic_not_new_primary_test','parent_sha256':sha256(raw),'groups':[]}
    for tf in TF:
        for method in METHODS[1:]:
            for n in (5,10,20,30):
                for period in ('all','2005-2009','2010-2014','2015-2019','2020-2025'):
                    same=0;pairs=[]
                    for op in parent['opportunities']:
                        if op['timeframe']!=tf or (period!='all' and not int(period[:4])<=int(op['signal_date'][:4])<=int(period[-4:])):continue
                        a=op['methods']['direct'];b=op['methods'][method]
                        av=a.get('outcomes',{}).get(str(n),{});bv=b.get('outcomes',{}).get(str(n),{})
                        if av.get('status')!= 'complete' or bv.get('status')!='complete':continue
                        if a['fill_date']==b['fill_date']:same+=1;continue
                        pairs.append((op['symbol'],{k:bv[k]-av[k] for k in ('return','mae','excess','mfe')}))
                    row={'timeframe':tf,'method':method,'days':n,'period':period,'same_fill':same,'delayed_pairs':len(pairs)}
                    for key in ('return','mae','excess','mfe'):
                        row[key]=median(v[key] for _,v in pairs) if pairs else None
                        if period=='all':row[key+'_ci95']=bootstrap(pairs,key)
                    result['groups'].append(row)
    (folder/'delayed-only.json').write_bytes(encode(result))
    for r in result['groups']:
        if r['period']=='all' and r['days']==20:print(json.dumps(r))

if __name__=='__main__':main()
