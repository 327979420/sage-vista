"""Fixed computation of membership registration material, never registration.

The server must construct and persist the original input from trusted readback,
then bind this output and recheck the current root/permission/lease at commit.
"""
import hashlib
import json
import time

from services.contracts.validation import (
    membership_registration_input, membership_registration_completion, publication_preparation_check,
)
from services.market_data.membership_identity import build_observed_membership
from services.publication.configuration import read_configuration_sources


def validate_membership_registration_input(raw, *, clock=lambda: time.time_ns() // 1_000_000):
    started = clock()
    value = membership_registration_input(raw)
    sources = read_configuration_sources(value['identity']['code_commit'])
    publication_preparation_check(value['preparation'], sources, started_ms=started, completed_ms=started)
    result = build_observed_membership(value['membership_evidence'], as_of=value['preparation']['evidence']['as_of'])
    completed = clock()
    prepared = membership_registration_completion(value, started_ms=started, completed_ms=completed)
    return json.dumps({'protocol': 'm12-membership-registration/1',
        'input_sha256': 'sha256:' + hashlib.sha256(raw).hexdigest(), 'input_size_bytes': len(raw),
        'started_ms': started, 'completed_ms': completed, 'preparation': prepared,
        'membership_registration': {'as_of': result.as_of, 'expected_index': value['expected_index'],
            'candidate_archive': value['candidate_archive'], 'member_count': len(result.members),
            'members_fingerprint': result.membership_evidence['content_fingerprint']}},
        sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode() + b'\n'
