"""Independent, dated external observations. Never use scanner stock samples as fallback."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen
from services.contracts.market_data import canonical_fingerprint, require_date
from services.scanner.market_internals_daily import atomic, immutable

ROOT = Path(__file__).resolve().parents[2]
SOURCE_PAGE = 'https://www.cboe.com/tradable-products/vix/vix-historical-data'
SOURCES = {
    'vix': ('VIX', 'VIX · 未来30天波动预期', '标普500指数期权'),
    'vix9d': ('VIX9D', 'VIX9D · 未来9天波动预期', '标普500指数期权'),
}


def source_url(key):
    return f'https://cdn-api.cboe.com/api/global/us_indices/daily_prices/{SOURCES[key][0]}_History.csv'


def parse_history(content, as_of):
    require_date(as_of, 'as_of')
    reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
    if not reader.fieldnames or not {'DATE', 'CLOSE'} <= set(reader.fieldnames):
        raise ValueError('external_csv_schema')
    rows = []
    previous = None
    for row in reader:
        if not row.get('DATE') or not row.get('CLOSE'):
            raise ValueError('external_missing_row_fields')
        day = datetime.strptime(row['DATE'], '%m/%d/%Y').date().isoformat()
        if previous and day <= previous:
            raise ValueError('external_dates_duplicate_or_unordered')
        previous = day
        value = float(row['CLOSE'])
        if not math.isfinite(value) or value <= 0:
            raise ValueError('external_invalid_value')
        if day <= as_of:
            rows.append({'date': day, 'value': value})
    if not rows:
        raise ValueError('external_no_observations_as_of')
    return rows[-252:]


def observation(key, content, as_of, fetched_at):
    rows = parse_history(content, as_of)
    last = rows[-1]
    return {'id': key, 'provider': 'Cboe', 'label': SOURCES[key][1], 'scope': SOURCES[key][2],
            'source_url': source_url(key), 'source_page': SOURCE_PAGE, 'fetched_at': fetched_at,
            'source_sha256': hashlib.sha256(content).hexdigest(),
            'status': 'current' if last['date'] == as_of else 'stale',
            'observation_date': last['date'], 'value': last['value'], 'history': rows,
            'previous_observation_date': rows[-2]['date'] if len(rows) > 1 else None,
            'change_previous': round(last['value'] - rows[-2]['value'], 6) if len(rows) > 1 else None,
            'message': '直接读取官方日终值；变化为与上一条官方记录之差。'}


def unavailable(key, fetched_at, error):
    # Deliberately omit yesterday's values on transport/parse failure.
    return {'id': key, 'provider': 'Cboe', 'label': SOURCES[key][1], 'scope': SOURCES[key][2],
            'source_url': source_url(key), 'source_page': SOURCE_PAGE, 'fetched_at': fetched_at,
            'source_sha256': None, 'status': 'unavailable', 'observation_date': None,
            'value': None, 'history': [], 'previous_observation_date': None,
            'change_previous': None, 'message': '本次未取得可验证数据，请到原站查看。',
            'error_type': type(error).__name__}


def fetch_content(key):
    request = Request(source_url(key), headers={'User-Agent': 'SageVista-MarketOverview/1.0'})
    with urlopen(request, timeout=20) as response:
        content = response.read(2_000_001)
    if len(content) > 2_000_000:
        raise ValueError('external_response_too_large')
    return content


def validate(payload, expected=None):
    if payload.get('schema_version') != 'market-external-v1':
        raise ValueError('external_schema_mismatch')
    as_of = payload['as_of']
    require_date(as_of, 'as_of')
    if expected is not None and as_of != expected:
        raise ValueError('external_target_date_mismatch')
    if set(payload['indicators']) != set(SOURCES):
        raise ValueError('external_sources_mismatch')
    for key, item in payload['indicators'].items():
        if item['id'] != key or item['source_url'] != source_url(key) or item['source_page'] != SOURCE_PAGE or item['provider'] != 'Cboe':
            raise ValueError('external_source_identity')
        if item['status'] == 'unavailable':
            if item['value'] is not None or item['observation_date'] is not None or item['history'] or item['change_previous'] is not None or item['previous_observation_date'] is not None:
                raise ValueError('external_unavailable_has_value')
            continue
        rows = item['history']
        dates = [r['date'] for r in rows]
        if not rows or len(rows) > 252 or dates != sorted(set(dates)):
            raise ValueError('external_history_order')
        for r in rows:
            require_date(r['date'], 'observation_date')
            if r['date'] > as_of or isinstance(r['value'], bool) or not isinstance(r['value'], (int, float)) or not math.isfinite(r['value']) or r['value'] <= 0:
                raise ValueError('external_invalid_observation')
        if item['value'] != rows[-1]['value'] or item['observation_date'] != dates[-1]:
            raise ValueError('external_latest_mismatch')
        if item['status'] != ('current' if dates[-1] == as_of else 'stale'):
            raise ValueError('external_freshness_mismatch')
        previous = dates[-2] if len(rows) > 1 else None
        change = round(rows[-1]['value']-rows[-2]['value'], 6) if len(rows) > 1 else None
        if item['change_previous'] != change or item['previous_observation_date'] != previous:
            raise ValueError('external_change_mismatch')
        digest = item['source_sha256']
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('external_source_hash')
    if payload['content_fingerprint'] != canonical_fingerprint({k:v for k,v in payload.items() if k != 'content_fingerprint'}):
        raise ValueError('external_fingerprint_mismatch')
    return payload


def run(as_of, *, out=ROOT/'public/market-external.json', state=ROOT/'data/market/external-v1', fetcher=fetch_content, refresh=False):
    require_date(as_of, 'as_of')
    previous = validate(json.loads(Path(out).read_bytes())) if Path(out).exists() else None
    same_day = previous is not None and previous['as_of'] == as_of
    if same_day and not refresh and all(item['status'] == 'current' for item in previous['indicators'].values()):
        return {'result': 'already_current', 'as_of': as_of, 'changed': False,
                'source_status': {k:v['status'] for k,v in previous['indicators'].items()},
                'content_fingerprint': previous['content_fingerprint']}
    fetched_at = datetime.now(timezone.utc).isoformat()
    indicators = {}
    for key in SOURCES:
        if same_day and not refresh and previous['indicators'][key]['status'] == 'current':
            indicators[key] = previous['indicators'][key]
            continue
        try:
            indicators[key] = observation(key, fetcher(key), as_of, fetched_at)
        except (OSError, ValueError, KeyError, csv.Error, UnicodeError) as error:
            indicators[key] = unavailable(key, fetched_at, error)
    if previous:
        def semantic(items):
            return {k:{f:v for f,v in item.items() if f != 'fetched_at'} for k,item in items.items()}
        if previous['as_of'] == as_of and semantic(previous['indicators']) == semantic(indicators):
            return {'result':'already_current','as_of':as_of,'changed':False,
                    'source_status':{k:v['status'] for k,v in indicators.items()},
                    'content_fingerprint':previous['content_fingerprint']}
    payload = {'schema_version': 'market-external-v1', 'as_of': as_of, 'fetched_at': fetched_at, 'indicators': indicators}
    payload['content_fingerprint'] = canonical_fingerprint(payload)
    validate(payload, as_of)
    # Keep prior revisions; retrying can improve freshness but cannot erase evidence.
    snapshot = Path(state)/f"{as_of}-{payload['content_fingerprint'].split(':')[-1]}.json"
    immutable(snapshot, payload)
    changed = atomic(out, payload)
    return {'result': 'updated' if changed else 'already_current', 'as_of': as_of, 'changed': changed,
            'source_status': {k:v['status'] for k,v in indicators.items()},
            'content_fingerprint': payload['content_fingerprint']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--as-of', required=True)
    parser.add_argument('--refresh', action='store_true', help='Recheck same-day vendor revisions; preserve prior snapshots')
    args = parser.parse_args()
    print(json.dumps(run(args.as_of, refresh=args.refresh)))
