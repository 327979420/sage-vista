"""Independent result invariants, run after a completed cloud study."""
import argparse
import json
from bisect import bisect_left
from pathlib import Path
from research.backtest.run_store import encode, sha256
from research.backtest.entry_confirmation_report import read_analysis
from research.backtest.entry_confirmation import TRANSITIONS, METHODS
from research.backtest.observation_classification import classify
from services.contracts.cr056_policy import POLICY_FINGERPRINT


def audit(folder):
    folder=Path(folder);manifest=json.loads((folder/'manifest.json').read_bytes())
    for name,value in manifest['files'].items():
        assert sha256(read_analysis(folder) if name=='analysis.json' else (folder/name).read_bytes())==value,('artifact_hash',name)
    data=json.loads(read_analysis(folder))
    parent=json.loads(Path('research/backtest/output/reusable-runs/35048162507-1/receipt.json').read_bytes())
    originals={e['episode_id']:e for e in parent['events'] if classify(e)['research_label']}
    assert len(originals)==data['raw_events']==1041
    assert data['policy']==POLICY_FINGERPRINT
    assert all(e['entry_gate']['policy_fingerprint']==data['policy'] for e in originals.values())
    seen=set();last={};filled=0;unapplied=0
    for op in data['opportunities']:
        assert op['signal_date']>last.get(op['symbol'],'')
        last[op['symbol']]=op['reserved_through']
        assert op['timeframe']==classify(originals[op['episode_id']])['research_label']
        for eid in op['merged_event_ids']:
            assert eid not in seen
            seen.add(eid)
        unapplied+=len(set(op['merged_event_ids'])-set(op['applied_event_ids']))
        for source in op['source_timeline']:
            assert source['date']==originals[source['event']]['signal_date']
        for method,r in op['methods'].items():
            log=r['states'];assert log[0]['state']=='DETECTED'
            for a,b in zip(log,log[1:]):
                assert b['state'] in TRANSITIONS[a['state']]
                assert b['date']>=a['date']
            assert sum(x['state']=='OPEN_POSITION' for x in log)<=1
            assert not any(x['state']=='EXPIRED' for x in log)
            if r['status']=='filled':
                filled+=1
                assert r['fill_date']>r['trigger_date']>=op['signal_date']
                assert r['wait_days']>=1
                for n,outcome in r['outcomes'].items():
                    if outcome['status']=='complete':
                        assert outcome['end']>=r['fill_date']
                        assert outcome['mae']<=0<=outcome['mfe']
            if method=='direct' and 'trigger_date' in r:assert r['trigger_date']==op['signal_date']
    assert seen==set(originals)
    for s in data['statistics']:
        assert sum(s['statuses'].values())==s['setups']
        assert s['paired_n']<=s['complete']<=s['filled']<=s['setups']
        assert s['missed_no_fill']<=s['missed_prior_high']<=s['target_available']<=s['setups']
    answer={'status':'passed','source_events':len(seen),'unified_opportunities':len(data['opportunities']),
            'fills_across_four_counterfactual_methods':filled,'merged_events_not_activated':unapplied,
            'analysis_sha256':manifest['files']['analysis.json'],
            'scope':'identity, coverage, single opportunity, activation dates, lifecycle, fill timing, denominators; not strategy proof'}
    (folder/'verification.json').write_bytes(encode(answer));print(json.dumps(answer,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');audit(p.parse_args().folder)
