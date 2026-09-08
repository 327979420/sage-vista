"""Immutable derived legacy research files, deliberately outside M10 formal.

The Actions publisher serializes Git index updates. This local writer also uses
an exclusive lock and atomic index replacement so retries cannot lose receipts.
No source prices, arbitrary files, or engine-generated scripts are published.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'research/backtest/output/reusable-runs'
RUN_ID = re.compile(r'[1-9][0-9]{0,19}-[1-9][0-9]{0,5}')
STATUSES = {'completed', 'unavailable', 'failed'}


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       indent=2, allow_nan=False) + '\n').encode()


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_receipt(receipt):
    """Single validation gate for this small derived receipt and its index."""
    if receipt.get('schema_version') != 'legacy-research-run-v1':
        raise ValueError('unsupported_research_receipt')
    if not RUN_ID.fullmatch(receipt.get('id', '')):
        raise ValueError('invalid_run_identity')
    if receipt.get('status') not in STATUSES or receipt.get('result_role') != 'legacy/research':
        raise ValueError('invalid_research_status_or_role')
    if not isinstance(receipt.get('request'), dict) or not isinstance(receipt.get('summary'), dict):
        raise ValueError('request_and_summary_required')
    if not re.fullmatch(r'[0-9a-f]{40}', receipt.get('code_commit', '')):
        raise ValueError('code_commit_required')
    if receipt['status'] != 'completed' and not receipt.get('reason'):
        raise ValueError('noncompletion_reason_required')
    fp = receipt.get('content_sha256')
    if fp != sha256(encode({k: v for k, v in receipt.items() if k != 'content_sha256'})):
        raise ValueError('receipt_fingerprint_mismatch')
    report = receipt.get('report')
    if report is not None:
        if receipt['status'] != 'completed' or report.get('path') != receipt['id'] + '/report.html':
            raise ValueError('invalid_report_reference')
        if not re.fullmatch(r'[0-9a-f]{64}', report.get('sha256', '')):
            raise ValueError('invalid_report_fingerprint')
    return receipt


def seal(receipt):
    payload = {k: v for k, v in receipt.items() if k != 'content_sha256'}
    return validate_receipt({**payload, 'content_sha256': sha256(encode(payload))})


def _immutable(path, raw):
    if path.is_symlink():
        raise ValueError('symlink_output_file')
    if path.exists():
        if path.read_bytes() != raw:
            raise FileExistsError('run_identity_already_contains_different_bytes')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.write-', delete=False) as stream:
        tmp = Path(stream.name)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(tmp, path)
    finally:
        tmp.unlink()


@contextmanager
def _lock(root):
    # The lock is outside output: never include a runtime lock in Git results.
    key = sha256(str(root).encode())
    with (Path(tempfile.gettempdir()) / ('sage-research-' + key + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def save(receipt, html=None, root=OUTPUT):
    receipt = validate_receipt(receipt)
    root = Path(root).resolve()
    if ROOT / 'public' == root or ROOT / 'public' in root.parents:
        raise ValueError('research_writer_cannot_write_public_assets')
    report = receipt.get('report')
    if (report is None) != (html is None):
        raise ValueError('report_reference_and_bytes_must_agree')
    if html is not None and sha256(html) != report['sha256']:
        raise ValueError('report_bytes_mismatch')
    with _lock(root):
        root.mkdir(parents=True, exist_ok=True)
        target = root / receipt['id']
        if target.is_symlink():
            raise ValueError('symlink_run_directory')
        existing = target / 'receipt.json'
        if existing.exists() and existing.read_bytes() != encode(receipt):
            raise FileExistsError('run_identity_already_contains_different_bytes')
        if report:
            _immutable(target / 'report.html', html)
        _immutable(target / 'receipt.json', encode(receipt))
        # Rebuild from verified receipts, never from untrusted supplied indexes.
        # A crash after immutable files but before index is recovered by retry.
        entries = []
        for path in root.glob('*/receipt.json'):
            value = validate_receipt(json.loads(path.read_bytes()))
            if path.parent.name != value['id'] or path.is_symlink() or path.parent.is_symlink():
                raise ValueError('receipt_directory_identity_mismatch')
            if value.get('report') and sha256((path.parent / 'report.html').read_bytes()) != value['report']['sha256']:
                raise ValueError('stored_report_bytes_mismatch')
            entry = {k: value[k] for k in
                     ('id', 'status', 'request', 'summary', 'code_commit', 'content_sha256')}
            entry['receipt_sha256'] = sha256(path.read_bytes())
            entries.append(entry)
        entries.sort(key=lambda e: tuple(int(n) for n in e['id'].split('-')), reverse=True)
        raw = encode({'schema_version': 'legacy-research-index-v1', 'runs': entries})
        with tempfile.NamedTemporaryFile(dir=root, prefix='.index-', delete=False) as stream:
            tmp = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, root / 'index.json')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--html')
    args = parser.parse_args()
    save(json.loads(Path(args.receipt).read_bytes()), Path(args.html).read_bytes() if args.html else None)
