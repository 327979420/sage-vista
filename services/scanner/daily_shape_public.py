"""One compact public projection and fail-closed validation for the daily picker."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from services.contracts.market_data import canonical_fingerprint
from services.contracts.cr056_policy import POLICY_FINGERPRINT
from services.scanner.daily_shape_picker import evaluate_shape
from services.scanner.cr056_daily import replace_bytes, encoded

VERSION = 'daily-shape-picker-v1'


def logic_fingerprint():
    return hashlib.sha256(Path(__file__).with_name('daily_shape_picker.py').read_bytes()).hexdigest()


def project(report):
    keep = ('symbol', 'as_of', 'state', 'state_zh', 'shape_zh', 'bottom_confirmed', 'bottom',
            'three_push', 'price', 'invalidation_price', 'explanation_zh', 'window_fingerprint',
            'policy_fingerprint', 'chart', 'liquidity', 'source_sha256', 'input_fingerprint', 'activity_rank')
    result = {'version': VERSION, 'as_of': report['as_of'], 'result_role': 'daily_observation_picker',
              'price_version': report['price_version'], 'source_identity': report['source_identity'],
              'policy_fingerprint': POLICY_FINGERPRINT, 'logic_fingerprint': logic_fingerprint(),
              'universe': report['universe'], 'state_counts': report['state_counts'],
              'rows': [{k: r[k] for k in keep} for r in report['rows'] if r['selected']],
              'audit': {'future_data_used': False, 'account_connected': False,
                        'main_ranking_changed': False, 'raw_cash_turnover': True},
              'selection_note_zh': '已覆盖普通股中的当日成交额前100；交易热度不代表社交关注度。',
              'purpose_zh': '日线形态观察，供人工核图。底部确认不保证以后不会跌破。'}
    result['content_fingerprint'] = canonical_fingerprint(result)
    validate(result, report['as_of'])
    return result


def validate(payload, as_of):
    if payload.get('version') != VERSION or payload.get('as_of') != as_of:
        raise ValueError('picker_version_or_date_mismatch')
    if payload.get('policy_fingerprint') != POLICY_FINGERPRINT or payload.get('logic_fingerprint') != logic_fingerprint():
        raise ValueError('picker_policy_or_logic_mismatch')
    if payload.get('result_role') != 'daily_observation_picker':
        raise ValueError('picker_role_mismatch')
    if payload.get('audit') != {'future_data_used': False, 'account_connected': False,
                               'main_ranking_changed': False, 'raw_cash_turnover': True}:
        raise ValueError('picker_audit_failed')
    plain = {k:v for k,v in payload.items() if k != 'content_fingerprint'}
    if canonical_fingerprint(plain) != payload.get('content_fingerprint'):
        raise ValueError('picker_content_hash_mismatch')
    identity = payload['source_identity']
    if identity['as_of'] != as_of or canonical_fingerprint(identity) != payload['price_version']:
        raise ValueError('picker_price_version_mismatch')
    symbols = set(); ranks = set(); states = Counter()
    for row in payload['rows']:
        if row['symbol'] in symbols or row['activity_rank'] in ranks:
            raise ValueError('picker_duplicate_symbol_or_rank')
        symbols.add(row['symbol']); ranks.add(row['activity_rank'])
        if not 1 <= row['activity_rank'] <= payload['universe']['selected_activity_count']:
            raise ValueError('picker_activity_rank_outside_universe')
        if row['as_of'] != as_of or identity['sources'].get(row['symbol']) != row['source_sha256']:
            raise ValueError('picker_row_source_mismatch')
        facts = evaluate_shape(row['chart'], as_of=as_of)
        if not facts['selected']:
            raise ValueError('picker_unconfirmed_bottom_published')
        for key in ('state','state_zh','shape_zh','bottom_confirmed','bottom','three_push','price',
                    'invalidation_price','explanation_zh','window_fingerprint','policy_fingerprint'):
            if facts[key] != row[key]: raise ValueError('picker_derived_fact_mismatch:'+key)
        states[row['state']] += 1
    if any(payload['state_counts'].get(k,0) != states[k] for k in ('waiting','broken_out','above_line','retest')):
        raise ValueError('picker_counts_mismatch')
    if sum(payload['state_counts'].values()) != payload['universe']['selected_activity_count']:
        raise ValueError('picker_universe_count_mismatch')
    return payload


def publish(report, path):
    payload = project(report)
    content = encoded(payload)
    changed = not path.exists() or path.read_bytes() != content
    if changed: replace_bytes(path, content)
    return {'result': 'updated' if changed else 'already_current', 'changed': changed,
            'as_of': payload['as_of'], 'waiting': payload['state_counts'].get('waiting',0),
            'price_version': payload['price_version']}
