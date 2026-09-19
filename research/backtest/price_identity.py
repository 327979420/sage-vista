"""Content-bound price identities and fail-closed baseline promotion."""
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def freeze_manifest(files, *, source):
    body = {'schema': 'price-world-v1', 'basis': 'normalized_adjusted_OHLCV',
            'source': source, 'files': files}
    return {**body, 'price_version': 'sha256:' + digest(body)}


def validate_manifest(manifest):
    body = {k: v for k, v in manifest.items() if k != 'price_version'}
    if not manifest.get('files') or manifest.get('price_version') != 'sha256:' + digest(body):
        raise ValueError('price_manifest_invalid')
    return manifest['price_version']


def bind(payload, manifest, *, symbols, verified):
    version = validate_manifest(manifest)
    if not set(symbols) <= set(manifest['files']):
        raise ValueError('price_symbols_missing')
    return {'price_version': version, 'symbols': sorted(symbols), 'verified': verified,
            'payload_sha256': digest(payload), 'payload': payload}


def require_consistent_baseline(contract):
    if not isinstance(contract, dict):
        raise ValueError('price_contract_required')
    version = validate_manifest(contract['manifest'])
    required = set(contract['manifest']['files']) - {'SPY'}
    for role in ('signal', 'support', 'account'):
        artifact = contract.get(role, {})
        if artifact.get('price_version') != version:
            raise ValueError('price_version_mismatch:' + role)
        if artifact.get('verified') is not True or not required <= set(artifact.get('symbols', [])):
            raise ValueError('price_dependency_unverified:' + role)
        if artifact.get('payload_sha256') != digest(artifact.get('payload')):
            raise ValueError('price_dependency_tampered:' + role)
    return version


def validate_baseline_receipt(receipt):
    """A matching contract must bind this account and its actual trade signals."""
    contract = receipt.get('price_consistency')
    version = require_consistent_baseline(contract)
    if contract['account']['payload'] != receipt.get('portfolio_ledger'):
        raise ValueError('price_contract_wrong_account')
    events = {e['event_id']: e for e in contract['signal']['payload']}
    supports = contract['support']['payload']
    for trade in receipt.get('trades', []):
        event = events.get(trade['event_id'], {})
        selection = trade.get('signal_snapshot', {}).get('selection')
        if (event.get('symbol') != trade['symbol'] or event.get('signal_date') != trade['signal_date']
                or event.get('selection') != selection):
            raise ValueError('price_contract_wrong_signal')
        if supports.get(trade['symbol']) != selection.get('support_plan'):
            raise ValueError('price_contract_wrong_support')
    if len(events) != len(receipt.get('trades', [])):
        raise ValueError('price_contract_signal_coverage')
    return version
