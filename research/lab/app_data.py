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
import re
from pathlib import Path
import subprocess
import tempfile

from research.lab import datasets, factor_tags, triangle_forward, triangle15
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


def market_state(prices, day, *, spy=None):
    spy = prices.get('SPY', spy)
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


# Ticket evidence is a projection only. Frozen helpers remain the decision authority.
TICKET_MAX_BYTES = 60_000


def ticket_name(ident):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', ident) or ident == 'index':
        raise ValueError(f'unsafe ticket id: {ident!r}')
    return f'tickets/{ident}.json'


def ticket_outcome(rec, series, outcomes):
    """Replay the rounded recorded order, exactly as forward.outcome does.

    r19 is rounded to four decimals by the recorder. Missing R is not zero;
    waiting/cancelled orders can only be verified by matching their raw status.
    Market-blocked trades are counterfactual and must stay skipped.
    """
    p = rec['plan']
    base = dict(status='unverified', fill_date=None, exit_date=None, exit=None, R=None,
                source='outcomes.json r19 unavailable')
    if not p['go']:
        return {**base, 'status': 'skipped', 'source': 'recorded plan', 'why': p['why']}
    raw = next((o.get('r19') for o in outcomes['outcomes'] if o['id'] == rec['id']), None)
    d = series['date'].index(rec['signal_day'])
    got = triangle15.trade(series, d, p['level'], p['stop'],
                           p['level'] + 3 * (p['level'] - p['stop']), hold=130)
    actual_r = round(got['R'], 4) if got.get('R') is not None else None
    if raw is None or actual_r != raw.get('R') or got['status'] != raw.get('status'):
        return {**base, 'source': 'frozen trade() recompute mismatch',
                'mismatch': dict(recorded=raw, recomputed=dict(status=got['status'], R=actual_r))}
    matched = actual_r is not None
    base.update(source=('frozen trade() recompute, R matches outcomes.json' if matched else
                        'frozen trade() recompute, status matches outcomes.json; R unavailable'),
                source_status=got['status'], R=actual_r)
    if not rec['market']['ok']:
        return {**base, 'status': 'skipped', 'R': None, 'why': 'market filter',
                'counterfactual_R': actual_r}
    status = {'open': 'filled', 'win': 'closed', 'loss': 'closed', 'time': 'closed'}.get(got['status'], got['status'])
    return {**base, 'status': status,
            'fill_date': series['date'][got['fill_day']] if 'fill_day' in got else None,
            # For open positions exit_day/exit are a mark, not an executed exit.
            'exit_date': series['date'][got['exit_day']] if status == 'closed' else None,
            'exit': got.get('exit') if status == 'closed' else None,
            'mark_date': series['date'][got['exit_day']] if status == 'filled' else None,
            'mark': got.get('exit') if status == 'filled' else None}


def shape_evidence(rows, highs, atr, ln, bots, t):
    """Derived numeric projections, checked against frozen _shape on boundary fixtures."""
    N, T = triangle15, triangle15.T
    p = ln['pushes']
    H1, L1, Lk = rows[p[0]]['high'], min(v for _, v in bots), bots[-1][1]
    level, stop = rows[t]['high'] * 1.001, Lk * .99
    prior_low = min(r['low'] for r in rows[max(0, p[0] - 156):p[0] + 1])
    piv = sorted(set([i for i in highs if p[0] <= i <= t - 2] + p))
    cands = sorted({rows[i]['high'] * .97 for i in piv if rows[i]['high'] * .97 >= rows[t]['close'] * 1.07})
    t1 = cands[0] if cands else None
    checks = []
    def add(key, value, passed, derived=True):
        checks.append(dict(id=key, value=value, **{'pass': bool(passed)}, derived=derived))
    pullback=(H1-L1)/H1
    add('pullback_pct', dict(pct=100*pullback, minimum=100*T.P['min_pullback'], maximum=60), T.P['min_pullback'] <= pullback <= .60)
    add('flat_bottom_pct', dict(pct=100*(Lk/L1-1), maximum=10), Lk <= L1*1.10)
    add('bottom_count', dict(count=len(bots), minimum=2), len(bots)>=2)
    add('not_three_year_low', dict(bottom=L1, prior_low=prior_low, floor=prior_low*.9), L1 >= prior_low*.9)
    add('shape_stop_atr', dict(distance=level-stop, atr=atr[t], minimum_multiple=T.P['stop_min_atr']), level-stop >= T.P['stop_min_atr']*atr[t])
    add('target_at_least_7pct', dict(candidates=cands, target=t1, close=rows[t]['close'],
        pct=(t1/rows[t]['close']-1)*100 if t1 is not None else None, minimum_pct=7), bool(cands) and t1>stop)
    if t1 is None or level <= stop:
        return checks
    needs_adjustment = t1 <= level or (t1-level)/(level-stop)<1.5
    adjusted_distance=(t1+1.5*stop)/2.5-stop
    add('shape_reward_to_risk', dict(rr=(t1-level)/(level-stop), minimum=1.5,
                                  adjustment_needed=needs_adjustment, adjusted_stop_distance=adjusted_distance,
                                  minimum_distance=T.P['stop_min_atr']*atr[t]),
        not needs_adjustment or adjusted_distance >= T.P['stop_min_atr']*atr[t])
    shape = N._shape(rows,highs,atr,ln,bots,t)
    add('shape_helper', shape, shape is not None, False)
    return checks


def ticket_checks(series, sig, market, *, start, end):
    """Measured projections in signals/_shape/plan order; derived fields are explicit.

    Replay the pre-zero-line shape cooldown with the frozen helpers: rejected
    positive-DIF shapes still reserve 13 weeks. Do not infer it from accepted signals.
    """
    N, T, BS = triangle15, triangle15.T, triangle15.BS
    W = BS.periods(series, 'week')
    t, d = sig['t'], sig['day']
    rows = [dict(date=W['date'][i], **{f: W[f][i] for f in ('open', 'high', 'low', 'close')})
            for i in range(len(W['close']) - 1)]
    atr = N._atr(rows)  # Preserve the two frozen call sites, even when values coincide.
    highs = N.pivots([r['high'] for r in rows], 'high')
    hist = [a - b for a, b in zip(W['dif'], W['dea'])]
    last = -99
    for j in range(60, t):
        if not rows[j]['close'] > rows[j]['open'] or j - last < 13 or not (
                hist[j] > 0 and all(hist[k] < 0 for k in range(j - 4, j))):
            continue
        for ln in T.push_lines(rows, highs, j, broken=None):
            bots = T.bottoms_of(rows, ln['pushes'], j + 1)
            if (bots and bots[-1][0] < j and rows[j]['low'] <= bots[-1][1] + 1.5 * atr[j]
                    and T.converging(ln['line'], bots, ln['pushes'][0], j)
                    and N._shape(rows, highs, atr, ln, bots, j)):
                last = j
                break
    p = sig['pushes']
    ln = next((ln for ln in T.push_lines(rows, highs, t, broken=None) if ln['pushes'] == p), None)
    if ln is None:
        raise ValueError('recorded push line cannot be reproduced')
    bots = T.bottoms_of(rows, p, t + 1)
    if not bots or [j for j, _ in bots] != sig['bottoms']:
        raise ValueError('recorded bottoms cannot be reproduced')
    checks = []
    def add(key, value, passed, derived=True):
        checks.append(dict(id=key, value=value, **{'pass': bool(passed)}, derived=derived))
    add('weekly_history', dict(completed_bars=len(rows), minimum=80, signal_index=t), len(rows) >= 80 and 60 <= t < len(rows) - 1)
    add('bullish_week', dict(open=rows[t]['open'], close=rows[t]['close']), rows[t]['close'] > rows[t]['open'])
    add('cooldown', dict(previous_shape_index=last if last != -99 else None, weeks=t-last, minimum=13), t-last >= 13)
    add('golden_cross', dict(histogram=hist[t-4:t+1], minimum_weeks_under=4), hist[t] > 0 and all(x < 0 for x in hist[t-4:t]))
    add('push_line', dict(pushes=p, span=t-p[0], span_range=list(T.P['span']),
                         drop_ratios=[rows[b]['high']/rows[a]['high'] for a,b in zip(p,p[1:])],
                         middle_deviation=abs(rows[p[1]]['high']/ln['line'](p[1])-1),
                         max_close_to_line=max(rows[j]['close']/ln['line'](j) for j in range(p[0]+1,t)),
                         maximum_drop_ratio=T.P['push_drop'],maximum_middle_deviation=T.P['push_fit'],
                         maximum_close_to_line=1.01), True)
    add('bottoms', dict(indices=sig['bottoms'], prices=[v for _,v in bots], count=len(bots)), bool(bots), False)
    add('bottom_before_signal', dict(last_bottom=bots[-1][0], signal=t), bots[-1][0] < t)
    add('near_bottom', dict(low=rows[t]['low'], last_bottom=bots[-1][1], shape_atr=atr[t], max_atr=1.5), rows[t]['low'] <= bots[-1][1]+1.5*atr[t])
    add('converging', dict(anchors=[[W['date'][j],v] for j,v in bots], first_push=p[0], signal=t), T.converging(ln['line'],bots,p[0],t), False)
    checks.extend(shape_evidence(rows, highs, atr, ln, bots, t))
    add('dif_under_zero', W['dif'][t], W['dif'][t]<0)
    add('signal_window', dict(week=sig['week'],start=start,end=end), start<=sig['week']<=end)
    pool=N.POOL
    add('tradable_pool', dict(history_index=d, minimum_history=pool['min_history'],
        price=series.get('raw_close',series['close'])[d], raw_close_available='raw_close' in series,
        minimum_close=pool['min_close'], dollar_volume=series['close'][d]*series['volume'][d],
        minimum_dollar_volume=pool['min_dollar_volume']), N.buytrain.tradable(series,d,pool), True)
    plan=N.plan(series,sig,W['atr'][t])
    add('plan_stop', dict(limit=plan['level'],stop=plan['stop'],bottom_stop=sig['stop'],plan_atr=W['atr'][t],minimum_atr=.5),
        plan['stop']==min(sig['stop'],plan['level']-.5*W['atr'][t]))
    add('plan_geometry', dict(limit=plan['level'],stop=plan['stop'],t1=plan['t1']), 0<plan['stop']<plan['level']<plan['t1'])
    M=BS.periods(series,'month'); m=BS.completed(M,d,len(series['close']))
    add('monthly_macd_veto', dict(veto=N.monthly_veto(series,d), completed_month=M['date'][m] if m>=0 else None,
        dif=M['dif'][m] if m>=0 else None, hist=[M['dif'][j]-M['dea'][j] for j in range(max(0,m-2),m+1)]),
        not N.monthly_veto(series,d),False)
    add('plan_reward_to_risk', dict(rr=plan['rr'],minimum=1.5),plan['rr'] is not None and plan['rr']>=1.5,False)
    add('spy_over_200d', dict(close=market['close'],sma200=market['sma200'],price_as_of=market['price_as_of']), market['spy_over_200d'],False)
    add('breadth_over_half', dict(fraction=market['breadth'],sample_size=market['breadth_sample'],minimum_exclusive=.5),market.get('breadth_over_half'),True)
    return checks, W, plan


def build_ticket(rec, prices, outcomes, *, start, end, example=False, spy=None):
    series=prices[rec['symbol']]
    # Bounds select signal weeks, not indicator warm-up. The input is the same
    # frozen series as the recorder; example inputs are explicitly cut to development data.
    sig=next((s for s in triangle15.signals(series,start=start,end=end) if s['week']==rec['week']),None)
    if sig is None:
        raise ValueError(f"signal cannot be reproduced: {rec['id']}")
    market=market_state(prices,rec['signal_day'],spy=spy)
    if any(market[k] != rec['market'][k] for k in ('spy_over_200d','breadth','ok')):
        raise ValueError(f"market evidence changed: {rec['id']}")
    checks,W,plan=ticket_checks(series,sig,market,start=start,end=end)
    rounded={k:round(v,4) if isinstance(v,float) else v for k,v in plan.items()}
    if rounded != rec['plan']:
        raise ValueError(f"recorded plan changed: {rec['id']}")
    p=rec['plan']; risk=p['level']-p['stop']
    def point(j,field):
        return dict(date=W['date'][j],price=W[field][j])
    until=rec['signal_day']
    for _ in range(triangle15.WAIT):
        until=next_session(until)
    return dict(schema_version=1,id=rec['id'],symbol=rec['symbol'],version=VERSION,dataset=rec['dataset'],
        signal_week=rec['week'],signal_day=rec['signal_day'],example=example,checks=checks,
        pushes=[point(j,'high') for j in sig['pushes']],bottoms=[point(j,'low') for j in sig['bottoms']],
        trend_line=[point(sig['pushes'][j],'high') for j in (0,2)],
        order=dict(limit=p['level'],stop=p['stop'],target=p['level']+3*risk,R=risk,R_multiple=3,
                   valid_until=until,valid_until_basis='regular_NYSE_sessions_estimate',wait_sessions=triangle15.WAIT,
                   max_hold_sessions=130,eligible=p['go'] and rec['market']['ok']),
        weekly=[dict(date=W['date'][j],**{f:W[f][j] for f in ('open','high','low','close','dif','dea')})
                for j in range(max(0,sig['t']-59),sig['t']+1)],
        outcome=ticket_outcome(rec,series,outcomes))


def ticket_payloads(records, outcomes, price_sets, folder, *, start):
    payloads={}
    for rec in sorted(records,key=lambda r:(r['week'],r['id'])):
        if rec.get('version')!=VERSION:
            continue
        name=ticket_name(rec['id']); path=folder/name
        if path.exists():
            ticket=json.loads(path.read_text())
            ticket['outcome']=ticket_outcome(rec,price_sets[rec['dataset']][rec['symbol']],outcomes)
        else:
            ticket=build_ticket(rec,price_sets[rec['dataset']],outcomes,start=start,end=rec['week'],
                                spy=price_sets[UNIVERSE].get('SPY'))
        payloads[name]=ticket
    payloads['tickets/index.json']=[dict(id=t['id'],symbol=t['symbol'],signal_week=t['signal_week'],
                                      status=t['outcome']['status'],R=t['outcome']['R']) for t in payloads.values()]
    return payloads


def preserve_ticket(previous, current):
    """Only outcome can change, including when another publisher created it first."""
    old=json.loads(previous); new=json.loads(current)
    if any(old.get(k)!=new.get(k) for k in ('id','symbol','signal_week','version','dataset','example')):
        raise ValueError('ticket identity changed')
    if old.get('outcome')==new.get('outcome'):
        return previous
    old['outcome']=new['outcome']
    return json_bytes(old)


def json_bytes(payload):
    return (json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()


def validate_ticket_bytes(name, data):
    if len(data)>=TICKET_MAX_BYTES:
        raise ValueError(f'ticket exceeds 60 KB: {name} ({len(data)} bytes)')



def encode(payloads):
    if not set(FILES) <= set(payloads):
        raise ValueError('expected four app files')
    for name in set(payloads) - set(FILES):
        if name != 'tickets/index.json' and name != ticket_name(Path(name).stem):
            raise ValueError(f'unexpected app path: {name}')
    encoded = {}
    for name in payloads:
        data = json_bytes(payloads[name])
        if name.startswith('tickets/') and name != 'tickets/index.json':
            validate_ticket_bytes(name, data)
        validate_asset(f'app/{name}', data)
        if len(data) > MAX_BYTES:
            raise ValueError(f'app file exceeds 2 MB: {name} ({len(data)} bytes)')
        encoded[name] = data
    return encoded


def write(encoded, folder):
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in encoded.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if name.startswith('tickets/') and name != 'tickets/index.json' and path.exists():
            content = preserve_ticket(path.read_bytes(), content)
            validate_ticket_bytes(name, content)
        if path.exists() and path.read_bytes() == content:
            continue
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(content)
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
    payloads = build(sectors=sectors, universe=universe, records=records, outcomes=outcomes,
                 prices_by_dataset=price_sets, facts=facts, as_of=as_of, generated_at=generated_at)
    config_path = root / FORWARD / 'config.json'
    start = json.loads(config_path.read_text())['start'] if config_path.exists() else '2026-10-12'
    payloads.update(ticket_payloads(records, outcomes, price_sets, root / 'public/app', start=start))
    return payloads


def publish(encoded, root=ROOT) -> bool:
    """Commit app projections and tickets with an isolated index; never switch branches.

    Refuse stale forward inputs and non-fast-forward races. This is deliberately
    fail-closed: the next scheduled run can build a new snapshot. Return whether
    a new commit was pushed successfully.
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
    remote_tickets = set()
    if 'tickets/index.json' in encoded:
        remote_tickets = set(git('ls-tree', '-r', '--name-only', parent, '--', 'public/app/tickets').decode().splitlines())
        missing = remote_tickets - {'public/app/' + name for name in encoded}
        if missing:
            raise RuntimeError(f'existing tickets absent from snapshot: {sorted(missing)}')
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, 'GIT_INDEX_FILE': str(Path(tmp) / 'index')}
        git('read-tree', parent, env=env)
        for name, content in encoded.items():
            if name.startswith('tickets/') and name != 'tickets/index.json':
                if json.loads(content).get('example'):
                    raise ValueError('example tickets cannot be published')
                if f'public/app/{name}' in remote_tickets:
                    content = preserve_ticket(git('show', f'{parent}:public/app/{name}'), content)
                validate_ticket_bytes(name, content)
            oid = git('hash-object', '-w', '--stdin', input=content).decode().strip()
            git('update-index', '--add', '--cacheinfo', f'100644,{oid},public/app/{name}', env=env)
        tree = git('write-tree', env=env).decode().strip()
        if tree == git('rev-parse', f'{parent}^{{tree}}').decode().strip():
            return False
        if in_eod_window():
            raise RuntimeError('inside the 23:30-04:30 UTC EOD window')
        commit = git('-c', 'user.name=sage-vista-bot', '-c',
                     'user.email=sage-vista-bot@users.noreply.github.com',
                     'commit-tree', tree, '-p', parent, '-m', 'research: app data [skip ci]').decode().strip()
        if in_eod_window():
            raise RuntimeError('inside the 23:30-04:30 UTC EOD window')
        git('push', 'origin', f'{commit}:refs/heads/main')
        return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--generated-at', help='fixed ISO timestamp for reproducible builds')
    args = parser.parse_args(argv)
    if args.generated_at:
        dt.datetime.fromisoformat(args.generated_at.replace('Z', '+00:00'))
    if args.publish and in_eod_window():
        raise RuntimeError('inside the 23:30-04:30 UTC EOD window')
    payloads = load_build(allow_download=args.publish, generated_at=args.generated_at)
    encoded = encode(payloads)
    for name, payload in payloads.items():
        if name.startswith('tickets/') and name != 'tickets/index.json' and payload['outcome'].get('mismatch'):
            print(f"UNVERIFIED {payload['id']}: {json.dumps(payload['outcome']['mismatch'], sort_keys=True)}")
    if args.publish:
        pushed = publish(encoded)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                output.write(f'pushed={str(pushed).lower()}\n')
    else:
        write(encoded, ROOT / 'work/app-data')
    for name, data in encoded.items():
        print(f'{name}: {len(data)} bytes')


if __name__ == '__main__':
    main()
