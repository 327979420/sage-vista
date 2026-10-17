"""Small read-only app projections. Preview is offline; --publish is Actions-only.

Dates are source dates, not a promise of live prices. generated_at is an explicit
build input; use --generated-at to reproduce the same bytes at another time.
Distances use the recorded planned risk (limit - stop), not an inferred fill.
"""
from __future__ import annotations

import argparse
import bisect
from collections import Counter
import datetime as dt
import gzip
import json
import os
import random
from pathlib import Path
import subprocess
import tempfile

from research.lab import datasets, factor_tags, triangle_forward
from research.lab.run_queue import in_eod_window
from services.scanner.public_asset_limits import validate_asset

ROOT = Path(__file__).resolve().parents[2]
SECTOR = 'sector-etf-1998-to-2026-10-v1'
UNIVERSE = 'universe-1985-v1'
VERSION = '3w-1.9'
SLEEVES = ['XLB', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLU', 'XLV', 'XLY', 'SPY']
FILES = ('today.json', 'signals.json', 'portfolio.json', 'record.json')
MAX_BYTES = 2_000_000
FORWARD = Path('research/lab/forward/triangle')


def frozen_prices(dataset_id, root=ROOT, *, allow_download=False):
    entry = datasets.manifest(dataset_id)
    if entry is None:
        raise ValueError(f'missing dataset manifest: {dataset_id}')
    path = root / 'work/lab' / entry['asset']
    if not path.exists() and allow_download:
        path = datasets.download(entry, root / 'work/lab')
    if not path.exists():
        raise FileNotFoundError(f'offline dataset missing: {path}')
    return datasets.load(path, entry['sha256'])['prices']


def bulk_files(root):
    return {p.name[:10]: p for p in sorted((root / 'work/triangle-bulk').glob('????-??-??.json.gz'))}


def extend_prices(prices, files):
    # Reuse the forward recorder's split guard and missing-bar semantics.
    triangle_forward.extend(prices, sorted(files),
                            lambda day: json.loads(gzip.decompress(files[day].read_bytes())))
    return prices


def quote(series, day):
    i = bisect.bisect_right(series['date'], day) - 1 if series else -1
    if i < 0:
        return dict(price_as_of=None, close=None, sma200=None, distance_pct=None, stale=True)
    close = series['close'][i]
    sma = sum(series['close'][i - 199:i + 1]) / 200 if i >= 199 else None
    return dict(price_as_of=series['date'][i], close=close, sma200=sma,
                distance_pct=(close / sma - 1) * 100 if sma else None,
                stale=series['date'][i] != day)


def market_state(prices, day):
    spy = prices.get('SPY')
    q = quote(spy, day)
    if q['stale'] or q['sma200'] is None:
        return dict(spy_over_200d=None, breadth=None, breadth_sample=None, ok=None, light=None, **q)
    # The frozen function owns the exact sampling, inclusion and rounding rules.
    old = triangle_forward.PX, triangle_forward.SPY, triangle_forward.BREADTH
    try:
        triangle_forward.PX, triangle_forward.SPY, triangle_forward.BREADTH = prices, spy, {}
        state = triangle_forward.market(day)
        breadth = triangle_forward.BREADTH[day]
        # Read-only denominator projection of the frozen sampler; no new market rule.
        sample = random.Random(day).sample(sorted(prices), min(300, len(prices)))
        state['breadth_sample'] = sum(
            i >= 200 and i < len(prices[symbol]['date']) and prices[symbol]['date'][i] == day
            for symbol in sample
            for i in [bisect.bisect_left(prices[symbol]['date'], day)])
        state["breadth_over_half"] = breadth > 0.5 if breadth is not None else None
    finally:
        triangle_forward.PX, triangle_forward.SPY, triangle_forward.BREADTH = old
    return {**state, **q, 'light': light(state)}


def light(state):
    if state['breadth'] is None or state['spy_over_200d'] is None:
        return None
    # ok uses the unrounded breadth inside the frozen function. When SPY is
    # below its SMA we must likewise use the raw breadth for the half boundary.
    breadth_over = state.get('breadth_over_half', state['breadth'] > 0.5)
    if state['spy_over_200d']:
        breadth_over = state['ok']
    return ('red', 'amber', 'green')[int(state['spy_over_200d']) + int(breadth_over)]


def next_session(day):
    """Next regular US equity session; unexpected exchange closures are unknown."""
    def holidays(year):
        def nth(month, weekday, n):
            first = dt.date(year, month, 1)
            return first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
        def observed(month, day):
            d = dt.date(year, month, day)
            return d + dt.timedelta(days=-1 if d.weekday() == 5 else 1 if d.weekday() == 6 else 0)
        # Gregorian Easter (Good Friday is two days earlier).
        a, b, c = year % 19, year // 100, year % 100
        d, e = b // 4, b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i, k = c // 4, c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        easter = dt.date(year, (h + l - 7 * m + 114) // 31, (h + l - 7 * m + 114) % 31 + 1)
        memorial = dt.date(year, 5, 31)
        memorial -= dt.timedelta(days=memorial.weekday())
        dates = {nth(2, 0, 3), easter - dt.timedelta(days=2), memorial,
                 observed(7, 4), nth(9, 0, 1), nth(11, 3, 4), observed(12, 25)}
        new_year = dt.date(year, 1, 1)
        # NYSE does not observe a Saturday New Year on the preceding Friday.
        dates.add(new_year + dt.timedelta(days=1 if new_year.weekday() == 6 else 0))
        if year >= 1998:
            dates.add(nth(1, 0, 3))
        if year >= 2022:
            dates.add(observed(6, 19))
        return dates
    following = dt.date.fromisoformat(day) + dt.timedelta(days=1)
    while following.weekday() >= 5 or following in holidays(following.year):
        following += dt.timedelta(days=1)
    return following.isoformat()


def month_state(prices, day):
    """Month-end decision, executed next session. Never use a later price."""
    due = next_session(day)[:7] != day[:7]
    if due:
        return day, True
    previous = dt.date.fromisoformat(day).replace(day=1) - dt.timedelta(days=1)
    # A missing SPY quote must not move the month-end signal to an earlier day.
    # The quote at this scheduled boundary will instead be explicitly stale.
    while next_session((previous - dt.timedelta(days=1)).isoformat()) != previous.isoformat():
        previous -= dt.timedelta(days=1)
    return previous.isoformat(), False



def portfolio(prices, day):
    month_end, due = month_state(prices, day)
    sleeves = []
    for symbol in SLEEVES:
        def decision(at):
            q = quote(prices.get(symbol), at) if at else quote(None, day)
            # Carry the last observed decision, explicitly dated and stale.
            hold = None if q['sma200'] is None else symbol if q['close'] > q['sma200'] else 'SHY'
            return {**q, 'signal_as_of': at, 'hold': hold}
        current, previous = decision(day), decision(month_end)
        sleeves.append(dict(symbol=symbol, stale=current['stale'], today=current,
                            month_end=previous,
                            would_switch=(current['hold'] != previous['hold'])
                            if current['hold'] and previous['hold'] else None))
    return dict(status='candidate', month_end_signal_as_of=month_end,
                rebalance_due=due, next_session=next_session(day), calendar_basis='regular_NYSE_holidays',
                sleeves=sleeves, shy=quote(prices.get('SHY'), day))


def signal_rows(records, outcomes, prices_by_dataset, day):
    by_id = {o['id']: o for o in outcomes['outcomes']}
    result = []
    for rec in sorted(records, key=lambda r: (r['signal_day'], r['id'])):
        if rec.get('version') != VERSION:
            continue
        p = rec['plan']
        level, stop = p.get('level'), p.get('stop')
        risk = level - stop if level is not None and stop is not None else None
        target = level + 3 * risk if risk and risk > 0 else None
        outcome = by_id.get(rec['id'], {})
        raw = outcome.get('r19', {})
        eligible = bool(p['go'] and rec['market'].get('ok'))
        source_status = raw.get('status', outcome.get('status') if not p['go'] else None)
        status = ('skipped' if not eligible else
                  'closed' if source_status in ('win', 'loss', 'time') else source_status or 'unavailable')
        series = prices_by_dataset.get(rec['dataset'], {}).get(rec['symbol'])
        q = quote(series, day)
        tags = dict(entry=[], risk=[], context_only=True, available=False, as_of=q['price_as_of'])
        if series:
            end = bisect.bisect_right(series['date'], day) - 1
            if end >= 0:
                start = bisect.bisect_left(series['date'], '2005-01-01')
                rows = datasets.expand({k: v[start:end + 1] for k, v in series.items()})
                if not rows:
                    raise ValueError('factor context must be after the locked-data boundary')
                entry = factor_tags.entry_audit(rows, len(rows) - 1)
                warnings = factor_tags.risk_timeline(rows, len(rows) - 1)[-1]
                tags.update(entry=entry['tags'], risk=warnings['tags'], available=True,
                            entry_unavailable=entry['unavailable'], risk_unavailable=warnings['unavailable'])
        distances = None
        if status == 'open' and q['close'] and risk and risk > 0:
            close = q['close']
            distances = dict(to_stop_pct=(close - stop) / close * 100,
                             to_target_pct=(target - close) / close * 100,
                             to_stop_R=(close - stop) / risk,
                             to_target_R=(target - close) / risk,
                             R_basis='planned_limit_minus_stop')
        result.append(dict(id=rec['id'], symbol=rec['symbol'], version=VERSION,
                           dataset=rec['dataset'], week=rec['week'], signal_day=rec['signal_day'],
                           market=rec['market'], order=dict(limit=level, stop=stop, target=target,
                           R_multiple=3 if target is not None else None, eligible=eligible),
                           status=status, source_status=source_status,
                           R=raw.get('R') if eligible else None, quote=q,
                           distances=distances, factor_tags=tags))
    return result


def completed_signal_week(day):
    """Last completed regular NYSE week, labeled by its final session date."""
    end = dt.date.fromisoformat(day)
    while True:
        previous = (end - dt.timedelta(days=1)).isoformat()
        if (next_session(previous) == end.isoformat()
                and dt.date.fromisoformat(next_session(end.isoformat())).isocalendar()[:2]
                != end.isocalendar()[:2]):
            return end.isoformat()
        end -= dt.timedelta(days=1)


def stale_inputs(universe, book, signals, day):
    """Source-qualified names preserve missing dates as null, never as fresh."""
    stale = {}
    def add(name, q):
        if q['stale']:
            stale[name] = q['price_as_of']
    add('market.SPY', quote(universe.get('SPY'), day))
    for sleeve in book['sleeves']:
        for period in ('today', 'month_end'):
            add(f"sectors.{sleeve['symbol']}.{period}", sleeve[period])
    add('sectors.SHY', book['shy'])
    for signal in signals:
        add(f"signals.{signal['id']}.{signal['symbol']}", signal['quote'])
    return stale


def build(*, sectors, universe, records, outcomes, prices_by_dataset, facts, as_of, generated_at):
    header = dict(schema_version=1, generated_at=generated_at, as_of=as_of)
    book = portfolio(sectors, as_of)
    signals = signal_rows(records, outcomes, prices_by_dataset, as_of)
    signal_week = completed_signal_week(as_of)
    week_key = dt.date.fromisoformat(signal_week).isocalendar()[:2]
    def in_signal_week(record):
        return (record['signal_day'] <= as_of
                and dt.date.fromisoformat(record['week']).isocalendar()[:2] == week_key)
    actions = [dict(kind='new_order', signal_id=s['id'], symbol=s['symbol'], text='挂限价单')
               for s in signals if s['status'] == 'waiting' and s['order']['eligible']
               and in_signal_week(s)]
    orders_to_place = len(actions)
    new_signals = sum(r.get('version') == VERSION and in_signal_week(r) for r in records)
    if book['rebalance_due']:
        actions.append(dict(kind='month_end_rebalance', text='月底调仓'))
    counts = Counter(s['status'] for s in signals)
    return {
        'today.json': {**header, 'breadth_source': UNIVERSE, 'market': market_state(universe, as_of), 'this_week': actions,
                       'signal_week': signal_week, 'new_signals_this_week': new_signals,
                       'orders_to_place': orders_to_place,
                       'month_end': {k: book[k] for k in ('rebalance_due', 'next_session')} | {
                           'would_switch': [s['symbol'] for s in book['sleeves'] if s['would_switch'] is True]},
                       'stale': stale_inputs(universe, book, signals, as_of)},
        'signals.json': {**header, 'outcomes_as_of': outcomes['computed_at'], 'signals': signals},
        'portfolio.json': {**header, **book},
        'record.json': {**header, 'facts': facts, 'forward': {
            'version': VERSION, 'computed_at': outcomes['computed_at'], 'signals': len(signals),
            'counts': {k: counts[k] for k in ('waiting', 'open', 'closed', 'cancelled', 'skipped', 'unavailable')}}},
    }


def encode(payloads):
    if set(payloads) != set(FILES):
        raise ValueError('expected exactly four app files')
    encoded = {}
    for name in FILES:
        data = (json.dumps(payloads[name], ensure_ascii=False, sort_keys=True,
                           separators=(',', ':'), allow_nan=False) + '\n').encode()
        validate_asset(f'app/{name}', data)
        if len(data) > MAX_BYTES:
            raise ValueError(f'app file exceeds 2 MB: {name} ({len(data)} bytes)')
        encoded[name] = data
    return encoded


def write(encoded, folder):
    folder.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        path = folder / name
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(encoded[name])
        temporary.replace(path)


def load_build(root=ROOT, *, allow_download=False, generated_at=None):
    generated_at = generated_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    outcomes = json.loads((root / FORWARD / 'outcomes.json').read_text())
    records = triangle_forward.load_records(root)
    facts = json.loads((root / 'research/lab/app/record_facts.json').read_text())
    files = bulk_files(root)
    sectors = extend_prices(frozen_prices(SECTOR, root, allow_download=allow_download), files)
    as_of = max([sectors['SPY']['date'][-1], *files])
    universe = extend_prices(frozen_prices(UNIVERSE, root, allow_download=allow_download), files)
    # Preserve the full universe for the frozen breadth sampler.
    price_sets = {UNIVERSE: universe}
    for ds in sorted({r['dataset'] for r in records if r.get('version') == VERSION} - {UNIVERSE}):
        price_sets[ds] = extend_prices(frozen_prices(ds, root, allow_download=allow_download), files)
    return build(sectors=sectors, universe=universe, records=records, outcomes=outcomes,
                 prices_by_dataset=price_sets, facts=facts, as_of=as_of, generated_at=generated_at)


def publish(encoded, root=ROOT):
    """Commit only four app paths with an isolated index; never switch branches.

    Refuse stale forward inputs and non-fast-forward races. This is deliberately
    fail-closed: the next scheduled run can build a new snapshot.
    """
    if in_eod_window():
        raise RuntimeError('inside the 23:30-04:30 UTC EOD window')
    def git(*args, **kwargs):
        return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True, **kwargs).stdout
    git('fetch', 'origin', 'main')
    parent = git('rev-parse', 'origin/main').decode().strip()
    for rel in [FORWARD / 'signals.jsonl', FORWARD / 'outcomes.json', FORWARD / 'config.json',
                Path('research/lab/app/record_facts.json')]:
        if git('show', f'{parent}:{rel}') != (root / rel).read_bytes():
            raise RuntimeError(f'upstream input changed: {rel}')
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, 'GIT_INDEX_FILE': str(Path(tmp) / 'index')}
        git('read-tree', parent, env=env)
        for name, content in encoded.items():
            oid = git('hash-object', '-w', '--stdin', input=content).decode().strip()
            git('update-index', '--add', '--cacheinfo', f'100644,{oid},public/app/{name}', env=env)
        tree = git('write-tree', env=env).decode().strip()
        if tree == git('rev-parse', f'{parent}^{{tree}}').decode().strip():
            return
        if in_eod_window():
            raise RuntimeError('inside the 23:30-04:30 UTC EOD window')
        commit = git('-c', 'user.name=sage-vista-bot', '-c',
                     'user.email=sage-vista-bot@users.noreply.github.com',
                     'commit-tree', tree, '-p', parent, '-m', 'research: app data [skip ci]').decode().strip()
        if in_eod_window():
            raise RuntimeError('inside the 23:30-04:30 UTC EOD window')
        git('push', 'origin', f'{commit}:refs/heads/main')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--generated-at', help='fixed ISO timestamp for reproducible builds')
    args = parser.parse_args(argv)
    if args.generated_at:
        dt.datetime.fromisoformat(args.generated_at.replace('Z', '+00:00'))
    if args.publish and in_eod_window():
        raise RuntimeError('inside the 23:30-04:30 UTC EOD window')
    encoded = encode(load_build(allow_download=args.publish, generated_at=args.generated_at))
    if args.publish:
        publish(encoded)
    else:
        write(encoded, ROOT / 'work/app-data')
    for name, data in encoded.items():
        print(f'{name}: {len(data)} bytes')


if __name__ == '__main__':
    main()
