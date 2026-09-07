"""Run the reviewed candidate policy against restored/repaired inputs, offline.

Outputs are derived comparison reports. Existing histories/public data are read
only; no supplier, deployment, notification or new-trade entry is called here.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
from services.contracts.cr056_policy import POLICY_VERSION, POLICY_FINGERPRINT
from services.contracts.market_data import canonical_fingerprint
from services.market_data.normalization import validate_adjusted_rows
from services.market_data.storage import require_shadow_root
from services.gates.baseline import exact_daily_macd_bull_cross, MIN_HISTORY_SESSIONS, MIN_CLOSE, MIN_DOLLAR_VOLUME
from services.factors.cr056 import collect_direction_facts
from services.selectors.cr056 import assess_permission
from services.ranking.cr056 import score_candidate
from services.ledger.cr056 import review_watch
from services.scanner.factor_detectors import evaluate_all_factors
from services.scanner.macd_factor_backtest import adjusted_rows


def historical_origins(history, *, as_of):
    result = {}
    for day in sorted(history.get('days', []), key=lambda d: d['date']):
        if day['date'] > as_of: continue
        for row in day.get('ranking', []):
            symbol = row['symbol']
            if symbol not in result:
                result[symbol] = {'date': day['date'], 'kind': 'imported_legacy_ranking',
                    'model_version': day.get('model_version'),
                    'record_fingerprint': canonical_fingerprint(row), 'original_record': row}
    return result


def run_snapshot(cache_dir, *, as_of, history, code_commit, input_report, previous=None):
    if input_report.get('as_of') != as_of or input_report.get('result_role') != 'legacy_comparison_input_repair':
        raise ValueError('repaired input report date or role mismatch')
    if previous and (previous.get('result_role') != 'legacy_comparison' or previous['as_of'] > as_of):
        raise ValueError('previous snapshot is not an earlier candidate comparison')
    sources = {r['symbol']: r for r in input_report['repaired']}
    prior = {r['symbol']: r['watch'] for r in previous.get('reviews', []) if r.get('watch')} if previous else {}
    origins = historical_origins(history, as_of=as_of)
    for symbol, watch in prior.items(): origins[symbol] = watch['origin']
    reference = Path(cache_dir)/'SPY.json'
    if not reference.exists(): raise ValueError('repaired reference history missing')
    content = reference.read_bytes()
    if hashlib.sha256(content).hexdigest() != sources.get('SPY', {}).get('repaired_sha256'):
        raise ValueError('reference input hash mismatch')
    reference_rows = json.loads(content)
    reference_sessions = [r['date'] for r in reference_rows if r['date'] <= as_of]
    if not reference_sessions or reference_sessions[-1] != as_of:
        raise ValueError('reference latest complete session missing')
    reviews, counts = [], Counter()
    for symbol in sorted(set(sources) | set(origins) | set(input_report.get('excluded', {}))):
        source = sources.get(symbol)
        item = {'symbol': symbol, 'instrument_id': 'legacy-observed:'+symbol, 'as_of': as_of,
            'origin': origins.get(symbol), 'code_commit': code_commit, 'new_nomination': False,
            'result_role': 'legacy_comparison', 'watch': None}
        missing = None
        try:
            if source is None: raise ValueError(input_report.get('excluded', {}).get(symbol, 'source_history_unavailable'))
            content = (Path(cache_dir)/f'{symbol}.json').read_bytes()
            if hashlib.sha256(content).hexdigest() != source['repaired_sha256']:
                raise ValueError('repaired_source_hash_mismatch')
            raw = json.loads(content)
            rows = adjusted_rows(raw)
            if len(rows) != len(raw): raise ValueError('invalid_cached_ohlcv')
            rows = validate_adjusted_rows(rows)
            if not rows or rows[-1]['date'] != as_of: raise ValueError('source_date_mismatch')
            input_fp = canonical_fingerprint(list(rows))
            item['input_fingerprint'] = input_fp
            item['source_sha256'] = source['repaired_sha256']
            item['original_cache_sha256'] = source['source_sha256']
            # Existing tradability rules, not a repeated MACD gate for watched stocks.
            if len(rows) < MIN_HISTORY_SESSIONS: raise ValueError('daily_history_below_420')
            if rows[-1]['close'] < MIN_CLOSE or rows[-1]['close']*rows[-1]['volume'] < MIN_DOLLAR_VOLUME:
                item['status'] = 'excluded'; item['reason_codes'] = ['daily_tradability_not_met']
                missing = 'daily_tradability_not_met'
            trigger = exact_daily_macd_bull_cross(rows)
            item['exact_daily_cross_today'] = trigger
            if missing is None and symbol not in origins and not trigger:
                item['status'] = 'not_nominated'; item['reason_codes'] = ['no_initial_daily_cross']
                counts['not_nominated'] += 1; reviews.append(item); continue
            if missing is not None: raise ValueError(missing)
            facts = collect_direction_facts(rows, as_of=as_of, complete_session=True)
            permission = assess_permission(facts)
            states = [s.dict() for s in evaluate_all_factors(rows, as_of, complete_session=True)]
            score = score_candidate(states, permission)
            item.update({'status': score['score_status'], 'price': rows[-1]['close'], 'permission': permission,
                'score': score, 'factor_states': states, 'reason_codes': score['reason_codes'],
                'periods': {tf: facts[tf]['completed_through'] for tf in ('monthly','weekly')},
                'period_boundary': 'explicit_complete_session_US_weekend_boundary; holidays_not_inferred'})
            if symbol not in origins and permission['eligible'] and score['total_score'] is not None:
                origins[symbol] = {'date': as_of, 'kind': 'candidate_initial_nomination',
                    'model_version': POLICY_VERSION, 'input_fingerprint': input_fp,
                    'original_score': score, 'record_fingerprint': score['score_fingerprint']}
                item['new_nomination'] = True
            item['origin'] = origins.get(symbol)
            if item['origin']:
                item['watch'] = review_watch(symbol=symbol, as_of=as_of, origin=item['origin'], score=score,
                    previous=prior.get(symbol), reference_sessions=reference_sessions)
        except (ValueError, TypeError, KeyError, OSError, ZeroDivisionError) as error:
            if str(error) == 'same-day watch content conflict':
                raise
            item.pop('score', None)
            reason = str(error).split(':')[0][:120] or type(error).__name__
            item['status'] = 'unavailable' if missing is None else 'excluded'
            item['reason_codes'] = [reason]
            if item['origin']:
                fallback = {'total_score': None, 'permission': 'blocked' if missing else 'unavailable',
                    'high_score_eligible': False, 'reason_codes': [reason]}
                item['watch'] = review_watch(symbol=symbol, as_of=as_of, origin=item['origin'], score=fallback,
                    previous=prior.get(symbol), reference_sessions=reference_sessions)
        counts[item['status']] += 1
        reviews.append(item)
    ranked = [r for r in reviews if r.get('score', {}).get('total_score') is not None]
    ranked.sort(key=lambda r: (-r['score']['total_score'],
        -r['score']['timeframes']['monthly_completed']['normalized'],
        -r['score']['timeframes']['weekly_completed']['normalized'], r['instrument_id']))
    for rank, r in enumerate(ranked, 1): r['rank'] = rank
    report = {'schema_version': 'cr056-backend-report-1.0.0', 'result_role': 'legacy_comparison',
        'as_of': as_of, 'code_commit': code_commit, 'policy_version': POLICY_VERSION,
        'policy_fingerprint': POLICY_FINGERPRINT, 'input_report_fingerprint': canonical_fingerprint(input_report),
        'historical_ranking_fingerprint': canonical_fingerprint(history),
        'previous_snapshot_fingerprint': previous.get('snapshot_fingerprint') if previous else None,
        'input_coverage': {k: input_report[k] for k in ('repaired_count', 'excluded_count')},
        'counts': dict(counts), 'ranked_symbols': [r['symbol'] for r in ranked],
        'selected_symbols': [r['symbol'] for r in ranked[:5]],
        'new_nomination_symbols': [r['symbol'] for r in ranked if r['new_nomination']],
        'continuing_ranked_symbols': [r['symbol'] for r in ranked if not r['new_nomination']],
        'reviews': reviews, 'limitations': ['candidate priority is not validated return or a trade instruction',
            'imported legacy historical nominations are not a complete unbiased universe',
            'ticker-only observed identity; never formal promotion',
            'restored inputs are point-in-time comparison snapshots, not a production activation']}
    report['snapshot_fingerprint'] = canonical_fingerprint(report)
    return report


def save_report(report, output_dir):
    output = require_shadow_root(output_dir, workspace_root=Path(__file__).resolve().parents[2])
    output.mkdir(parents=True, exist_ok=True)
    suffix = report['snapshot_fingerprint'].split(':')[-1][:16]
    path = output/f"ranking-{report['as_of']}-{suffix}.json"
    data = json.dumps(report, ensure_ascii=False, indent=2)+'\n'
    if path.exists():
        if path.read_text() != data: raise ValueError('immutable report conflict')
    else:
        with path.open('x') as f: f.write(data)
    lines = [f"# CR056真实行情候选对照榜｜{report['as_of']}", '',
             '这是新候选政策后台对照，不是已验证收益或线上策略。', '',
             '| 排名 | 股票 | 总分 | 月分 | 周分 | 日分 | 覆盖 | 类型 |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in sorted((r for r in report['reviews'] if r.get('rank')), key=lambda r:r['rank']):
        s = r['score']; frames = s['timeframes']
        parts = [f"{100*frames[t]['normalized']:.1f}" for t in ('monthly_completed','weekly_completed','daily')]
        lines.append(f"| {r['rank']} | {r['symbol']} | {s['total_score']:.2f} | {' | '.join(parts)} | {s['coverage']:.0%} | {'新提名' if r['new_nomination'] else '持续观察复评'} |")
    cutoffs = sorted({(r['periods']['monthly'], r['periods']['weekly']) for r in report['reviews'] if r.get('periods')})
    lines += ['', '完整周期截止（月／周）：' + ', '.join(f'{m}／{w}' for m,w in cutoffs),
              '精选（当前合格榜前5）：' + ', '.join(report['selected_symbols'])]
    lines += ['', '## 入选/排除统计', '', json.dumps(report['counts'], ensure_ascii=False), '',
              '每票完整因子、许可/排除原因、原提名与来源指纹见同名JSON。',
              '若没有合格条目，不表示交付完成；须检查可计算覆盖及具体阻断原因。']
    md = path.with_suffix('.md')
    md_text = '\n'.join(lines)+'\n'
    if md.exists() and md.read_text() != md_text: raise ValueError('immutable summary conflict')
    if not md.exists(): md.write_text(md_text)
    return path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--as-of', required=True)
    p.add_argument('--private-dir', default='work/cr056-private')
    p.add_argument('--history', default='public/unified-v2-rankings.json')
    p.add_argument('--output-dir', default='work/cr056-results')
    p.add_argument('--previous')
    args = p.parse_args()
    private = Path(args.private_dir)
    report = run_snapshot(private/'eodhd-cache', as_of=args.as_of,
        history=json.loads(Path(args.history).read_text()),
        code_commit=subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
        input_report=json.loads((private/'input-repair-report.json').read_text()),
        previous=json.loads(Path(args.previous).read_text()) if args.previous else None)
    path = save_report(report, args.output_dir)
    print(json.dumps({'output': str(path), 'as_of': report['as_of'], 'counts': report['counts'],
        'ranked': len(report['ranked_symbols']), 'new_nominations': len(report['new_nomination_symbols'])}))

if __name__ == '__main__': main()
