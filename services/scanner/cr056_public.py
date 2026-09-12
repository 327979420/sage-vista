"""Small display-only projection of the reviewed CR056 report; never scores."""
import argparse
import json
from pathlib import Path
from services.contracts.market_data import canonical_fingerprint
from services.contracts.cr056_policy import WHITE_LIST, MAPPED_FACTORS
from services.scanner.factor_registry import FACTORS_BY_ID


VIEW_VERSION = 'nomination-observation-1'

def project_report(report):
    body = {k: v for k, v in report.items() if k != 'snapshot_fingerprint'}
    if canonical_fingerprint(body) != report.get('snapshot_fingerprint'):
        raise ValueError('source snapshot fingerprint mismatch')
    if report['result_role'] != 'legacy_comparison':
        raise ValueError('expected candidate comparison')
    catalog = {fid: {'name': m['name'], 'timeframe': m['timeframe'], 'role': m['role'],
                     'research_status': m['research_status'], 'source_ids': m['source_ids']}
               for fid, m in MAPPED_FACTORS.items()}
    reviews = []
    for row in report['reviews']:
        score = row.get('score')
        permission = row.get('permission', {})
        item = {k: row.get(k) for k in ('symbol', 'rank', 'price', 'status', 'new_nomination', 'periods')}
        tracking = row.get('entry_tracking') or (row.get('watch') or {}).get('entry_tracking')
        if tracking:
            # Keep the public table compact; full episode history stays in the ledger.
            active = [r for r in tracking['records'] if r['state']=='active']
            latest = {}
            for record in sorted(active or tracking['records'],key=lambda r:r['trigger_date']):
                latest[(record['path'],record['timeframe'])] = record
            item['watch_entries'] = [{k:r.get(k) for k in ('path','timeframe','trigger_date','trigger_close',
                                      'state','invalidated_at','observation_return','observed_sessions','confirmation_kinds')}
                                     for r in latest.values()]
            item['watch_history_start'] = tracking['history_start']
            item['watch_as_of'] = tracking['as_of']

        observation = row.get('nomination_observation') or {}
        if observation:
            item['watch_return'] = observation.get('price_change')
            item['nomination_price'] = observation.get('price')
        paths = (row.get('entry_gate') or {}).get('paths', [])
        if paths:
            # Table tags need only path/type; exact gate dates stay in project_details.
            item['entry_paths'] = [{k:p.get(k) for k in ('path','timeframe','confirmation_kinds') if p.get(k)} for p in paths]
        # Non-ranked rows retain reasons and scores, without repeating period labels.
        if not row.get('rank'): item.pop('periods', None)
        item.update(origin_date=(row.get('origin') or {}).get('date'),
                    reason_codes=row['reason_codes'],
                    total=score['total_score'] if score else None,
                    coverage=score['coverage'] if score else None,
                    frames={tf: score['timeframes'][tf]['normalized'] for tf in WHITE_LIST} if score else None,
                    high_score_eligible=score['high_score_eligible'] if score else False)
        # Detailed contribution groups are only needed for the small eligible list.
        if row.get('rank'):
            item['checks'] = permission.get('checks', {})
            # Full evidence is loaded on demand from the matching compressed detail file.
        # False display flags are the default; omit their repeated wire keys.
        # Scores, dates, prices, reasons and all watch evidence remain exact.
        for flag in ('new_nomination', 'high_score_eligible'):
            if not item.get(flag): item.pop(flag, None)
        reviews.append(item)
    return {'view_version': VIEW_VERSION, 'as_of': report['as_of'], 'result_role': report['result_role'],
        'policy_version': report['policy_version'], 'policy_fingerprint': report['policy_fingerprint'], 'source_snapshot': report['snapshot_fingerprint'],
        'source_commit': report['code_commit'], 'automatic_updates_connected': False,
        'input_coverage': report['input_coverage'], 'counts': report['counts'],
        **{k: report[k] for k in ('ranked_symbols', 'selected_symbols', 'new_nomination_symbols', 'continuing_ranked_symbols')},
        'factor_catalog': catalog, 'detail_path': '/cr056-factor-details.json.gz', 'reviews': reviews}


def project_details(report):
    # Reuse the single source-integrity check; no recomputation of scores.
    project_report(report)
    reviews = {}
    for r in report['reviews']:
        if not r.get('score'): continue
        score = r['score']
        tracking = r.get('entry_tracking') or (r.get('watch') or {}).get('entry_tracking') or {}
        latest_structures = {}
        for episode in sorted(tracking.get('records', []), key=lambda e: e['trigger_date']):
            latest_structures[(episode['path'], episode['timeframe'])] = episode
        reviews[r['symbol']] = {
            'entry_gate': r.get('entry_gate'),
            'checks': (r.get('permission') or {}).get('checks', {}),
            'structures': [{k: episode.get(k) for k in ('path', 'timeframe', 'trigger_date',
                           'structure_floor', 'state', 'invalidated_at')}
                           for episode in latest_structures.values()],
            'groups': [g for tf in WHITE_LIST for g in score['timeframes'][tf]['groups']],
            'factors': [{k: s.get(k) for k in ('factor_id','available','hit','recent_hit','bars_since_hit',
                         'latest_hit_date','runtime_status','score_role','completed_through','period_bar_count',
                         'minimum_bars','evidence')} for s in r['factor_states']],
        }
    return {'source_snapshot': report['snapshot_fingerprint'], 'as_of': report['as_of'],
            'policy_version': report['policy_version'], 'reviews': reviews}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--source', required=True)
    p.add_argument('--output', default='public/cr056-ranking.json'); args = p.parse_args()
    result = project_report(json.loads(Path(args.source).read_text()))
    data = json.dumps(result, ensure_ascii=False, separators=(',', ':'))+'\n'
    if len(data.encode()) > 750_000: raise ValueError('public projection exceeds size budget')
    Path(args.output).write_text(data)
    print(f'{len(data.encode())} bytes; {len(result["ranked_symbols"])} ranked')

if __name__ == '__main__': main()
