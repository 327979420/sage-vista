"""Fixed local Git + sole preparation checker; no permission or external writes.

The result binds input bytes but is not a signature. The trusted runtime must
bind execution and the coordinator must recheck the current root at actual use.
"""
import hashlib
import json
import time

from services.contracts.validation import publication_preparation_input, publication_preparation_check, publication_preparation_completion
from services.publication.configuration import read_configuration_sources


def validate_preparation_input(raw: bytes, *, clock=lambda: time.time_ns() // 1_000_000) -> bytes:
    started = clock()
    value = publication_preparation_input(raw)
    sources = read_configuration_sources(value['identity']['code_commit'])
    # Complete policy/source work before taking the completion clock. The final
    # time/date guard also stays in the unique validation module.
    publication_preparation_check(value, sources, started_ms=started, completed_ms=started)
    completed = clock()
    result = publication_preparation_completion(value, started_ms=started, completed_ms=completed)
    return json.dumps({'protocol': 'm12-preparation-validation/1',
        'input_sha256': 'sha256:' + hashlib.sha256(raw).hexdigest(), 'input_size_bytes': len(raw),
        'started_ms': started, 'completed_ms': completed, 'preparation': result},
        sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode() + b'\n'
