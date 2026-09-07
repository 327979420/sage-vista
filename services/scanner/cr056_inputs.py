"""Bounded repair of existing recent EOD histories into a private comparison cache.

Only this explicitly invoked data step may call the existing supplier. It never
changes the original cache, uploads raw data, or downloads per-stock histories.
"""
import argparse
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
from services.scanner.macd_factor_backtest import adjusted_rows
from services.market_data.normalization import validate_adjusted_rows
from services.market_data.storage import require_shadow_root


def merge_recent_history(raw, bulk_by_day, *, as_of, expected_sessions):
    """Pure merge with adjustment-anchor checks; stale identities are not revived."""
    if not isinstance(raw, list) or not raw:
        raise ValueError('empty_cached_history')
    before = {r['date']: r for r in raw if r.get('date', '') <= as_of}
    if len(before) != sum(r.get('date', '') <= as_of for r in raw):
        raise ValueError('duplicate_cached_date')
    if not before:
        raise ValueError('no_history_at_as_of')
    last = max(before)
    if (date.fromisoformat(as_of) - date.fromisoformat(last)).days > 10:
        raise ValueError('old_tail_not_automatically_revived')
    if last not in bulk_by_day:
        raise ValueError('adjustment_anchor_missing')
    for day, row in sorted(bulk_by_day.items()):
        if day > as_of or row.get('date') != day:
            raise ValueError('bulk_date_mismatch')
        if day in before:
            old = before[day]
            if not old.get('close') or not row.get('close'):
                raise ValueError('invalid_adjustment_anchor')
            a, b = old['adjusted_close']/old['close'], row['adjusted_close']/row['close']
            if not math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-10):
                raise ValueError('historical_adjustment_changed')
        before[day] = dict(row)
    needed = [d for d in expected_sessions if last <= d <= as_of]
    if any(day not in before for day in needed) or as_of not in before:
        raise ValueError('recent_session_missing')
    output = [before[day] for day in sorted(before)]
    normalized = adjusted_rows(output)
    if len(normalized) != len(output):
        raise ValueError('cached_ohlcv_invalid')
    validate_adjusted_rows(normalized)
    return output


def repair_existing_cache(cache_dir, private_dir, *, as_of, fetch_bulk):
    private_dir = require_shadow_root(private_dir, workspace_root=Path(__file__).resolve().parents[2])
    original = Path(cache_dir).resolve()
    if private_dir == original or private_dir in original.parents or original in private_dir.parents:
        raise ValueError('private_cache_must_be_separate_from_original')
    cutoff = date.fromisoformat(as_of)
    if cutoff.isoformat() != as_of:
        raise ValueError('noncanonical_as_of')
    paths = sorted(Path(cache_dir).glob('*.json'))
    if not paths:
        raise ValueError('no_existing_cache_no_network_download_fallback')
    candidates, excluded, source_hashes = {}, {}, {}
    for p in paths:
        try:
            content = p.read_bytes(); raw = json.loads(content)
            if not isinstance(raw, list) or not raw: raise ValueError('empty_cached_history')
            tail = max(r['date'] for r in raw if r['date'] <= as_of)
            if (cutoff-date.fromisoformat(tail)).days > 10: raise ValueError('old_tail_not_automatically_revived')
            candidates[p.stem] = (raw, tail)
            source_hashes[p.stem] = hashlib.sha256(content).hexdigest()
        except (ValueError, TypeError, KeyError):
            excluded[p.stem] = 'empty_invalid_or_old_cache'
    if not candidates: raise ValueError('no_recent_cached_histories')
    # Include the earliest old tail as a same-date adjustment consistency anchor.
    start = date.fromisoformat(min(tail for _,tail in candidates.values()))
    days = []
    while start <= cutoff:
        if start.weekday() < 5: days.append(start.isoformat())
        start += timedelta(days=1)
    if len(days) > 9: raise ValueError('bounded_bulk_request_budget_exceeded')
    series = {symbol: {} for symbol in candidates}
    sessions, hashes = [], {}
    for day in days:
        rows = fetch_bulk(day)
        if not isinstance(rows, list) or not rows or any(r.get('date') != day for r in rows):
            raise ValueError('bulk_date_mismatch_or_unavailable')
        by_code = {}
        duplicates = set()
        for row in rows:
            code = row.get('code') or row.get('Code')
            if code in by_code: duplicates.add(code)
            by_code[code] = row
        if 'SPY' not in by_code or 'SPY' in duplicates:
            raise ValueError('reference_session_not_proven')
        sessions.append(day)
        hashes[day] = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        for symbol in candidates:
            if symbol in duplicates: excluded[symbol] = 'ambiguous_bulk_symbol'
            elif symbol in by_code: series[symbol][day] = by_code[symbol]
    out = Path(private_dir) / 'eodhd-cache'; out.mkdir(parents=True, exist_ok=True)
    repaired = []
    for symbol, (raw, tail) in candidates.items():
        if symbol in excluded: continue
        try:
            merged = merge_recent_history(raw, series[symbol], as_of=as_of, expected_sessions=sessions)
            content = json.dumps(merged, separators=(',', ':')).encode()
            dest = out / f'{symbol}.json'
            if dest.exists() and dest.read_bytes() != content:
                raise ValueError('private_cache_conflict')
            if not dest.exists(): dest.write_bytes(content)
            repaired.append({'symbol': symbol, 'old_tail': tail, 'new_tail': as_of,
                'rows': len(merged), 'source_sha256': source_hashes[symbol],
                'repaired_sha256': hashlib.sha256(content).hexdigest()})
        except (ValueError, TypeError, KeyError, ZeroDivisionError) as error:
            excluded[symbol] = str(error) if isinstance(error, ValueError) else 'merge_or_adjustment_inconsistent'
    report = {'as_of': as_of, 'result_role': 'legacy_comparison_input_repair',
        'original_cache_unchanged': True, 'requested_bulk_dates': days,
        'observed_reference_sessions': sessions, 'bulk_content_fingerprints': hashes,
        'repaired_count': len(repaired), 'excluded_count': len(excluded),
        'repaired': repaired, 'excluded': excluded,
        'limitations': ['ticker-only identities; no formal universe promotion',
                       'observed SPY sessions are not a general holiday calendar',
                       'adjustment mismatch requires separate source reconciliation, never a silent splice']}
    report_path = Path(private_dir)/'input-repair-report.json'
    report_bytes = json.dumps(report, indent=2)+'\n'
    if report_path.exists() and report_path.read_text() != report_bytes:
        raise ValueError('immutable_input_report_conflict')
    if not report_path.exists():
        with report_path.open('x') as handle: handle.write(report_bytes)
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--as-of', required=True)
    p.add_argument('--cache-dir', default='work/eodhd-cache')
    p.add_argument('--private-dir', default='work/cr056-private')
    args = p.parse_args()
    from services.scanner.resonance_tracker import bulk_day
    report = repair_existing_cache(args.cache_dir, args.private_dir, as_of=args.as_of,
        fetch_bulk=lambda day: bulk_day(day, cache_dir=str(Path(args.private_dir)/'bulk'), strict=True))
    print(json.dumps({k: report[k] for k in ('as_of', 'requested_bulk_dates', 'repaired_count', 'excluded_count')}))

if __name__ == '__main__': main()
