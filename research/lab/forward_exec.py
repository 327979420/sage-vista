"""Task048: executable replay beside the immutable rule-1.9 record."""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import multiprocessing
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

from research.lab import buysystem as BS, datasets, selection, triangle15 as N
from research.lab import triangle_forward as F, forward_judge as J


def live_day(dates, signal_idx, recorded_at=None):
    day = dt.date.fromisoformat(dates[signal_idx])
    monday = day - dt.timedelta(days=day.weekday())
    first = bisect.bisect_left(dates, (monday + dt.timedelta(days=14)).isoformat())
    live = first + 1
    if recorded_at is not None:
        stamp = dt.datetime.fromisoformat(recorded_at.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('recorded_at must include a timezone')
        while live < len(dates):
            opening = dt.datetime.combine(dt.date.fromisoformat(dates[live]), dt.time(9, 30), ZoneInfo('America/New_York'))
            if stamp <= opening:
                break
            live += 1
    return min(live, len(dates))


def executable(series, signal_idx, plan, recorded_at=None):
    live = live_day(series['date'], signal_idx, recorded_at)
    base = {'live': series['date'][live] if live < len(series['date']) else None}
    level, stop = plan['level'], plan['stop']
    target = level + 3 * (level - stop)
    for i in range(signal_idx + 1, live):
        if series['low'][i] <= stop:
            return {**base, 'status': 'skip_stop'}
        if series['high'][i] >= target:
            return {**base, 'status': 'skip_target'}
    if live >= len(series['date']):
        return {**base, 'status': 'waiting'}
    trade = N.trade(series, live - 1, level, stop, target, hold=130, wait=40 - (live - 1 - signal_idx))
    result = {**base, 'status': trade['status']}
    if 'fill_day' in trade:
        result['fill'] = series['date'][trade['fill_day']]
    if 'exit_day' in trade:
        result['exit'] = series['date'][trade['exit_day']]
    if trade['status'] in J.DONE:
        result['R'] = J.net_r(trade['entry'], trade['exit'], stop)
    return result


def _scan(symbol):
    s = F.PX[symbol]
    rows = []
    for sig in N.signals(s, start='2005-01-01', end='2024-06-30'):
        p = N.plan(s, sig, BS.periods(s, 'week')['atr'][sig['t']])
        if not p['go'] or not F.market(s['date'][sig['day']])['ok']:
            continue
        a = N.trade(s, sig['day'], p['level'], p['stop'], p['level'] + 3 * (p['level'] - p['stop']), hold=130)
        b = executable(s, sig['day'], p)
        rows.append({'sym': symbol, 'day': s['date'][sig['day']], 'stop': p['stop'],
                     'a': a['status'], 'aR': J.net_r(a['entry'], a['exit'], p['stop']) if a['status'] in J.DONE else None,
                     'b': b['status'], 'bR': b.get('R')})
    return rows


def history(config):
    rows = []
    for ds in config['datasets']:
        entry = datasets.manifest(ds)
        # Deliberately never call download: missing local data is an error.
        F.PX = datasets.load(F.ROOT / 'work/lab' / entry['asset'], entry['sha256'])['prices']
        for sym, s in F.PX.items():
            end = bisect.bisect_right(s['date'], '2025-06-30')
            F.PX[sym] = {k: v[:end] for k, v in s.items()}
        if 'SPY' in F.PX:
            F.SPY = F.PX['SPY']
        F.BREADTH.clear()
        flagged = selection.impossible_jumps(F.PX)
        syms = sorted(x for x in F.PX if x not in flagged and x not in N.FUNDS)
        with multiprocessing.get_context('fork').Pool(4) as pool:
            batch = [r for chunk in pool.map(_scan, syms, chunksize=8) for r in chunk]
        rows.extend({**r, 'ds': ds} for r in batch)
        print(ds, len(batch), flush=True)
    for key, label in [('aR', 'as-recorded'), ('bR', 'executable')]:
        values = [r[key] for r in rows if r[key] is not None]
        print(f'{label}: {len(values)} trades {J.mean(values):+.3f}R', flush=True)
    return rows


FOLDER = 'research/lab/forward_exec'
SUMMARY_FIELDS = ('trades', 'wins', 'mean_R', 'sum_R', 'skipped_stop', 'skipped_target', 'waiting', 'open')


def compute(config, records, outcomes, now):
    rows = []
    eligible = [r for r in records if r['plan']['go'] and r.get('market', {}).get('ok')]
    if any(r['dataset'] not in config['datasets'] for r in eligible):
        raise ValueError('unknown forward dataset')
    as_of = dt.datetime.fromisoformat(outcomes['computed_at'].replace('Z', '+00:00')).astimezone(dt.timezone.utc).date().isoformat()
    for ds in config['datasets']:
        recs = [r for r in eligible if r['dataset'] == ds]
        if not recs:
            continue
        prices = J.cached_prices(ds, config, as_of)
        for rec in recs:
            raw = prices.get(rec['symbol'])
            if not raw or rec['signal_day'] not in raw['date']:
                raise ValueError(f"missing prices: {rec['id']}")
            end = bisect.bisect_right(raw['date'], as_of)
            series = {k: v[:end] for k, v in raw.items()}
            if rec['signal_day'] not in series['date']:
                raise ValueError(f"signal after outcome cutoff: {rec['id']}")
            if any(len(series[k]) != end or any(v is None for v in series[k]) for k in ('open', 'high', 'low', 'close')):
                raise ValueError(f"missing OHLC prices: {rec['id']}")
            got = executable(series, series['date'].index(rec['signal_day']), rec['plan'], rec['recorded_at'])
            rows.append({'id': rec['id'], 'symbol': rec['symbol'], **{k: got[k] for k in ('live', 'status', 'R') if k in got}})
    values = [r['R'] for r in rows if r['status'] in J.DONE]
    summary = dict(trades=len(values), wins=sum(r > 0 for r in values), mean_R=J.mean(values), sum_R=sum(values),
                   skipped_stop=sum(r['status'] == 'skip_stop' for r in rows),
                   skipped_target=sum(r['status'] == 'skip_target' for r in rows),
                   waiting=sum(r['status'] == 'waiting' for r in rows), open=sum(r['status'] == 'open' for r in rows))
    return dict(schema_version=1, version='3w-1.9', computed_at=now, outcomes_computed_at=outcomes['computed_at'],
                rows=sorted(rows, key=lambda r: r['id']), summary=summary)


def write(root, snapshot):
    path = Path(root) / FOLDER / 'latest.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def publish(snapshot, attempts=3):
    """Bot-only publication, following paper.publish; never called by offline replay."""
    from research.lab.run_queue import in_eod_window
    def git(*args, check=True):
        return subprocess.run(['git', *args], cwd=F.ROOT, check=check, text=True, capture_output=True)
    for _ in range(attempts):
        if in_eod_window():
            raise RuntimeError('inside the 23:30-04:30 UTC EOD window; executable record not published')
        git('fetch', 'origin', 'main')
        git('switch', '--detach', '--force', 'origin/main')
        current = json.loads((F.ROOT / F.FOLDER / 'outcomes.json').read_text())
        if current['computed_at'] != snapshot['outcomes_computed_at']:
            raise ValueError('forward outcomes changed; executable snapshot not published')
        write(F.ROOT, snapshot)
        git('add', '--', FOLDER)
        if git('diff', '--cached', '--quiet', check=False).returncode == 0:
            return
        git('-c', 'user.name=sage-vista-bot', '-c', 'user.email=sage-vista-bot@users.noreply.github.com',
            'commit', '--only', '-m', f"research: executable forward {snapshot['computed_at']} [skip ci]", '--', FOLDER)
        if git('push', 'origin', 'HEAD:main', check=False).returncode == 0:
            return
    raise RuntimeError('could not publish executable record after retries')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--history', action='store_true')
    group.add_argument('--publish', action='store_true')
    args = parser.parse_args(argv)
    config = json.loads(F.CONFIG.read_text())
    if args.history:
        history(config)
        return
    outcomes = json.loads((F.ROOT / F.FOLDER / 'outcomes.json').read_text())
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    snapshot = compute(config, F.load_records(), outcomes, now)
    if args.publish:
        publish(snapshot)
    else:
        write(F.ROOT, snapshot)
    print(json.dumps(snapshot['summary'], ensure_ascii=False))


if __name__ == '__main__':
    main()
