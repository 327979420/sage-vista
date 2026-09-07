"""Append-only candidate watch review state; does not compute trading signals."""
from services.contracts.cr056_policy import SETTINGS as S
from services.contracts.market_data import canonical_fingerprint


def watch_identity(symbol):
    return 'watch:' + canonical_fingerprint({'instrument_id': 'legacy-observed:' + symbol,
        'model_lineage': 'complex_multifactor', 'scope': 'legacy_comparison'})


def review_watch(*, symbol, as_of, origin, score, previous, reference_sessions):
    watch_id = watch_identity(symbol)
    if previous is not None:
        if previous['watch_id'] != watch_id or previous['as_of'] > as_of:
            raise ValueError('watch identity or chronological order mismatch')
        if previous['origin'] != origin:
            raise ValueError('original nomination must remain frozen')
    score_binding = canonical_fingerprint(score)
    if previous and previous['as_of'] == as_of:
        if previous.get('score_binding') != score_binding:
            raise ValueError('same-day watch content conflict')
        return dict(previous)
    qualified = score['total_score'] is not None
    state = 'qualified' if qualified else 'disqualified' if score['permission'] == 'blocked' else 'data_unavailable'
    previous_state = previous['state'] if previous else None
    restored = state == 'qualified' and previous_state in {'disqualified', 'data_unavailable'}
    dates = sorted(set(reference_sessions))
    high = score['high_score_eligible']
    prior_date = dates[dates.index(as_of)-1] if as_of in dates and dates.index(as_of) > 0 else None
    consecutive = (previous.get('consecutive_high_sessions', 0)
                   if previous and previous['as_of'] == prior_date else 0) + 1 if high else 0
    last_alert = previous.get('last_alert_as_of') if previous else None
    cooled = last_alert is None or (last_alert in dates and as_of in dates and dates.index(as_of)-dates.index(last_alert) >= S['alert_cooldown_sessions'])
    same_day_alert = last_alert == as_of
    alert_due = bool(high and cooled and not same_day_alert)
    # This is an internal website alert fact, not an external notification receipt.
    result = {'watch_id': watch_id, 'symbol': symbol, 'as_of': as_of, 'origin': origin,
        'state': state, 'restored': restored, 'consecutive_high_sessions': consecutive,
        'last_alert_as_of': as_of if alert_due else last_alert,
        'alert_due': alert_due, 'alert_channel': 'website_candidate_only',
        'alert_dedupe_key': f'{watch_id}:{as_of}:website' if alert_due else None,
        'score_fingerprint': score.get('score_fingerprint'), 'score_binding': score_binding,
        'reason_codes': score['reason_codes']}
    result['review_fingerprint'] = canonical_fingerprint(result)
    return result
