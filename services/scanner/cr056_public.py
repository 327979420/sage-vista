"""Small display-only projection of the reviewed CR056 report; never scores."""
import argparse
import json
from pathlib import Path
from services.contracts.market_data import canonical_fingerprint
from services.contracts.cr056_policy import WHITE_LIST, MAPPED_FACTORS
from services.scanner.factor_registry import FACTORS_BY_ID


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
        reviews.append(item)
    return {'as_of': report['as_of'], 'result_role': report['result_role'],
        'policy_version': report['policy_version'], 'source_snapshot': report['snapshot_fingerprint'],
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
        reviews[r['symbol']] = {
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
