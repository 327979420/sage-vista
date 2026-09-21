"""Popular-stock daily shapes, reusing CR056 facts; no orders/network.

Calibration and the approved daily observation page use the same facts.
Neither is a main ranking, formal ModelAssessment, or trading-account input.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
from statistics import mean

from services.contracts.cr056_policy import ENTRY_SETTINGS, POLICY_FINGERPRINT
from services.contracts.market_data import canonical_fingerprint
from services.scanner.cr056_inputs import normalized_comparison_rows
from services.market_data.normalization import validate_adjusted_rows
from services.scanner.detectors import multi_bottom_structure, pivots
from services.scanner.macd_factor_backtest import three_push_breakout_setup
from services.scanner.favorite_pattern_tracker import evaluate as old_evaluate, REFERENCE_CASES

VERSION = 'daily-shape-picker-v1-calibration'
LABELS = {'waiting': '底部已确认，等待突破', 'broken_out': '已突破，继续观察',
          'retest': '曾突破，现回到趋势线附近或下方',
          'above_line': '已越线，突破尚未确认', 'unconfirmed': '底部未确认，不入选',
          'invalidated': '结构已破坏，不入选', 'sweep_rejected': '支撑区深扫，暂不入选'}


def evaluate_shape(rows, *, as_of):
    """Exact CR056 daily window/config, without the entry ticket or score gate."""
    rows = validate_adjusted_rows(rows)
    if not rows or rows[-1]['date'] != as_of:
        raise ValueError('picker_requires_exact_completed_session')
    size = ENTRY_SETTINGS['triple_bottom']['lookback_bars'] + 1
    if len(rows) < size:
        raise ValueError('picker_daily_window_incomplete')
    bars = rows[-size:]
    zone = multi_bottom_structure(bars, len(bars)-1, ENTRY_SETTINGS)
    line = three_push_breakout_setup(bars, len(bars)-1, require_breakout=False)
    confirmed = zone['strength'] > 0 and len(zone['anchors']) >= 2
    bottom_dates = [p['confirmed_at'] for p in zone['anchors']]
    if any(d > as_of for d in bottom_dates):
        raise ValueError('future_bottom_confirmation')
    historical_breakout = None
    if line:
        # The helper names this field breakout_index even when BOS is disabled.
        # Never propagate that unconfirmed field as a real breakout event.
        line = {k: v for k, v in line.items() if k != 'breakout_index'}
        highs = {p['index']: p for p in pivots(bars, len(bars)-1, ENTRY_SETTINGS)['highs']}
        line['anchors'] = [{**p, 'confirmed_at': bars[highs[p['index']]['confirmed_index']]['date']}
                           for p in line['anchors']]
        # Replay only this <=121-bar structure, with prefix-safe shared BOS.
        # A post-breakout pullback must not be labelled a first pre-breakout setup.
        first_known = max(highs[p['index']]['confirmed_index'] for p in line['anchors'])
        identity = [p['date'] for p in line['anchors']]
        for j in range(first_known, len(bars)):
            past = three_push_breakout_setup(bars[:j+1], j)
            if past and [p['date'] for p in past['anchors']] == identity:
                historical_breakout = bars[j]['date']
                break
        line['breakout_date'] = historical_breakout
    if zone['stage'] == 'invalidated':
        state = 'invalidated'
    elif zone['stage'] == 'deep_sweep_rejected':
        state = 'sweep_rejected'
    elif not confirmed:
        state = 'unconfirmed'
    elif line:
        state = ('broken_out' if bars[-1]['close'] > line['level'] else 'retest') if historical_breakout else (
            'above_line' if bars[-1]['close'] > line['level'] else 'waiting')
    else:
        state = 'broken_out' if zone['breakout_date'] else 'waiting'
    shape = '三推回调＋多底支撑' if line and confirmed else '多底支撑' if confirmed else '尚无确认形态'
    return {'as_of': as_of, 'state': state, 'state_zh': LABELS[state], 'selected': confirmed,
            'shape_zh': shape, 'bottom_confirmed': confirmed, 'bottom': zone, 'three_push': line,
            'price': bars[-1]['close'], 'invalidation_price': zone.get('zone_lower'),
            'explanation_zh': (f"{len(zone['anchors'])}个低点已确认；" +
                ('三个下降高点形成趋势线。' if line else '未识别到合格三推，不贴三推标签。')) if confirmed else LABELS[state],
            'window_fingerprint': canonical_fingerprint(list(bars)),
            'policy_fingerprint': POLICY_FINGERPRINT,
            'chart': list(bars)}


def liquidity(raw, *, as_of):
    """Cash turnover uses traded close and raw shares, never adjusted close."""
    rows = [r for r in raw if r['date'] <= as_of]
    if not rows or rows[-1]['date'] != as_of:
        raise ValueError('missing_same_day_quote')
    last = rows[-1]
    # Strict raw validation is done by normalized_comparison_rows before use.
    prior_volume = mean(r['volume'] for r in rows[-21:-1]) if len(rows) >= 21 else None
    return {'dollar_volume': last['close'] * last['volume'], 'traded_close': last['close'],
            'relative_volume': last['volume']/prior_volume if prior_volume else None}


def compare_symbol(symbol, raw, *, as_of, source_sha256, heat=None):
    prefix = [r for r in raw if r['date'] <= as_of]
    rows = normalized_comparison_rows(prefix, as_of=as_of)
    new = evaluate_shape(rows, as_of=as_of)
    # V3's dates are MM/DD/YYYY in its actual tracker caller.
    legacy_rows = [{**r, 'date': date.fromisoformat(r['date']).strftime('%m/%d/%Y')} for r in rows]
    old = old_evaluate(legacy_rows)
    return {'symbol': symbol, **new, 'liquidity': heat or liquidity(prefix, as_of=as_of),
            'source_sha256': source_sha256, 'input_fingerprint': canonical_fingerprint(list(rows)),
            'old': {'stage': old.get('stage'), 'stage_zh': old.get('stage_zh'),
                    'match_count': old.get('match_count'), 'bottom': old.get('double_bottom'),
                    'three_push': old.get('three_push'), 'conditions': old.get('conditions')},
            'comparison_zh': ('旧版也确认双底，但展示/突破要求不同' if old.get('double_bottom') else
                             '旧版未认出双底，共享底部逻辑认出支撑区') if new['selected'] else
                            ('旧版认出双底，共享逻辑未通过，需核图' if old.get('double_bottom') else '两版均未确认底部')}


def build_preview(cache_dir, common_path, *, as_of, top=100, index_path=None, include_legacy=True):
    cache_dir = Path(cache_dir)
    common_path = Path(common_path)
    if top < 1 or top > 1000: raise ValueError('top_out_of_bounds')
    common_bytes = common_path.read_bytes()  # Missing membership cannot silently mean all tickers.
    common = json.loads(common_bytes)
    symbols = {r['Code'] for r in common}
    expected = None
    if index_path:
        index = json.loads(Path(index_path).read_bytes())
        if index['as_of'] != as_of: raise ValueError('cache_index_date_mismatch')
        expected = {r['symbol']: r['repaired_sha256'] for r in index['repaired']}
    candidates, excluded, sources = [], {}, {}
    paths = sorted(cache_dir.glob('*.json'))
    for path in paths:
        symbol = path.stem
        if symbol not in symbols: continue
        content = path.read_bytes(); digest = hashlib.sha256(content).hexdigest()
        if expected is not None:
            if symbol not in expected: raise ValueError('cache_symbol_not_in_manifest')
            if digest != expected[symbol]: raise ValueError('cache_price_hash_mismatch')
        raw = json.loads(content)
        try:
            prefix = [r for r in raw if r['date'] <= as_of]
            normalized_comparison_rows(prefix, as_of=as_of)
            heat = liquidity(prefix, as_of=as_of)
            if heat['traded_close'] < 5 or heat['dollar_volume'] < 10_000_000:
                excluded[symbol] = 'below_existing_liquidity_floor'; continue
            if len(prefix) < ENTRY_SETTINGS['triple_bottom']['lookback_bars'] + 1:
                excluded[symbol] = 'insufficient_daily_history'; continue
        except (ValueError, TypeError, KeyError) as error:
            excluded[symbol] = str(error); continue
        candidates.append((symbol, heat, path, digest))
        sources[symbol] = digest
    if not candidates: raise ValueError('no_covered_current_common_stocks')
    if expected is not None:
        missing = (set(expected) & symbols) - {p.stem for p in paths}
        if missing: raise ValueError('cache_manifest_files_missing')
    ranked = sorted(candidates, key=lambda item: (-item[1]['dollar_volume'], item[0]))
    selected = ranked[:top]
    results = []
    for rank, (symbol, heat, path, digest) in enumerate(selected, 1):
        raw = json.loads(path.read_bytes())
        if include_legacy:
            item = compare_symbol(symbol, raw, as_of=as_of, source_sha256=digest, heat=heat)
        else:
            rows = normalized_comparison_rows([r for r in raw if r['date'] <= as_of], as_of=as_of)
            item = {'symbol': symbol, **evaluate_shape(rows, as_of=as_of),
                    'source_sha256': digest, 'liquidity': heat,
                    'input_fingerprint': canonical_fingerprint(list(rows))}
        item['activity_rank'] = rank
        results.append(item)
    reference_results = []
    available = {r[0]: r for r in candidates}
    for symbol in (REFERENCE_CASES if include_legacy else ()):
        if symbol in available:
            _, heat, path, digest = available[symbol]
            reference_results.append(compare_symbol(symbol, json.loads(path.read_bytes()),
                as_of=as_of, source_sha256=digest, heat=heat))
        else:
            reference_results.append({'symbol': symbol, 'unavailable': True,
                'reason': excluded.get(symbol, 'not_in_verified_cache_or_common_stock_membership')})
    # Only matched stocks and explicit review cases need chart payloads.
    for row in results:
        if not row['selected'] and not row.get('old', {}).get('bottom'): row.pop('chart')
    source_identity = {'as_of': as_of, 'sources': sources,
                       'common_sha256': hashlib.sha256(common_bytes).hexdigest()}
    return {'version': VERSION, 'as_of': as_of, 'result_role': 'calibration_not_live_alert',
            'price_version': canonical_fingerprint(source_identity), 'source_identity': source_identity,
            'common_stock_membership': 'current cached list; not historical point-in-time membership',
            'source_cache': str(cache_dir), 'index_sha256': hashlib.sha256(Path(index_path).read_bytes()).hexdigest() if index_path else None,
            'universe': {'common_list_count': len(symbols), 'cached_common_count': sum(p.stem in symbols for p in paths),
                         'eligible_covered_count': len(ranked), 'selected_activity_count': len(results), 'top': top,
                         'definition_zh': '已覆盖普通股中的当日成交额排序，不代表全市场或社交热度'},
            'state_counts': dict(Counter(r['state'] for r in results)),
            'selected_count': sum(r['selected'] for r in results),
            'excluded': excluded, 'rows': results, 'teaching_cases': reference_results,
            'audit': {'future_data_used': False, 'raw_cash_turnover': True, 'main_logic_reused': True,
                      'account_connected': False, 'human_accuracy_verified': False}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache-dir', default='work/cr056-daily/cache/eodhd-cache')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--common-path', default='work/eodhd-active-common.json')
    parser.add_argument('--index-path')
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--top', type=int, default=100)
    parser.add_argument('--out', default='work/daily-shape-picker')
    args = parser.parse_args()
    if args.live:
        if not args.index_path: raise ValueError('live_picker_requires_verified_cache_index')
        report = build_preview(args.cache_dir, args.common_path, as_of=args.as_of, top=args.top,
                               index_path=args.index_path, include_legacy=False)
        from services.scanner.daily_shape_public import publish
        print(json.dumps(publish(report, Path(args.out)), ensure_ascii=False))
        return
    report = build_preview(args.cache_dir, args.common_path, as_of=args.as_of, top=args.top, index_path=args.index_path)
    from services.scanner.daily_shape_report import write_report
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out/'comparison.json').write_text(json.dumps(report, ensure_ascii=False, separators=(',', ':'))+'\n')
    write_report(report, out)
    print(json.dumps({k: report[k] for k in ('as_of', 'selected_count', 'state_counts', 'price_version')}, ensure_ascii=False))


if __name__ == '__main__': main()
