"""Existing-opportunity permission; initial selection stays frozen."""
from services.contracts.market_data import canonical_fingerprint

# Tracking policy is separate from frozen selection/scoring policy 3.5.
WATCH_PERMISSION_VERSION = 'cr056-watch-permission-1.1.0'


def assess_watch_permission(permission, tracking):
    """An existing surviving opportunity does not reapply its initial discount.

    All other checks remain authoritative pending their individual review.
    Call only for an existing nomination, never to qualify a new entrant.
    """
    if not tracking or tracking.get('as_of') != permission['as_of']:
        return permission
    if not any(r.get('state') == 'active' for r in tracking.get('records', [])):
        return permission
    check = permission['checks'].get('pullback', {})
    if check.get('reason') != 'no_pullback_60d' or check.get('status') != 'blocked':
        return permission
    checks = {**permission['checks'], 'pullback': {
        'status': 'allowed', 'reason': 'initial_pullback_not_reapplied_to_watch'}}
    status = 'unavailable' if any(c['status'] == 'unavailable' for c in checks.values()) else (
        'blocked' if any(c['status'] == 'blocked' for c in checks.values()) else 'allowed')
    return {**permission, 'checks': checks, 'permission': status, 'eligible': status == 'allowed',
            'reason_codes': [c['reason'] for c in checks.values() if c['status'] != 'allowed'],
            'watch_permission_version': WATCH_PERMISSION_VERSION,
            'watch_tracking_fingerprint': canonical_fingerprint(tracking),
            'initial_permission': permission['permission']}


