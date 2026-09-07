"""Original-contract replay of a trusted execution archive's complete readback.

This internal byte codec grants no authority. The caller must obtain snapshot
and objects from ExecutionTaskArchive under its live lease, then bind any result
to that exact snapshot before writes. There is no RPC or enabled runtime route.
External M02/configuration references are NOT a complete SourceInventory here.
"""
from dataclasses import dataclass, fields, is_dataclass
import hashlib
import json
from typing import Mapping

from services.contracts.configuration import _policy_objects
from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError
from services.execution import current_exit_state
from services.factors import SupportEvidenceBatch
from services.ledger import EventLedgerBatch
from services.ledger.producer import _freeze
from services.market_data import RepositoryRead
from services.publication.execution_continuation import (
    continue_execution_signal, freeze_execution_signal,
)


MAX_BYTES = 32 * 1024 * 1024


def _plain(value):
    if is_dataclass(value):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def encode(value):
    return json.dumps(_plain(value), sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode()


def _decode(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise ContractError('execution history requires bounded original bytes')
    try:
        value = json.loads(raw)
        if encode(value) != raw:
            raise ValueError('noncanonical encoding')
        return value
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ContractError('execution history encoding is invalid') from exc


def encode_signal(signal):
    signal = freeze_execution_signal(signal.ranking, signal.support, signal.events)
    return encode({'format': 'm12-execution-signal/1', 'signal': signal})


def _signal(raw):
    value = _decode(raw)
    try:
        if set(value) != {'format', 'signal'} or value['format'] != 'm12-execution-signal/1':
            raise ValueError('format')
        source = value['signal']
        if set(source) != {'ranking', 'support', 'events'}:
            raise ValueError('signal fields')
        return freeze_execution_signal(source['ranking'], SupportEvidenceBatch(**source['support']),
                                       EventLedgerBatch(**source['events']))
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError('execution signal envelope is invalid') from exc


def execution_task_id(signal):
    policies = _policy_objects()
    refs = {
        'ranking_ref': {'id': signal.ranking['ranking_snapshot_id'],
                        'content_fingerprint': signal.ranking['ranking_content_fingerprint']},
        'event_batch_ref': {'id': signal.events.batch_id,
                            'content_fingerprint': signal.events.batch_id.split(':', 1)[1]},
    }
    for kind in ('plan', 'exit'):
        policy = policies['M08.' + kind]
        refs[kind + '_policy_ref'] = {'id': kind + '-policy:' + policy['policy_version'],
                                     'content_fingerprint': policy['policy_fingerprint']}
    return 'execution-task:' + canonical_fingerprint(refs)


def _read(ref, objects):
    try:
        raw = objects[ref['key']]
        digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
        if (set(ref) != {'key', 'sha256', 'size_bytes'} or type(ref['size_bytes']) is not int or
                ref['key'] != 'raw/' + digest[7:] or ref['sha256'] != digest or len(raw) != ref['size_bytes']):
            raise ValueError('descriptor')
        _decode(raw)
        return raw
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError('execution archived original is missing or changed') from exc


def _request(raw):
    value = _decode(raw)
    if not isinstance(value, dict) or set(value) != {
        'as_of', 'sessions_by_instrument', 'entry_reads', 'completed_reads', 'generated_at',
    }:
        raise ContractError('execution input envelope is invalid')
    try:
        for name in ('entry_reads', 'completed_reads'):
            value[name] = {key: RepositoryRead(**{**item, 'rows': _freeze(item['rows'])})
                           for key, item in value[name].items()}
    except (TypeError, AttributeError) as exc:
        raise ContractError('execution repository envelope is invalid') from exc
    return value


def _pairs(result):
    links = [obj for kind, obj in result.records if kind == 'link' and obj['link_type'] == 'trade_plan_decision']
    yield (canonical_fingerprint({'kind': 'plans', 'id': result.plan_batch.batch_id}),
           encode({'kind': 'plans', 'batch': result.plan_batch}), encode(links))
    for index, (kind, obj) in enumerate(result.records):
        if kind == 'exit':
            link_kind, link = result.records[index + 1]
            if link_kind != 'link':
                raise ContractError('execution pair order is invalid')
            yield (canonical_fingerprint({'kind': 'exit', 'id': obj['exit_state_id']}),
                   encode({'kind': 'exit', 'state': obj}), encode(link))


@dataclass(frozen=True)
class ExecutionHistory:
    signal: object
    plans: tuple
    states: tuple
    entry_reads: Mapping
    confirmed_through: Mapping
    registered_steps: frozenset


def restore_execution_history(snapshot, objects):
    """Check every registered input/object/link before returning business leaves.

    SQL index completeness remains the server's responsibility. Hash checking
    here binds its actual readback, never turns caller-supplied roots into trust.
    """
    root = snapshot['root']
    signal = _signal(_read(root['root'], objects))
    task_id = execution_task_id(signal)
    if root['task_id'] != task_id or snapshot['revision'] != len(snapshot['history']):
        raise ContractError('execution task/history identity mismatch')
    required = {root['root']['key']}
    for row in snapshot['history']:
        required.update(row[name]['key'] for name in ('input', 'object', 'link'))
    if set(objects) != required:
        raise ContractError('execution readback must contain the entire registered history only')
    plans, states, reads, steps = {}, {}, {}, set()
    previous_step = None
    for position, row in enumerate(snapshot['history'], 1):
        if row['task_id'] != task_id or row['position'] != position or row['previous_step_id'] != previous_step:
            raise ContractError('execution history sequence mismatch')
        request = _request(_read(row['input'], objects))
        object_raw, link_raw = _read(row['object'], objects), _read(row['link'], objects)
        for instrument, frozen_read in reads.items():
            if instrument not in request['entry_reads'] or encode(request['entry_reads'][instrument]) != encode(frozen_read):
                raise ContractError('execution history changes a frozen entry read')
        result = continue_execution_signal(signal, **request,
            existing_plans=tuple(plans.values()), existing_states=tuple(states.values()))
        candidates = {step: (obj, link) for step, obj, link in _pairs(result)}
        if row['step_id'] in steps or candidates.get(row['step_id']) != (object_raw, link_raw):
            raise ContractError('execution pair does not match original producers')
        value = _decode(object_raw)
        if value['kind'] == 'plans':
            for plan in result.plan_batch.plans:
                plans[plan['plan_id']] = plan
            reads.update(request['entry_reads'])
        else:
            state = value['state']
            if state['plan_id'] not in plans:
                raise ContractError('execution state precedes its registered plan/link pair')
            chain = [item for item in states.values() if item['plan_id'] == state['plan_id']]
            current_exit_state([*chain, state])  # Original unique-chain identity check.
            states[state['exit_state_id']] = _freeze(state)
        steps.add(row['step_id'])
        previous_step = row['step_id']
    through = {}
    for plan_id in plans:
        chain = [state for state in states.values() if state['plan_id'] == plan_id]
        through[plan_id] = current_exit_state(chain)['as_of'] if chain else None
    return ExecutionHistory(signal, tuple(plans.values()), tuple(states.values()),
                            _freeze(reads), _freeze(through), frozenset(steps))


def prepare_execution_pairs(snapshot, objects, request):
    """Return deterministic pending pairs from full restored history.

    Persist one pair, then read the current history again before the next pair.
    Already registered semantic steps retain their original bytes and timestamps.
    """
    history = restore_execution_history(snapshot, objects)
    value = _plain(request)
    entries = {key: _plain(read) for key, read in history.entry_reads.items()}
    for key, read in value['entry_reads'].items():
        if key in entries and entries[key] != read:
            raise ContractError('execution request changes a frozen entry read')
        entries[key] = read
    value['entry_reads'] = entries
    raw = encode(value)
    result = continue_execution_signal(history.signal, **_request(raw),
        existing_plans=history.plans, existing_states=history.states)
    return tuple({'step_id': step, 'input_bytes': raw, 'object_bytes': obj, 'link_bytes': link}
                 for step, obj, link in _pairs(result) if step not in history.registered_steps)
