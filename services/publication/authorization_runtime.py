"""Fixed Actions entry; disabled configuration is not an activation approval.

Only platform context and committed configuration are inputs. Local checks are
defence in depth; server OIDC/review verification remains authoritative.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = '.github/workflows/m12-publication-authorize.yml'
CONFIG = 'config/publication-authorization-runtime.json'


class AuthorizationRuntimeError(RuntimeError):
    """Sanitized fixed-entry failure."""


def _git(*args):
    return subprocess.run(
        ['/usr/bin/git', '-c', 'core.fsmonitor=false', *args], cwd=ROOT,
        env={'PATH': '/usr/bin:/bin', 'GIT_CONFIG_NOSYSTEM': '1',
             'GIT_CONFIG_GLOBAL': '/dev/null', 'LC_ALL': 'C'},
        check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=15, close_fds=True).stdout


def _checkout(env):
    sha = env.get('GITHUB_SHA', '')
    repo = env.get('GITHUB_REPOSITORY', '')
    required = {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
                'GITHUB_REF': 'refs/heads/main', 'GITHUB_REF_TYPE': 'branch',
                'GITHUB_REF_PROTECTED': 'true', 'GITHUB_RUN_ATTEMPT': '1',
                'RUNNER_ENVIRONMENT': 'github-hosted', 'RUNNER_OS': 'Linux',
                'GITHUB_WORKFLOW_REF': f'{repo}/{WORKFLOW}@refs/heads/main',
                'GITHUB_WORKFLOW_SHA': sha}
    if (not re.fullmatch(r'[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+', repo) or
            not re.fullmatch(r'[a-f0-9]{40}', sha) or
            any(env.get(k) != v for k, v in required.items()) or
            any(not re.fullmatch(r'[1-9][0-9]*', env.get(k, '')) for k in
                ('GITHUB_REPOSITORY_ID', 'GITHUB_RUN_ID', 'GITHUB_ACTOR_ID')) or
            Path(env.get('GITHUB_WORKSPACE', '')).resolve() != ROOT or
            _git('rev-parse', 'HEAD').decode().strip() != sha):
        raise AuthorizationRuntimeError('authorization checkout context invalid')
    # Read actual bytes against Git objects, not version labels or cached diff.
    # These are the sole repository import roots of the fixed validator.
    paths = ['services', CONFIG, WORKFLOW]
    if _git('ls-files', '--others', '--', *paths):  # Includes ignored import files.
        raise AuthorizationRuntimeError('authorization checkout contains extra files')
    entries = _git('ls-tree', '-rz', sha, '--', *paths).split(b'\0')
    found = set()
    for entry in filter(None, entries):
        metadata, name = entry.split(b'\t', 1)
        mode, kind, oid = metadata.split()
        path = ROOT / name.decode('utf-8')
        if (mode not in (b'100644', b'100755') or kind != b'blob' or
                path.is_symlink() or not stat.S_ISREG(path.stat().st_mode) or
                path.resolve() != path):
            raise AuthorizationRuntimeError('authorization checkout file invalid')
        raw = path.read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != oid.decode():
            raise AuthorizationRuntimeError('authorization checkout bytes changed')
        found.add(name.decode())
    if not {CONFIG, WORKFLOW, 'services/publication/authorization_runtime.py'} <= found:
        raise AuthorizationRuntimeError('authorization checkout incomplete')


def _configuration():
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError('duplicate config key')
            result[k] = v
        return result
    raw = (ROOT / CONFIG).read_bytes()
    if len(raw) > 4096:
        raise AuthorizationRuntimeError('authorization runtime config invalid')
    value = json.loads(raw, object_pairs_hook=pairs)
    if (type(value) is not dict or set(value) != {'protocol', 'enabled', 'coordinator_origin'} or
            value['protocol'] != 'm12-authorization-runtime/1' or type(value['enabled']) is not bool or
            (not value['enabled'] and value['coordinator_origin'] is not None)):
        raise AuthorizationRuntimeError('authorization runtime config invalid')
    return value


def run():
    """No arguments, injected clients, replacement commands or caller payloads."""
    config = _configuration()
    if not config['enabled']:
        return 'authorization_runtime_disabled'
    if not sys.flags.isolated or sys.version_info[:3] != (3, 12, 12):
        raise AuthorizationRuntimeError('authorization runtime interpreter invalid')
    env = dict(os.environ)
    _checkout(env)
    parent = Path(env.get('RUNNER_TEMP', ''))
    if not parent.is_absolute() or not parent.is_dir() or parent.resolve() != parent or parent.is_relative_to(ROOT):
        raise AuthorizationRuntimeError('authorization recovery parent invalid')
    directory = parent / ('m12-authorization-' + env['GITHUB_RUN_ID'] + '-1')
    # Register only services, without exposing root-level modules to imports.
    sys.dont_write_bytecode = True
    runpy.run_path(str(Path(__file__).with_name('authorization_imports.py')))
    from services.publication.authorization_recovery import RecoverableAuthorizationTransport
    from services.publication.authorization_supervision import execute_supervised_authorization_validation
    client = RecoverableAuthorizationTransport(config['coordinator_origin'], env, recovery_directory=directory)
    try:
        execute_supervised_authorization_validation(client)
        return 'validation_return_received'
    except Exception:
        recovery_id = client.recovery_id
        if not recovery_id:
            raise AuthorizationRuntimeError('authorization validation failed') from None
        # Same original Job only, fresh client; never rerun prepare/return.
        _checkout(env)
        replacement = RecoverableAuthorizationTransport(config['coordinator_origin'], env, recovery_directory=directory)
        replacement.recover(recovery_id)
        return 'historical_return_verified'


def main():
    try:
        if len(sys.argv) != 1:
            raise AuthorizationRuntimeError('authorization runtime takes no arguments')
        print(run())
        return 0
    except Exception:
        print('authorization_runtime_failed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
