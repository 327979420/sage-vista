"""Append-only candidate watch review state; does not compute trading signals."""
from services.contracts.cr056_policy import SETTINGS as S
from services.contracts.market_data import canonical_fingerprint


def watch_identity(symbol):
    return 'watch:' + canonical_fingerprint({'instrument_id': 'legacy-observed:' + symbol,
        'model_lineage': 'complex_multifactor', 'scope': 'legacy_comparison'})


def review_watch(*, symbol, as_of, origin, score, previous, reference_sessions, policy_revision=False, entry_tracking=None):
    watch_id = watch_identity(symbol)
    if previous is not None:
        if previous['watch_id'] != watch_id or previous['as_of'] > as_of:
            raise ValueError('watch identity or chronological order mismatch')
        if previous['origin'] != origin:
            raise ValueError('original nomination must remain frozen')
    score_binding = canonical_fingerprint(score)
    entry_binding = canonical_fingerprint(entry_tracking) if entry_tracking is not None else None
    if previous and previous['as_of'] == as_of and not policy_revision:
        if previous.get('score_binding') != score_binding or previous.get('entry_binding') != entry_binding:
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
    if policy_revision and previous and previous['as_of'] == as_of:
        consecutive = previous.get('consecutive_high_sessions', 0) if high else 0
    last_alert = previous.get('last_alert_as_of') if previous else None
    cooled = last_alert is None or (last_alert in dates and as_of in dates and dates.index(as_of)-dates.index(last_alert) >= S['alert_cooldown_sessions'])
    same_day_alert = last_alert == as_of
    alert_due = bool(high and cooled and not same_day_alert and not policy_revision)
    # This is an internal website alert fact, not an external notification receipt.
    result = {'watch_id': watch_id, 'symbol': symbol, 'as_of': as_of, 'origin': origin,
        'state': state, 'restored': restored, 'consecutive_high_sessions': consecutive,
        'last_alert_as_of': as_of if alert_due else last_alert,
        'alert_due': alert_due, 'alert_channel': 'website_candidate_only',
        'alert_dedupe_key': f'{watch_id}:{as_of}:website' if alert_due else None,
        'score_fingerprint': score.get('score_fingerprint'), 'score_binding': score_binding,
        'reason_codes': score['reason_codes']}
    if entry_tracking is not None:
        result['entry_tracking'] = entry_tracking
        result['entry_binding'] = entry_binding
    if policy_revision and previous:
        result['supersedes_review_fingerprint'] = previous['review_fingerprint']
    result['review_fingerprint'] = canonical_fingerprint(result)
    return result


def watch_checkpoint(report):
    """Persist only frozen origins and latest watch state, not full factor arrays."""
    checkpoint = {k: report[k] for k in ('as_of', 'result_role', 'snapshot_fingerprint')}
    checkpoint['reviews'] = [{'symbol': r['symbol'], 'watch': r['watch']}
                             for r in report['reviews'] if r.get('watch')]
    checkpoint['checkpoint_fingerprint'] = canonical_fingerprint(checkpoint)
    return checkpoint


def validate_watch_checkpoint(checkpoint):
    body = {k: v for k, v in checkpoint.items() if k != 'checkpoint_fingerprint'}
    if canonical_fingerprint(body) != checkpoint.get('checkpoint_fingerprint'):
        raise ValueError('watch_checkpoint_content_mismatch')
    if checkpoint.get('result_role') != 'legacy_comparison':
        raise ValueError('watch_checkpoint_role_mismatch')
    seen = set()
    for row in checkpoint['reviews']:
        watch = row['watch']; symbol = row['symbol']
        if symbol in seen or watch['watch_id'] != watch_identity(symbol) or watch['as_of'] != checkpoint['as_of']:
            raise ValueError('watch_checkpoint_identity_mismatch')
        body = {k: v for k, v in watch.items() if k != 'review_fingerprint'}
        if canonical_fingerprint(body) != watch.get('review_fingerprint'):
            raise ValueError('watch_review_content_mismatch')
        seen.add(symbol)
    return checkpoint


def track_entry_structures(rows, *, as_of, previous=None, start_date=None):
    """Reconstruct or increment the existing watch ledger using the shared gate.

    Price observations are not filled trades. Invalidated episodes stay in the
    record; a price rebound cannot resurrect an old structure identity.
    """
    import copy
    from services.contracts.cr056_policy import POLICY_VERSION, POLICY_FINGERPRINT
    from services.factors.cr056 import collect_entry_facts
    from services.selectors.cr056 import assess_entry
    from services.gates.baseline import MIN_HISTORY_SESSIONS, MIN_CLOSE, MIN_DOLLAR_VOLUME
    if not rows or rows[-1]['date'] != as_of:
        raise ValueError('watch_tracking_date_mismatch')
    index = {r['date']:i for i,r in enumerate(rows)}
    cutoff = index.get(previous.get('as_of')) if previous else None
    compatible = (previous is not None and cutoff is not None
                  and previous.get('policy_fingerprint') == POLICY_FINGERPRINT
                  and previous.get('source_fingerprint') == canonical_fingerprint(list(rows[:cutoff+1])))
    records = copy.deepcopy(previous['records']) if compatible else []
    first = cutoff+1 if compatible else MIN_HISTORY_SESSIONS-1
    if start_date and not compatible:
        first = max(first, next((i for i,r in enumerate(rows) if r['date']>=start_date),len(rows)))
    for i in range(first,len(rows)):
        day = rows[i]['date']
        facts = collect_entry_facts(rows[:i+1],as_of=day,complete_session=True)
        for record in records:
            frame = facts['frames'][record['timeframe']]
            if (record['state']=='active' and frame['completed_through']
                    and frame['completed_through'] > record['confirmed_through']
                    and frame['close'] < record['structure_floor']):
                record.update(state='invalidated',invalidated_at=day,
                              invalidation_bar=frame['completed_through'])
        if rows[i]['close'] < MIN_CLOSE or rows[i]['close']*rows[i]['volume'] < MIN_DOLLAR_VOLUME:
            continue
        known = {r['structure_key'] for r in records}
        for path in assess_entry(facts)['paths']:
            if path['structure_key'] in known or path['structure_floor'] is None: continue
            records.append({**path,'trigger_date':day,'trigger_close':rows[i]['close'],
                            'state':'active','invalidated_at':None,'policy_version':POLICY_VERSION})
    for record in records:
        record['observation_return'] = rows[-1]['close']/record['trigger_close']-1
        record['observed_sessions'] = len(rows)-1-index[record['trigger_date']]
    return {'as_of':as_of,'policy_version':POLICY_VERSION,'policy_fingerprint':POLICY_FINGERPRINT,
            'source_fingerprint':canonical_fingerprint(list(rows)),
            'history_start':previous['history_start'] if compatible else rows[first]['date'] if first<len(rows) else as_of,
            'reconstructed':previous.get('reconstructed',False) if compatible else start_date is None,'records':records,
            'eligible':any(r['state']=='active' for r in records),
            'return_basis':'adjusted_close_price_change_not_trade_return'}
