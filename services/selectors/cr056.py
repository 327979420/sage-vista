"""Single CR-056 direction/background permission calculation; no scores here."""
from services.contracts.cr056_policy import SETTINGS as S, POLICY_VERSION, POLICY_FINGERPRINT


def _negative_improvement(h, confirmations):
    tail = h[-(confirmations + 1):]
    return len(tail) == confirmations + 1 and tail[-1] < 0 and all(
        previous < current for previous, current in zip(tail, tail[1:]))


def direction_permission(h, *, timeframe):
    if timeframe not in ('monthly', 'weekly'):
        raise ValueError('unknown permission timeframe')
    confirmations = S[timeframe + '_negative_improvements']
    if len(h) < max(confirmations + 1, S['weekly_positive_peak_window'] if timeframe == 'weekly' else 2):
        return {'status': 'unavailable', 'reason': 'insufficient_histogram', 'score_multiplier': None}
    current, previous = h[-1], h[-2]
    if _negative_improvement(h, confirmations):
        return {'status': 'allowed', 'reason': 'negative_histogram_improving', 'score_multiplier': 1.0}
    if current > 0 and current >= previous:
        return {'status': 'allowed', 'reason': 'positive_histogram_supported', 'score_multiplier': 1.0}
    if timeframe == 'weekly' and 0 < current < previous:
        peak = max([v for v in h[-S['weekly_positive_peak_window']:] if v > 0])
        if current > S['weekly_near_cross_fraction'] * peak:
            return {'status': 'allowed', 'reason': 'positive_histogram_shrinking',
                    'score_multiplier': S['weekly_shrinking_multiplier']}
        reason = 'weekly_near_bear_cross'
    else:
        reason = timeframe + '_not_confirmed'
    return {'status': 'blocked', 'reason': reason, 'score_multiplier': None}


def assess_permission(facts):
    """Consume objective M04 facts; never recalculate MACD, EMA or pivots."""
    checks = {}
    def record(name, status, reason):
        checks[name] = {'status': status, 'reason': reason}
    if facts['daily_rows'] < S['minimum_daily_rows']:
        record('history', 'unavailable', 'daily_history_below_420')
    if facts['monthly']['completed_count'] < S['minimum_completed_months']:
        record('monthly_history', 'unavailable', 'completed_months_below_61')
    checks['monthly'] = direction_permission(facts['monthly']['histogram'], timeframe='monthly')
    checks['weekly'] = direction_permission(facts['weekly']['histogram'], timeframe='weekly')
    c = facts['close']
    history_high = facts['observed_history_high']
    if history_high is None:
        record('history_high', 'unavailable', 'history_high_missing')
    else:
        near = c >= S['near_history_high_fraction'] * history_high
        record('history_high', 'blocked' if near else 'allowed',
               'near_observed_history_high' if near else 'below_observed_high_proves_below_all_time_high')
    high = facts['monthly_high_zone']
    if high is None:
        record('monthly_high_zone', 'unavailable', 'monthly_high_window_missing')
    else:
        extension = c/high['ema20']-1 > S['monthly_ema_extension']
        indicator_high = (high['latest_line'] > 0 and high['normalized_line'] >= high['line_p90']) or (
            high['latest_histogram'] > 0 and high['normalized_histogram'] >= high['histogram_p90'])
        record('monthly_high_zone', 'blocked' if extension or indicator_high else 'allowed',
               'monthly_high_zone' if extension or indicator_high else 'monthly_high_zone_clear')
    prior_high = facts['prior_60_high']
    pullback = prior_high is not None and c <= S['pullback_fraction'] * prior_high
    record('pullback', 'allowed' if pullback else 'blocked', 'pullback_60d' if pullback else 'no_pullback_60d')
    local = facts['local_structure']
    if local.get('status') != 'observed':
        record('structure', 'unavailable', 'local_structure_unavailable')
    else:
        broken = local['classification'] == 'structure_broken'
        record('structure', 'blocked' if broken else 'allowed', local['classification'])
    base = facts['base']
    base_passed = False
    if base is not None:
        touches = base['touch_indices']
        base_passed = ((base['prior_peak']-base['low'])/base['prior_peak'] >= S['base_prior_drawdown']
            and (base['high']-base['low'])/base['low'] <= S['base_max_width']
            and any(b-a >= S['base_touch_gap'] for a in touches for b in touches)
            and base['last_half_low'] >= S['base_min_low_ratio']*base['first_half_low']
            and c >= base['median_close'])
    backgrounds = {'uptrend_pullback': bool(facts['legacy_long_trend']),
                   'long_base_pullback': base_passed if base is not None else None}
    primary = 'uptrend_pullback' if backgrounds['uptrend_pullback'] else 'long_base_pullback' if base_passed else None
    record('background', 'allowed' if primary else 'unavailable' if base is None else 'blocked',
           primary or 'no_available_background')
    status = 'unavailable' if any(x['status'] == 'unavailable' for x in checks.values()) else (
        'blocked' if any(x['status'] == 'blocked' for x in checks.values()) else 'allowed')
    return {'as_of': facts['as_of'], 'permission': status, 'eligible': status == 'allowed',
            'checks': checks, 'backgrounds': backgrounds, 'primary_background': primary,
            'reason_codes': [x['reason'] for x in checks.values() if x['status'] != 'allowed'],
            'policy_version': POLICY_VERSION, 'policy_fingerprint': POLICY_FINGERPRINT,
            'facts_input_fingerprint': facts['input_fingerprint']}


def assess_entry(facts):
    """Single alternative-ticket decision. No scores or cross-period mixing."""
    paths = []
    for timeframe, frame in facts['frames'].items():
        if not frame['available']: continue
        for name, hit in (('bottom_macd', len(frame['bottoms']) >= 2 and frame['macd_valid']),
                          ('three_push_breakout', len(frame['bottoms']) >= 2 and frame['breakout']),
                          ('support_reversal', frame['support_reversal'])):
            if hit:
                paths.append({'path':name,'timeframe':timeframe,
                              'confirmed_through':frame['completed_through'],
                              'cross_date':frame.get('cross_date') if name=='bottom_macd' else None})
    return {'as_of':facts['as_of'],'eligible':bool(paths),'paths':paths,
            'reason_codes':[] if paths else ['no_confirmed_reversal_entry'],
            'policy_version':POLICY_VERSION,'policy_fingerprint':POLICY_FINGERPRINT,
            'evidence':facts['frames']}
