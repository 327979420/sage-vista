"""Read-only context tags; never a 3W trade rule.

Inputs are chronological completed daily OHLCV mappings, ``end`` is an inclusive
zero-based index. Entry tags use canonical current ``hit``, not recent-only
memory. Dates are the start of the current uninterrupted observable episode;
latest_event_date separately preserves canonical event occurrence dates. A left-censored episode
has date=None and first_observed_date. Availability is explicit, never a miss.
"""
from bisect import bisect_right
from datetime import date
import json
from pathlib import Path

from services.scanner import factor_detectors as detectors
from services.scanner.factor_registry import FACTORS_BY_ID, REGISTRY_VERSION
from services.scanner.macd_factor_backtest import (
    completed_groups, ema, long_trend_ok, overhead_unfilled_gap,
)
from services.scanner.technical import macd, rsi
from services.gates.long_term_state import period_closed_at_session

REGISTRY_PATH = Path(__file__).resolve().parents[2] / 'public/factor-registry.json'
RISK_LABELS = {
    'macd.weekly_bear_cross': '完整周线MACD死叉',
    'macd.monthly_high_bear_setup': '月线零轴上柱连续两根下降',
    'rsi.overbought': '日线RSI14超买',
    'rsi.bearish_divergence': 'RSI顶背离',
    'structure.weekly_bearish_engulfing': '完整周线看跌吞没',
    'trend.below_ema200': '日线收盘低于EMA200',
    'risk.overhead_unfilled_gap': '上方未补跳空缺口',
}
RSI_UNAVAILABLE = ('原底背离内嵌于_raw，含close <= pivot*1.15价格比例限制；'
                   '直接负价格镜像不对称，独立重写会引入新定义。')


def factor_availability(factor_ids=None):
    """Code-path availability, distinct from enough data at a particular end."""
    registry = json.loads(REGISTRY_PATH.read_text())
    if registry['registry_version'] != REGISTRY_VERSION:
        raise ValueError('registry version mismatch')
    factors = {f['id']: f for f in registry['factors']}
    if set(factors) != set(FACTORS_BY_ID):
        raise ValueError('registry identities mismatch')
    result = []
    for fid in factors if factor_ids is None else factor_ids:
        f = factors.get(fid)
        available = bool(f and f['runtime_status'] == 'ready')
        result.append(dict(id=fid, label_zh=f['name_zh'] if f else fid,
                           available=available,
                           reason='implemented' if available else
                           'definition_required' if f else 'unknown_factor'))
    return result


def risk_availability():
    return [dict(id=fid, label_zh=label, available=fid != 'rsi.bearish_divergence',
                 reason=RSI_UNAVAILABLE if fid == 'rsi.bearish_divergence' else 'implemented')
            for fid, label in RISK_LABELS.items()]


def _prefix(rows, end):
    if not isinstance(end, int) or end < 0 or end >= len(rows):
        raise ValueError('end must index an existing completed daily bar')
    view = [dict(r) for r in rows[:end + 1]]
    if any(a['date'] >= b['date'] for a, b in zip(view, view[1:])):
        raise ValueError('daily bars must have unique ascending dates')
    return view


def mirror_bars(rows):
    """Exact sign reflection for price-order-only rules, with high/low swapped."""
    return [dict(r, open=-r['open'], high=-r['low'], low=-r['high'], close=-r['close'])
            for r in rows]


def bearish_engulfing(bars):
    return detectors.higher_timeframe_bullish_engulfing(mirror_bars(bars), 'weekly_completed')[0]


def _tag(fid, label, direction, onset, first, as_of):
    return dict(id=fid, label_zh=label, direction=direction, date=onset,
                first_observed_date=first, left_censored=onset is None, as_of=as_of)


def entry_audit(rows, end):
    """Return triggered tags plus every unavailable factor (including short history)."""
    view = _prefix(rows, end)
    as_of = view[-1]['date']
    states = detectors.evaluate_all_factors(view, as_of, complete_session=True)
    availability = {x['id']: x for x in factor_availability()}
    tags, unavailable, raw_cache = [], [], {}
    long_average = ema([r['close'] for r in view], 200)

    def hit_at(fid, i):
        if i < 259:
            return None  # canonical snapshot's 260-bar availability floor
        if fid == 'qualification.long_trend':
            return long_trend_ok(view, i, long_average)
        if i not in raw_cache:
            raw_cache[i] = detectors._raw(view, i, complete_session=True)
        hit, evidence = raw_cache[i][fid]
        return bool(hit) if evidence.get('detector_available', True) else None

    for state in states:
        fid = state.factor_id
        if not state.available:
            unavailable.append(dict(id=fid, label_zh=availability[fid]['label_zh'],
                                    reason=state.evidence.get('reason', state.runtime_status)))
            continue
        if not state.hit:
            continue
        i = end
        while i > 0 and hit_at(fid, i - 1) is True:
            i -= 1
        first = view[i]['date']
        onset = first if i > 0 and hit_at(fid, i - 1) is False else None
        tag = _tag(fid, availability[fid]['label_zh'],
                   '利空' if fid.startswith('risk.') else '利好', onset, first, as_of)
        if state.factor_type == 'event':
            tag['latest_event_date'] = state.latest_hit_date
        tags.append(tag)
    return dict(tags=tags, unavailable=unavailable, as_of=as_of)


def entry_tags(rows, end):
    return entry_audit(rows, end)['tags']


def risk_timeline(rows, end):
    """All observable daily risk states through end, sharing prefix-safe indicators.

    No future group is selectable. Holiday period ends are conservative: when the
    existing calendar helper cannot prove closure, confirmation waits until the
    next period. Dates are knowledge dates, not backdated pivot/period dates.
    """
    view = _prefix(rows, end)
    closes = [r['close'] for r in view]
    rv, average = rsi(closes, 14), ema(closes, 200)
    periods = {}
    for period in ('weekly', 'monthly'):
        groups = completed_groups(view, period)
        keys = [key for key, _ in groups]
        bars = [bar for _, bar in groups]
        line, signal = macd([r['close'] for r in bars])
        periods[period] = (keys, bars, line, signal)
    active, first_seen, output = {}, {}, []
    for i, row in enumerate(view):
        day = date.fromisoformat(row['date'])
        selected = {}
        for period, (keys, bars, line, signal) in periods.items():
            key = (day.isocalendar().year, day.isocalendar().week) if period == 'weekly' else (day.year, day.month)
            j = bisect_right(keys, key) - 1
            if not period_closed_at_session(row['date'], period, complete_session=True):
                j -= 1
            selected[period] = (j, bars, line, signal)
        w, wb, wl, ws = selected['weekly']
        m, mb, ml, ms = selected['monthly']
        hist = [ml[k] - ms[k] for k in range(m - 2, m + 1)] if m >= 2 else []
        states = {
            'macd.weekly_bear_cross': None if w < 1 else wl[w] < ws[w] and wl[w-1] >= ws[w-1],
            'macd.monthly_high_bear_setup': None if m < 2 else ml[m] > 0 and hist[2] < hist[1] < hist[0],
            'rsi.overbought': None if rv[i] is None else rv[i] > 70,
            'structure.weekly_bearish_engulfing': None if w < 1 else bearish_engulfing(wb[w-1:w+1]),
            'trend.below_ema200': None if i < 199 else closes[i] < average[i],
            'risk.overhead_unfilled_gap': None if i < 1 else overhead_unfilled_gap(view, i),
        }
        tags = []
        for fid, hit in states.items():
            previous = active.get(fid)
            if hit is True:
                if previous is not True:
                    first_seen[fid] = (row['date'] if previous is False else None, row['date'])
                onset, first = first_seen[fid]
                tags.append(_tag(fid, RISK_LABELS[fid], '利空', onset, first, row['date']))
            active[fid] = hit
        output.append(dict(date=row['date'], tags=tags,
                           unavailable=[fid for fid, hit in states.items() if hit is None] + ['rsi.bearish_divergence']))
    return output


def risk_tags(rows, end):
    return risk_timeline(rows, end)[-1]['tags']


def first_new_warnings(timeline, entry_date, exit_date):
    """Strictly after entry day and before exit day; reactivation is a new episode."""
    warnings = {}
    for observation in timeline:
        if not entry_date < observation['date'] < exit_date:
            continue
        for tag in observation['tags']:
            if tag['date'] is not None and tag['date'] > entry_date:
                day = date.fromisoformat(tag['date'])
                iso = day.isocalendar()
                warnings.setdefault(tag['id'], dict(tag, first_week=f'{iso.year}-W{iso.week:02d}'))
    return warnings
