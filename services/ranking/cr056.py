"""Sole CR-056 candidate score calculation, shared by snapshots and daily reviews."""
from services.contracts.cr056_policy import WHITE_LIST, SETTINGS as S, WEIGHTS, CAPS, POLICY_VERSION, POLICY_FINGERPRINT, MAPPED_FACTORS
from services.contracts.market_data import canonical_fingerprint
from services.scanner.factor_registry import FACTORS_BY_ID, REGISTRY_VERSION
from dataclasses import asdict

def _metadata(factor_id):
    return MAPPED_FACTORS[factor_id]


def score_candidate(states, permission):
    states = list(states)
    if any(s.get('as_of') != permission.get('as_of') for s in states):
        raise ValueError('factor date does not match permission as_of')
    if not isinstance(permission.get('facts_input_fingerprint'), str) or not permission['facts_input_fingerprint']:
        raise ValueError('permission input fingerprint is required')
    factor_input_fingerprint = canonical_fingerprint(sorted(states, key=lambda s: s['factor_id']))
    registry_fingerprint = canonical_fingerprint({'version': REGISTRY_VERSION, 'mapping': dict(MAPPED_FACTORS),
        'factors': [asdict(FACTORS_BY_ID[fid]) for fid in sorted(FACTORS_BY_ID)]})
    by_id = {s['factor_id']: s for s in states}
    if len(by_id) != len(states):
        raise ValueError('duplicate factor state')
    frame_results, all_groups, active_families = {}, [], set()
    for timeframe, ids in WHITE_LIST.items():
        meta = {fid: _metadata(fid) for fid in ids}
        group_for = {fid: meta[fid]['group'] for fid in ids}
        q, available = {}, {}
        for fid in ids:
            state = by_id.get(fid)
            available[fid] = state is not None and state.get('available') is True
            strength = 0.0
            if available[fid]:
                if meta[fid]['template'] == 'direction.macd_state':
                    strength = float(state.get('value', 0))
                elif state.get('hit') is True:
                    strength = 1.0
                elif state.get('recent_hit') is True and meta[fid]['window'] > 0:
                    age = state.get('bars_since_hit')
                    if isinstance(age, int) and not isinstance(age, bool) and 0 <= age < meta[fid]['window']:
                        strength = S['recent_strength']
            q[fid] = strength
        # Resolve parent constraints independently of registry ordering.
        for _ in range(len(ids)):
            for fid in ids:
                if any((q.get(parent, 0) <= 0 if parent in q else not by_id.get(parent, {}).get('hit')) for parent in meta[fid]['parents']):
                    q[fid] = 0.0
        groups, families = [], {}
        for group in sorted(set(group_for.values())):
            members = [fid for fid in ids if group_for[fid] == group]
            family = meta[members[0]]['family']
            if any(meta[fid]['family'] != family for fid in members):
                raise ValueError('mixed family redundancy group')
            complete = all(available[fid] for fid in members)
            confirmation = min(S['confirmation_cap'], sum(S['child_confirmation'] * q[fid]
                for fid in members if meta[fid]['parents'] and q[fid] > 0))
            value = min(S['story_cap'], max(q[fid] for fid in members) + confirmation) if complete else 0.0
            entry = {'timeframe': timeframe, 'group': group, 'family': family, 'factor_ids': members,
                     'available': complete, 'contribution': value, 'strengths': {fid: q[fid] for fid in members},
                     'missing_factor_ids': [fid for fid in members if not available[fid]]}
            groups.append(entry)
            families[family] = min(S['family_cap'], families.get(family, 0.0) + value)
            if value > 0: active_families.add(family)
        raw = sum(families.values())
        multiplier = permission['checks']['weekly'].get('score_multiplier') if timeframe == 'weekly_completed' else 1.0
        multiplier = 1.0 if multiplier is None else multiplier
        normalized = raw / CAPS[timeframe] * multiplier
        frame_results[timeframe] = {'raw': raw, 'cap': CAPS[timeframe], 'multiplier': multiplier,
            'normalized': normalized, 'weight': WEIGHTS[timeframe], 'families': families, 'groups': groups}
        all_groups.extend(groups)
    coverage = sum(g['available'] for g in all_groups) / len(all_groups)
    diagnostic_score = round(100 * sum(f['normalized'] * f['weight'] for f in frame_results.values()) / sum(WEIGHTS.values()), 4)
    score_status = ('excluded' if permission['permission'] == 'blocked' else 'unavailable') if not permission['eligible'] else (
        'unavailable' if coverage < S['minimum_score_coverage'] else 'scored' if coverage == 1 else 'partial')
    total = diagnostic_score if score_status in {'scored', 'partial'} else None
    result = {'policy_version': POLICY_VERSION, 'policy_fingerprint': POLICY_FINGERPRINT,
        'as_of': permission['as_of'], 'permission': permission['permission'], 'score_status': score_status,
        'facts_input_fingerprint': permission['facts_input_fingerprint'],
        'factor_input_fingerprint': factor_input_fingerprint, 'registry_version': REGISTRY_VERSION,
        'registry_fingerprint': registry_fingerprint,
        'total_score': total, 'diagnostic_score': diagnostic_score, 'coverage': coverage,
        'positive_family_count': len(active_families), 'timeframes': frame_results,
        'high_score_eligible': total is not None and coverage == 1 and total >= S['high_score']
            and len(active_families) >= S['alert_family_minimum'],
        'reason_codes': list(permission['reason_codes'])}
    result['score_fingerprint'] = canonical_fingerprint(result)
    return result
