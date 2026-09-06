"""Fixed isolated checker; verify all source bytes BEFORE business imports."""
import hashlib
import json
from pathlib import Path
import re
import runpy
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
MAX_INPUT = 32 * 1024 * 1024


def _git(*args):
    return subprocess.run(['/usr/bin/git', '--no-replace-objects', '-c', 'core.fsmonitor=false', '-C', str(ROOT), *args],
        env={'PATH': '/usr/bin:/bin', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
             'GIT_ALLOW_PROTOCOL': '', 'GIT_NO_LAZY_FETCH': '1'},
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=True, timeout=5, close_fds=True).stdout


def _checkout(raw):
    # This label selects expected bytes, NOT an approved GitHub identity. The
    # caller/runtime and server still bind the authenticated original input.
    commit = json.loads(raw)['identity']['code_commit']
    if type(commit) is not str or not re.fullmatch('[a-f0-9]{40}', commit):
        raise ValueError('invalid commit')
    if _git('rev-parse', 'HEAD').decode().strip() != commit or _git('ls-files', '--others', '--', 'services'):
        raise ValueError('checkout differs or contains additional import files')
    found = set()
    for entry in filter(None, _git('ls-tree', '-r', '-z', commit, '--', 'services').split(b'\0')):
        metadata, name = entry.split(b'\t', 1)
        mode, kind, blob = metadata.split()
        path = ROOT / name.decode('utf-8')
        if mode not in (b'100644', b'100755') or kind != b'blob' or path.is_symlink() or path.resolve() != path or not stat.S_ISREG(path.stat().st_mode):
            raise ValueError('source file invalid')
        data = path.read_bytes()
        if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != blob.decode():
            raise ValueError('source bytes changed')
        found.add(name.decode())
    if not {'services/publication/preparation_validation_worker.py', 'services/publication/authorization_imports.py',
            'services/publication/preparation_validation.py', 'services/contracts/validation.py'} <= found:
        raise ValueError('source missing')


def main():
    try:
        if len(sys.argv) != 1 or not sys.flags.isolated:
            return 1
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if not 0 < len(raw) <= MAX_INPUT:
            return 1
        _checkout(raw)
        sys.dont_write_bytecode = True
        runpy.run_path(str(Path(__file__).resolve().with_name('authorization_imports.py')))
        protocol = json.loads(raw).get('protocol')
        if protocol == 'm12-preparation-validation/1':
            from services.publication.preparation_validation import validate_preparation_input
            output = validate_preparation_input(raw)
        elif protocol == 'm12-membership-registration/1':
            from services.publication.membership_validation import validate_membership_registration_input
            output = validate_membership_registration_input(raw)
        else:
            return 1
        _checkout(raw)  # Reject source replacement during computation as well.
        if not 0 < len(output) <= 65536:
            return 1
        sys.stdout.buffer.write(output)
        return 0
    except Exception:
        return 1  # No private input, diagnostics or success-shaped fallback.


if __name__ == '__main__':
    raise SystemExit(main())
