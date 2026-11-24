"""Stock lookup index: every stock SV tracks today and what SV's views say about it.

The site's search box and /stock pages read this one small file. It only joins
results the daily update already produced (the multi-factor snapshot and
ranking, the daily shape picker, the 3W app data) and adds three plain price
facts per stock. It adds no score, ranking or trading rule, and it publishes no
price history: charts on /stock pages come from files that are already public.
"""
import argparse
import json
import os
import pathlib
import tempfile
from datetime import datetime, timezone

from .macd_factor_backtest import adjusted_rows

OUT = 'stock-index.json'
ACTIVE = 'work/eodhd-active-common.json'
SCHEMA_VERSION = 1
# The tracked universe is the multi-factor snapshot's eligibility gate (factor_snapshot.build_snapshot);
# the build fails if the count ever differs from the snapshot's own eligible_count.
MIN_CLOSE, MIN_DOLLAR_VOLUME, MIN_SESSIONS = 5, 10_000_000, 420
HALF_YEAR, YEAR, SMA = 126, 252, 200
BIG_NAMES = 10
SHAPE_STATES = ('waiting', 'broken_out', 'retest')


def load_cache(cache_dir, active_path=ACTIVE):
    """Cached rows for active common stocks only (ETFs and benchmarks share the cache), as the snapshot loads them."""
    active_file = pathlib.Path(active_path)
    active = {row['Code'] for row in json.loads(active_file.read_text())} if active_file.exists() else None
    data = {}
    for path in sorted(pathlib.Path(cache_dir).glob('*.json')):
        if active is not None and path.stem not in active:
            continue
        try:
            rows = adjusted_rows(json.loads(path.read_text()))
        except (ValueError, TypeError, KeyError, ZeroDivisionError):
            continue
        if rows:
            data[path.stem] = rows
    return data


def tracked(symbol_rows, as_of):
    """Price facts for every stock that passes the snapshot's eligibility gate on as_of."""
    out = {}
    for symbol, rows in sorted(symbol_rows.items()):
        rows = [row for row in rows if row['date'] <= as_of]
        if not rows or rows[-1]['date'] != as_of or len(rows) < MIN_SESSIONS:
            continue
        close, volume = rows[-1]['close'], rows[-1]['volume']
        if close < MIN_CLOSE or close * volume < MIN_DOLLAR_VOLUME:
            continue
        closes = [row['close'] for row in rows]
        out[symbol] = {'c': round(close, 2), 'dv': round(close * volume),
                       'm6': round((close / closes[-HALF_YEAR - 1] - 1) * 100, 1),
                       'hi': round((close / max(closes[-YEAR:]) - 1) * 100, 1),
                       'ma': close > sum(closes[-SMA:]) / SMA}
    return out


def _read(public, name):
    return json.loads((public / name).read_text())


def _require(payload, as_of, name):
    if payload.get('as_of') != as_of:
        raise ValueError(f'stock index: {name} is for {payload.get("as_of")}, expected {as_of}')
    return payload


def _new_since(previous, stocks, as_of):
    """What appeared since the previous index: ranked candidates, shape states and 3W signals."""
    if previous and previous.get('as_of') == as_of:
        return previous.get('new', {'mf': [], 'sh': [], 'w3': []}), previous.get('new_since')
    if not previous or previous.get('as_of', '') > as_of:
        return {'mf': [], 'sh': [], 'w3': []}, None
    before = previous.get('stocks', {})
    was = lambda symbol, key: before.get(symbol, {}).get(key)
    new = {'mf': sorted((s for s, e in stocks.items() if e.get('mf') and not was(s, 'mf')), key=lambda s: stocks[s]['mf']),
           'sh': sorted(s for s, e in stocks.items() if e.get('sh') in ('waiting', 'broken_out') and was(s, 'sh') != e['sh']),
           'w3': sorted(s for s, e in stocks.items() if e.get('w3') and (was(s, 'w3') or {}).get('id') != e['w3']['id'])}
    return new, previous['as_of']


def build(symbol_rows, as_of, public, previous=None, generated_at=None):
    public = pathlib.Path(public)
    snapshot = _require(_read(public, 'daily-factor-snapshot.json'), as_of, 'daily-factor-snapshot')
    stocks = tracked(symbol_rows, as_of)
    if len(stocks) != snapshot['eligible_count']:
        raise ValueError(f'stock index: {len(stocks)} tracked stocks but the factor snapshot counted {snapshot["eligible_count"]}')
    count = len(stocks)
    days = _read(public, 'unified-v2-latest.json').get('days') or []
    if not days or days[-1].get('date') != as_of:
        raise ValueError('stock index: unified-v2-latest is not for ' + as_of)
    picker = _require(_read(public, 'daily-shape-picker.json'), as_of, 'daily-shape-picker')
    signals, today = _read(public, 'app/signals.json'), _read(public, 'app/today.json')
    closed = _read(public, 'app/record.json').get('forward', {}).get('counts', {}).get('closed', 0)

    def entry(symbol, price=None):
        if symbol not in stocks:
            stocks[symbol] = {'c': round(price, 2) if isinstance(price, (int, float)) else None, 'x': True}
        return stocks[symbol]

    for row in snapshot['symbols']:
        entry(row['symbol'], row.get('price'))['mf'] = 0
    ranking = days[-1].get('ranking') or []
    for position, row in enumerate(ranking, 1):
        resonance = row.get('technical_resonance') or {}
        item = entry(row['symbol'], row.get('price'))
        item.update(mf=row.get('rank') or position, h=resonance.get('positive_hit_count'), f=resonance.get('families') or [])
    for row in picker['rows']:
        if row.get('state') in SHAPE_STATES:
            entry(row['symbol'], row.get('price')).update(sh=row['state'], a=row.get('activity_rank'))
    latest_week = max((s['week'] for s in signals['signals']), default=None)
    for signal in sorted(signals['signals'], key=lambda s: s['week']):
        quote = signal.get('quote') or {}
        entry(signal['symbol'], quote.get('close'))['w3'] = {'id': signal['id'], 'week': signal['week'], 'status': signal['status']}
    big = [s for s, _ in sorted(((s, e['dv']) for s, e in stocks.items() if 'dv' in e), key=lambda x: -x[1])[:BIG_NAMES]]
    for item in stocks.values():
        item.pop('dv', None)
    new, new_since = _new_since(previous, stocks, as_of)
    market = today.get('market') or {}
    return {'schema_version': SCHEMA_VERSION, 'as_of': as_of,
            'generated_at': generated_at or datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'rule': {'market': 'US', 'min_close': MIN_CLOSE, 'min_dollar_volume': MIN_DOLLAR_VOLUME, 'min_sessions': MIN_SESSIONS},
            'count': count, 'mf_triggered': len(snapshot['symbols']), 'mf_ranked': len(ranking),
            'shape_watch': (picker.get('universe') or {}).get('selected_activity_count'), 'shape_counts': picker.get('state_counts') or {},
            'w3': {'as_of': today.get('as_of'), 'week': today.get('signal_week'), 'new': today.get('new_signals_this_week'),
                   'light': market.get('light'), 'latest_week': latest_week,
                   'latest': sorted(s['symbol'] for s in signals['signals'] if s['week'] == latest_week), 'since_lock': len(signals['signals'])},
            'closed': closed, 'big': big, 'new': new, 'new_since': new_since,
            'stocks': dict(sorted(stocks.items()))}


def write(index, path):
    path = pathlib.Path(path)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix='.stock-index-')
    with os.fdopen(handle, 'w') as out:
        out.write(json.dumps(index, ensure_ascii=False, separators=(',', ':')) + '\n')
    os.replace(temporary, path)


def run(as_of, cache_dir='work/eodhd-cache', public='public', active_path=ACTIVE):
    path = pathlib.Path(public) / OUT
    previous = json.loads(path.read_text()) if path.exists() else None
    index = build(load_cache(cache_dir, active_path), as_of, public, previous)
    changed = previous is None or {k: v for k, v in previous.items() if k != 'generated_at'} != {k: v for k, v in index.items() if k != 'generated_at'}
    if changed:
        write(index, path)
    return {'result': 'updated' if changed else 'already_current', 'as_of': as_of, 'count': index['count'], 'changed': changed}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--cache-dir', default='work/eodhd-cache')
    parser.add_argument('--public', default='public')
    parser.add_argument('--active', default=ACTIVE)
    args = parser.parse_args()
    print(json.dumps(run(args.as_of, args.cache_dir, args.public, args.active)))
