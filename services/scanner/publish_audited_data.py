"""Publish checked EOD data despite concurrent, presentation-only documentation edits.

Never force push or silently combine new code/data with an already audited run.
Only the explicit human documentation files below may advance during publication.
"""
import argparse
import pathlib
import subprocess

SAFE_DOCUMENTS = frozenset({
    'docs/CHANGE_REQUESTS_ZH.md', 'README.md', 'README.zh-CN.md',
})


def git(repo, *args, check=True):
    return subprocess.run(['git', *args], cwd=repo, check=check,
                          text=True, capture_output=True)


def changed(repo, start, end):
    # Disable rename detection so both removed and added paths are checked.
    return set(filter(None, git(repo, 'diff', '--no-renames', '--name-only',
                               '-z', start, end).stdout.split('\0')))


def publish(repo, validated_base, attempts=3):
    repo = pathlib.Path(repo)
    if git(repo, 'status', '--porcelain', '--untracked-files=no').stdout:
        raise RuntimeError('Commit all tracked changes before publishing audited data')
    validated_base = git(repo, 'rev-parse', '--verify', validated_base).stdout.strip()
    audited_head = git(repo, 'rev-parse', 'HEAD').stdout.strip()
    git(repo, 'merge-base', '--is-ancestor', validated_base, audited_head)
    branch_base = validated_base
    for _ in range(attempts):
        git(repo, 'fetch', 'origin', 'main')
        upstream = git(repo, 'rev-parse', 'refs/remotes/origin/main').stdout.strip()
        if git(repo, 'merge-base', '--is-ancestor', validated_base, upstream,
               check=False).returncode:
            raise RuntimeError('Production history changed; rerun from current main')
        unsafe = changed(repo, validated_base, upstream) - SAFE_DOCUMENTS
        if unsafe:
            raise RuntimeError('Production code/data changed; rerun and audit current main: '
                               + ', '.join(sorted(unsafe)))
        if upstream != branch_base:
            result = git(repo, 'rebase', '--onto', upstream, branch_base, check=False)
            if result.returncode:
                git(repo, 'rebase', '--abort', check=False)
                raise RuntimeError('Documentation synchronization conflicted; publication stopped')
            branch_base = upstream
        if changed(repo, audited_head, 'HEAD') - SAFE_DOCUMENTS:
            raise RuntimeError('Audited code/data changed during synchronization; publication stopped')
        result = git(repo, 'push', 'origin', 'HEAD:main', check=False)
        if result.returncode == 0:
            return git(repo, 'rev-parse', 'HEAD').stdout.strip()
        # A writer can still advance main between fetch and push. Recheck on
        # the next bounded attempt; a code/data edit will fail closed above.
    raise RuntimeError('Could not publish after bounded retries: ' + result.stderr.strip())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validated-base', required=True)
    args = parser.parse_args()
    print(publish(pathlib.Path.cwd(), args.validated_base))
