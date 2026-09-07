"""Fixed task inventory/next-pair computation, not registration or permission."""
import base64
from datetime import datetime, timezone
import hashlib
import json
import time
from services.contracts.validation import ContractError, execution_computation_input
from services.publication.configuration import build_research_configuration, ConfigurationSourceError
from services.publication.execution_history import _decode, _read, encode, prepare_execution_pairs
from services.publication.execution_inventory import build_execution_source_inventory


def validate_execution_input(raw, *, clock=lambda: time.time_ns() // 1_000_000):
    started = clock()
    value = execution_computation_input(raw)
    identity = value['identity']
    def alive(now):
        if type(now) is not int or not identity['issued_at'] * 1000 <= started <= now < identity['expires_at'] * 1000:
            raise ContractError('execution computation outside original identity window')
    alive(started)
    root = _decode(_read(value['snapshot']['root']['root'], value['objects']))
    if root.get('format') != 'm12-execution-signal/2':
        raise ContractError('execution computation requires registered sources')
    config = json.loads(base64.b64decode(root['sources']['configuration_bytes'], validate=True))
    try:
        runtime_config = json.loads(build_research_configuration(identity['code_commit']).raw_bytes)
    except ConfigurationSourceError as exc:
        raise ContractError('execution runtime configuration is unavailable') from exc
    # Original source code identity is historical. Current runtime sources are
    # independently verified against the same fixed business definitions.
    semantic = lambda item: {key: value for key, value in item.items()
                             if key not in {'code_commit', 'runtime_source_overrides'}}
    if semantic(config) != semantic(runtime_config):
        raise ContractError('execution runtime changes the frozen business configuration')
    generated_at = datetime.fromtimestamp(started / 1000, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    inventory = build_execution_source_inventory(value['snapshot'], value['objects'], generated_at=generated_at)
    pairs = prepare_execution_pairs(value['snapshot'], value['objects'], _decode(value['request_bytes']))
    pair = None if not pairs else {key: base64.b64encode(item).decode() if isinstance(item, bytes) else item
                                 for key, item in pairs[0].items()}
    completed = clock()
    alive(completed)
    result = encode({'protocol': value['protocol'], 'input_sha256': 'sha256:' + hashlib.sha256(raw).hexdigest(),
        'input_size_bytes': len(raw), 'started_ms': started, 'completed_ms': completed,
        'task_id': value['snapshot']['root']['task_id'],
        'snapshot_sha256': 'sha256:' + hashlib.sha256(encode(value['snapshot'])).hexdigest(),
        'inventory_bytes': base64.b64encode(encode(inventory)).decode(), 'next_pair': pair})
    if len(result) > 2 * 1024 * 1024:
        raise ContractError('execution computation result too large')
    return result
