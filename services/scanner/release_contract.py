"""Pre-deploy release contract for the generated public bundle.

Runs the production validators on the files the EOD job is about to commit and
deploy. It is the only place live-data invariants are gated; unit tests use a
frozen fixture instead. Content that legitimately varies day to day (a source
late or unavailable, a count below a display threshold) is reported as a
warning in the job summary and never blocks the release.
"""
import argparse
import gzip
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGACY_VIEWS = ('macd_buy_top10', 'macd_sell_top10', 'combined_top10', 'rsi_top10', 'volume_top10')
RAW_BAR_FIELDS = {'open', 'high', 'low', 'close', 'volume'}


def read(root, name):
    return json.loads((root / name).read_bytes())


def experiment_ids(root):
    lines = (root / 'research' / 'experiments.jsonl').read_text().splitlines()
    return {json.loads(line)['experiment_id'] for line in lines if line.strip()}


def has_raw_bars(value):
    if isinstance(value, dict):
        return RAW_BAR_FIELDS <= value.keys() or any(has_raw_bars(v) for v in value.values())
    if isinstance(value, list):
        return any(has_raw_bars(v) for v in value)
    return False


def check_market_assets(root, public, as_of, warnings):
    from services.scanner.daily_shape_public import validate as validate_picker
    from services.scanner.market_cockpit import validate as validate_cockpit
    from services.scanner.market_external import validate as validate_external
    from services.scanner.market_internals_daily import logic_fingerprint, validate_public
    picker = read(public, 'daily-shape-picker.json')
    validate_picker(picker, as_of)
    if not picker['rows']:
        warnings.append('daily-shape-picker: no rows today')
    internals = validate_public(read(public, 'market-internals.json'), as_of)
    if internals['logic_fingerprint'] != logic_fingerprint():
        raise ValueError('market-internals: published history was not built by the current logic')
    state = root / 'data' / 'market' / internals['config']['series_id']
    for snapshot in internals['history']:
        if snapshot != read(state / 'snapshots', f"{snapshot['date']}.json"):
            raise ValueError(f"market-internals: {snapshot['date']} differs from its immutable snapshot")
    if internals['config'] != read(root / 'data' / 'market', 'config-v1.json'):
        raise ValueError('market-internals: config differs from data/market/config-v1.json')
    external = validate_external(read(public, 'market-external.json'), as_of)
    for key, item in external['indicators'].items():
        if item['status'] != 'current':
            warnings.append(f"market-external: {key} is {item['status']} (last observation {item['observation_date']})")
    cockpit = validate_cockpit(read(public, 'market-cockpit.json'), as_of)
    for key, panel in cockpit['panels'].items():
        if panel.get('status') not in ('available', None):
            warnings.append(f"market-cockpit: {key} panel is {panel['status']}")


def check_candidate_checkpoint(root, public, as_of):
    from services.ledger.cr056 import validate_watch_checkpoint
    checkpoint = validate_watch_checkpoint(json.loads(gzip.decompress((root / 'automation' / 'cr056-watch-state.json.gz').read_bytes())))
    ranking = read(public, 'cr056-ranking.json')
    if checkpoint['as_of'] != ranking['as_of'] or ranking['as_of'] != as_of:
        raise ValueError('cr056: committed checkpoint and ranking dates differ')
    if checkpoint['snapshot_fingerprint'] != ranking['source_snapshot']:
        raise ValueError('cr056: committed checkpoint is not the reviewed ranking snapshot')
    if has_raw_bars(checkpoint):
        raise ValueError('cr056: committed checkpoint contains raw OHLCV bars')


def check_release_manifest(root, public, as_of):
    from services.contracts import build_shadow_manifest, verify_shadow_manifest
    from services.contracts.manifest import FROZEN_RELEASE_NAMES
    known = experiment_ids(root)
    manifest = build_shadow_manifest([public / name for name in FROZEN_RELEASE_NAMES],
                                     generated_at='2000-01-01T00:00:00Z', known_experiment_ids=known)
    verify_shadow_manifest(manifest, public, known_experiment_ids=known)
    if manifest['as_of'] != as_of:
        raise ValueError(f"release manifest date {manifest['as_of']} != {as_of}")


def check_tracker_and_status(public, as_of, warnings):
    tracker = read(public, 'resonance-tracker.json')
    radar = read(public, 'rare-opportunity-radar.json')
    status = read(public, 'update-status.json')
    for key in LEGACY_VIEWS:
        if not isinstance(tracker.get(key), list):
            raise ValueError(f'resonance-tracker: legacy view {key} missing')
    audit = tracker['consistency_audit']
    if audit['details_cover_all_published'] is not True or audit['duplicate_symbols'] or audit['completed_higher_timeframes_only'] is not True:
        raise ValueError('resonance-tracker: consistency audit failed')
    if tracker['as_of'] != as_of or radar['as_of'] != as_of or radar['scan']['future_data_used'] is not False:
        raise ValueError('tracker/radar date or future-data audit failed')
    if (status['status'] != 'up_to_date' or status['data_dates_match'] is not True or status['future_data_used'] is not False
            or {status['source_latest_complete_date'], status['tracker_as_of'], status['radar_as_of']} != {as_of}):
        raise ValueError('update-status does not prove a same-day release')
    industry = read(public, 'industry-radar.json')
    semi = next(t for t in industry['themes'] if t['theme_id'] == 'semiconductors')
    if semi['valid_member_count'] < 5 and semi['state'] != 'Unavailable':
        raise ValueError('industry-radar: semiconductors scored with fewer than 5 valid members')
    if semi['source_status'] != 'available' or semi['member_count'] < 5:
        warnings.append(f"industry-radar: semiconductors membership {semi['source_status']} ({semi['member_count']} members)")
    funds = industry.get('display_context', {}).get('funds', {})
    missing = sorted(k for k, v in funds.items() if not v.get('available'))
    if missing:
        warnings.append(f"industry-radar: ETF context unavailable for {', '.join(missing)}")


def check_release(as_of, root=ROOT, public=None):
    """Return (errors, warnings); errors must block the release."""
    public = public or root / 'public'
    errors, warnings = [], []
    checks = (
        ('market assets', lambda: check_market_assets(root, public, as_of, warnings)),
        ('candidate checkpoint', lambda: check_candidate_checkpoint(root, public, as_of)),
        ('release manifest', lambda: check_release_manifest(root, public, as_of)),
        ('tracker and status', lambda: check_tracker_and_status(public, as_of, warnings)),
    )
    for label, check in checks:
        try:
            check()
        except Exception as error:  # report every failed contract, not only the first
            errors.append(f'{label}: {type(error).__name__}: {error}')
    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', required=True)
    args = parser.parse_args()
    errors, warnings = check_release(args.as_of)
    lines = [f'Release contract for {args.as_of}: ' + ('FAILED' if errors else 'passed')]
    lines += [f'ERROR: {e}' for e in errors] + [f'WARNING: {w}' for w in warnings]
    print('\n'.join(lines))
    for warning in warnings:
        print(f'::warning title=EOD data::{warning}')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write('\n### Release contract\n\n' + '\n'.join(f'- {line}' for line in lines) + '\n')
    raise SystemExit(1 if errors else 0)


if __name__ == '__main__':
    main()
