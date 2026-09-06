"""Fixed local Git source producer. No supplied roots, network or file writes.

Builds a configuration FOR an explicit commit; this does not authenticate the
executing runner. The runtime factory must bind it to actual OIDC/code identity.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import subprocess
from types import MappingProxyType
from typing import Mapping

from services.contracts.configuration import BASELINE_BLOBS, DEFINITION_COMMIT, configuration_source_allowed
from services.contracts.validation import publication_configuration_body, verify_publication_configuration, _canonical

ROOT = Path(__file__).resolve().parents[2]


class ConfigurationSourceError(RuntimeError):
    pass


def _git(*args):
    try:
        result = subprocess.run(['/usr/bin/git', '--no-replace-objects', '-C', str(ROOT), *args],
            env={'PATH': '/usr/bin:/bin', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
                 'GIT_ALLOW_PROTOCOL': '', 'GIT_NO_LAZY_FETCH': '1'},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True, timeout=5)
        if len(result.stdout) > 1024 * 1024:
            raise ValueError('source too large')
        return result.stdout
    except Exception:
        raise ConfigurationSourceError('configuration_git_source_unavailable') from None


def read_configuration_sources(code_commit: str):
    if type(code_commit) is not str or not re.fullmatch('[a-f0-9]{40}', code_commit):
        raise ConfigurationSourceError('configuration_explicit_commit_required')
    cache = {}
    def read(commit, *, runtime=False):
        raw_commit = _git('cat-file', 'commit', commit)
        if hashlib.sha1(b'commit ' + str(len(raw_commit)).encode() + b'\0' + raw_commit).hexdigest() != commit:
            raise ConfigurationSourceError('configuration_commit_identity_invalid')
        rows = _git('ls-tree', '-r', '-z', commit, '--', *BASELINE_BLOBS)
        found = {}
        for row in rows.split(b'\0'):
            if not row: continue
            metadata, path = row.decode('utf-8').split('\t')
            mode, kind, blob = metadata.split()
            if kind != 'blob' or path not in BASELINE_BLOBS or path in found:
                raise ConfigurationSourceError('configuration_source_tree_invalid')
            if not configuration_source_allowed(path, mode, blob, runtime=runtime):
                raise ConfigurationSourceError('configuration_business_source_drift')
            if blob not in cache: cache[blob] = _git('cat-file', 'blob', blob)
            found[path] = {'mode': mode, 'blob': blob, 'bytes': cache[blob]}
        if set(found) != set(BASELINE_BLOBS):
            raise ConfigurationSourceError('configuration_source_tree_incomplete')
        return found
    return {'definition_commit': DEFINITION_COMMIT, 'code_commit': code_commit,
            'definition_sources': read(DEFINITION_COMMIT), 'runtime_sources': read(code_commit, runtime=True)}


@dataclass(frozen=True)
class ResearchConfiguration:
    raw_bytes: bytes
    config_ref: Mapping[str, str]


def build_research_configuration(code_commit: str) -> ResearchConfiguration:
    sources = read_configuration_sources(code_commit)
    body = publication_configuration_body(sources)
    raw = _canonical(body) + b'\n'
    reference = verify_publication_configuration(raw, sources)
    return ResearchConfiguration(raw, MappingProxyType(reference))
