"""Receipt-only score-gap diagnostic; never assign a new opportunity label."""
import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path
from research.backtest.observation_horizons import verify_parent, PARENT, PARENT_HASH
from research.backtest.run_store import encode

FRAMES = ('daily', 'weekly_completed', 'monthly_completed')


def diagnose(parent):
    verify_parent(parent)
    rows=[]
    for e in parent['events']:
        scores=e['timeframe_scores']
        if set(scores)!=set(FRAMES):raise ValueError('three_frozen_frame_scores_required')
        tickets={p['timeframe'] for p in e['entry_gate']['paths']}
        high=max(scores.values());leaders=[tf for tf in FRAMES if scores[tf]==high]
        ordered=sorted(scores.values(),reverse=True)
        row={'episode_id':e['episode_id'],'symbol':e['symbol'],'signal_date':e['signal_date'],
             'original_label':e['timeframe'],**scores,'score_leader':leaders[0] if len(leaders)==1 else 'tie',
             'score_gap':ordered[0]-ordered[1],'leader_has_ticket':len(leaders)==1 and leaders[0] in tickets,
             'ticket_frames':';'.join(sorted(tickets))}
        rows.append(row)
    groups=[]
    for tf in FRAMES:
        original=[r for r in rows if r['original_label']==tf]
        groups.append({'original_label':tf,'events':len(original),
             'strictly_highest_all_three':sum(r[tf]>max(r[t] for t in FRAMES if t!=tf) for r in original),
             'tied_highest':sum(r[tf]==max(r[t] for t in FRAMES if t!=tf) for r in original),
             'another_frame_higher':sum(r[tf]<max(r[t] for t in FRAMES if t!=tf) for r in original)})
    coverage=[]
    for tf in FRAMES:
        for gap in (0,5,10,15):
            selected=[r for r in rows if r['score_leader']==tf and r['score_gap']>=gap]
            covered=[r for r in selected if r['leader_has_ticket']]
            coverage.append({'score_leader':tf,'minimum_gap':gap,'strict_lead_required':True,
                'events':len(selected),'with_own_ticket':len(covered),
                'symbols_with_own_ticket':len({r['symbol'] for r in covered})})
    summary={'version':'opportunity-level-input-diagnostic-v1','parent_id':PARENT,'parent_content_sha256':PARENT_HASH,
        'events':len(rows),'original_label_comparison':groups,'gap_coverage':coverage,
        'score_leaders':dict(Counter(r['score_leader'] for r in rows)),
        'interpretation':'分差与门票覆盖诊断，不是新机会分类；未使用收益，不选最赚钱阈值，不评价结构证据是否充分。'}
    return summary,rows


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--parent',required=True);parser.add_argument('--output',default='work/observation-classification');args=parser.parse_args()
    result,rows=diagnose(json.loads(Path(args.parent).read_bytes()));out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    (out/'summary.json').write_bytes(encode(result))
    buffer=io.StringIO();writer=csv.DictWriter(buffer,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (out/'events.csv').write_text('\ufeff'+buffer.getvalue())
    print(json.dumps(result,ensure_ascii=False))


def classify(event, minimum_gap=10):
    """Signal-time research classification; never reads outcomes or total score."""
    import math
    if minimum_gap not in (5,10,15):raise ValueError('unregistered_classification_gap')
    scores=event.get('timeframe_scores',{})
    base={'original_label':event['timeframe'],'research_label':None,'minimum_gap':minimum_gap}
    if any(type(scores.get(tf)) not in (int,float) or not math.isfinite(scores[tf]) or not 0<=scores[tf]<=100 for tf in FRAMES):
        return {**base,'reason':'scores_unavailable','score_gap':None,'score_leader':None}
    order=sorted(FRAMES,key=lambda tf:scores[tf],reverse=True)
    gap=scores[order[0]]-scores[order[1]];base.update(score_gap=gap,score_leader=order[0] if gap>0 else None)
    if gap==0:return {**base,'reason':'tied_scores'}
    if gap<minimum_gap:return {**base,'reason':'lead_too_small'}
    paths=event.get('entry_gate',{}).get('paths',[])
    if not any(p.get('timeframe')==order[0] and type(p.get('structure_floor')) in (int,float) and math.isfinite(p['structure_floor']) and p['structure_floor']>0 for p in paths):
        return {**base,'reason':'leader_without_matching_ticket'}
    return {**base,'research_label':order[0],'reason':'classified'}
