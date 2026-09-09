"""CR-056 objective facts, sharing M02 validation and the existing pure indicators."""
from math import ceil
from statistics import median
from services.contracts.cr056_policy import SETTINGS as S
from services.contracts.market_data import canonical_fingerprint
from services.market_data.normalization import validate_adjusted_rows
from services.gates.baseline import legacy_long_trend_equivalence
from services.gates.local_structure import assess_local_structure
from services.gates.long_term_state import completed_period_bars
from services.scanner.technical import macd
from services.scanner.macd_factor_backtest import ema


def _period_facts(bars):
    closes = [r['close'] for r in bars]
    line, signal = macd(closes)
    return {'completed_count': len(bars), 'completed_through': bars[-1]['date'] if bars else None,
            'histogram': [a-b for a,b in zip(line, signal)], 'macd_line': line,
            'closes': closes}


def collect_direction_facts(rows, *, as_of, complete_session=False):
    """Return immutable-input facts, never a score or a trading permission."""
    rows = validate_adjusted_rows(rows)
    if not rows or rows[-1]['date'] != as_of or any(r['date'] > as_of for r in rows):
        raise ValueError('CR056 requires a complete point-in-time read ending at as_of')
    monthly = completed_period_bars(rows, as_of=as_of, period='monthly', complete_session=complete_session)
    weekly = completed_period_bars(rows, as_of=as_of, period='weekly', complete_session=complete_session)
    result = {'as_of': as_of, 'input_fingerprint': canonical_fingerprint(list(rows)),
              'daily_rows': len(rows), 'monthly': _period_facts(monthly),
              'weekly': _period_facts(weekly), 'local_structure': assess_local_structure(rows),
              'legacy_long_trend': legacy_long_trend_equivalence(rows), 'close': rows[-1]['close']}
    c = result['close']
    result['observed_history_high'] = max((r['high'] for r in rows[:-1]), default=None)
    result['prior_60_high'] = max((r['high'] for r in rows[-S['pullback_window']-1:-1]), default=None)
    if len(monthly) >= S['minimum_completed_months']:
        facts = result['monthly']
        a = [abs(v)/price for v,price in zip(facts['macd_line'], facts['closes'])]
        b = [abs(v)/price for v,price in zip(facts['histogram'], facts['closes'])]
        def percentile(values):
            history = sorted(values[-S['monthly_percentile_history']-1:-1])
            return history[ceil(S['high_percentile'] * len(history))-1]
        result['monthly_high_zone'] = {
            'ema20': ema(facts['closes'], 20)[-1], 'normalized_line': a[-1],
            'normalized_histogram': b[-1], 'line_p90': percentile(a), 'histogram_p90': percentile(b),
            'latest_line': facts['macd_line'][-1], 'latest_histogram': facts['histogram'][-1]}
    else:
        result['monthly_high_zone'] = None
    n = S['base_months']
    if len(monthly) >= n + S['prior_base_months'] + 1:
        base = monthly[-n-1:-1]
        prior = monthly[-n-S['prior_base_months']-1:-n-1]
        low, high = min(r['low'] for r in base), max(r['high'] for r in base)
        touch = [i for i,r in enumerate(base) if r['low'] <= low*(1+S['base_touch_tolerance'])]
        result['base'] = {'low': low, 'high': high,
            'prior_peak': max(r['high'] for r in prior), 'touch_indices': touch,
            'first_half_low': min(r['low'] for r in base[:n//2]),
            'last_half_low': min(r['low'] for r in base[n//2:]),
            'median_close': median(r['close'] for r in base),
            'start': base[0]['date'], 'end': base[-1]['date']}
    else:
        result['base'] = None
    return result


def collect_entry_facts(rows, *, as_of, complete_session=False):
    """Completed native-period structure facts, also used by the replay prefilter."""
    from services.contracts.cr056_policy import ENTRY_SETTINGS
    from services.scanner.detectors import pivots, _retest_candle
    from services.scanner.macd_factor_backtest import three_push_breakout_setup
    from services.scanner.technical import atr, macd_bull_cross_at
    rows = validate_adjusted_rows(rows)
    if not rows or rows[-1]['date'] != as_of:
        raise ValueError('entry facts require rows ending at as_of')
    periods = {'daily': rows}
    for tf, period in (('weekly_completed', 'weekly'), ('monthly_completed', 'monthly')):
        periods[tf] = completed_period_bars(rows, as_of=as_of, period=period, complete_session=complete_session)
    cfg = ENTRY_SETTINGS; limits = cfg['triple_bottom']
    frames = {}
    for tf, all_bars in periods.items():
        bars = all_bars[-limits['lookback_bars']-1:]
        end = len(bars)-1
        frame = {'completed_through': bars[-1]['date'] if bars else None,
                 'available': len(bars) >= 5, 'bottoms': [], 'support_reversal': False,
                 'breakout': False, 'macd_valid': False, 'cross_date': None}
        frames[tf] = frame
        if not frame['available']: continue
        a = atr(bars); points = pivots(bars, end, cfg)['lows']
        def pair_valid(first, second):
            gap = second['index']-first['index']
            tolerance = max(first['price']*limits['max_low_spread_pct'], a[second['index']]*limits['max_low_spread_atr'])
            peak = max((b['high'] for b in bars[first['index']+1:second['index']]), default=0)
            return (limits['min_separation_bars'] <= gap <= limits['max_separation_bars']
                    and abs(second['price']-first['price']) <= tolerance
                    and peak-max(first['price'], second['price']) >= limits['min_intervening_bounce_atr']*a[second['index']]
                    and min(b['close'] for b in bars[second['index']:]) >= min(first['price'], second['price']))
        pair = points[-2:] if len(points) >= 2 and pair_valid(*points[-2:]) else []
        frame['bottoms'] = [{'date': bars[p['index']]['date'], 'price': p['price'],
                             'confirmed_at': bars[p['confirmed_index']]['date']} for p in pair]
        line, signal = macd([b['close'] for b in all_bars])
        crosses = [i for i in range(1,len(all_bars)) if macd_bull_cross_at(line,signal,i)]
        last = crosses[-1] if crosses else None
        frame['cross_date'] = all_bars[last]['date'] if last is not None else None
        frame['cross_age_bars'] = len(all_bars)-1-last if last is not None else None
        frame['cross_below_zero'] = bool(last is not None and line[last] < 0 and signal[last] < 0)
        frame['macd_valid'] = bool(pair and last is not None and line[-1] > signal[-1]
                                  and frame['cross_date'] >= frame['bottoms'][0]['date'])
        setup = three_push_breakout_setup(bars,end) if pair else None
        if setup:
            frame['breakout'] = bars[-2]['close'] <= setup['level']-setup['slope']
            frame['trendline'] = setup
        # A present reversal can confirm a retest without future pivot bars.
        prior = [p for p in points if p['confirmed_index'] < end]
        if prior:
            first = prior[-1]; current = {'index':end,'price':bars[-1]['low']}
            reversal, evidence = _retest_candle(bars,end,first['price'],cfg)
            proximity = cfg['retest']['proximity_atr']*a[-1]
            touched = bars[-1]['low'] <= first['price']+proximity and bars[-1]['high'] >= first['price']-proximity
            frame['support_reversal'] = bool(pair_valid(first,current) and touched and reversal
                                              and bars[-1]['close'] >= first['price'])
            frame['support'] = {'date':bars[first['index']]['date'],'price':first['price'],
                                'confirmed_at':bars[first['confirmed_index']]['date'],'signals':evidence}
    return {'as_of':as_of,'frames':frames}
