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
