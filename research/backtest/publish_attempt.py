"""Persist a derived attempt via ordinary Git commits; no deploy or force push.

Run only inside a clean disposable Actions checkout. A concurrent main update
causes a fresh index rebuild on that main, preserving every immutable receipt.
"""
import argparse
import json
from pathlib import Path
import subprocess
from research.backtest.run_store import ROOT, save, validate_receipt


def publish(receipt, *, repo=ROOT, max_attempts=3):
    validate_receipt(receipt)
    if receipt['status'] == 'completed':
        raise ValueError('account_result_publication_not_enabled')
    repo = Path(repo).resolve()

    def git(*args, check=True):
        return subprocess.run(['git', *args], cwd=repo, check=check, text=True, capture_output=True)

    if git('status', '--porcelain').stdout.strip():
        raise ValueError('publisher_requires_clean_disposable_checkout')
    relative = Path('research/backtest/output/reusable-runs')
    for _ in range(max_attempts):
        git('fetch', 'origin', 'main')
        git('switch', '--detach', 'origin/main')
        save(receipt, root=repo / relative)
        # Exactly two derived files in this preflight-only publisher. Never git
        # add a directory, raw data, engine environment, or unrelated changes.
        git('add', '--', str(relative / receipt['id'] / 'receipt.json'), str(relative / 'index.json'))
        if git('diff', '--cached', '--quiet', check=False).returncode == 0:
            return git('rev-parse', 'HEAD').stdout.strip()
        git('-c', 'user.name=sage-vista-bot', '-c', 'user.email=sage-vista-bot@users.noreply.github.com',
            'commit', '-m', f'research: retain attempt {receipt["id"]} [skip ci]')
        result = git('push', 'origin', 'HEAD:main', check=False)
        if result.returncode == 0:
            return git('rev-parse', 'HEAD').stdout.strip()
    raise RuntimeError('ordinary_result_push_failed_after_retries; attempt artifact retained for recovery')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', required=True)
    args = parser.parse_args()
    print(publish(json.loads(Path(args.receipt).read_bytes())))
