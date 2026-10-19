"""PR guardrails: fail when frozen 3W code or locked data references change (owner override: PR label 'owner-approved').

Usage: python3 scripts/guardrails.py <base-sha> <head-sha> [labels...]
"""
import subprocess
import sys

FROZEN = [
    'research/lab/triangle15.py', 'research/lab/triangle.py', 'research/lab/buysystem.py', 'research/lab/account.py',
    'research/lab/v3weekly.py', 'research/lab/triangle_forward.py',
]
LOCKED_TOKENS = ['hk-exam-b-v1', 'hk-b-1995']
ALLOWED_LOCKED_FILES = ('docs/', 'research/lab/universes/hk-exam-b-v1.txt', 'research/generated/', 'research/experiments.jsonl',
                        'research/lab/SCOREBOARD.md', 'research/lab/results/', 'research/lab/queue/', 'scripts/guardrails.py')


def changed(base, head):
    out = subprocess.run(['git', 'diff', '--name-only', f'{base}...{head}'], capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if p]


def added_lines(base, head, path):
    out = subprocess.run(['git', 'diff', f'{base}...{head}', '--', path], capture_output=True, text=True, check=True).stdout
    return [l[1:] for l in out.splitlines() if l.startswith('+') and not l.startswith('+++')]


def check(base, head, labels):
    problems = []
    files = changed(base, head)
    for p in files:
        if p in FROZEN:
            problems.append(f'frozen 3W code changed: {p}')
    frozen_cfg = 'research/lab/forward/triangle/config.json'
    if frozen_cfg in files and any('"frozen"' in l or 'fingerprint' in l for l in added_lines(base, head, frozen_cfg)):
        problems.append('the frozen fingerprint in the forward config changed')
    for p in files:
        if p.startswith(ALLOWED_LOCKED_FILES):
            continue
        if any(tok in l for l in added_lines(base, head, p) for tok in LOCKED_TOKENS):
            problems.append(f'locked HK group B referenced in {p}')
    if problems and 'owner-approved' not in labels:
        return problems
    return []


if __name__ == '__main__':
    base, head, labels = sys.argv[1], sys.argv[2], sys.argv[3:]
    found = check(base, head, labels)
    for p in found:
        print('GUARDRAIL:', p)
    if found:
        print('Add the PR label "owner-approved" only if the owner explicitly approved this change.')
        sys.exit(1)
    print('guardrails ok')
