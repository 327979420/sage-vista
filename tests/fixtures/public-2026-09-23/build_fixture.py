"""Rebuild this frozen fixture from a real, verified public/ release.

Usage (repo root): PYTHONPATH=. python3 tests/fixtures/public-2026-09-23/build_fixture.py
Only list lengths and ticker-keyed maps are trimmed; every kept record is the
real published record; sealed assets are stored unmodified as .json.gz.
Unit tests read this directory, never the moving public/ output.
"""
import gzip
import json
from pathlib import Path

from services.contracts.manifest import FROZEN_RELEASE_NAMES

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'public'
OUT = Path(__file__).resolve().parent


def load(name):
    return json.loads((SOURCE / name).read_bytes())


def head(mapping, n=5):
    return {k: mapping[k] for k in list(mapping)[:n]}


def kept_cases():
    cases = load('signal-history.json')['cases']
    events = {(e.get('symbol'), e.get('signal_date')): e.get('event_id') for e in load('opportunity-ledger.json')['events']}
    shared = [c for c in cases if events.get((c['symbol'], c['first_seen_date']), c['signal_id']) != c['signal_id']]
    return shared[:3] + [c for c in cases[:6] if c not in shared[:3]][:3]


def trim(name, p):
    if name == 'daily-factor-snapshot.json':
        p['symbols'] = p['symbols'][:3]
    elif name == 'favorite-pattern.json':
        for key in ('entry_ready_candidates', 'near_matches', 'reference_cases'):
            p[key] = p[key][:1]
    elif name == 'industry-radar.json':
        p['ticker_context'] = head(p['ticker_context'])
        p['classification_by_ticker'] = head(p['classification_by_ticker'])
        p['membership_overlap'] = p['membership_overlap'][:5]
        for key, value in p['price_data_audit'].items():
            if isinstance(value, list):
                p['price_data_audit'][key] = value[:5]
        context = p.get('display_context', {})
        for key in ('ticker_themes', 'classifications'):
            if isinstance(context.get(key), dict):
                context[key] = head(context[key])
    elif name == 'opportunity-ledger.json':
        # Keep events sharing ticker and date with kept signal cases so the
        # fixture still exercises the legacy "ambiguous" reconciliation path.
        pairs = {(c['symbol'], c['first_seen_date']) for c in kept_cases()}
        ids = {c['signal_id'] for c in kept_cases()}
        shared = [e for e in p['events'] if (e.get('symbol'), e.get('signal_date')) in pairs and e.get('event_id') not in ids]
        p['events'] = p['events'][:4] + shared[:4]
    elif name == 'opportunity-ledger-latest.json':
        p['events'] = p['events'][:8]
    elif name == 'resonance-tracker.json':
        for key, value in list(p.items()):
            if key.endswith('_top10') and isinstance(value, list):
                p[key] = value[:1]
        p['details'] = head(p['details'], 3)
        tracker = p['favorite_pattern_tracker']
        for key in ('candidates', 'entry_ready_candidates', 'near_matches', 'reference_cases'):
            if isinstance(tracker.get(key), list):
                tracker[key] = tracker[key][:1]
    elif name == 'signal-history.json':
        p['cases'] = kept_cases()
        for case in p['cases']:
            case['daily_states'] = case['daily_states'][-3:]
    elif name == 'signal-history-summary.json':
        keys = {(c['symbol'], c['first_seen_date']) for c in kept_cases()}
        p['cases'] = [c for c in p['cases'] if (c['symbol'], c['first_seen_date']) in keys]
    elif name in ('unified-v2-latest.json', 'unified-v2-rankings.json'):
        p['days'] = p['days'][-1:]
        for day in p['days']:
            for key in ('rare_opportunities', 'candidate_pool', 'ranking'):
                if isinstance(day.get(key), list):
                    day[key] = day[key][:3]
    return p


if __name__ == '__main__':
    for name in sorted(FROZEN_RELEASE_NAMES):
        payload = trim(name, load(name))
        (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')
    # Sealed assets with count/hash cross-checks are kept byte-for-byte.
    for name in ('daily-shape-picker.json', 'market-internals.json', 'market-external.json', 'market-cockpit.json', 'cr056-ranking.json'):
        (OUT / f'{name}.gz').write_bytes(gzip.compress((SOURCE / name).read_bytes(), 9, mtime=0))
    print(sum(p.stat().st_size for p in OUT.glob('*.json*')), 'bytes')
