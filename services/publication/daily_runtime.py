"""Fixed protected daily entry; currently membership intake, never formal scan.

Configuration is disabled. Real activation and license installation require the
launch card. Local Git/context checks do not replace the server's OIDC checks.
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
WORKFLOW = '.github/workflows/m12-daily.yml'
CONFIG = 'config/publication-daily-runtime.json'
ENTRY = 'services/publication/daily_runtime.py'


class DailyRuntimeError(RuntimeError):
    pass


def _git(*args):
    return subprocess.run(['/usr/bin/git', '--no-replace-objects', '-c', 'core.fsmonitor=false', '-C', str(ROOT), *args],
        env={'PATH': '/usr/bin:/bin', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
             'GIT_ALLOW_PROTOCOL': '', 'GIT_NO_LAZY_FETCH': '1'},
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        check=True, timeout=5, close_fds=True).stdout


def _checkout(env):
    sha, repo = env.get('GITHUB_SHA', ''), env.get('GITHUB_REPOSITORY', '')
    expected = {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
        'GITHUB_REF': 'refs/heads/main', 'GITHUB_REF_TYPE': 'branch', 'GITHUB_REF_PROTECTED': 'true',
        'GITHUB_RUN_ATTEMPT': '1', 'RUNNER_ENVIRONMENT': 'github-hosted', 'RUNNER_OS': 'Linux',
        'GITHUB_WORKFLOW_REF': f'{repo}/{WORKFLOW}@refs/heads/main', 'GITHUB_WORKFLOW_SHA': sha}
    if not re.fullmatch('[a-f0-9]{40}', sha) or not re.fullmatch(r'[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+', repo) or any(env.get(k) != v for k, v in expected.items()) or any(not re.fullmatch('[1-9][0-9]*', env.get(k, '')) for k in ('GITHUB_REPOSITORY_ID', 'GITHUB_RUN_ID', 'GITHUB_ACTOR_ID')) or Path(env.get('GITHUB_WORKSPACE', '')).resolve() != ROOT:
        raise DailyRuntimeError('daily checkout context invalid')
    if _git('rev-parse', 'HEAD').decode().strip() != sha or _git('ls-files', '--others', '--', 'services', CONFIG, WORKFLOW):
        raise DailyRuntimeError('daily checkout differs')
    found = set()
    for entry in filter(None, _git('ls-tree', '-r', '-z', sha, '--', 'services', CONFIG, WORKFLOW).split(b'\0')):
        metadata, name = entry.split(b'\t', 1)
        mode, kind, oid = metadata.split()
        path = ROOT / name.decode()
        if mode not in (b'100644', b'100755') or kind != b'blob' or path.is_symlink() or path.resolve() != path or not stat.S_ISREG(path.stat().st_mode):
            raise DailyRuntimeError('daily source invalid')
        data = path.read_bytes()
        if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != oid.decode():
            raise DailyRuntimeError('daily source changed')
        found.add(name.decode())
    if not {ENTRY, CONFIG, WORKFLOW} <= found:
        raise DailyRuntimeError('daily source incomplete')


def _configuration():
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate config key')
            result[key] = value
        return result
    raw = (ROOT / CONFIG).read_bytes()
    if not 0 < len(raw) <= 4096:
        raise DailyRuntimeError('daily configuration invalid')
    value = json.loads(raw, object_pairs_hook=pairs)
    if type(value) is not dict or set(value) != {'protocol', 'enabled', 'coordinator_origin'} or value['protocol'] != 'm12-daily-runtime/1' or type(value['enabled']) is not bool or (not value['enabled'] and value['coordinator_origin'] is not None):
        raise DailyRuntimeError('daily configuration invalid')
    return value


def run():
    config = _configuration()
    if not config['enabled']:
        return 'daily_runtime_disabled'
    if not sys.flags.isolated or sys.version_info[:3] != (3, 12, 12):
        raise DailyRuntimeError('daily interpreter invalid')
    env = dict(os.environ)
    _checkout(env)
    if not isinstance(env.get('EODHD_API_TOKEN'), str) or not re.fullmatch(r'[\x21-\x7e]{1,4096}', env['EODHD_API_TOKEN']):
        raise DailyRuntimeError('daily source credential unavailable')
    sys.dont_write_bytecode = True
    runpy.run_path(str(Path(__file__).resolve().with_name('authorization_imports.py')))
    from services.publication.daily_transport import DailyPreparationTransport
    from services.market_data.membership_collection import collect_membership
    client = DailyPreparationTransport(config['coordinator_origin'], env)
    prepared = client.prepare_and_validate()
    _checkout(env)
    collected = collect_membership(prepared['as_of'], authorize=client.authorize, archive=client)
    _checkout(env)
    if collected.failure is not None or collected.parsed is None:
        raise DailyRuntimeError('daily membership incomplete')
    return 'daily_membership_archived_not_formal'


def main():
    try:
        if len(sys.argv) != 1:
            raise DailyRuntimeError('daily runtime takes no arguments')
        print(run())
        return 0
    except Exception:
        print('daily_runtime_failed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
